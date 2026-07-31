"""Tool Registry: unica fonte di verita' su quali tool sono disponibili
all'LLM, come sono descritti (schema JSON per Ollama) e come vengono
eseguiti.

Prima di questo modulo, Gateway ed Executor mantenevano due elenchi
separati (TOOL_SCHEMAS nel Gateway, un if/elif nell'Executor) tenuti
allineati manualmente e verificati solo a posteriori da un test. Un tool
dichiarato al modello ma non implementato (o viceversa) era un bug
strutturalmente possibile. Con un ToolDefinition unico, dichiarazione ed
esecuzione sono la stessa struttura dati: non possono divergere.

Usato da:
- LLMGatewayService: registry.ollama_schemas() per il campo 'tools' inviato
  a Ollama in ogni richiesta di chat.
- ToolExecutorService: registry.dispatch(name, arguments) per eseguire.
- mcp_server.py: registry.all() per generare i tool MCP dinamicamente.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

# Timeout di default per un tool che non gestisce da solo la propria
# terminazione (vedi ToolDefinition.manages_own_timeout). Un tool che lancia
# un subprocess deve gestire il proprio timeout con un kill() esplicito del
# processo figlio: un wait_for esterno lo cancellerebbe "da fuori" senza
# dargli la possibilita' di ripulire, lasciando un processo orfano.
DEFAULT_TOOL_TIMEOUT_SECONDS = 10.0

ToolHandler = Callable[[dict[str, Any]], Awaitable[tuple[str, bool]]]


@dataclass(frozen=True)
class ToolDefinition:
    """Un tool cosi' come lo vede l'LLM (nome, descrizione, schema JSON dei
    parametri) insieme all'handler che lo esegue davvero. Nome e
    comportamento vivono nella stessa struttura: non possono disallinearsi."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: ToolHandler
    # True per i tool che gestiscono da soli timeout/cancellazione delle
    # proprie risorse (es. system_run_cmd, che deve killare il subprocess).
    # Il chiamante (ToolExecutorService) applica un wait_for generico solo
    # ai tool con manages_own_timeout=False.
    manages_own_timeout: bool = False


class ToolRegistry:
    """Registro di ToolDefinition indicizzate per nome. Un nome puo' essere
    registrato una volta sola: una doppia registrazione e' un errore di
    programmazione (due tool con lo stesso nome sarebbero indistinguibili
    per il modello), non un caso limite da ignorare in silenzio."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' gia' registrato nel ToolRegistry")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def ollama_schemas(self) -> list[dict[str, Any]]:
        """Formato atteso dal campo 'tools' dell'API /api/chat di Ollama."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                },
            }
            for tool in self._tools.values()
        ]

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        tool = self.get(name)
        if tool is None:
            return f"Tool non riconosciuto: {name}", True
        return await tool.handler(arguments)
