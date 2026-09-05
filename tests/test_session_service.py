from pathlib import Path

from raspyCode.services.session_service import load_session, save_session, session_path


def test_session_is_scoped_to_working_directory(tmp_path: Path):
    history = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "salve"},
    ]
    path = save_session(history=history, model="qwen3:4b", pi_ip="10.42.0.2", workdir=tmp_path)
    assert path == session_path(tmp_path)
    data = load_session(tmp_path)
    assert data is not None
    assert data["model"] == "qwen3:4b"
    assert data["history"] == history


def test_missing_session_returns_none(tmp_path: Path):
    assert load_session(tmp_path) is None
