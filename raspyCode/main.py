"""Entry point di raspyCode.

Istanzia l'EventBus e i microservizi, rileva l'hardware, si collega
(best-effort) al server MCP locale, ed esegue l'interfaccia Textual in
foreground e i servizi in background.
"""
import asyncio
import os

from .core.event_bus import EventBus
from .core.events import StatusEvent
from .services.connectivity_service import ConnectivityService
from .services.hardware import HardwareDetectionService
from .services.llm_gateway_service import LLMGatewayService, build_tool_schemas
from .services.local_ollama_service import LocalOllamaService
from .services.mcp_client_service import MCPToolClient
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
    use_mcp = os.environ.get("RASPY_USE_MCP", "1") != "0"

    mcp_client: MCPToolClient | None = None
    if use_mcp:
        mcp_client = MCPToolClient()
        connected = await mcp_client.connect()
        if connected:
            await bus.publish(
                StatusEvent(text="Server MCP locale collegato (biotoolkit_*).", level="info")
            )
        else:
            await bus.publish(
                StatusEvent(
                    text="Server MCP non raggiungibile: uso il routing locale statico.",
                    level="warning",
                )
            )

    tool_schemas = await build_tool_schemas(mcp_client)

    app = RaspyCodeApp(bus, pi_ip=pi_ip, model=model)
    gateway = LLMGatewayService(bus, pi_ip=pi_ip, model=model, tool_schemas=tool_schemas)
    executor = ToolExecutorService(bus, mcp_client=mcp_client)
    connectivity = ConnectivityService(bus, pi_ip=pi_ip)
    local_ollama = LocalOllamaService(bus)

    services = [gateway.run(), executor.run(), connectivity.run(), local_ollama.run()]

    if _HAS_DISPLAY_MODULE:
        services.append(TFTDisplayService(bus).run())

    hw_mode = await HardwareDetectionService.detect()
    app.hw_mode = hw_mode

    asyncio.create_task(splash_screen_sequence(bus))

    tasks = [asyncio.create_task(coro) for coro in services]

    try:
        await app.run_async()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if mcp_client is not None:
            await mcp_client.aclose()


def start() -> None:
    """Entrypoint sincrono per l'eseguibile generato da pyproject.toml."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    start()
