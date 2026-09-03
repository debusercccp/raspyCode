"""Regressione: ModelSelectedEvent uccideva silenziosamente run() perché
self.current_model non era mai inizializzato in __init__, e self.model
non veniva mai riassegnato dal branch di selezione modello (quindi
_on_user_message continuava a vedere 'Nessun modello selezionato' anche
dopo che l'utente aveva scelto un modello dalle impostazioni)."""

from unittest.mock import AsyncMock, patch

import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import ModelSelectedEvent, StatusEvent
from raspyCode.services.llm_gateway_service import LLMGatewayService


@pytest.fixture
def gateway():
    bus = EventBus()
    # Nessun modello iniziale: replica lo scenario "avvio senza RASPY_MODEL"
    gw = LLMGatewayService(bus, pi_ip="127.0.0.1", model=None)
    return gw


@pytest.mark.asyncio
async def test_model_selected_event_does_not_raise_without_prior_model(gateway):
    """current_model deve essere inizializzato: niente AttributeError
    al primo ModelSelectedEvent quando non c'era ancora un modello attivo."""
    event = ModelSelectedEvent(model="qwen3:4b")
    # Non deve sollevare AttributeError su self.current_model
    await gateway._handle_event(event)
    assert gateway.model == "qwen3:4b"
    assert gateway.current_model == "qwen3:4b"


@pytest.mark.asyncio
async def test_model_selected_event_updates_model_used_for_chat(gateway):
    """self.model (letto da _on_user_message/_converse) deve riflettere
    la selezione, non solo self.current_model."""
    await gateway._handle_event(ModelSelectedEvent(model="gemma:e4b"))
    assert gateway.model == "gemma:e4b"


@pytest.mark.asyncio
async def test_switching_model_triggers_unload_of_previous(gateway):
    """Selezionare un secondo modello diverso dal primo deve tentare
    l'unload (keep_alive=0) del modello precedente senza propagare
    eccezioni anche se la richiesta di unload fallisce."""
    await gateway._handle_event(ModelSelectedEvent(model="qwen3:4b"))
    assert gateway.model == "qwen3:4b"

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=Exception("boom")
    ):
        # Anche se l'unload fallisce, il branch non deve propagare l'errore
        await gateway._handle_event(ModelSelectedEvent(model="gemma:e4b"))

    assert gateway.model == "gemma:e4b"
    assert gateway.current_model == "gemma:e4b"


@pytest.mark.asyncio
async def test_run_loop_survives_exception_in_single_event_handling():
    """Un'eccezione imprevista nella gestione di un evento non deve piu'
    uccidere in silenzio il task run(): il gateway deve restare vivo e
    continuare a processare gli eventi successivi."""
    bus = EventBus()
    gw = LLMGatewayService(bus, pi_ip="127.0.0.1", model=None)
    bus.subscribe(StatusEvent)

    import asyncio

    task = asyncio.create_task(gw.run())
    try:
        with patch.object(
            gw,
            "_handle_event",
            new_callable=AsyncMock,
            side_effect=[Exception("boom"), None],
        ):
            await bus.publish(ModelSelectedEvent(model="qwen3:4b"))
            await asyncio.sleep(0.05)
            # Il task deve essere ancora vivo dopo l'eccezione
            assert not task.done()

            # E deve continuare a processare eventi successivi
            await bus.publish(ModelSelectedEvent(model="gemma:e4b"))
            await asyncio.sleep(0.05)
            assert not task.done()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
