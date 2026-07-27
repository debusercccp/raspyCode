from unittest.mock import AsyncMock, patch

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
