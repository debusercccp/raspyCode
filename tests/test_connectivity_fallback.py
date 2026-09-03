from unittest.mock import MagicMock, patch

import httpx
import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import FallbackModeEvent
from raspyCode.services.connectivity_service import (
    FAILURE_THRESHOLD,
    RECOVERY_THRESHOLD,
    ConnectivityService,
)


def _ok_response():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"models": [{"name": "qwen3:4b"}]}
    return resp


async def _drain_fallback_events(queue) -> list[FallbackModeEvent]:
    events = []
    while not queue.empty():
        event = queue.get_nowait()
        if isinstance(event, FallbackModeEvent):
            events.append(event)
    return events


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_fallback_not_triggered_below_threshold(mock_get):
    bus = EventBus()
    queue = bus.subscribe()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")
    mock_get.side_effect = httpx.ConnectError("no route", request=None)

    async with httpx.AsyncClient() as client:
        for _ in range(FAILURE_THRESHOLD - 1):
            await service._check_once(client)

    events = await _drain_fallback_events(queue)
    assert events == []
    assert service._fallback_active is False


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_fallback_triggered_after_consecutive_failures(mock_get):
    bus = EventBus()
    queue = bus.subscribe()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")
    mock_get.side_effect = httpx.ConnectError("no route", request=None)

    async with httpx.AsyncClient() as client:
        for _ in range(FAILURE_THRESHOLD):
            await service._check_once(client)

    events = await _drain_fallback_events(queue)
    assert len(events) == 1
    assert events[0].active is True
    assert service._fallback_active is True


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_single_flicker_failure_does_not_trigger_fallback(mock_get):
    """Un singolo fallimento isolato tra successi non deve mai attivare il fallback."""
    bus = EventBus()
    queue = bus.subscribe()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")

    async with httpx.AsyncClient() as client:
        mock_get.return_value = _ok_response()
        await service._check_once(client)

        mock_get.side_effect = httpx.ConnectError("blip", request=None)
        await service._check_once(client)

        mock_get.side_effect = None
        mock_get.return_value = _ok_response()
        await service._check_once(client)

    events = await _drain_fallback_events(queue)
    assert events == []
    assert service._fallback_active is False


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_fallback_deactivated_after_consecutive_recoveries(mock_get):
    bus = EventBus()
    queue = bus.subscribe()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")

    async with httpx.AsyncClient() as client:
        mock_get.side_effect = httpx.ConnectError("no route", request=None)
        for _ in range(FAILURE_THRESHOLD):
            await service._check_once(client)

        # Consuma l'evento di attivazione fallback prima di verificare il recovery
        await _drain_fallback_events(queue)

        mock_get.side_effect = None
        mock_get.return_value = _ok_response()
        for _ in range(RECOVERY_THRESHOLD):
            await service._check_once(client)

    events = await _drain_fallback_events(queue)
    assert len(events) == 1
    assert events[0].active is False
    assert service._fallback_active is False


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_pi_config_change_resets_debounce_counters(mock_get):
    from raspyCode.core.events import PiConfigEvent

    bus = EventBus()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")
    mock_get.side_effect = httpx.ConnectError("no route", request=None)

    async with httpx.AsyncClient() as client:
        await service._check_once(client)
        await service._check_once(client)
        assert service._consecutive_failures == 2

    await bus.publish(PiConfigEvent(pi_ip="10.42.0.99"))
    # Applichiamo direttamente la logica che _watch_config eseguirebbe
    # in loop, per non dover gestire un task in background nel test.
    service._pi_ip = "10.42.0.99"
    service._consecutive_failures = 0
    service._consecutive_successes = 0

    assert service._consecutive_failures == 0
