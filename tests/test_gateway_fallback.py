import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import FallbackModeEvent, PiConfigEvent
from raspyCode.services.llm_gateway_service import (
    LOCAL_OLLAMA_HOST,
    LOCAL_OLLAMA_PORT,
    LLMGatewayService,
)


def _make_gateway(pi_ip="10.42.0.2"):
    bus = EventBus()
    return LLMGatewayService(bus, pi_ip=pi_ip, model="qwen3:4b")


@pytest.mark.asyncio
async def test_initial_base_url_points_to_pi():
    gateway = _make_gateway()
    assert gateway.base_url == "http://10.42.0.2:11434"
    assert gateway._local_fallback_active is False


@pytest.mark.asyncio
async def test_fallback_active_switches_to_local_ollama():
    gateway = _make_gateway()
    await gateway._on_fallback_mode(FallbackModeEvent(active=True))
    assert gateway.base_url == f"http://{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}"
    assert gateway._local_fallback_active is True


@pytest.mark.asyncio
async def test_fallback_recovery_switches_back_to_pi():
    gateway = _make_gateway(pi_ip="10.42.0.2")
    await gateway._on_fallback_mode(FallbackModeEvent(active=True))
    await gateway._on_fallback_mode(FallbackModeEvent(active=False))
    assert gateway.base_url == "http://10.42.0.2:11434"
    assert gateway._local_fallback_active is False


@pytest.mark.asyncio
async def test_pi_config_change_during_fallback_is_deferred():
    """Se l'utente cambia IP del Pi mentre siamo in fallback locale, il
    routing non deve cambiare finche' il fallback non si disattiva."""
    gateway = _make_gateway(pi_ip="10.42.0.2")
    await gateway._on_fallback_mode(FallbackModeEvent(active=True))

    await gateway._on_pi_config(PiConfigEvent(pi_ip="10.42.0.50"))

    assert gateway.pi_ip == "10.42.0.50"
    assert gateway.base_url == f"http://{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}"

    # Al ripristino del Pi, il routing deve usare il nuovo IP configurato
    await gateway._on_fallback_mode(FallbackModeEvent(active=False))
    assert gateway.base_url == "http://10.42.0.50:11434"


@pytest.mark.asyncio
async def test_pi_config_change_outside_fallback_applies_immediately():
    gateway = _make_gateway(pi_ip="10.42.0.2")
    await gateway._on_pi_config(PiConfigEvent(pi_ip="10.42.0.77"))
    assert gateway.base_url == "http://10.42.0.77:11434"


@pytest.mark.asyncio
async def test_gateway_run_loop_reacts_to_fallback_event():
    import asyncio

    bus = EventBus()
    gateway = LLMGatewayService(bus, pi_ip="10.42.0.2", model="qwen3:4b")
    status_queue = bus.subscribe()

    task = asyncio.create_task(gateway.run())
    try:
        await bus.publish(FallbackModeEvent(active=True))
        await asyncio.sleep(0.05)
        assert gateway.base_url == f"http://{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}"

        # Drena la coda di StatusEvent pubblicati nel frattempo, senza
        # asserzioni stringenti sul contenuto testuale.
        while not status_queue.empty():
            status_queue.get_nowait()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
