"""
FrontendService: TUI locale basata su `rich`. L'input utente (bloccante)
gira in un executor separato per non bloccare l'event loop; lo streaming
dei token assistant, i tool-call e i risultati vengono renderizzati non
appena arrivano sul bus.
"""
import asyncio
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .event_bus import EventBus
from .events import (
    AssistantTokenEvent,
    Event,
    LLMToolCallEvent,
    StatusEvent,
    ToolResultEvent,
    UserMessageEvent,
)

USER_IDENTITY = "noya"  # identita' fissa, coerente con il prompt di sistema


class FrontendService:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self.console = Console()
        self._current_response = ""
        self._live: Optional[Live] = None
        self._stop = asyncio.Event()

    async def run(self) -> None:
        self.console.print(
            Panel.fit(
                f"[bold green]raspyCode[/] agent — utente [cyan]{USER_IDENTITY}[/]  "
                f"[dim](/quit per uscire)[/]",
                border_style="green",
            )
        )
        await asyncio.gather(self._listen_events(), self._input_loop())

    async def _listen_events(self) -> None:
        while not self._stop.is_set():
            event = await self._queue.get()
            self._handle(event)
            self._queue.task_done()

    def _handle(self, event: Event) -> None:
        if isinstance(event, AssistantTokenEvent):
            self._on_assistant_token(event)
        elif isinstance(event, LLMToolCallEvent):
            self._on_tool_call(event)
        elif isinstance(event, ToolResultEvent):
            self._on_tool_result(event)
        elif isinstance(event, StatusEvent):
            self._on_status(event)

    def _on_assistant_token(self, event: AssistantTokenEvent) -> None:
        if self._live is None and event.content:
            self._live = Live(console=self.console, refresh_per_second=12, transient=False)
            self._live.__enter__()

        if event.content:
            self._current_response += event.content
            if self._live is not None:
                self._live.update(Markdown(self._current_response))

        if event.done:
            if self._live is not None:
                self._live.__exit__(None, None, None)
                self._live = None
            self._current_response = ""

    def _on_tool_call(self, event: LLMToolCallEvent) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_row(
            "[bold yellow]tool_call[/]",
            f"[bold]{event.tool_name}[/]",
            Text(str(event.arguments), style="dim"),
        )
        self.console.print(table)

    def _on_tool_result(self, event: ToolResultEvent) -> None:
        style = "red" if event.is_error else "green"
        self.console.print(
            Panel(event.result_output or "(output vuoto)", title=event.tool_name, border_style=style)
        )

    def _on_status(self, event: StatusEvent) -> None:
        color = {"info": "dim", "warning": "yellow", "error": "bold red"}.get(event.level, "dim")
        self.console.print(f"[{color}]{event.text}[/{color}]")

    async def _input_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            try:
                line = await loop.run_in_executor(None, input, f"{USER_IDENTITY}> ")
            except (EOFError, KeyboardInterrupt):
                self._stop.set()
                return

            line = line.strip()
            if not line:
                continue
            if line in {"/quit", "/exit"}:
                self.console.print("[bold red]Chiusura raspyCode...[/]")
                self._stop.set()
                return

            await self._bus.publish(UserMessageEvent(sender_name=USER_IDENTITY, content=line))
