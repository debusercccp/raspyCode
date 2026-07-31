from unittest.mock import AsyncMock, patch

import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import LLMToolCallEvent
from raspyCode.services.tool_executor_service import ToolExecutorService
from raspyCode.tools.system import run_system_cmd


@pytest.fixture
def executor_service():
    bus = EventBus()
    return ToolExecutorService(bus)


@pytest.mark.asyncio
async def test_system_cmd_rejected_not_in_allowlist():
    # rm non è nell'allowlist [ls, wc, cat, pwd, free, head, tail, uname, whoami, df]
    event = LLMToolCallEvent(
        call_id="123",
        tool_name="system_run_cmd",
        arguments={
            "command": "rm -rf /"
        },  # Corretto: 'arguments' invece di 'args', e formato dict!
    )

    # run_system_cmd vive ora in raspyCode.tools.system (unica fonte di
    # verita' condivisa da Gateway/Executor/MCP), non piu' come metodo
    # privato di ToolExecutorService.
    result, is_error = await run_system_cmd(event.arguments)

    assert is_error is True
    assert "non in allow-list" in result


@pytest.mark.asyncio
@patch("raspyCode.tools.system.asyncio.create_subprocess_exec")
async def test_system_cmd_allowed(mock_exec):
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"mocked output\n", b"")
    mock_proc.returncode = 0
    mock_exec.return_value = mock_proc

    result, is_error = await run_system_cmd({"command": "ls -l"})

    assert is_error is False
    assert result == "mocked output"


@pytest.mark.asyncio
async def test_system_cmd_reaches_registry_via_executor(executor_service):
    """Verifica end-to-end che ToolExecutorService instradi davvero
    system_run_cmd attraverso il ToolRegistry condiviso (non e' piu' un
    metodo diretto sull'Executor, quindi vale la pena un test dedicato
    sul percorso completo _execute -> registry -> run_system_cmd)."""
    from raspyCode.core.event_bus import EventBus as Bus
    from raspyCode.core.events import ToolResultEvent

    bus = Bus()
    executor = ToolExecutorService(bus)
    result_queue = bus.subscribe()

    await executor._execute(
        LLMToolCallEvent(
            call_id="x", tool_name="system_run_cmd", arguments={"command": "pwd"}
        )
    )

    while True:
        event = await result_queue.get()
        if isinstance(event, ToolResultEvent):
            break
    assert event.is_error is False
    assert event.result_output
