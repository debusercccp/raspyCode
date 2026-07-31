import asyncio

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


async def run_tool(tool_name: str, arguments: dict) -> ToolResultEvent:
    bus = EventBus()
    executor = ToolExecutorService(bus)
    result_queue = bus.subscribe()
    await executor._execute(
        LLMToolCallEvent(call_id="t", tool_name=tool_name, arguments=arguments)
    )
    return await get_tool_result(result_queue)


@pytest.mark.asyncio
async def test_executor_gc_content_tool():
    response = await run_tool("biotoolkit_gc_content", {"args": ["ATGC"]})
    assert response.is_error is False
    assert "50.0" in response.result_output


@pytest.mark.asyncio
async def test_executor_rev_comp_tool():
    response = await run_tool("biotoolkit_rev_comp", {"args": ["ATGC"]})
    assert response.is_error is False
    assert "GCAT" in response.result_output


@pytest.mark.asyncio
async def test_executor_dna_to_rna_tool():
    response = await run_tool("biotoolkit_dna_to_rna", {"args": ["ATCGt"]})
    assert response.is_error is False
    assert "AUCGu" in response.result_output


@pytest.mark.asyncio
async def test_executor_rna_to_prot_tool():
    response = await run_tool("biotoolkit_rna_to_prot", {"args": ["AUGUUUUAA"]})
    assert response.is_error is False
    assert "MF" in response.result_output


@pytest.mark.asyncio
async def test_executor_base_count_tool():
    response = await run_tool("biotoolkit_base_count", {"args": ["AATT"]})
    assert response.is_error is False
    assert "'A': 2" in response.result_output


@pytest.mark.asyncio
async def test_executor_hamming_dist_tool():
    response = await run_tool("biotoolkit_hamming_dist", {"args": ["ABC", "ABD"]})
    assert response.is_error is False
    assert "1" in response.result_output


@pytest.mark.asyncio
async def test_executor_orf_finder_tool():
    response = await run_tool("biotoolkit_orf_finder", {"args": ["MKV*"]})
    assert response.is_error is False
    assert "MKV*" in response.result_output


@pytest.mark.asyncio
async def test_executor_how_many_seq_tool():
    response = await run_tool(
        "biotoolkit_how_many_seq", {"args": [">a\nATG\n>b\nCGT\n"]}
    )
    assert response.is_error is False
    assert "2" in response.result_output


@pytest.mark.asyncio
async def test_executor_longest_shared_seq_tool():
    response = await run_tool(
        "biotoolkit_longest_shared_seq", {"args": ["GATTACA", "TACAG"]}
    )
    assert response.is_error is False
    assert "TACA" in response.result_output


@pytest.mark.asyncio
async def test_executor_genome_assembly_tool():
    response = await run_tool(
        "biotoolkit_genome_assembly", {"args": ["ATG", "TGC", "GCA"]}
    )
    assert response.is_error is False
    assert "ATGCA" in response.result_output


@pytest.mark.asyncio
async def test_executor_system_run_cmd_success_path():
    # "pwd" e' in allow-list: esercita il vero ramo subprocess (non solo il rifiuto)
    response = await run_tool("system_run_cmd", {"command": "pwd"})
    assert response.is_error is False
    assert response.result_output  # stdout non vuoto


@pytest.mark.asyncio
async def test_executor_unparsable_command():
    response = await run_tool("system_run_cmd", {"command": "echo 'unclosed"})
    assert response.is_error is True
    assert "non parsabile" in response.result_output


@pytest.mark.asyncio
async def test_executor_catches_unexpected_exception():
    # Un intero al posto di una stringa fa fallire seq.upper() dentro gc_content:
    # esercita il ramo `except Exception` di _execute.
    response = await run_tool("biotoolkit_gc_content", {"args": [123]})
    assert response.is_error is True
    assert "Errore esecuzione tool" in response.result_output


@pytest.mark.asyncio
async def test_executor_run_loop_processes_events_from_bus():
    bus = EventBus()
    executor = ToolExecutorService(bus)
    result_queue = bus.subscribe()

    task = asyncio.create_task(executor.run())
    try:
        await bus.publish(
            LLMToolCallEvent(
                call_id="loop",
                tool_name="biotoolkit_gc_content",
                arguments={"args": ["GGCC"]},
            )
        )
        response = await asyncio.wait_for(get_tool_result(result_queue), timeout=2)
        assert response.is_error is False
        assert "100.0" in response.result_output
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
