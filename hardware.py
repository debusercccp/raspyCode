"""Rilevamento hardware di inferenza disponibile sul nodo corrente."""
import asyncio


class HardwareDetectionService:
    @staticmethod
    async def detect() -> str:
        if await HardwareDetectionService._check("rocm-smi"):
            return "GPU_AMD_ROCm"
        if await HardwareDetectionService._check("nvidia-smi"):
            return "GPU_NVIDIA_CUDA"
        return "CPU_ONLY"

    @staticmethod
    async def _check(binary: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return await proc.wait() == 0
        except FileNotFoundError:
            return False
