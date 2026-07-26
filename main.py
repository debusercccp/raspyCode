"""
Entry point di raspyCode. Istanzia l'EventBus e i microservizi,
rileva l'hardware disponibile, e li esegue in parallelo fino a
richiesta di uscita dal FrontendService (/quit).

Esecuzione (da ~/progetti, cioe' dalla cartella PADRE di raspyCode/):
    python3 -m raspyCode.main

Questo e' necessario perche' il modulo usa import relativi (from .xxx
import ...): per funzionare, main.py deve essere eseguito come parte del
pacchetto raspyCode, non come script standalone (python3 main.py da dentro
raspyCode/ non funziona, perche' in quel caso Python non lo tratta come
membro del pacchetto e gli import relativi falliscono).
"""
import asyncio
import os

from .event_bus import EventBus
from .events import StatusEvent
from .frontend_service import FrontendService
from .hardware import HardwareDetectionService
from .llm_gateway_service import LLMGatewayService
from .tool_executor_service import ToolExecutorService

try:
    from .display_service import TFTDisplayService
    _HAS_DISPLAY_MODULE = True
except ImportError:
    _HAS_DISPLAY_MODULE = False


async def main() -> None:
    bus = EventBus()

    frontend = FrontendService(bus)
    gateway = LLMGatewayService(
        bus,
        pi_ip=os.environ.get("RASPY_PI_IP", "10.42.0.2"),
        model=os.environ.get("RASPY_MODEL", "gemma:e4b"),
    )
    executor = ToolExecutorService(bus)

    services = [frontend.run(), gateway.run(), executor.run()]
    if _HAS_DISPLAY_MODULE:
        services.append(TFTDisplayService(bus).run())

    hw_mode = await HardwareDetectionService.detect()
    frontend.console.print(
        f"[bold]raspyCode boot[/] — utente [cyan]noya[/] — hardware: [magenta]{hw_mode}[/]"
    )
    await bus.publish(StatusEvent(text="SYSTEM BOOT COMPLETED"))

    tasks = [asyncio.create_task(coro) for coro in services]

    # Il FrontendService segnala la fine tramite il suo asyncio.Event interno
    # (/quit, /exit, EOF, Ctrl-C). Appena scatta, cancelliamo tutti i task
    # residui invece di aspettare che asyncio.gather() termini da solo
    # (i servizi girano in loop infiniti e non ritornerebbero mai).
    await frontend._stop.wait()

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
