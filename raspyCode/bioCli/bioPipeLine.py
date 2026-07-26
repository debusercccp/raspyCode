#!/usr/bin/env python3
"""
BioCLI Pipeline Creator
Crea, salva ed esegui pipeline di script BioCLI in modo interattivo.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table, Column
from rich.text import Text
from rich.tree import Tree
from rich import box

console = Console()

# --------------------------------------------------
# Catalogo degli script disponibili
# --------------------------------------------------
TOOLS: Dict[str, Dict[str, Any]] = {
    # sequence/
    "baseCount": {
        "script": "sequence/baseCount.py",
        "desc": "Frequenza tetranucleotidica (A C G T)",
        "category": "sequence",
        "args": [{"name": "dna", "help": "Sequenza DNA o file", "positional": True}],
        "output": "stdout",
    },
    "dnaToRna": {
        "script": "sequence/dnaToRna.py",
        "desc": "Trascrizione DNA → RNA",
        "category": "sequence",
        "args": [
            {"name": "file", "help": "File FASTA (opzionale)", "positional": True, "optional": True},
            {"name": "-s", "help": "Sequenza diretta", "optional": True},
            {"name": "-o", "help": "Directory output", "optional": True, "default": "out"},
        ],
        "output": "stdout_or_file",
    },
    "rnaToProt": {
        "script": "sequence/rnaToProt.py",
        "desc": "Traduzione RNA/DNA → proteine (FASTA multi-record)",
        "category": "sequence",
        "args": [{"name": "input", "help": "Sequenza RNA/DNA o file FASTA", "positional": True}],
        "output": "stdout",
    },
    "revComp": {
        "script": "sequence/revComp.py",
        "desc": "Complemento inverso Watson-Crick",
        "category": "sequence",
        "args": [{"name": "dna", "help": "Sequenza DNA o file", "positional": True}],
        "output": "stdout",
    },
    "gcContent": {
        "script": "sequence/gcContent.py",
        "desc": "Percentuale GC, record con GC massimo",
        "category": "sequence",
        "args": [
            {"name": "file", "help": "File FASTA", "positional": True, "optional": True},
            {"name": "-s", "help": "Sequenza diretta", "optional": True},
        ],
        "output": "stdout",
    },
    "hammDist": {
        "script": "sequence/hammDist.py",
        "desc": "Distanza di Hamming tra due sequenze",
        "category": "sequence",
        "args": [
            {"name": "seq1", "help": "Sequenza 1", "positional": True},
            {"name": "seq2", "help": "Sequenza 2", "positional": True},
        ],
        "output": "stdout",
    },
    # search/
    "motifFind": {
        "script": "search/motifFind.py",
        "desc": "Posizioni di una sottosequenza",
        "category": "search",
        "args": [
            {"name": "seq", "help": "Sequenza", "positional": True},
            {"name": "subseq", "help": "Sottosequenza", "positional": True},
        ],
        "output": "stdout",
    },
    "nGlicMotif": {
        "script": "search/nGlicMotif.py",
        "desc": "Motivo N-glicosilazione, fetch UniProt",
        "category": "search",
        "args": [
            {"name": "input", "help": "Sequenza AA, UniProt ID o file di ID", "positional": True},
            {"name": "-d", "help": "Directory download FASTA", "optional": True, "default": "fasta"},
        ],
        "output": "stdout",
    },
    "grepFastx": {
        "script": "search/grepFastx.py",
        "desc": "Grep regex su header FASTA/FASTQ",
        "category": "search",
        "args": [
            {"name": "pattern", "help": "Pattern regex", "positional": True},
            {"name": "file", "help": "File FASTA/Q", "positional": True},
            {"name": "-f", "help": "Formato input (fasta/fastq)", "optional": True},
            {"name": "-O", "help": "Formato output", "optional": True},
            {"name": "-o", "help": "File output", "optional": True},
            {"name": "-i", "help": "Case-insensitive", "flag": True},
        ],
        "output": "stdout_or_file",
    },
    "recSite": {
        "script": "search/recSite.py",
        "desc": "Siti di restrizione (palindromi inversi k=4–12)",
        "category": "search",
        "args": [{"name": "file", "help": "File FASTA", "positional": True}],
        "output": "stdout",
    },
    # assembly/
    "genAsmb": {
        "script": "assembly/genAsmb.py",
        "desc": "Grafo di overlap da FASTA",
        "category": "assembly",
        "args": [
            {"name": "file", "help": "File FASTA", "positional": True},
            {"name": "-k", "help": "Dimensione overlap", "optional": True, "default": "3"},
        ],
        "output": "stdout",
    },
    "longestSharedSeq": {
        "script": "assembly/longestSharedSeq.py",
        "desc": "Sottostringa comune più lunga",
        "category": "assembly",
        "args": [{"name": "file", "help": "File FASTA", "positional": True}],
        "output": "stdout",
    },
    "orfFinder": {
        "script": "assembly/orfFinder.py",
        "desc": "Open Reading Frame (6 frame)",
        "category": "assembly",
        "args": [{"name": "file", "help": "File FASTA", "positional": True}],
        "output": "stdout",
    },
    "hwMnySeq": {
        "script": "assembly/hwMnySeq.py",
        "desc": "Numero di mRNA possibili per una proteina",
        "category": "assembly",
        "args": [
            {"name": "protein", "help": "Sequenza proteica o file", "positional": True},
            {"name": "-m", "help": "Valore modulo", "optional": True, "default": "1000000"},
        ],
        "output": "stdout",
    },
    # io/
    "fastxSampler": {
        "script": "io/fastxSampler.py",
        "desc": "Subset probabilistico FASTA/Q",
        "category": "io",
        "args": [
            {"name": "file", "help": "File/directory FASTA/Q", "positional": True},
            {"name": "-p", "help": "Percentuale reads (0-1)", "optional": True, "default": "0.1"},
            {"name": "-m", "help": "Max reads", "optional": True, "default": "0"},
            {"name": "-s", "help": "Seed random", "optional": True},
            {"name": "-o", "help": "Directory output", "optional": True, "default": "out"},
        ],
        "output": "file",
    },
    "seqMagique": {
        "script": "io/seqMagique.py",
        "desc": "Statistiche FASTA (min/max/avg/num)",
        "category": "io",
        "args": [{"name": "file", "help": "File FASTA (uno o più)", "positional": True}],
        "output": "stdout",
    },
    "blastOutput": {
        "script": "io/blastOutput.py",
        "desc": "Annota output BLAST -outfmt 6",
        "category": "io",
        "args": [
            {"name": "-b", "help": "File BLAST hits", "required": True},
            {"name": "-a", "help": "File annotazioni CSV", "required": True},
            {"name": "-o", "help": "File output", "optional": True, "default": "out.csv"},
            {"name": "-p", "help": "Minimo pident", "optional": True, "default": "0"},
        ],
        "output": "file",
    },
    # synthesis/
    "synthSeq": {
        "script": "synthesis/synthSeq.py",
        "desc": "Genera DNA sintetico via catena di Markov",
        "category": "synthesis",
        "args": [
            {"name": "file", "help": "File FASTA training", "positional": True},
            {"name": "-n", "help": "Numero sequenze", "optional": True, "default": "100"},
            {"name": "-k", "help": "Dimensione k-mer", "optional": True, "default": "10"},
            {"name": "-x", "help": "Lunghezza massima", "optional": True, "default": "75"},
            {"name": "-m", "help": "Lunghezza minima", "optional": True, "default": "50"},
            {"name": "-s", "help": "Seed random", "optional": True},
            {"name": "-o", "help": "File output", "optional": True, "default": "out.fa"},
        ],
        "output": "file",
    },
}

CATEGORY_COLORS = {
    "sequence":  "cyan",
    "search":    "yellow",
    "assembly":  "green",
    "io":        "blue",
    "synthesis": "magenta",
}

PIPELINES_FILE = Path("pipelines.json")

# --------------------------------------------------
# Persistenza pipeline
# --------------------------------------------------

def load_pipelines() -> Dict[str, Any]:
    if PIPELINES_FILE.exists():
        with open(PIPELINES_FILE) as f:
            return json.load(f)
    return {}

def save_pipelines(pipelines: Dict[str, Any]) -> None:
    with open(PIPELINES_FILE, "w") as f:
        json.dump(pipelines, f, indent=2)
    console.print(f"[dim]Pipeline salvate in {PIPELINES_FILE}[/dim]")

# --------------------------------------------------
# UI helpers
# --------------------------------------------------

def print_header() -> None:
    console.print()
    console.print(Panel(
        Text("BioCLI Pipeline Creator", justify="center", style="bold white"),
        subtitle="[dim]crea · salva · esegui pipeline di analisi bioinformatica[/dim]",
        style="bold cyan",
        box=box.DOUBLE_EDGE,
    ))
    console.print()

def print_tools_table() -> None:
    table = Table(
        Column("ID", style="bold white", no_wrap=True),
        Column("Script", style="dim"),
        Column("Categoria", justify="center"),
        Column("Descrizione"),
        box=box.SIMPLE_HEAD,
        header_style="bold cyan",
        show_lines=False,
        expand=True,
    )
    for name, info in TOOLS.items():
        color = CATEGORY_COLORS.get(info["category"], "white")
        table.add_row(
            name,
            info["script"],
            f"[{color}]{info['category']}[/{color}]",
            info["desc"],
        )
    console.print(Panel(table, title="[bold cyan]Strumenti disponibili[/bold cyan]",
                        box=box.ROUNDED))

def print_pipeline(steps: List[Dict]) -> None:
    if not steps:
        console.print("[dim]  (pipeline vuota)[/dim]")
        return
    tree = Tree("[bold cyan]Pipeline[/bold cyan]")
    for i, step in enumerate(steps, 1):
        color = CATEGORY_COLORS.get(TOOLS[step["tool"]]["category"], "white")
        node = tree.add(
            f"[bold]{i}.[/bold] [{color}]{step['tool']}[/{color}]"
            f"  [dim]{TOOLS[step['tool']]['desc']}[/dim]"
        )
        for k, v in step["args"].items():
            if v:
                node.add(f"[dim]{k}[/dim] = [yellow]{v}[/yellow]")
    console.print(node.root if hasattr(node, 'root') else tree)

def build_command(step: Dict, biocli_dir: str) -> List[str]:
    tool = TOOLS[step["tool"]]
    script = os.path.join(biocli_dir, tool["script"])
    cmd = [sys.executable, script]
    for arg_def in tool["args"]:
        name = arg_def["name"]
        val = step["args"].get(name, "")
        if not val:
            continue
        if arg_def.get("flag"):
            if val in ("true", "1", "yes", "si"):
                cmd.append(name)
        elif arg_def.get("positional"):
            cmd.append(str(Path(val).expanduser()) if val.startswith("~") else str(val))
        else:
            expanded = str(Path(val).expanduser()) if val.startswith("~") else str(val)
            cmd.extend([name, expanded])
    return cmd

# --------------------------------------------------
# Costruzione interattiva di un passo
# --------------------------------------------------

def build_step(tool_name: str) -> Optional[Dict]:
    if tool_name not in TOOLS:
        console.print(f"[red]Strumento '{tool_name}' non trovato.[/red]")
        return None

    tool = TOOLS[tool_name]
    color = CATEGORY_COLORS.get(tool["category"], "white")
    console.print()
    console.print(Panel(
        f"[bold]{tool['desc']}[/bold]\n[dim]{tool['script']}[/dim]",
        title=f"[{color}]Configura: {tool_name}[/{color}]",
        box=box.ROUNDED,
    ))

    args: Dict[str, str] = {}
    for arg_def in tool["args"]:
        name = arg_def["name"]
        help_text = arg_def.get("help", "")
        default = arg_def.get("default", "")
        optional = arg_def.get("optional", False)
        required = arg_def.get("required", False)
        is_flag = arg_def.get("flag", False)

        prompt_text = f"  [cyan]{name}[/cyan] [dim]{help_text}[/dim]"
        if default:
            prompt_text += f" [dim](default: {default})[/dim]"
        if optional and not required:
            prompt_text += " [dim](invio per saltare)[/dim]"

        console.print(prompt_text)
        if is_flag:
            val = Prompt.ask("    →", choices=["si", "no"], default="no")
            args[name] = val
        else:
            val = Prompt.ask("    →", default=default or "")
            args[name] = val

    return {"tool": tool_name, "args": args}

# --------------------------------------------------
# Esecuzione pipeline
# --------------------------------------------------

def run_pipeline(steps: List[Dict], biocli_dir: str) -> None:
    if not steps:
        console.print("[yellow]Pipeline vuota, nulla da eseguire.[/yellow]")
        return

    console.print()
    console.print(Rule("[bold cyan]Esecuzione Pipeline[/bold cyan]"))
    total = len(steps)

    for i, step in enumerate(steps, 1):
        tool_name = step["tool"]
        color = CATEGORY_COLORS.get(TOOLS[tool_name]["category"], "white")
        cmd = build_command(step, biocli_dir)

        console.print()
        console.print(
            f"[bold][{i}/{total}][/bold] [{color}]{tool_name}[/{color}]"
            f"  [dim]{TOOLS[tool_name]['desc']}[/dim]"
        )

        # Mostra il comando che verrà eseguito
        cmd_str = " ".join(cmd)
        console.print(Syntax(cmd_str, "bash", theme="monokai", word_wrap=True))

        t0 = time.time()
        try:
            result = subprocess.run(cmd, capture_output=False, text=True)
            elapsed = time.time() - t0
            if result.returncode == 0:
                console.print(
                    f"  [green]✓[/green] completato in [bold]{elapsed:.2f}s[/bold]"
                )
            else:
                console.print(
                    f"  [red]✗[/red] errore (returncode={result.returncode})"
                )
                if Confirm.ask("  Continuare con il passo successivo?", default=False):
                    continue
                else:
                    console.print("[red]Pipeline interrotta.[/red]")
                    return
        except FileNotFoundError:
            console.print(
                f"  [red]✗[/red] Script non trovato: [bold]{cmd[1]}[/bold]\n"
                f"  Controlla il percorso BioCLI: [yellow]{biocli_dir}[/yellow]"
            )
            if not Confirm.ask("  Continuare?", default=False):
                return

    console.print()
    console.print(Rule("[bold green]Pipeline completata[/bold green]"))

# --------------------------------------------------
# Menu principale
# --------------------------------------------------

def menu_new_pipeline(pipelines: Dict) -> None:
    console.print()
    name = Prompt.ask("[cyan]Nome della nuova pipeline[/cyan]")
    if name in pipelines:
        if not Confirm.ask(f"[yellow]'{name}' esiste già. Sovrascrivere?[/yellow]"):
            return

    steps: List[Dict] = []
    print_tools_table()

    while True:
        console.print()
        console.print(Rule("[dim]Pipeline corrente[/dim]"))
        print_pipeline(steps)
        console.print()
        console.print("[dim]Comandi: [bold]nome_tool[/bold] per aggiungere  |  "
                      "[bold]rm[/bold] per rimuovere  |  "
                      "[bold]fine[/bold] per salvare  |  "
                      "[bold]annulla[/bold] per uscire[/dim]")
        cmd = Prompt.ask("[cyan]>[/cyan]").strip()

        if cmd == "annulla":
            console.print("[yellow]Creazione annullata.[/yellow]")
            return
        elif cmd == "fine":
            if not steps:
                console.print("[yellow]Pipeline vuota, non salvata.[/yellow]")
                return
            pipelines[name] = {"steps": steps, "desc": Prompt.ask("Descrizione breve")}
            save_pipelines(pipelines)
            console.print(f"[green]Pipeline '[bold]{name}[/bold]' salvata con {len(steps)} passi.[/green]")
            return
        elif cmd == "rm":
            if not steps:
                console.print("[yellow]Nessun passo da rimuovere.[/yellow]")
                continue
            idx = Prompt.ask(f"Numero passo da rimuovere (1-{len(steps)})")
            try:
                removed = steps.pop(int(idx) - 1)
                console.print(f"[green]Rimosso: {removed['tool']}[/green]")
            except (ValueError, IndexError):
                console.print("[red]Indice non valido.[/red]")
        elif cmd in TOOLS:
            step = build_step(cmd)
            if step:
                steps.append(step)
                console.print(f"[green]✓ Aggiunto: {cmd}[/green]")
        else:
            console.print(f"[red]'{cmd}' non riconosciuto. Usa un ID dalla tabella.[/red]")

def menu_list_pipelines(pipelines: Dict) -> None:
    if not pipelines:
        console.print("[yellow]Nessuna pipeline salvata.[/yellow]")
        return
    table = Table(
        Column("Nome", style="bold white"),
        Column("Passi", justify="right"),
        Column("Descrizione"),
        box=box.SIMPLE_HEAD,
        header_style="bold cyan",
    )
    for name, data in pipelines.items():
        table.add_row(name, str(len(data["steps"])), data.get("desc", ""))
    console.print(Panel(table, title="[bold cyan]Pipeline salvate[/bold cyan]", box=box.ROUNDED))

def menu_run_pipeline(pipelines: Dict, biocli_dir: str) -> None:
    if not pipelines:
        console.print("[yellow]Nessuna pipeline disponibile.[/yellow]")
        return
    menu_list_pipelines(pipelines)
    name = Prompt.ask("[cyan]Nome pipeline da eseguire[/cyan]")
    if name not in pipelines:
        console.print(f"[red]Pipeline '{name}' non trovata.[/red]")
        return
    steps = pipelines[name]["steps"]
    print_pipeline(steps)

    errors = validate_pipeline(steps, biocli_dir)
    if errors:
        console.print()
        console.print(Panel(
            "\n".join(f"[red]\u2717[/red] {e}" for e in errors),
            title="[bold red]Problemi rilevati[/bold red]",
            box=box.ROUNDED,
        ))
        if not Confirm.ask("[yellow]Eseguire comunque?[/yellow]", default=False):
            return

    if Confirm.ask(f"\nEseguire '[bold]{name}[/bold]' ({len(steps)} passi)?"):
        run_pipeline(steps, biocli_dir)

def menu_inspect_pipeline(pipelines: Dict) -> None:
    if not pipelines:
        console.print("[yellow]Nessuna pipeline disponibile.[/yellow]")
        return
    menu_list_pipelines(pipelines)
    name = Prompt.ask("[cyan]Nome pipeline da ispezionare[/cyan]")
    if name not in pipelines:
        console.print(f"[red]Pipeline '{name}' non trovata.[/red]")
        return
    print_pipeline(pipelines[name]["steps"])
    # Mostra anche i comandi che verrebbero eseguiti
    console.print()
    console.print(Rule("[dim]Comandi generati[/dim]"))
    biocli_dir = Prompt.ask("Percorso BioCLI", default=".")
    for i, step in enumerate(pipelines[name]["steps"], 1):
        cmd = build_command(step, biocli_dir)
        console.print(f"[dim]{i}.[/dim] ", end="")
        console.print(Syntax(" ".join(cmd), "bash", theme="monokai"))

def menu_delete_pipeline(pipelines: Dict) -> None:
    if not pipelines:
        console.print("[yellow]Nessuna pipeline da eliminare.[/yellow]")
        return
    menu_list_pipelines(pipelines)
    name = Prompt.ask("[cyan]Nome pipeline da eliminare[/cyan]")
    if name not in pipelines:
        console.print(f"[red]Pipeline '{name}' non trovata.[/red]")
        return
    if Confirm.ask(f"[red]Eliminare '[bold]{name}[/bold]'?[/red]"):
        del pipelines[name]
        save_pipelines(pipelines)
        console.print(f"[green]Pipeline '{name}' eliminata.[/green]")

def menu_export_pipeline(pipelines: Dict) -> None:
    if not pipelines:
        console.print("[yellow]Nessuna pipeline disponibile.[/yellow]")
        return
    menu_list_pipelines(pipelines)
    name = Prompt.ask("[cyan]Nome pipeline da esportare come script bash[/cyan]")
    if name not in pipelines:
        console.print(f"[red]Pipeline '{name}' non trovata.[/red]")
        return
    biocli_dir = Prompt.ask("Percorso BioCLI", default=".")
    out_path = Prompt.ask("File output", default=f"{name}.sh")

    lines = ["#!/usr/bin/env bash", f"# Pipeline: {name}", f"# {pipelines[name].get('desc', '')}", "set -e", ""]
    for i, step in enumerate(pipelines[name]["steps"], 1):
        cmd = build_command(step, biocli_dir)
        lines.append(f"# Passo {i}: {step['tool']}")
        lines.append(" ".join(cmd))
        lines.append("")

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    os.chmod(out_path, 0o755)
    console.print(f"[green]Script bash esportato: [bold]{out_path}[/bold][/green]")
    console.print(Syntax("\n".join(lines[:20]), "bash", theme="monokai"))

# --------------------------------------------------
# Entrypoint
# --------------------------------------------------

def detect_biocli_dir() -> str:
    """ Auto-rileva il percorso BioCLI: prima prova la cartella dello script stesso """
    script_dir = Path(__file__).resolve().parent
    # Se bioPipeline.py è dentro la cartella bioCLI, usala direttamente
    if (script_dir / "sequence").is_dir():
        return str(script_dir)
    # Fallback: chiedi
    return str(Path.home() / "Progettini" / "toolKit" / "bioCli")

def validate_pipeline(steps: List[Dict], biocli_dir: str) -> List[str]:
    """ Ritorna lista di errori trovati nella pipeline prima dell'esecuzione """
    errors = []
    for i, step in enumerate(steps, 1):
        tool_name = step["tool"]
        tool = TOOLS[tool_name]
        script_path = Path(biocli_dir) / tool["script"]

        # Controlla esistenza script
        if not script_path.exists():
            errors.append(f"Passo {i} ({tool_name}): script non trovato → {script_path}")

        # Controlla argomenti obbligatori non opzionali
        for arg_def in tool["args"]:
            name = arg_def["name"]
            is_required = not arg_def.get("optional", False) and not arg_def.get("flag", False)
            val = step["args"].get(name, "").strip()
            if is_required and not val and not arg_def.get("default"):
                errors.append(f"Passo {i} ({tool_name}): argomento obbligatorio mancante → '{name}'")

    return errors

def main() -> None:
    print_header()

    default_dir = detect_biocli_dir()
    biocli_dir = Prompt.ask(
        "[cyan]Percorso della cartella BioCLI[/cyan]",
        default=default_dir,
    )

    # Verifica immediata del percorso
    if not Path(biocli_dir).is_dir():
        console.print(f"[red]Percorso non trovato: {biocli_dir}[/red]")
        sys.exit(1)

    found = sum(1 for t in TOOLS.values()
                if (Path(biocli_dir) / t["script"]).exists())
    console.print(
        f"[dim]BioCLI: [bold]{biocli_dir}[/bold]  "
        f"[green]{found}[/green]/[white]{len(TOOLS)}[/white] script trovati[/dim]"
    )

    pipelines = load_pipelines()

    MENU = {
        "1": ("Nuova pipeline",          lambda: menu_new_pipeline(pipelines)),
        "2": ("Lista pipeline salvate",  lambda: menu_list_pipelines(pipelines)),
        "3": ("Esegui pipeline",         lambda: menu_run_pipeline(pipelines, biocli_dir)),
        "4": ("Ispeziona pipeline",      lambda: menu_inspect_pipeline(pipelines)),
        "5": ("Esporta come script bash",lambda: menu_export_pipeline(pipelines)),
        "6": ("Elimina pipeline",        lambda: menu_delete_pipeline(pipelines)),
        "7": ("Mostra strumenti",        print_tools_table),
        "0": ("Esci",                    None),
    }

    while True:
        console.print()
        console.print(Rule("[bold cyan]Menu[/bold cyan]"))
        for key, (label, _) in MENU.items():
            style = "bold red" if key == "0" else "cyan"
            console.print(f"  [{style}]{key}[/{style}]  {label}")
        console.print()

        choice = Prompt.ask("[cyan]Scelta[/cyan]", choices=list(MENU.keys()))
        if choice == "0":
            console.print("\n[dim]Ciao![/dim]\n")
            break
        _, action = MENU[choice]
        if action:
            action()

if __name__ == "__main__":
    main()
