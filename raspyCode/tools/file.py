"""Tool per lavorare con file nella directory da cui e' stato avviato raspyCode.

Nessun path assoluto e' accettato e ogni percorso viene risolto rispetto alla
working directory di avvio, impedendo traversal e symlink verso l'esterno.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import ToolDefinition

WORKSPACE_ROOT = Path.cwd().resolve()
MAX_FILE_WRITE_BYTES = 4 * 1024 * 1024
MAX_FILE_READ_BYTES = 4 * 1024 * 1024


def safe_workspace_path(relative_path: str, *, allow_missing: bool = True) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError("Il percorso deve essere relativo alla directory di avvio.")
    candidate = (WORKSPACE_ROOT / relative_path).resolve(strict=False)
    try:
        candidate.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ValueError("Percorso fuori dalla directory di lavoro non consentito.") from exc
    if not allow_missing and not candidate.exists():
        raise FileNotFoundError(relative_path)
    # Un symlink esistente non puo' essere usato per uscire dal workspace.
    if candidate.exists():
        real = candidate.resolve()
        try:
            real.relative_to(WORKSPACE_ROOT)
        except ValueError as exc:
            raise ValueError("Symlink fuori dalla directory di lavoro non consentito.") from exc
    return candidate


def _args(arguments: dict[str, Any]) -> list[str]:
    args = arguments.get("args", [])
    if not isinstance(args, list):
        raise ValueError("args deve essere una lista.")
    return [str(x) for x in args]


async def write_file(arguments: dict[str, Any]) -> tuple[str, bool]:
    args = _args(arguments)
    if len(args) < 2:
        return "Servono 2 argomenti: percorso_relativo, contenuto[, append]", True
    path = safe_workspace_path(args[0])
    content = args[1]
    append = len(args) > 2 and args[2].lower() in {"1", "true", "yes", "append"}
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_WRITE_BYTES:
        return f"File troppo grande: massimo {MAX_FILE_WRITE_BYTES} byte.", True
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "ab" if append else "wb"
    with path.open(mode) as fh:
        fh.write(data)
    return f"File scritto: {path.relative_to(WORKSPACE_ROOT)} ({len(data)} byte).", False


async def read_file(arguments: dict[str, Any]) -> tuple[str, bool]:
    args = _args(arguments)
    if len(args) < 1:
        return "Serve 1 argomento: percorso_relativo", True
    path = safe_workspace_path(args[0], allow_missing=False)
    if not path.is_file():
        return f"Non e' un file: {args[0]}", True
    data = path.read_bytes()
    if len(data) > MAX_FILE_READ_BYTES:
        return f"File troppo grande per la lettura: massimo {MAX_FILE_READ_BYTES} byte.", True
    return data.decode("utf-8", errors="replace"), False


async def list_files(arguments: dict[str, Any]) -> tuple[str, bool]:
    args = _args(arguments)
    relative = args[0] if args else "."
    path = safe_workspace_path(relative, allow_missing=False)
    if not path.is_dir():
        return f"Non e' una directory: {relative}", True
    entries = sorted(
        (p.relative_to(WORKSPACE_ROOT).as_posix() + ("/" if p.is_dir() else ""))
        for p in path.iterdir()
    )
    return "\n".join(entries), False


_ARGS_SCHEMA = {
    "type": "object",
    "properties": {
        "args": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["args"],
}


def build_file_tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="file_write",
            description="Crea o sovrascrive un file dentro la directory da cui e' stato avviato raspyCode. Supporta sottocartelle.",
            parameters_schema=_ARGS_SCHEMA,
            handler=write_file,
        ),
        ToolDefinition(
            name="file_read",
            description="Legge un file testuale dentro la directory da cui e' stato avviato raspyCode.",
            parameters_schema=_ARGS_SCHEMA,
            handler=read_file,
        ),
        ToolDefinition(
            name="file_list",
            description="Elenca file e directory dentro la directory da cui e' stato avviato raspyCode.",
            parameters_schema=_ARGS_SCHEMA,
            handler=list_files,
        ),
    ]
