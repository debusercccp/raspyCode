"""Persistenza delle sessioni per working directory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SESSION_FILENAME = ".raspycode_session.json"


def session_path(workdir: Path | None = None) -> Path:
    root = (workdir or Path.cwd()).resolve()
    return root / SESSION_FILENAME


def load_session(workdir: Path | None = None) -> dict[str, Any] | None:
    path = session_path(workdir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if data.get("working_directory") != str(path.parent):
        return None
    return data


def save_session(
    *,
    history: list[dict[str, Any]],
    model: str | None,
    pi_ip: str,
    workdir: Path | None = None,
) -> Path:
    path = session_path(workdir)
    payload = {
        "version": 1,
        "working_directory": str(path.parent),
        "model": model,
        "pi_ip": pi_ip,
        "history": history,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path
