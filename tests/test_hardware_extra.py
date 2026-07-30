import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from raspyCode.services.hardware import HardwareDetectionService


@pytest.mark.asyncio
async def test_check_returns_true_when_subprocess_succeeds():
    fake_proc = AsyncMock()
    fake_proc.wait.return_value = 0
    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        assert await HardwareDetectionService._check("rocm-smi") is True


@pytest.mark.asyncio
async def test_check_returns_false_when_subprocess_exits_nonzero():
    fake_proc = AsyncMock()
    fake_proc.wait.return_value = 1
    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        assert await HardwareDetectionService._check("nvidia-smi") is False


@pytest.mark.asyncio
async def test_check_returns_false_when_binary_missing():
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        assert await HardwareDetectionService._check("binario-inesistente") is False


@pytest.mark.asyncio
async def test_check_times_out_and_kills_hanging_process():
    import raspyCode.services.hardware as mod

    async def hang_then_die(*_a, **_kw):
        # Prima chiamata (pre-kill): pende, viene cancellata da wait_for.
        # Seconda chiamata (post-kill): ritorna subito, come farebbe un
        # processo appena ucciso.
        if not hang_then_die.called:
            hang_then_die.called = True
            await asyncio.sleep(3600)
        return -9

    hang_then_die.called = False

    fake_proc = AsyncMock()
    fake_proc.wait = AsyncMock(side_effect=hang_then_die)
    fake_proc.kill = MagicMock()  # asyncio.subprocess.Process.kill() e' sincrono

    original_timeout = mod.CHECK_TIMEOUT_SECONDS
    mod.CHECK_TIMEOUT_SECONDS = 0.01
    try:
        with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
            result = await HardwareDetectionService._check("rocm-smi")
        assert result is False
        fake_proc.kill.assert_called_once()
    finally:
        mod.CHECK_TIMEOUT_SECONDS = original_timeout
