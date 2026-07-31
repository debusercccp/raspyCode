"""Tool system_run_cmd: esecuzione di comandi di sistema in allow-list, con
doppio limite indipendente:

1. quale BINARIO puo' girare (SYSTEM_CMD_ALLOWLIST);
2. quali DATI puo' leggere (is_safe_path_arg: gli argomenti non-flag devono
   risolvere dentro SYSTEM_CMD_ALLOWED_ROOT). L'allow-list da sola protegge
   il programma ma non i file: "cat" e' innocuo in astratto, ma
   "cat ~/.ssh/id_rsa" o "cat /etc/shadow" non lo sono.

Oltre a questo: timeout con kill() effettivo del subprocess (non solo
abbandono del await) e limite alla dimensione dell'output.
"""

from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any

from .registry import ToolDefinition

SYSTEM_CMD_ALLOWLIST = {
    "ls",
    "cat",
    "df",
    "free",
    "uname",
    "whoami",
    "pwd",
    "head",
    "tail",
    "wc",
}

SYSTEM_CMD_ALLOWED_ROOT = Path.cwd().resolve()

# Comandi come "ls" su directory enormi possono richiedere piu' margine dei
# tool bio in-process (che sono quasi sempre istantanei): timeout dedicato,
# disaccoppiato da DEFAULT_TOOL_TIMEOUT_SECONDS.
SYSTEM_CMD_TIMEOUT_SECONDS = 15.0

# Limite alla dimensione dell'output: un comando come "cat" su un file
# enorme non deve ne' saturare la memoria ne' gonfiare a dismisura il
# prompt rispedito al modello.
MAX_OUTPUT_BYTES = 64_000


def is_safe_path_arg(arg: str, allowed_root: Path | None = None) -> bool:
    """True se arg, interpretato come percorso, resta dentro allowed_root
    (default SYSTEM_CMD_ALLOWED_ROOT) dopo aver espanso '~' e risolto
    '..'/symlink."""
    root = allowed_root if allowed_root is not None else SYSTEM_CMD_ALLOWED_ROOT
    expanded = os.path.expanduser(arg)
    candidate = Path(expanded)
    resolved = (
        candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    )
    try:
        resolved.relative_to(root)
        return True
    except ValueError:
        return False


async def run_system_cmd(arguments: dict[str, Any]) -> tuple[str, bool]:
    command = arguments.get("command", "")
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return f"Comando non parsabile: {exc}", True

    if not parts or parts[0] not in SYSTEM_CMD_ALLOWLIST:
        allowlist_str = ", ".join(sorted(SYSTEM_CMD_ALLOWLIST))
        return (
            f"Comando '{parts[0] if parts else command}' non in allow-list ({allowlist_str}).",
            True,
        )

    for arg in parts[1:]:
        if arg.startswith("-"):
            continue
        if not is_safe_path_arg(arg):
            return (
                f"Percorso '{arg}' non consentito: system_run_cmd puo' "
                f"accedere solo a file dentro {SYSTEM_CMD_ALLOWED_ROOT}.",
                True,
            )

    proc = await asyncio.create_subprocess_exec(
        *parts,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(SYSTEM_CMD_ALLOWED_ROOT),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=SYSTEM_CMD_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return (
            f"Comando '{command}' interrotto: timeout di "
            f"{SYSTEM_CMD_TIMEOUT_SECONDS:.0f}s superato.",
            True,
        )
    text = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
    text_bytes = text.encode(errors="replace")
    if len(text_bytes) > MAX_OUTPUT_BYTES:
        text = (
            text_bytes[:MAX_OUTPUT_BYTES].decode(errors="replace")
            + f"\n... [output troncato a {MAX_OUTPUT_BYTES} byte]"
        )
    return text, proc.returncode != 0


def build_system_run_cmd_tool() -> ToolDefinition:
    return ToolDefinition(
        name="system_run_cmd",
        description=(
            "Esegue un comando di sistema in allow-list "
            f"({', '.join(sorted(SYSTEM_CMD_ALLOWLIST))}), limitato a leggere "
            "file dentro la directory di lavoro corrente."
        ),
        parameters_schema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
        handler=run_system_cmd,
        manages_own_timeout=True,
    )
