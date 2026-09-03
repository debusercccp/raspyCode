import asyncio

import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import LLMToolCallEvent, ToolResultEvent
from raspyCode.services.llm_gateway_service import (
    GATEWAY_TOOL_TIMEOUT_SECONDS,
    LLMGatewayService,
)


@pytest.fixture
def gateway():
    bus = EventBus()
    gw = LLMGatewayService(bus, pi_ip="127.0.0.1", model="test-model")
    yield gw


async def _drain_status_events(queue) -> list:
    """Consuma tutti gli eventi gia' in coda senza bloccare."""
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


@pytest.mark.asyncio
async def test_malformed_tool_call_missing_function_does_not_raise(gateway):
    # bug originale: call["function"] con KeyError avrebbe ucciso _converse()
    await gateway._handle_tool_calls([{"id": "1"}])

    assert gateway.history[-1]["role"] == "tool"
    assert "malformato" in gateway.history[-1]["content"]
    assert "1" not in gateway._pending_tool_calls


@pytest.mark.asyncio
async def test_malformed_tool_call_bad_json_arguments_does_not_raise(gateway):
    # bug originale: json.loads() su un JSON non valido avrebbe ucciso _converse()
    bad_call = {
        "id": "2",
        "function": {"name": "biotoolkit_gc_content", "arguments": "{not valid json"},
    }
    await gateway._handle_tool_calls([bad_call])

    assert gateway.history[-1]["role"] == "tool"
    assert "malformato" in gateway.history[-1]["content"]
    assert "2" not in gateway._pending_tool_calls


@pytest.mark.asyncio
async def test_multiple_malformed_calls_all_handled_independently(gateway):
    calls = [{"id": "a"}, {"id": "b", "function": {}}]
    await gateway._handle_tool_calls(calls)

    tool_msgs = [h for h in gateway.history if h["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert {m["tool_call_id"] for m in tool_msgs} == {"a", "b"}


@pytest.mark.asyncio
async def test_tool_call_succeeds_when_executor_responds(gateway):
    call = {
        "id": "ok-1",
        "function": {"name": "biotoolkit_gc_content", "arguments": {"args": ["ATGC"]}},
    }

    async def fake_executor():
        event = await gateway._queue.get()
        assert isinstance(event, LLMToolCallEvent)
        assert event.call_id == "ok-1"
        # Risolve direttamente il Future pendente, come fa gateway.run()
        # quando riceve il ToolResultEvent corrispondente (qui bypassato
        # perche' run() non e' attivo in questo test isolato).
        fut = gateway._pending_tool_calls.get("ok-1")
        assert fut is not None
        fut.set_result(
            ToolResultEvent(
                call_id="ok-1",
                tool_name="biotoolkit_gc_content",
                result_output="Contenuto GC: 50.0%",
                is_error=False,
            )
        )

    executor_task = asyncio.create_task(fake_executor())
    await gateway._handle_tool_calls([call])
    await executor_task

    assert gateway.history[-1]["content"] == "Contenuto GC: 50.0%"
    assert "ok-1" not in gateway._pending_tool_calls


@pytest.mark.asyncio
async def test_tool_call_times_out_and_cleans_up_pending_future(gateway, monkeypatch):
    # bug originale: await fut senza timeout => deadlock permanente se
    # l'executor non risponde mai. Verifichiamo sia il timeout sia il
    # cleanup di _pending_tool_calls (altrimenti leak di memoria).
    import raspyCode.services.llm_gateway_service as mod

    monkeypatch.setattr(mod, "GATEWAY_TOOL_TIMEOUT_SECONDS", 0.05)

    call = {
        "id": "timeout-1",
        "function": {"name": "biotoolkit_gc_content", "arguments": {"args": ["ATGC"]}},
    }
    # nessun executor collegato: nessuno risponde mai a LLMToolCallEvent
    await asyncio.wait_for(gateway._handle_tool_calls([call]), timeout=5)

    assert "Timeout" in gateway.history[-1]["content"]
    assert "timeout-1" not in gateway._pending_tool_calls


@pytest.mark.asyncio
async def test_gateway_default_timeout_constant_is_reasonable():
    # Deve essere maggiore del timeout del ToolExecutor (10s, vedi
    # tool_executor_service.TOOL_TIMEOUT_SECONDS) per lasciargli margine di
    # rispondere anche nel caso limite.
    assert GATEWAY_TOOL_TIMEOUT_SECONDS >= 10.0
