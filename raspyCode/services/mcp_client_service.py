"""MCPToolClient: gestisce la connessione (stdio) a un server MCP esterno.

Nel setup di raspyCode il server di riferimento e' `raspyCode/mcp_server.py`,
lanciato come sottoprocesso Python che espone gli stessi tool biotoolkit_*
gia' eseguiti in-process da ToolExecutorService (stesso dispatch condiviso,
vedi `biotoolkit_dispatch.py`). Il client resta pensato per essere generico:
qualunque server MCP conforme puo' essere collegato passando command/args.

La connessione e' best-effort: se il processo MCP non parte o si chiude,
`connected` torna False e i chiamanti (ToolExecutorService, LLMGatewayService)
devono continuare a funzionare col percorso locale, senza mai crashare
l'agente per un server MCP assente o non ancora avviato.
"""
from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any


class MCPToolClient:
    def __init__(
        self,
        command: str = "python",
        args: list[str] | None = None,
    ) -> None:
        self._command = command
        self._args = args if args is not None else ["-m", "raspyCode.mcp_server"]
        self._session: Any = None
        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Avvia il sottoprocesso MCP e inizializza la sessione.

        Ritorna True se la connessione ha successo, False altrimenti (mai
        solleva: il chiamante decide se continuare senza MCP).
        """
        if self._connected:
            return True
        try:
            # Import posticipato: l'SDK mcp e' una dipendenza opzionale,
            # l'agente deve restare funzionante anche se non e' installata.
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(command=self._command, args=self._args)
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
            self._connected = True
            return True
        except Exception:
            # Binario mcp assente, server_script mancante, processo che
            # muore subito, SDK non installata: qualunque errore qui non deve
            # propagare e bloccare l'avvio del resto dell'agente.
            self._connected = False
            self._session = None
            return False

    async def list_tools(self) -> list[dict[str, Any]]:
        """Ritorna gli schema dei tool esposti dal server, in formato Ollama
        (`{"type": "function", "function": {...}}`), oppure [] se non
        connesso o in caso di errore.
        """
        if not self._connected or self._session is None:
            return []
        try:
            result = await self._session.list_tools()
        except Exception:
            return []
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            }
            for tool in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Invoca un tool remoto. Ritorna (output, is_error); non solleva mai."""
        if not self._connected or self._session is None:
            return "Server MCP non connesso.", True
        try:
            result = await self._session.call_tool(name, arguments)
        except Exception as exc:
            return f"Errore chiamata MCP '{name}': {exc}", True

        text_parts = [c.text for c in result.content if hasattr(c, "text")]
        output = "\n".join(text_parts) if text_parts else str(result.content)
        return output, bool(result.isError)

    async def aclose(self) -> None:
        if self._connected or self._session is not None:
            await self._exit_stack.aclose()
        self._connected = False
        self._session = None
