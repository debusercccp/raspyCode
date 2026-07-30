import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import LLMToolCallEvent, ToolResultEvent
from raspyCode.services.tool_executor_service import ToolExecutorService

FASTA = ">seq1 primo record\nATGCGATCG\n>seq2 secondo record\nATGGGGCCC\n"


async def get_tool_result(queue) -> ToolResultEvent:
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
async def test_grep_fastx_tool():
    response = await run_tool("biotoolkit_grep_fastx", {"args": ["seq1", FASTA]})
    assert response.is_error is False
    assert "seq1" in response.result_output


@pytest.mark.asyncio
async def test_grep_fastx_tool_missing_args():
    response = await run_tool("biotoolkit_grep_fastx", {"args": ["solo_uno"]})
    assert response.is_error is True


@pytest.mark.asyncio
async def test_motif_find_tool():
    response = await run_tool("biotoolkit_motif_find", {"args": ["GC", "ATGCGC"]})
    assert response.is_error is False
    assert "3" in response.result_output


@pytest.mark.asyncio
async def test_n_glyc_motif_tool():
    response = await run_tool("biotoolkit_n_glyc_motif", {"args": ["NATGAAA"]})
    assert response.is_error is False
    assert "1" in response.result_output


@pytest.mark.asyncio
async def test_restriction_site_tool():
    response = await run_tool("biotoolkit_restriction_site", {"args": ["GAATTC"]})
    assert response.is_error is False
    assert "6" in response.result_output


@pytest.mark.asyncio
async def test_fastx_sampler_tool():
    response = await run_tool(
        "biotoolkit_fastx_sampler", {"args": [FASTA, "100.0", "1"]}
    )
    assert response.is_error is False
    assert "seq1" in response.result_output


@pytest.mark.asyncio
async def test_seq_magic_tool():
    response = await run_tool("biotoolkit_seq_magic", {"args": [FASTA]})
    assert response.is_error is False
    assert "seq1" in response.result_output


@pytest.mark.asyncio
async def test_blast_output_tool():
    line = "q1\ts1\t98.5\t120\t2\t0\t1\t120\t5\t124\t1e-50\t210.0"
    response = await run_tool("biotoolkit_blast_output", {"args": [line]})
    assert response.is_error is False
    assert "q1" in response.result_output


@pytest.mark.asyncio
async def test_synth_seq_tool():
    training = ">t\n" + "ATGCATGCATGCATGC" * 4
    response = await run_tool(
        "biotoolkit_synth_seq", {"args": [training, "3", "20", "42"]}
    )
    assert response.is_error is False
    assert len(response.result_output) == 20


@pytest.mark.asyncio
async def test_synth_seq_tool_missing_args():
    response = await run_tool("biotoolkit_synth_seq", {"args": ["ATGC", "3"]})
    assert response.is_error is True


@pytest.mark.asyncio
async def test_system_run_cmd_times_out_and_kills_process():
    bus = EventBus()
    executor = ToolExecutorService(bus)
    result_queue = bus.subscribe()

    async def hang_forever():
        await asyncio.sleep(3600)
        return (b"", b"")

    fake_proc = AsyncMock()
    fake_proc.communicate = AsyncMock(side_effect=hang_forever)
    fake_proc.kill = MagicMock()  # asyncio.subprocess.Process.kill() e' sincrono
    fake_proc.wait = AsyncMock(return_value=-9)

    import raspyCode.services.tool_executor_service as mod

    original_timeout = mod.TOOL_TIMEOUT_SECONDS
    mod.TOOL_TIMEOUT_SECONDS = 0.01
    try:
        with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
            await executor._execute(
                LLMToolCallEvent(
                    call_id="slow",
                    tool_name="system_run_cmd",
                    arguments={"command": "ls -la"},
                )
            )
        response = await get_tool_result(result_queue)
        assert response.is_error is True
        assert "timeout" in response.result_output.lower()
        fake_proc.kill.assert_called_once()
    finally:
        mod.TOOL_TIMEOUT_SECONDS = original_timeout


@pytest.mark.asyncio
async def test_unknown_tool_still_returns_gracefully():
    response = await run_tool("biotoolkit_inesistente", {"args": []})
    assert response.is_error is True
    assert "non riconosciuto" in response.result_output
