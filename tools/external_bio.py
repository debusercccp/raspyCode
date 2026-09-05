"""Wrapper sicuri per samtools e bcftools.

I comandi vengono eseguiti senza shell e con i percorsi confinati al workspace
di avvio. Gli argomenti CLI restano sotto il controllo del modello, ma non e'
possibile concatenare comandi tramite shell.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from ..tools.file import WORKSPACE_ROOT, safe_workspace_path
from ..tools.registry import ToolDefinition

EXTERNAL_TOOL_TIMEOUT_SECONDS = 300.0
MAX_OUTPUT_BYTES = 256 * 1024


def _args(arguments: dict[str, Any]) -> list[str]:
    args = arguments.get("args", [])
    if not isinstance(args, list):
        raise ValueError("args deve essere una lista.")
    return [str(x) for x in args]


def _validate_args(args: list[str]) -> None:
    for arg in args:
        if arg.startswith("-") or arg in {".", ".."}:
            continue
        # Solo gli argomenti che sembrano path vengono verificati. I valori
        # normali (regioni, numeri, nomi di contig) restano invariati.
        if "/" in arg or arg.startswith("~") or Path(arg).suffix:
            if Path(arg).is_absolute():
                safe_workspace_path(arg)  # produce l'errore corretto
            elif (WORKSPACE_ROOT / arg).exists():
                safe_workspace_path(arg)


async def run_bio_cli(executable: str, arguments: dict[str, Any]) -> tuple[str, bool]:
    args = _args(arguments)
    if not shutil.which(executable):
        return f"{executable} non installato o non presente nel PATH.", True
    try:
        _validate_args(args)
        proc = await asyncio.create_subprocess_exec(
            executable, *args,
            cwd=str(WORKSPACE_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=EXTERNAL_TOOL_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"{executable} interrotto: timeout di {EXTERNAL_TOOL_TIMEOUT_SECONDS:.0f}s superato.", True
        text = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
        raw = text.encode(errors="replace")
        if len(raw) > MAX_OUTPUT_BYTES:
            text = raw[:MAX_OUTPUT_BYTES].decode(errors="replace") + f"\n... [output troncato a {MAX_OUTPUT_BYTES} byte]"
        return text, proc.returncode != 0
    except Exception as exc:
        return f"Errore {executable}: {exc}", True


_ARGS_SCHEMA = {
    "type": "object",
    "properties": {"args": {"type": "array", "items": {"type": "string"}}},
    "required": ["args"],
}


def build_external_bio_tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="biotoolkit_samtools",
            description="Esegue samtools nel workspace corrente senza shell (es. view, sort, index, flagstat). I file devono stare nel workspace.",
            parameters_schema=_ARGS_SCHEMA,
            handler=lambda arguments: run_bio_cli("samtools", arguments),
            manages_own_timeout=True,
        ),
        ToolDefinition(
            name="biotoolkit_bcftools",
            description="Esegue bcftools nel workspace corrente senza shell (es. view, query, stats, filter). I file devono stare nel workspace.",
            parameters_schema=_ARGS_SCHEMA,
            handler=lambda arguments: run_bio_cli("bcftools", arguments),
            manages_own_timeout=True,
        ),
    ]
