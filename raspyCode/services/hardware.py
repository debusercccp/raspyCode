"""Rilevamento hardware di inferenza disponibile sul nodo corrente."""
import asyncio

# Timeout per ogni probe di binario: rocm-smi/nvidia-smi non dovrebbero mai
# pendere, ma se lo fanno (driver rotto, hardware in stato anomalo) non deve
# bloccare l'avvio dell'intera app.
CHECK_TIMEOUT_SECONDS = 5.0


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
        except FileNotFoundError:
            return False

        try:
            returncode = await asyncio.wait_for(
                proc.wait(), timeout=CHECK_TIMEOUT_SECONDS
            )
            return returncode == 0
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return False
