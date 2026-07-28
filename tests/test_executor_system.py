import pytest
from unittest.mock import patch, AsyncMock
from raspyCode.services.tool_executor_service import ToolExecutorService
from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import LLMToolCallEvent

@pytest.fixture
def executor_service():
    bus = EventBus()
    return ToolExecutorService(bus)

@pytest.mark.asyncio
async def test_system_cmd_rejected_not_in_allowlist(executor_service):
    # rm non è nell'allowlist [ls, wc, cat, pwd, free, head, tail, uname, whoami, df]
    event = LLMToolCallEvent(
        call_id="123",
        tool_name="system_run_cmd",
        arguments={"command": "rm -rf /"}  # Corretto: 'arguments' invece di 'args', e formato dict!
    )
    
    # Eseguiamo direttamente il bypass testando la risposta del comando
    result, is_error = await executor_service._run_system_cmd(event.arguments)
    
    assert is_error is True
    assert "non in allow-list" in result

@pytest.mark.asyncio
@patch("raspyCode.services.tool_executor_service.asyncio.create_subprocess_exec")
async def test_system_cmd_allowed(mock_exec, executor_service):
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"mocked output\n", b"")
    mock_proc.returncode = 0
    mock_exec.return_value = mock_proc

    # Passiamo un dict come si aspetta la firma del metodo
    result, is_error = await executor_service._run_system_cmd({"command": "ls -l"})
    
    assert is_error is False
    assert result == "mocked output"
