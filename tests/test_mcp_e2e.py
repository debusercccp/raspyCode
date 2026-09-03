"""Test end-to-end: verifica empiricamente (non solo con mock) che
`raspyCode.mcp_server` esposto via stdio risponda correttamente sia a
list_tools() che a call_tool(), lanciando un vero sottoprocesso Python.

Richiede l'SDK 'mcp' installato (extra opzionale [mcp]); viene saltato
automaticamente se assente.
"""
import sys

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from raspyCode.services.biotoolkit_dispatch import BIOTOOLKIT_TOOL_NAMES  # noqa: E402


@pytest.mark.asyncio
async def test_mcp_server_exposes_all_biotoolkit_tools():
    params = StdioServerParameters(command=sys.executable, args=["-m", "raspyCode.mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            exposed_names = {tool.name for tool in result.tools}

    for name in BIOTOOLKIT_TOOL_NAMES:
        assert name in exposed_names
    assert "biotoolkit_run_genetic_sim" in exposed_names


@pytest.mark.asyncio
async def test_mcp_server_call_tool_gc_content_real_subprocess():
    params = StdioServerParameters(command=sys.executable, args=["-m", "raspyCode.mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("biotoolkit_gc_content", {"args": ["ATGC"]})

    text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
    assert "50.0" in text
    assert result.isError is not True


@pytest.mark.asyncio
async def test_mcp_server_call_tool_rev_comp_real_subprocess():
    params = StdioServerParameters(command=sys.executable, args=["-m", "raspyCode.mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("biotoolkit_rev_comp", {"args": ["ATGC"]})

    text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
    assert "GCAT" in text


@pytest.mark.asyncio
async def test_mcp_tool_client_end_to_end_against_real_server():
    """Stesso identico percorso che userebbe raspyCode a runtime:
    MCPToolClient.connect() + call_tool() contro il vero mcp_server.py."""
    from raspyCode.services.mcp_client_service import MCPToolClient

    client = MCPToolClient(command=sys.executable, args=["-m", "raspyCode.mcp_server"])
    connected = await client.connect()
    assert connected is True
    try:
        schemas = await client.list_tools()
        names = {s["function"]["name"] for s in schemas}
        assert "biotoolkit_hamming_dist" in names

        output, is_error = await client.call_tool(
            "biotoolkit_hamming_dist", {"args": ["ABC", "ABD"]}
        )
        assert is_error is not True
        assert "1" in output
    finally:
        await client.aclose()
