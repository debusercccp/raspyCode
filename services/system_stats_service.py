"""SystemStatsService: legge periodicamente CPU/RAM/temperatura dal
filesystem (/proc, /sys) senza dipendenze esterne (no psutil), coerente
con l'approccio 'tutto free e open' del progetto, e pubblica
SystemStatsEvent sul bus a intervalli regolari."""

import asyncio
import os

from ..core.event_bus import EventBus
from ..core.events import SystemStatsEvent

STATS_INTERVAL_SECONDS = 3.0
THERMAL_ZONE_PATH = "/sys/class/thermal/thermal_zone0/temp"


class SystemStatsService:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def run(self) -> None:
        while True:
            await self._bus.publish(self._collect())
            await asyncio.sleep(STATS_INTERVAL_SECONDS)

    @staticmethod
    def _collect() -> SystemStatsEvent:
        load1, _, _ = os.getloadavg()

        temp_c: float | None = None
        try:
            with open(THERMAL_ZONE_PATH) as f:
                temp_c = int(f.read().strip()) / 1000.0
        except (FileNotFoundError, ValueError, PermissionError):
            temp_c = None  # laptop senza questo thermal_zone, o Pi senza permessi

        mem_total_kb = mem_available_kb = 0
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_available_kb = int(line.split()[1])
        except FileNotFoundError:
            pass  # non-Linux, non dovrebbe capitare nel target ma non deve crashare

        mem_total_mb = mem_total_kb / 1024.0
        mem_used_mb = (mem_total_kb - mem_available_kb) / 1024.0

        return SystemStatsEvent(
            cpu_load_1min=load1,
            cpu_temp_c=temp_c,
            mem_used_mb=mem_used_mb,
            mem_total_mb=mem_total_mb,
        )
