"""Server MCP di raspyCode: espone i tool biotoolkit_* via stdio.

Ogni tool e' generato dinamicamente a partire da
`services.biotoolkit_dispatch.BIOTOOLKIT_TOOL_NAMES`, che e' la stessa lista
usata da `ToolExecutorService` per l'esecuzione locale in-process e da
`LLMGatewayService` per gli schema esposti al modello. Un client MCP esterno
(o `MCPToolClient` sul laptop stesso) vede quindi esattamente la stessa
superficie di tool del percorso locale, senza doverla duplicare a mano.

Uso:
    python -m raspyCode.mcp_server
"""
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Assicura che il pacchetto raspyCode sia risolvibile quando lo script viene
# lanciato direttamente come sottoprocesso (es. da MCPToolClient).
sys.path.append(str(Path(__file__).resolve().parent.parent))

from raspyCode.services.biotoolkit_dispatch import (  # noqa: E402
    run_biotoolkit,
)
from raspyCode.tools import build_default_registry  # noqa: E402

_registry = build_default_registry()

mcp = FastMCP("RaspyCode-BioToolkit")


def _make_tool(tool_name: str):
    """Costruisce una funzione-wrapper con firma `(args: list[str]) -> str`
    che delega al dispatch condiviso, cosi' la logica di ciascun tool vive in
    un unico posto (`biotoolkit_dispatch.py`) e non viene duplicata qui.
    """

    def _tool(args: list[str]) -> str:
        try:
            return run_biotoolkit(tool_name, args)
        except KeyError as exc:
            return f"Errore: {exc}"
        except Exception as exc:  # difesa: non far crashare il server MCP
            return f"Errore esecuzione tool '{tool_name}': {exc}"

    _tool.__name__ = tool_name
    _tool.__doc__ = f"Esegue lo script biotoolkit '{tool_name}' passando args come CLI."
    return _tool


async def _registry_tool(tool, args: list[str]) -> str:
    try:
        output, is_error = await tool.handler({"args": args})
        return output if not is_error else f"Errore: {output}"
    except Exception as exc:
        return f"Errore esecuzione tool '{tool.name}': {exc}"


def _make_registry_tool(tool):
    async def _tool(args: list[str]) -> str:
        return await _registry_tool(tool, args)
    _tool.__name__ = tool.name
    _tool.__doc__ = tool.description
    return _tool


for _tool_def in _registry.all():
    if _tool_def.name == "system_run_cmd":
        continue
    mcp.tool(name=_tool_def.name)(_make_registry_tool(_tool_def))


if __name__ == "__main__":
    # Avvia il server in modalità standard input/output (JSON-RPC)
    mcp.run(transport="stdio")
