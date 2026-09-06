"""RaspyCodeApp: interfaccia full-screen basata su Textual."""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import ClassVar

from rich.markdown import Markdown
from textual.app import App, ComposeResult
from textual.containers import Center, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from raspyCode.ui.banner import RASPY_BANNER

from ..core.event_bus import EventBus
from ..core.events import (
    AssistantTokenEvent,
    ConnectionStatusEvent,
    Event,
    FallbackModeEvent,
    LLMToolCallEvent,
    ModelListEvent,
    ModelSelectedEvent,
    PiConfigEvent,
    StatusEvent,
    ToolResultEvent,
    UserMessageEvent,
)

USER_IDENTITY = "noya"
WORKING_DIRECTORY = Path.cwd().resolve()

class SettingsScreen(ModalScreen[None]):
    """Impostazioni: routing (IP del Raspberry Pi) e scelta del modello."""

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [("escape", "dismiss", "Chiudi")]

    def __init__(self, current_pi_ip: str, current_model: str | None, models: list[str]) -> None:
        super().__init__()
        self._current_pi_ip = current_pi_ip
        self._current_model = current_model
        self._models = models

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Label("[bold]Impostazioni raspyCode[/]")
            yield Label("IP Raspberry Pi (routing verso Ollama):")
            yield Input(value=self._current_pi_ip, id="pi-ip-input")
            yield Label("Modello:")
            if self._models:
                yield ListView(
                    *[
                        ListItem(Label(m), classes="selected" if m == self._current_model else "")
                        for m in self._models
                    ],
                    id="model-list",
                )
            else:
                yield Label(
                    "[yellow]Nessun modello disponibile. Se il Raspberry Pi non e' raggiungibile, "
                    "raspyCode avvia automaticamente Ollama locale e aggiorna questa lista.[/]",
                    id="no-models-label",
                )
            yield Label(
                "[dim]↑/↓ per scegliere · Invio per confermare · Esc per chiudere[/dim]"
            )

    def on_mount(self) -> None:
        self.set_interval(0.5, self._refresh_model_list)
        self._refresh_model_list()

    def _refresh_model_list(self) -> None:
        """Aggiorna la lista anche se Ollama risponde dopo l'apertura della schermata."""
        app = self.app
        models = list(getattr(app, "available_models", []) or [])
        if models == self._models:
            return
        self._models = models
        with contextlib.suppress(Exception):
            old = self.query_one("#model-list", ListView)
            old.remove()
        with contextlib.suppress(Exception):
            no_models = self.query_one("#no-models-label", Label)
            no_models.remove()
        if not models:
            self.mount(Label("[yellow]Nessun modello disponibile. In attesa di Ollama...[/]", id="no-models-label"))
            return
        view = ListView(
            *[ListItem(Label(m)) for m in models],
            id="model-list",
        )
        self.mount(view)
        with contextlib.suppress(Exception):
            view.focus()
            if self._current_model in models:
                view.index = models.index(self._current_model)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "pi-ip-input" and event.value.strip():
            self.app.publish_from_ui(PiConfigEvent(pi_ip=event.value.strip()))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # ListView gestisce nativamente ↑/↓; Invio/click emette Selected.
        model_name = str(event.item.query_one(Label).render())
        self.app.publish_from_ui(ModelSelectedEvent(model=model_name))  # type: ignore[attr-defined]
        self.dismiss()

class RaspyCodeApp(App):
    """App full-screen: chat a tutto schermo + status bar + impostazioni."""

    CSS = """
    /* Centra l'intero layout verticalmente */
    Screen {
        align: center middle;
        scrollbar-size: 0 0;
        }

    #main-container {
        align: center middle;
        width: 100%;
        height: 1fr;
    }

    /* Container per centrare il blocco unico */
    #splash-container {
        width: 100%;
        height: auto;
        margin-bottom: 2;
        align: center middle;
    }

    /* Stile per il blocco ASCII unificato */
    #opencode-logo {
        width: auto;
        text-align: left; /* Mantiene la forma dell'ASCII */
        color: #888888; /* Grigio Opencode */
    }

    /* Barra di input centrale e ridotta */
    #chat-input {
        width: 60%;
        margin: 1 0; /* 1 riga verticale, 0 orizzontale */
        border: tall #444444;
        background: #1e1e1e;
    }

    /* Log della chat, inizialmente nascosto per lasciare spazio al banner */
    #chat-log {
        width: 80%;
        height: 1fr;
        display: none;
        margin-bottom: 1;
        background: transparent;
        scrollbar-size: 0 0;
    }

    /* Classe di utilità per mostrare il log dopo i 3 secondi */
    .visible {
        display: block !important;
    }
    """

    theme = "tokyo-night"

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("ctrl+s", "open_settings", "Impostazioni"),
        ("ctrl+q", "quit_app", "Esci"),
        ("ctrl+shift+c", "copy_last_response", "Copia risposta"),
    ]

    hw_mode: reactive[str] = reactive("rilevamento...")
    pi_connected: reactive[bool] = reactive(False)
    current_model: reactive[str | None] = reactive(None)
    pi_ip: reactive[str] = reactive("10.42.0.2")
    available_models: reactive[list[str]] = reactive(list)
    local_fallback: reactive[bool] = reactive(False)

    def __init__(self, bus: EventBus, pi_ip: str, model: str | None, initial_history: list[dict] | None = None) -> None:
        super().__init__()
        self._bus = bus
        self._queue = bus.subscribe()
        self.pi_ip = pi_ip
        self.current_model = model
        self._initial_history = initial_history or []
        # Cache usata dalla schermata impostazioni per confrontare gli aggiornamenti.
        # Deve esistere già al mount: Textual può chiamare _refresh_model_list
        # immediatamente, prima che arrivino i primi ModelListEvent.
        self._models: list[str] = []
        # Ultima risposta testuale completa del modello, usata da
        # Ctrl+Shift+C. Deve esistere fin dall'inizio: prima di questo fix
        # mancava del tutto e action_copy_last_response falliva con un
        # AttributeError silenziosamente inghiottito da contextlib.suppress,
        # quindi la scorciatoia sembrava "non fare nulla".
        self._last_response: str = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        # Container per centrare Logo combinato, Log e Input
        with Vertical(id="main-container"):
            # IL LOGO COMBINATO: un solo widget centrato
            with Center(id="splash-container"):
                yield Static(RASPY_BANNER, id="opencode-logo")

            yield RichLog(id="chat-log", markup=True, wrap=True, highlight=True)
            with Center():
                yield Input(placeholder=f"{USER_IDENTITY}> scrivi un messaggio...", id="chat-input")

        yield Static(self._status_text(), id="status-bar")
        # yield Footer()

    def on_mount(self) -> None:
        self.title = "raspyCode"
        self.sub_title = USER_IDENTITY
        self.query_one("#chat-input", Input).focus()
        self._show_initial_history()
        self.run_worker(self._consume_bus(), exclusive=False)


    def _show_initial_history(self) -> None:
        if not self._initial_history:
            return
        log = self.query_one("#chat-log", RichLog)
        for message in self._initial_history:
            role = message.get("role")
            content = message.get("content", "")
            if role == "user":
                log.write(f"[bold cyan]{USER_IDENTITY}>[/] {content}")
            elif role == "assistant" and content:
                log.write(Markdown(f"**raspyCode**\n\n{content}"))
        log.add_class("visible")
        with contextlib.suppress(Exception):
            self.query_one("#splash-container").display = False

    def transition_to_chat(self) -> None:
        # Nasconde il banner e mostra la chat
        with contextlib.suppress(Exception):
            self.query_one("#splash-container").display = False
            self.query_one("#chat-log").add_class("visible")

    def _status_text(self) -> str:
        if self.local_fallback:
            pi_status = "[bold yellow]Fallback locale (Ollama laptop)[/]"
        elif self.pi_connected:
            pi_status = "[green]Pi collegato[/]"
        else:
            pi_status = "[bold red]Pi non collegato[/]"
        model_status = (
            f"[cyan]{self.current_model}[/]"
            if self.current_model
            else "[bold yellow]Nessun modello selezionato[/]"
        )
        return (
            f" WD: [bold]{WORKING_DIRECTORY}[/]  ·  HW: {self.hw_mode}  ·  {pi_status} ({self.pi_ip})  ·  "
            f"Modello: {model_status}  ·  Ctrl+S impostazioni  ·  /save salva risposta  ·  Ctrl+Q esci"
        )

    def _render_created_file(self, result: str) -> Markdown | None:
        """Mostra subito in chat il file appena creato come blocco Markdown copiabile."""
        prefix = "File scritto: "
        if not result.startswith(prefix):
            return None
        relative = result[len(prefix):].split(" (", 1)[0].strip()
        if not relative:
            return None
        path = WORKING_DIRECTORY / relative
        try:
            path = path.resolve()
            path.relative_to(WORKING_DIRECTORY)
            if not path.is_file():
                return None
            content = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            return None
        language = {
            ".py": "python", ".pyw": "python", ".sh": "bash",
            ".bash": "bash", ".js": "javascript", ".ts": "typescript",
            ".json": "json", ".yaml": "yaml", ".yml": "yaml",
            ".md": "markdown", ".sql": "sql", ".txt": "text",
        }.get(path.suffix.lower(), "text")
        # I backtick nel contenuto non richiedono escaping: il fenced block
        # usa quattro backtick per restare copiabile anche con ``` interni.
        fence = "````"
        return Markdown(
            f"**Creato:** `{relative}`\n\n"
            f"{fence}{language}\n{content.rstrip()}\n{fence}"
        )

    def _refresh_status(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#status-bar", Static).update(self._status_text())

    def watch_pi_connected(self, _value: bool) -> None:
        self._refresh_status()

    def watch_current_model(self, _value: str | None) -> None:
        self._refresh_status()

    def watch_pi_ip(self, _value: str) -> None:
        self._refresh_status()

    def watch_hw_mode(self, _value: str) -> None:
        self._refresh_status()

    def watch_local_fallback(self, _value: bool) -> None:
        self._refresh_status()

    async def _consume_bus(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        current_response = ""
        while True:
            event = await self._queue.get()
            if isinstance(event, AssistantTokenEvent):
                if event.content:
                    current_response += event.content
                if event.done:
                    if current_response:
                        self._last_response = current_response
                        log.write(Markdown(f"**raspyCode**\n\n{current_response}"))
                    current_response = ""
            elif isinstance(event, LLMToolCallEvent):
                log.write(f"[yellow]tool_call[/] {event.tool_name} {event.arguments}")
            elif isinstance(event, ToolResultEvent):
                if event.tool_name == "file_write" and not event.is_error:
                    rendered = self._render_created_file(event.result_output)
                    if rendered is not None:
                        log.write(rendered)
                    else:
                        log.write(Markdown(f"**file_write**\n\n{event.result_output}"))
                else:
                    style = "red" if event.is_error else "green"
                    log.write(f"[{style}]{event.tool_name}[/] {event.result_output}")
            elif isinstance(event, StatusEvent):
                # Nessun filtro necessario: gestiamo tutti gli StatusEvent (es. SYSTEM BOOT COMPLETED)
                color = {"info": "dim", "warning": "yellow", "error": "bold red"}.get(
                    event.level, "dim"
                )
                log.write(f"[{color}]{event.text}[/{color}]")
            elif isinstance(event, ConnectionStatusEvent):
                self.pi_connected = event.connected
            elif isinstance(event, ModelListEvent):
                self.available_models = event.models
            elif isinstance(event, ModelSelectedEvent):
                self.current_model = event.model
            elif isinstance(event, PiConfigEvent):
                self.pi_ip = event.pi_ip
            elif isinstance(event, FallbackModeEvent):
                self.local_fallback = event.active

            self._queue.task_done()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "chat-input":
            return
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text in {"/quit", "/exit"}:
            self.action_quit_app()
            return
        if text.lower() in {"/copy", "/copia"}:
            self.action_copy_last_response()
            return
        if text.lower() in {"/save", "/salva"}:
            self.action_save_last_response()
            return

        # 1. FORZIAMO LA SCOMPARSA DEL BANNER E LA COMPARSA DEL LOG
        try:
            splash = self.query_one("#splash-container")
            splash.display = False
        except Exception:
            pass

        log = self.query_one("#chat-log", RichLog)
        log.add_class("visible")
        log.refresh() # Forza il redraw immediato del widget

        # 2. CONTROLLO MODELLO
        if not self.current_model:
            log.write("[bold red]Errore:[/] Nessun modello selezionato. Premi [cyan]Ctrl+S[/] per aprire le impostazioni e sceglierne uno.")
            return

        # 3. INVIO MESSAGGIO NORMALE
        log.write(f"[bold cyan]{USER_IDENTITY}>[/] {text}")
        self.publish_from_ui(UserMessageEvent(sender_name=USER_IDENTITY, content=text))

    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen(self.pi_ip, self.current_model, self.available_models))

    def action_copy_last_response(self) -> None:
        """Copia l'ultima risposta negli appunti via OSC52 (Ctrl+Shift+C o
        comando /copy). Molti terminali (kitty, foot, alacritty, ecc. - tipici
        su setup Wayland come niri) intercettano Ctrl+Shift+C a livello di
        emulatore per la propria funzione 'copia selezione' e non lo inoltrano
        mai all'applicazione: in quel caso questa action non viene proprio
        chiamata, ed e' per questo che il tasto puo' sembrare "non fare
        nulla" anche dopo aver risolto il bug di inizializzazione. Il comando
        testuale /copy scritto nella barra di input bypassa il problema
        perche' non dipende da nessuna scorciatoia di tastiera. Se anche
        cosi' il clipboard non funziona (terminale senza supporto OSC52,
        sessione remota senza passthrough), usare /save per scrivere la
        risposta su file invece che negli appunti."""
        log = self.query_one("#chat-log", RichLog)
        if not self._last_response:
            log.write("[yellow]Nessuna risposta da copiare ancora.[/]")
            return
        try:
            self.copy_to_clipboard(self._last_response)
            log.write(
                "[green]Risposta copiata negli appunti.[/] Se non compare da "
                "nessuna parte incollandola, il terminale probabilmente non "
                "supporta OSC52: usa [cyan]/save[/] per scriverla su file."
            )
        except Exception as exc:
            # Prima non veniva mai segnalato un fallimento (contextlib.suppress
            # ingoiava tutto): il tasto sembrava "non fare nulla" quando il
            # terminale non supporta OSC52 o il clipboard non è disponibile.
            log.write(
                f"[bold red]Copia negli appunti non riuscita ({exc}).[/] "
                "Usa [cyan]/save[/] per scrivere la risposta su file invece."
            )

    def action_save_last_response(self) -> None:
        """Scrive l'ultima risposta su file nel workspace invece che negli
        appunti: a differenza del clipboard (OSC52, spesso non supportato o
        intercettato dal terminale) scrivere su disco funziona sempre,
        indipendentemente da emulatore di terminale o sessione remota."""
        log = self.query_one("#chat-log", RichLog)
        if not self._last_response:
            log.write("[yellow]Nessuna risposta da salvare ancora.[/]")
            return
        path = WORKING_DIRECTORY / "ultima_risposta.txt"
        try:
            path.write_text(self._last_response, encoding="utf-8")
        except OSError as exc:
            log.write(f"[bold red]Impossibile scrivere {path}: {exc}[/]")
            return
        log.write(f"[green]Risposta salvata in:[/] {path}")

    def action_quit_app(self) -> None:
        self.exit()

    def publish_from_ui(self, event: Event) -> None:
        asyncio.get_running_loop().create_task(self._bus.publish(event))
