"""Test per mcp_server.py.

mcp_server.py espone bioCli come server MCP: e' un'estensione opzionale
(extra 'mcp' in pyproject.toml, richiede 'mcp>=1.28,<2' - vedi TODO.md punto
9 per il perche' del pin di versione). Se il pacchetto 'mcp' non e'
installato in questo ambiente, questi test vengono saltati invece di
fallire la CI standard.
"""
import pytest

mcp_pkg = pytest.importorskip(
    "mcp.server.fastmcp",
    reason="pacchetto opzionale 'mcp' (extra [mcp]) non installato",
)


@pytest.fixture(scope="module")
def mcp_server_module():
    from raspyCode import mcp_server

    return mcp_server


def test_calculate_gc_content_uses_correct_function(mcp_server_module):
    result = mcp_server_module.calculate_gc_content("ATGC")
    assert "50.0" in result


def test_reverse_complement_uses_correct_function(mcp_server_module):
    assert mcp_server_module.reverse_complement("ATGC") == "GCAT"


def test_translate_dna_to_rna_uses_correct_function(mcp_server_module):
    assert mcp_server_module.translate_dna_to_rna("ATCGt") == "AUCGu"


def test_calculate_gc_content_handles_errors_gracefully(mcp_server_module):
    # Un input che fa fallire la funzione pura (niente .upper() su un int)
    # non deve propagare l'eccezione, ma tornare un messaggio d'errore.
    result = mcp_server_module.calculate_gc_content(123)
    assert "Errore" in result
