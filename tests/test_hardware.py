import pytest
from unittest.mock import patch

from raspyCode.services.hardware import HardwareDetectionService

@pytest.mark.asyncio
async def test_hardware_detect_amd_rocm():
    # Simula il successo di rocm-smi e il fallimento del resto
    async def mock_check(binary: str) -> bool:
        return binary == "rocm-smi"

    with patch.object(HardwareDetectionService, "_check", side_effect=mock_check):
        result = await HardwareDetectionService.detect()
        assert result == "GPU_AMD_ROCm"

@pytest.mark.asyncio
async def test_hardware_detect_nvidia_cuda():
    async def mock_check(binary: str) -> bool:
        return binary == "nvidia-smi"

    with patch.object(HardwareDetectionService, "_check", side_effect=mock_check):
        result = await HardwareDetectionService.detect()
        assert result == "GPU_NVIDIA_CUDA"

@pytest.mark.asyncio
async def test_hardware_detect_cpu_only():
    # Se nessun binario GPU viene trovato, deve ripiegare su CPU
    async def mock_check(binary: str) -> bool:
        return False

    with patch.object(HardwareDetectionService, "_check", side_effect=mock_check):
        result = await HardwareDetectionService.detect()
        assert result == "CPU_ONLY"
