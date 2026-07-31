"""ToolExecutorService: esegue il tool-calling locale tramite il ToolRegistry
condiviso (raspyCode.tools), applicando timeout e pubblicando lo stato/i
risultati sull'EventBus.

La logica dei singoli tool (funzioni bio, system_run_cmd) non vive piu' qui:
vive in raspyCode/tools/, la stessa fonte di verita' usata da
LLMGatewayService per generare gli schemi Ollama. Questo elimina
strutturalmente il rischio di disallineamento tra "tool dichiarati al
modello" e "tool che l'executor sa eseguire".
"""

import asyncio

from ..core.event_bus import EventBus
from ..core.events import LLMToolCallEvent, StatusEvent, ToolResultEvent
from ..tools import DEFAULT_TOOL_TIMEOUT_SECONDS, ToolRegistry, build_default_registry

# Retrocompatibilita' per chi importava questa costante da qui prima del
# refactor verso il ToolRegistry condiviso.
TOOL_TIMEOUT_SECONDS = DEFAULT_TOOL_TIMEOUT_SECONDS


class ToolExecutorService:
    def __init__(self, bus: EventBus, registry: ToolRegistry | None = None) -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self._registry = registry or build_default_registry()

    async def run(self) -> None:
        while True:
            event = await self._queue.get()
            if isinstance(event, LLMToolCallEvent):
                await self._bus.publish(
                    StatusEvent(
                        text=f"[TOOL RUNNING]\n{event.tool_name}...", level="info"
                    )
                )
                await self._execute(event)
            self._queue.task_done()

    async def _execute(self, event: LLMToolCallEvent) -> None:
        is_error = False
        output = ""
        tool = self._registry.get(event.tool_name)

        try:
            if tool is not None and tool.manages_own_timeout:
                # Il tool gestisce da solo timeout/cleanup delle proprie
                # risorse (es. system_run_cmd deve poter killare il
                # subprocess): un wait_for esterno lo cancellerebbe "da
                # fuori" prima che riesca a ripulire, lasciando un
                # processo orfano.
                output, is_error = await tool.handler(event.arguments)
            else:
                output, is_error = await asyncio.wait_for(
                    self._registry.dispatch(event.tool_name, event.arguments),
                    timeout=DEFAULT_TOOL_TIMEOUT_SECONDS,
                )
        except asyncio.TimeoutError:
            output = (
                f"Timeout: il tool '{event.tool_name}' ha superato "
                f"{DEFAULT_TOOL_TIMEOUT_SECONDS:.0f}s di esecuzione ed e' stato interrotto."
            )
            is_error = True
        except Exception as exc:
            output = f"Errore esecuzione tool '{event.tool_name}': {exc}"
            is_error = True

        await self._bus.publish(
            StatusEvent(text="IDLE - in attesa di query...", level="info")
        )
        await self._bus.publish(
            ToolResultEvent(
                call_id=event.call_id,
                tool_name=event.tool_name,
                result_output=output,
                is_error=is_error,
            )
        )
