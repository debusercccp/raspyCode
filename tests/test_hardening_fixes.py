import asyncio

import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import Event, StatusEvent, UserMessageEvent

# --- EventBus: sottoscrizione tipizzata, unsubscribe, backpressure --------


@pytest.mark.asyncio
async def test_subscribe_without_args_receives_everything_backward_compat():
    bus = EventBus()
    q = bus.subscribe()
    await bus.publish(StatusEvent(text="a"))
    await bus.publish(UserMessageEvent(sender_name="x", content="y"))
    assert q.qsize() == 2


@pytest.mark.asyncio
async def test_subscribe_with_type_filters_events():
    bus = EventBus()
    q = bus.subscribe(UserMessageEvent)
    await bus.publish(StatusEvent(text="ignorato"))
    await bus.publish(UserMessageEvent(sender_name="x", content="preso"))
    assert q.qsize() == 1
    event = await q.get()
    assert isinstance(event, UserMessageEvent)


@pytest.mark.asyncio
async def test_subscribe_with_multiple_types():
    bus = EventBus()
    q = bus.subscribe(UserMessageEvent, StatusEvent)
    await bus.publish(UserMessageEvent(sender_name="x", content="y"))
    await bus.publish(StatusEvent(text="z"))
    await bus.publish(Event())  # non richiesto, non deve arrivare
    assert q.qsize() == 2


@pytest.mark.asyncio
async def test_unsubscribe_stops_receiving_events():
    bus = EventBus()
    q = bus.subscribe()
    bus.unsubscribe(q)
    await bus.publish(StatusEvent(text="dopo unsubscribe"))
    assert q.qsize() == 0


@pytest.mark.asyncio
async def test_publish_applies_backpressure_when_queue_full():
    bus = EventBus(max_queue_size=2)
    q = bus.subscribe()
    await bus.publish(StatusEvent(text="1"))
    await bus.publish(StatusEvent(text="2"))

    # la coda e' piena (maxsize=2): un publish ulteriore deve bloccarsi
    # finche' qualcuno non consuma, non accumulare all'infinito.
    publish_task = asyncio.create_task(bus.publish(StatusEvent(text="3")))
    await asyncio.sleep(0.05)
    assert not publish_task.done()

    await q.get()  # libera spazio
    await asyncio.wait_for(publish_task, timeout=1)
    assert publish_task.done()


# --- Gateway: timeout HTTP configurato, non infinito ----------------------


def test_gateway_http_timeout_is_not_infinite():
    from raspyCode.services.llm_gateway_service import OLLAMA_HTTP_TIMEOUT

    # httpx.Timeout(None) equivarrebbe a timeout infinito su ogni fase;
    # verifichiamo che almeno connect/write/pool abbiano un valore finito.
    assert OLLAMA_HTTP_TIMEOUT.connect is not None
    assert OLLAMA_HTTP_TIMEOUT.connect < 60
    assert OLLAMA_HTTP_TIMEOUT.pool is not None


# --- Gateway: limite alla history ------------------------------------------


def test_history_trim_preserves_system_message_and_caps_length():
    from raspyCode.core.event_bus import EventBus as Bus
    from raspyCode.services.llm_gateway_service import (
        MAX_HISTORY_MESSAGES,
        LLMGatewayService,
    )

    gw = LLMGatewayService(Bus(), pi_ip="127.0.0.1", model="m")
    system_msg = gw.history[0]
    assert system_msg["role"] == "system"

    for i in range(MAX_HISTORY_MESSAGES * 2):
        gw.history.append({"role": "user", "content": f"msg {i}"})

    gw._trim_history()

    assert len(gw.history) <= MAX_HISTORY_MESSAGES
    assert gw.history[0] == system_msg
    # gli ultimi messaggi aggiunti devono essere quelli piu' recenti (non i primi)
    assert gw.history[-1]["content"] == f"msg {MAX_HISTORY_MESSAGES * 2 - 1}"


def test_history_trim_is_noop_when_under_limit():
    from raspyCode.core.event_bus import EventBus as Bus
    from raspyCode.services.llm_gateway_service import LLMGatewayService

    gw = LLMGatewayService(Bus(), pi_ip="127.0.0.1", model="m")
    gw.history.append({"role": "user", "content": "ciao"})
    before = list(gw.history)
    gw._trim_history()
    assert gw.history == before


# --- ConnectivityService: lifecycle di _watch_config -----------------------


@pytest.mark.asyncio
async def test_connectivity_watch_config_task_is_cancelled_on_run_cancel():
    from unittest.mock import AsyncMock, patch

    from raspyCode.services.connectivity_service import ConnectivityService

    bus = EventBus()
    service = ConnectivityService(bus, pi_ip="127.0.0.1")

    with patch.object(service, "_check_once", new=AsyncMock()):
        run_task = asyncio.create_task(service.run())
        await asyncio.sleep(0.05)  # lascia partire run() e _watch_config()

        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

        # Nessuna task orfana rimasta viva dopo la cancellazione di run().
        all_tasks = asyncio.all_tasks()
        watch_related = [
            t
            for t in all_tasks
            if "ConnectivityService._watch_config" in repr(t) and not t.done()
        ]
        assert watch_related == []


# --- system_run_cmd: hardening path e output size --------------------------


@pytest.mark.asyncio
async def test_system_run_cmd_rejects_path_outside_allowed_root():
    from raspyCode.tools.system import run_system_cmd

    # bug originale: l'allow-list permetteva 'cat' su QUALUNQUE file
    # leggibile dall'utente, incluso ~/.ssh/id_rsa o /etc/shadow.
    result, is_error = await run_system_cmd({"command": "cat /etc/shadow"})
    assert is_error is True
    assert "non consentito" in result


@pytest.mark.asyncio
async def test_system_run_cmd_rejects_home_expansion_outside_root():
    from raspyCode.tools.system import run_system_cmd

    result, is_error = await run_system_cmd({"command": "cat ~/.ssh/id_rsa"})
    assert is_error is True
    assert "non consentito" in result


@pytest.mark.asyncio
async def test_system_run_cmd_allows_relative_path_inside_cwd(tmp_path, monkeypatch):
    import raspyCode.tools.system as mod

    test_file = tmp_path / "note.txt"
    test_file.write_text("contenuto di prova")

    monkeypatch.setattr(mod, "SYSTEM_CMD_ALLOWED_ROOT", tmp_path.resolve())

    result, is_error = await mod.run_system_cmd({"command": "cat note.txt"})
    assert is_error is False
    assert "contenuto di prova" in result


@pytest.mark.asyncio
async def test_system_run_cmd_truncates_large_output(monkeypatch):
    import raspyCode.tools.system as mod

    monkeypatch.setattr(mod, "MAX_OUTPUT_BYTES", 10)

    # 'uname -a' produce un output breve normalmente, ma forziamo il limite
    # bassissimo per esercitare il ramo di troncamento in modo deterministico.
    result, _ = await mod.run_system_cmd({"command": "uname -a"})
    assert "troncato" in result


def test_is_safe_path_arg_blocks_traversal(tmp_path, monkeypatch):
    import raspyCode.tools.system as mod

    monkeypatch.setattr(mod, "SYSTEM_CMD_ALLOWED_ROOT", tmp_path.resolve())
    assert mod.is_safe_path_arg("../../../etc/passwd") is False
    assert mod.is_safe_path_arg("subdir/file.txt") is True
