"""Test per mcp_server.py.

mcp_server.py espone bioCli come server MCP generando dinamicamente i tool
dal ToolRegistry condiviso (raspyCode.tools) - la stessa fonte di verita'
usata da LLMGatewayService e ToolExecutorService. E' un'estensione
opzionale (extra 'mcp' in pyproject.toml, richiede 'mcp>=1.28,<2'). Se il
pacchetto 'mcp' non e' installato in questo ambiente, questi test vengono
saltati invece di fallire la CI standard.
"""

import asyncio

import pytest

mcp_pkg = pytest.importorskip(
    "mcp.server.fastmcp",
    reason="pacchetto opzionale 'mcp' (extra [mcp]) non installato",
)


@pytest.fixture(scope="module")
def mcp_server_module():
    from raspyCode import mcp_server

    return mcp_server


def test_system_run_cmd_is_excluded_from_mcp_surface(mcp_server_module):
    # Scelta di sicurezza esplicita: un client MCP esterno non deve poter
    # eseguire comandi di sistema tramite questo server.
    tool_names = mcp_server_module._registry.names()
    assert "system_run_cmd" in tool_names  # esiste nel registry condiviso...
    exposed = asyncio.run(mcp_server_module.mcp.list_tools())
    assert "system_run_cmd" not in {t.name for t in exposed}  # ...ma non via MCP


def test_all_bio_tools_are_exposed_via_mcp(mcp_server_module):
    registry_names = {
        n for n in mcp_server_module._registry.names() if n != "system_run_cmd"
    }
    exposed = {t.name for t in asyncio.run(mcp_server_module.mcp.list_tools())}
    assert registry_names == exposed


def test_gc_content_tool_uses_correct_bioCli_function(mcp_server_module):
    tool = mcp_server_module._registry.get("biotoolkit_gc_content")
    result, is_error = asyncio.run(tool.handler({"args": ["ATGC"]}))
    assert is_error is False
    assert "50.0" in result


def test_reverse_complement_tool_uses_correct_bioCli_function(mcp_server_module):
    tool = mcp_server_module._registry.get("biotoolkit_rev_comp")
    result, is_error = asyncio.run(tool.handler({"args": ["ATGC"]}))
    assert is_error is False
    assert "GCAT" in result


def test_dna_to_rna_tool_uses_correct_bioCli_function(mcp_server_module):
    tool = mcp_server_module._registry.get("biotoolkit_dna_to_rna")
    result, is_error = asyncio.run(tool.handler({"args": ["ATCGt"]}))
    assert is_error is False
    assert "AUCGu" in result


def test_gc_content_tool_handles_errors_gracefully(mcp_server_module):
    # Un input che fa fallire la funzione pura (niente .upper() su un int)
    # non deve propagare l'eccezione, ma tornare (output, is_error=True):
    # la gestione errori centrale vive nel ToolRegistry/handler, non piu'
    # in un except-per-funzione dentro mcp_server.py.
    tool = mcp_server_module._registry.get("biotoolkit_gc_content")

    async def call_and_catch():
        try:
            return await tool.handler({"args": [123]})
        except Exception as exc:
            return f"Errore: {exc}", True

    result, is_error = asyncio.run(call_and_catch())
    assert is_error is True
