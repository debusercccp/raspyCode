from unittest.mock import AsyncMock

import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import LLMToolCallEvent, ToolResultEvent
from raspyCode.services.tool_executor_service import ToolExecutorService


async def get_tool_result(queue) -> ToolResultEvent:
    while True:
        event = await queue.get()
        if isinstance(event, ToolResultEvent):
            return event


@pytest.mark.asyncio
async def test_unknown_tool_without_mcp_client_is_unrecognized():
    bus = EventBus()
    executor = ToolExecutorService(bus)  # nessun mcp_client
    result_queue = bus.subscribe()

    await executor._execute(
        LLMToolCallEvent(call_id="1", tool_name="custom_external_tool", arguments={})
    )
    response = await get_tool_result(result_queue)

    assert response.is_error is True
    assert "Tool non riconosciuto" in response.result_output


@pytest.mark.asyncio
async def test_unknown_tool_with_disconnected_mcp_client_is_unrecognized():
    bus = EventBus()
    mcp_client = AsyncMock()
    mcp_client.connected = False
    executor = ToolExecutorService(bus, mcp_client=mcp_client)
    result_queue = bus.subscribe()

    await executor._execute(
        LLMToolCallEvent(call_id="1", tool_name="custom_external_tool", arguments={})
    )
    response = await get_tool_result(result_queue)

    assert response.is_error is True
    assert "Tool non riconosciuto" in response.result_output
    mcp_client.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_tool_with_connected_mcp_client_is_forwarded():
    bus = EventBus()
    mcp_client = AsyncMock()
    mcp_client.connected = True
    mcp_client.call_tool.return_value = ("risultato remoto", False)
    executor = ToolExecutorService(bus, mcp_client=mcp_client)
    result_queue = bus.subscribe()

    await executor._execute(
        LLMToolCallEvent(
            call_id="1", tool_name="custom_external_tool", arguments={"x": 1}
        )
    )
    response = await get_tool_result(result_queue)

    assert response.is_error is False
    assert response.result_output == "risultato remoto"
    mcp_client.call_tool.assert_awaited_once_with("custom_external_tool", {"x": 1})


@pytest.mark.asyncio
async def test_biotoolkit_tool_still_prefers_local_execution_over_mcp():
    """I tool biotoolkit_* devono girare in-process anche se e' presente un
    mcp_client connesso: niente round-trip inutile per il percorso veloce."""
    bus = EventBus()
    mcp_client = AsyncMock()
    mcp_client.connected = True
    executor = ToolExecutorService(bus, mcp_client=mcp_client)
    result_queue = bus.subscribe()

    await executor._execute(
        LLMToolCallEvent(call_id="1", tool_name="biotoolkit_gc_content", arguments={"args": ["ATGC"]})
    )
    response = await get_tool_result(result_queue)

    assert response.is_error is False
    assert "50.0" in response.result_output
    mcp_client.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_system_run_cmd_never_forwarded_to_mcp():
    """system_run_cmd resta escluso dal fallback MCP anche con client connesso."""
    bus = EventBus()
    mcp_client = AsyncMock()
    mcp_client.connected = True
    executor = ToolExecutorService(bus, mcp_client=mcp_client)
    result_queue = bus.subscribe()

    await executor._execute(
        LLMToolCallEvent(call_id="1", tool_name="system_run_cmd", arguments={"command": "pwd"})
    )
    await get_tool_result(result_queue)

    mcp_client.call_tool.assert_not_called()
