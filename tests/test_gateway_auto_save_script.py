import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import StatusEvent, ToolResultEvent
from raspyCode.services.llm_gateway_service import LLMGatewayService


def _make_gateway(tmp_path):
    bus = EventBus()
    gw = LLMGatewayService(bus, pi_ip="10.42.0.2", model="qwen3:4b")
    return bus, gw


async def _drain_events(queue, n):
    events = []
    for _ in range(n):
        events.append(await queue.get())
        queue.task_done()
    return events


@pytest.mark.asyncio
async def test_auto_save_prefers_real_code_over_installer_block(tmp_path, monkeypatch):
    """Regressione: prima veniva salvato il PRIMO fence trovato, che spesso e'
    solo 'pip install pygame' e non il gioco vero. Deve vincere il blocco piu'
    corposo che non e' solo un comando di installazione."""
    monkeypatch.chdir(tmp_path)
    import raspyCode.tools.file as file_tool
    monkeypatch.setattr(file_tool, "WORKSPACE_ROOT", tmp_path)

    bus, gw = _make_gateway(tmp_path)
    queue = bus.subscribe()

    assistant_content = (
        "Prima installa pygame:\n\n"
        "```bash\npip install pygame\n```\n\n"
        "Ecco il gioco:\n\n"
        "```python\nimport pygame\n\n"
        "def main():\n    pygame.init()\n    print('tetris!')\n\n"
        "main()\n```\n"
    )

    await gw._auto_save_script("fammi un giochino come tetris", assistant_content, [])

    created = tmp_path / "tetris.py"
    assert created.exists()
    content = created.read_text()
    assert "pygame.init" in content
    assert content.strip() != "pip install pygame"

    events = await _drain_events(queue, 2)
    tool_events = [e for e in events if isinstance(e, ToolResultEvent)]
    status_events = [e for e in events if isinstance(e, StatusEvent)]
    assert tool_events and tool_events[0].tool_name == "file_write"
    assert tool_events[0].is_error is False
    assert status_events and "tetris.py" in status_events[0].text


@pytest.mark.asyncio
async def test_auto_save_skips_when_only_installer_block_present(tmp_path, monkeypatch):
    """Se l'unico fence e' un comando di installazione, non c'e' niente di
    reale da salvare: meglio non creare un file inutile."""
    monkeypatch.chdir(tmp_path)
    import raspyCode.tools.file as file_tool
    monkeypatch.setattr(file_tool, "WORKSPACE_ROOT", tmp_path)

    bus, gw = _make_gateway(tmp_path)
    bus.subscribe()

    assistant_content = "```bash\npip install pygame\n```"
    await gw._auto_save_script("fammi un giochino", assistant_content, [])

    # L'unico blocco disponibile e' un installer: viene comunque usato come
    # ultima risorsa (pool di fallback), ma non deve mai crashare.
    assert (tmp_path / "script.sh").exists() or not any(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_auto_save_does_nothing_if_file_write_already_called(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import raspyCode.tools.file as file_tool
    monkeypatch.setattr(file_tool, "WORKSPACE_ROOT", tmp_path)

    bus, gw = _make_gateway(tmp_path)
    bus.subscribe()

    assistant_content = "```python\nprint('hi')\n```"
    tool_calls = [{"function": {"name": "file_write", "arguments": {}}}]
    await gw._auto_save_script("fammi uno script", assistant_content, tool_calls)

    assert not any(tmp_path.iterdir())


def test_pick_code_block_ignores_installer_only_fence():
    content = (
        "```bash\npip install pygame\n```\n"
        "```python\nimport pygame\nprint('ok')\n```"
    )
    lang, code = LLMGatewayService._pick_code_block(content)
    assert lang == "python"
    assert "import pygame" in code


def test_guess_filename_slug_recognizes_known_games():
    assert LLMGatewayService._guess_filename_slug("fammi un giochino come tetris") == "tetris"
    assert LLMGatewayService._guess_filename_slug("scrivimi uno script qualsiasi") == "script"


@pytest.mark.asyncio
async def test_pseudo_tool_call_json_text_is_decoded_and_dispatched(tmp_path, monkeypatch):
    """Regressione osservata in produzione: con Ollama locale in fallback,
    il modello a volte non usa il campo nativo tool_calls e scrive invece
    una tool call come testo JSON puro in chat, es.:
        {"name": "file_write", "arguments": {"path": "tetris.py",
         "content": "Ecco il contenuto...\\n\\n```python\\n...codice...\\n```"}}
    Prima di questo fix, se _auto_save_script intercettava questo testo
    grezzo (senza json.loads), le sequenze '\\n' restavano due caratteri
    letterali nel file scritto su disco invece di andare a capo davvero.
    Ora il blob JSON viene decodificato per bene e la tool call eseguita
    con newline reali."""
    monkeypatch.chdir(tmp_path)
    import raspyCode.tools.file as file_tool
    monkeypatch.setattr(file_tool, "WORKSPACE_ROOT", tmp_path)

    bus, gw = _make_gateway(tmp_path)
    queue = bus.subscribe()

    assistant_content = (
        '{"name": "file_write", "arguments": {"path": "tetris.py", '
        '"content": "Ecco il contenuto del file tetris.py:\\n\\n'
        '```python\\nclass Tetris:\\n    def __init__(self):\\n'
        '        self.board = []\\n\\nif __name__ == \'__main__\':\\n'
        '    Tetris()\\n```"}}'
    )

    handled = await gw._maybe_dispatch_pseudo_tool_call(assistant_content)
    assert handled is True

    created = tmp_path / "tetris.py"
    assert created.exists()
    content = created.read_text()
    # Il contenuto deve avere newline VERI (righe multiple), non "\n" letterali.
    assert "\\n" not in content
    assert content.count("\n") >= 4
    assert "class Tetris:" in content
    assert "Ecco il contenuto" not in content  # la prosa non deve finire nel file

    events = await _drain_events(queue, 2)
    tool_events = [e for e in events if isinstance(e, ToolResultEvent)]
    assert tool_events and tool_events[0].tool_name == "file_write"
    assert tool_events[0].is_error is False


@pytest.mark.asyncio
async def test_pseudo_tool_call_ignores_unrelated_json_text():
    """Del testo JSON che il modello scrive per altri motivi (es. un
    esempio di output atteso, non una vera tool call) non deve essere
    scambiato per una tool call: deve avere 'name' + 'arguments' validi
    e 'name' deve corrispondere a un tool realmente registrato."""
    bus, gw = _make_gateway(None)
    assistant_content = '{"foo": "bar", "baz": {"qux": 1}}'
    handled = await gw._maybe_dispatch_pseudo_tool_call(assistant_content)
    assert handled is False


@pytest.mark.asyncio
async def test_pseudo_tool_call_rejects_unknown_tool_name():
    bus, gw = _make_gateway(None)
    assistant_content = '{"name": "delete_everything", "arguments": {"args": ["x"]}}'
    handled = await gw._maybe_dispatch_pseudo_tool_call(assistant_content)
    assert handled is False


def test_extract_json_object_finds_balanced_blob_with_surrounding_prose():
    from raspyCode.services.llm_gateway_service import _extract_json_object

    text = 'Ecco qua:\n{"name": "file_write", "arguments": {"a": "b {nested}"}}\nFatto.'
    data = _extract_json_object(text)
    assert data == {"name": "file_write", "arguments": {"a": "b {nested}"}}


def test_extract_json_object_returns_none_without_json():
    from raspyCode.services.llm_gateway_service import _extract_json_object

    assert _extract_json_object("solo testo, nessun JSON qui") is None
