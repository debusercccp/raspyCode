"""Test per RaspyCodeApp: comandi testuali /save e /copy.

Il binding da tastiera Ctrl+Shift+C per copiare l'ultima risposta e' spesso
intercettato dal terminale stesso (kitty, foot, alacritty, ecc. - tipico su
setup Wayland) prima ancora di raggiungere Textual: l'azione non viene mai
invocata, quindi nessun fix lato action puo' bastare da solo. Per questo
esistono anche i comandi testuali /copy e /save, digitabili nella barra di
input come /quit: non dipendono da nessuna scorciatoia di tastiera.
"""
from unittest.mock import patch

import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.ui.frontend_service import RaspyCodeApp


def _make_app():
    bus = EventBus()
    return RaspyCodeApp(bus, pi_ip="10.42.0.2", model="qwen3:4b")


@pytest.mark.asyncio
async def test_save_command_writes_last_response_to_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import raspyCode.ui.frontend_service as frontend_module
    monkeypatch.setattr(frontend_module, "WORKING_DIRECTORY", tmp_path)

    app = _make_app()
    async with app.run_test() as pilot:
        app._last_response = "ecco il codice del gioco"
        app.action_save_last_response()
        await pilot.pause()

    saved = tmp_path / "ultima_risposta.txt"
    assert saved.exists()
    assert saved.read_text(encoding="utf-8") == "ecco il codice del gioco"


@pytest.mark.asyncio
async def test_save_command_without_response_shows_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import raspyCode.ui.frontend_service as frontend_module
    monkeypatch.setattr(frontend_module, "WORKING_DIRECTORY", tmp_path)

    app = _make_app()
    async with app.run_test() as pilot:
        assert app._last_response == ""
        app.action_save_last_response()
        await pilot.pause()

    assert not (tmp_path / "ultima_risposta.txt").exists()


@pytest.mark.asyncio
async def test_slash_save_command_from_input_bar(tmp_path, monkeypatch):
    """Il comando testuale /save deve funzionare esattamente come /quit:
    scritto nella barra di input, senza passare da nessuna scorciatoia."""
    monkeypatch.chdir(tmp_path)
    import raspyCode.ui.frontend_service as frontend_module
    monkeypatch.setattr(frontend_module, "WORKING_DIRECTORY", tmp_path)

    app = _make_app()
    async with app.run_test() as pilot:
        app._last_response = "risposta di prova"
        await pilot.click("#chat-input")
        await pilot.press(*"/save")
        await pilot.press("enter")
        await pilot.pause()

    saved = tmp_path / "ultima_risposta.txt"
    assert saved.exists()
    assert saved.read_text(encoding="utf-8") == "risposta di prova"


@pytest.mark.asyncio
async def test_slash_copy_command_invokes_clipboard():
    app = _make_app()
    async with app.run_test() as pilot:
        app._last_response = "testo da copiare"
        with patch.object(app, "copy_to_clipboard") as mock_copy:
            await pilot.click("#chat-input")
            await pilot.press(*"/copy")
            await pilot.press("enter")
            await pilot.pause()
        mock_copy.assert_called_once_with("testo da copiare")


@pytest.mark.asyncio
async def test_copy_command_reports_failure_instead_of_silence():
    """Prima un fallimento nella copia (es. terminale senza OSC52) veniva
    ingoiato in silenzio da un contextlib.suppress: il tasto sembrava 'non
    fare nulla'. Ora deve comparire un messaggio d'errore esplicito."""
    from textual.widgets import RichLog

    app = _make_app()
    async with app.run_test() as pilot:
        app._last_response = "qualcosa"
        log = app.query_one("#chat-log", RichLog)
        with (
            patch.object(app, "copy_to_clipboard", side_effect=RuntimeError("no OSC52")),
            patch.object(log, "write") as mock_write,
        ):
            app.action_copy_last_response()
            await pilot.pause()
        written = "\n".join(str(call.args[0]) for call in mock_write.call_args_list)
        assert "non riuscita" in written
        assert "/save" in written
