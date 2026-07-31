"""MCP server: espone i tool bioinformatici di raspyCode a client MCP
esterni (es. Claude Desktop, altri agenti).

Generato dinamicamente dal ToolRegistry condiviso (raspyCode.tools) - la
stessa fonte di verita' usata da LLMGatewayService (schema Ollama) e
ToolExecutorService (esecuzione locale). Prima questo file dichiarava
manualmente solo 3 tool con la sintassi @mcp.tool(), un terzo elenco
indipendente rispetto agli altri due (e con import verso funzioni
inesistenti, vedi git history).

SCELTA DI SICUREZZA ESPLICITA: system_run_cmd NON viene esposto qui, anche
se e' presente nel ToolRegistry condiviso. Un client MCP esterno connesso a
questo server via stdio potrebbe altrimenti eseguire comandi di sistema
sulla macchina che lo ospita; il file originale esponeva solo funzioni bio
pure e innocue, e questo refactor mantiene lo stesso perimetro. Se in
futuro serve esporre anche system_run_cmd via MCP, va deciso esplicitamente
qui, non ereditato automaticamente dal registry.
"""

from collections.abc import Awaitable, Callable

from mcp.server.fastmcp import FastMCP

from raspyCode.tools import build_default_registry
from raspyCode.tools.registry import ToolDefinition

# Tool del registry condiviso che NON vengono esposti via MCP (vedi nota di
# sicurezza sopra). Whitelist esplicita del genere "cosa NON esporre",
# valutata a ogni avvio: se in futuro si aggiungono altri tool con side
# effect di sistema, vanno aggiunti qui esplicitamente.
_MCP_EXCLUDED_TOOLS = {"system_run_cmd"}

mcp = FastMCP("RaspyCode-BioToolkit")

_registry = build_default_registry()


def _make_args_tool_fn(tool: ToolDefinition) -> Callable[[list[str]], Awaitable[str]]:
    """Fabbrica per i tool con schema generico {'args': [...]} (la
    stragrande maggioranza dei biotoolkit_*)."""

    async def fn(args: list[str]) -> str:
        output, _is_error = await tool.handler({"args": args})
        return output

    fn.__name__ = tool.name
    fn.__doc__ = tool.description
    return fn


def _make_genetic_sim_tool_fn(tool: ToolDefinition) -> Callable[[int], Awaitable[str]]:
    async def fn(generations: int) -> str:
        output, _is_error = await tool.handler({"generations": generations})
        return output

    fn.__name__ = tool.name
    fn.__doc__ = tool.description
    return fn


def _build_mcp_function(tool: ToolDefinition) -> Callable:
    if tool.name == "biotoolkit_run_genetic_sim":
        return _make_genetic_sim_tool_fn(tool)
    return _make_args_tool_fn(tool)


def register_all_tools() -> None:
    for tool in _registry.all():
        if tool.name in _MCP_EXCLUDED_TOOLS:
            continue
        fn = _build_mcp_function(tool)
        mcp.add_tool(fn, name=tool.name, description=tool.description)


register_all_tools()

if __name__ == "__main__":
    # Avvia il server in modalita' standard input/output (JSON-RPC)
    mcp.run(transport="stdio")
