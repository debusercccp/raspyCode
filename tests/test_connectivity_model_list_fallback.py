from unittest.mock import MagicMock, patch

import httpx
import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import ModelListEvent
from raspyCode.services.connectivity_service import (
    FAILURE_THRESHOLD,
    RECOVERY_THRESHOLD,
    ConnectivityService,
)


def _ok_response(model_names):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"models": [{"name": n} for n in model_names]}
    return resp


def _fail_response():
    return httpx.ConnectError("no route", request=None)


async def _drain_model_list_events(queue) -> list[ModelListEvent]:
    events = []
    while not queue.empty():
        event = queue.get_nowait()
        if isinstance(event, ModelListEvent):
            events.append(event)
    return events


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_no_model_list_published_while_pi_down_before_fallback_threshold(mock_get):
    """Prima che scatti il fallback (debounce), non pubblichiamo ancora
    nessuna lista modelli: il Pi e' giu' ma potrebbe essere solo un blip."""
    bus = EventBus()
    queue = bus.subscribe()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")
    mock_get.side_effect = _fail_response()

    async with httpx.AsyncClient() as client:
        for _ in range(FAILURE_THRESHOLD - 1):
            await service._check_once(client)

    assert await _drain_model_list_events(queue) == []


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_local_models_published_once_fallback_active(mock_get):
    """Una volta scattato il fallback, la lista modelli deve venire da
    Ollama in locale (127.0.0.1), non restare vuota o bloccata sul Pi."""
    bus = EventBus()
    queue = bus.subscribe()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")

    def side_effect(url, *args, **kwargs):
        if "10.42.0.2" in url:
            raise httpx.ConnectError("no route", request=None)
        assert "127.0.0.1" in url
        return _ok_response(["qwen2.5:3b", "qwen3:4b"])

    mock_get.side_effect = side_effect

    async with httpx.AsyncClient() as client:
        for _ in range(FAILURE_THRESHOLD):
            await service._check_once(client)

    events = await _drain_model_list_events(queue)
    assert len(events) == 1
    assert events[0].models == ["qwen2.5:3b", "qwen3:4b"]


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_local_models_empty_list_when_local_ollama_also_down(mock_get):
    """Se anche Ollama locale non risponde, pubblichiamo comunque un evento
    (lista vuota) cosi' la UI mostra il messaggio 'nessun modello
    disponibile' invece di restare bloccata sull'ultimo stato noto."""
    bus = EventBus()
    queue = bus.subscribe()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")
    mock_get.side_effect = httpx.ConnectError("no route", request=None)

    async with httpx.AsyncClient() as client:
        for _ in range(FAILURE_THRESHOLD):
            await service._check_once(client)

    events = await _drain_model_list_events(queue)
    assert len(events) == 1
    assert events[0].models == []


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_pi_models_republished_after_recovery(mock_get):
    """Al ripristino del Pi, la lista modelli deve tornare ad essere quella
    del Pi, non restare quella del fallback locale."""
    bus = EventBus()
    queue = bus.subscribe()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")

    async with httpx.AsyncClient() as client:
        # Fase 1: Pi giu', entra in fallback (mostra modelli locali)
        mock_get.side_effect = httpx.ConnectError("no route", request=None)
        for _ in range(FAILURE_THRESHOLD):
            await service._check_once(client)
        await _drain_model_list_events(queue)  # scarta gli eventi di fallback

        # Fase 2: Pi torna su, recovery threshold raggiunta
        mock_get.side_effect = None
        mock_get.return_value = _ok_response(["gemma:e4b"])
        for _ in range(RECOVERY_THRESHOLD):
            await service._check_once(client)

    events = await _drain_model_list_events(queue)
    assert len(events) >= 1
    assert events[-1].models == ["gemma:e4b"]
    assert service._fallback_active is False


@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_steady_state_pi_up_publishes_pi_models_as_before(mock_get):
    """Non-regressione: col Pi raggiungibile fin dall'inizio, il
    comportamento resta identico a prima di questa fix."""
    bus = EventBus()
    queue = bus.subscribe()
    service = ConnectivityService(bus, pi_ip="10.42.0.2")
    mock_get.return_value = _ok_response(["qwen3:4b"])

    async with httpx.AsyncClient() as client:
        await service._check_once(client)

    events = await _drain_model_list_events(queue)
    assert len(events) == 1
    assert events[0].models == ["qwen3:4b"]
