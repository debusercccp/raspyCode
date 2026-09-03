from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from raspyCode.services.mcp_client_service import MCPToolClient


@pytest.mark.asyncio
async def test_connect_failure_is_swallowed_when_sdk_missing():
    """Se il modulo 'mcp' non e' installato, connect() non deve sollevare
    ma tornare False e lasciare il client in stato non connesso."""
    client = MCPToolClient()
    with patch.dict("sys.modules", {"mcp": None}):
        result = await client.connect()
    assert result is False
    assert client.connected is False


@pytest.mark.asyncio
async def test_call_tool_when_not_connected_returns_error_without_raising():
    client = MCPToolClient()
    output, is_error = await client.call_tool("qualsiasi_tool", {"args": []})
    assert is_error is True
    assert "non connesso" in output


@pytest.mark.asyncio
async def test_list_tools_when_not_connected_returns_empty_list():
    client = MCPToolClient()
    assert await client.list_tools() == []


@pytest.mark.asyncio
async def test_call_tool_success_extracts_text_content():
    client = MCPToolClient()
    client._connected = True

    fake_content = MagicMock()
    fake_content.text = "Contenuto GC: 50.0%"
    fake_result = MagicMock()
    fake_result.content = [fake_content]
    fake_result.isError = False

    client._session = AsyncMock()
    client._session.call_tool.return_value = fake_result

    output, is_error = await client.call_tool("biotoolkit_gc_content", {"args": ["ATGC"]})

    assert output == "Contenuto GC: 50.0%"
    assert is_error is False
    client._session.call_tool.assert_awaited_once_with(
        "biotoolkit_gc_content", {"args": ["ATGC"]}
    )


@pytest.mark.asyncio
async def test_call_tool_propagates_is_error_flag():
    client = MCPToolClient()
    client._connected = True

    fake_content = MagicMock()
    fake_content.text = "boom"
    fake_result = MagicMock()
    fake_result.content = [fake_content]
    fake_result.isError = True

    client._session = AsyncMock()
    client._session.call_tool.return_value = fake_result

    output, is_error = await client.call_tool("tool_x", {})
    assert is_error is True
    assert output == "boom"


@pytest.mark.asyncio
async def test_call_tool_exception_is_caught():
    client = MCPToolClient()
    client._connected = True
    client._session = AsyncMock()
    client._session.call_tool.side_effect = RuntimeError("connessione persa")

    output, is_error = await client.call_tool("tool_x", {})
    assert is_error is True
    assert "connessione persa" in output


@pytest.mark.asyncio
async def test_list_tools_maps_to_ollama_schema_format():
    client = MCPToolClient()
    client._connected = True

    fake_tool = MagicMock()
    fake_tool.name = "biotoolkit_gc_content"
    fake_tool.description = "Calcola il contenuto GC"
    fake_tool.inputSchema = {"type": "object", "properties": {"args": {"type": "array"}}}

    fake_result = MagicMock()
    fake_result.tools = [fake_tool]

    client._session = AsyncMock()
    client._session.list_tools.return_value = fake_result

    schemas = await client.list_tools()

    assert schemas == [
        {
            "type": "function",
            "function": {
                "name": "biotoolkit_gc_content",
                "description": "Calcola il contenuto GC",
                "parameters": {"type": "object", "properties": {"args": {"type": "array"}}},
            },
        }
    ]


@pytest.mark.asyncio
async def test_list_tools_exception_returns_empty_list():
    client = MCPToolClient()
    client._connected = True
    client._session = AsyncMock()
    client._session.list_tools.side_effect = RuntimeError("boom")

    assert await client.list_tools() == []


@pytest.mark.asyncio
async def test_aclose_resets_state():
    client = MCPToolClient()
    client._connected = True
    client._session = AsyncMock()
    client._exit_stack.aclose = AsyncMock()

    await client.aclose()

    assert client.connected is False
    assert client._session is None
