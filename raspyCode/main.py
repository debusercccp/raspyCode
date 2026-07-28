"""Entry point di raspyCode.

Istanzia l'EventBus e i microservizi, rileva l'hardware, ed esegue
l'interfaccia Textual in foreground e i servizi in background.
"""
import asyncio
import os

from .core.event_bus import EventBus
from .core.events import StatusEvent
from .services.connectivity_service import ConnectivityService
from .services.hardware import HardwareDetectionService
from .services.llm_gateway_service import LLMGatewayService
from .services.tool_executor_service import ToolExecutorService
from .ui.frontend_service import RaspyCodeApp

try:
    from .services.display_service import TFTDisplayService
    _HAS_DISPLAY_MODULE = True
except ImportError:
    _HAS_DISPLAY_MODULE = False

async def splash_screen_sequence(bus: EventBus):    
    # 2. Aspetta 3 secondi
    await asyncio.sleep(3)
    
    # 3. Pulisce il TFT rimettendo il messaggio di base
    await bus.publish(StatusEvent(text="SYSTEM BOOT COMPLETED", level="info"))

async def main() -> None:
    bus = EventBus()

    pi_ip = os.environ.get("RASPY_PI_IP", "10.42.0.2")
    model = os.environ.get("RASPY_MODEL", None)

    app = RaspyCodeApp(bus, pi_ip=pi_ip, model=model)
    gateway = LLMGatewayService(bus, pi_ip=pi_ip, model=model)
    executor = ToolExecutorService(bus)
    connectivity = ConnectivityService(bus, pi_ip=pi_ip)

    services = [gateway.run(), executor.run(), connectivity.run()]

    if _HAS_DISPLAY_MODULE:
        services.append(TFTDisplayService(bus).run())

    hw_mode = await HardwareDetectionService.detect()
    app.hw_mode = hw_mode
    
    asyncio.create_task(splash_screen_sequence(bus))

    tasks = [asyncio.create_task(coro) for coro in services]

    await app.run_async()

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def start() -> None:
    """Entrypoint sincrono per l'eseguibile generato da pyproject.toml."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    start()
