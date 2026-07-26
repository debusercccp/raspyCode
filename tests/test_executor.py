import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import LLMToolCallEvent, ToolResultEvent
from raspyCode.services.tool_executor_service import ToolExecutorService

async def get_tool_result(queue) -> ToolResultEvent:
    """Helper per estrarre solo il ToolResultEvent ignorando gli StatusEvent di IDLE."""
    while True:
        event = await queue.get()
        if isinstance(event, ToolResultEvent):
            return event

@pytest.mark.asyncio
async def test_executor_unauthorized_command():
    bus = EventBus()
    executor = ToolExecutorService(bus)
    result_queue = bus.subscribe()
    
    forbidden_event = LLMToolCallEvent(
        call_id="123",
        tool_name="system_run_cmd",
        arguments={"command": "rm -rf /"}
    )
    
    await executor._execute(forbidden_event)
    
    # Usa l'helper per saltare lo StatusEvent
    response = await get_tool_result(result_queue)
    
    assert isinstance(response, ToolResultEvent)
    assert response.is_error is True
    assert "non in allow-list" in response.result_output

@pytest.mark.asyncio
async def test_executor_unknown_tool():
    bus = EventBus()
    executor = ToolExecutorService(bus)
    result_queue = bus.subscribe()
    
    unknown_event = LLMToolCallEvent(
        call_id="456",
        tool_name="biotoolkit_non_esistente",
        arguments={"args": []}
    )
    
    await executor._execute(unknown_event)
    
    response = await get_tool_result(result_queue)
    
    assert response.is_error is True
    assert "Tool non riconosciuto" in response.result_output

@pytest.mark.asyncio
async def test_executor_genetic_sim():
    bus = EventBus()
    executor = ToolExecutorService(bus)
    result_queue = bus.subscribe()
    
    sim_event = LLMToolCallEvent(
        call_id="789",
        tool_name="biotoolkit_run_genetic_sim",
        arguments={"generations": 500}
    )
    
    await executor._execute(sim_event)
    
    response = await get_tool_result(result_queue)
    
    assert response.is_error is False
    assert "Sim Gen x500 completata" in response.result_output
