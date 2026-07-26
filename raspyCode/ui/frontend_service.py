"""RaspyCodeApp: interfaccia full-screen basata su Textual."""
from __future__ import annotations

import asyncio
import contextlib
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from ..core.event_bus import EventBus
from ..core.events import (
    AssistantTokenEvent,
    ConnectionStatusEvent,
    Event,
    LLMToolCallEvent,
    ModelListEvent,
    ModelSelectedEvent,
    PiConfigEvent,
    StatusEvent,
    ToolResultEvent,
    UserMessageEvent,
)

USER_IDENTITY = "noya"

class SettingsScreen(ModalScreen[None]):
    """Impostazioni: routing (IP del Raspberry Pi) e scelta del modello."""

    # Correzione RUF012: tipizzazione esplicita ClassVar
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
                    "[yellow]Nessun modello disponibile — il Raspberry Pi non e' collegato "
                    "oppure non ha modelli installati.[/]",
                    id="no-models-label",
                )
            yield Label(
                "[dim]Invio su IP per confermare il routing · click su un modello "
                "per selezionarlo · Esc per chiudere[/dim]"
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "pi-ip-input" and event.value.strip():
            self.app.publish_from_ui(PiConfigEvent(pi_ip=event.value.strip()))  # type: ignore[attr-defined]

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        model_name = str(event.item.query_one(Label).renderable)
        self.app.publish_from_ui(ModelSelectedEvent(model=model_name))  # type: ignore[attr-defined]
        self.dismiss()

class RaspyCodeApp(App):
    """App full-screen: chat a tutto schermo + status bar + impostazioni."""

    CSS = """
    RichLog#chat-log {
        height: 1fr;
        border: round $accent;
        padding: 0 1;
    }
    #status-bar {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    #settings-box {
        width: 64;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    # Correzione RUF012: tipizzazione esplicita ClassVar
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("ctrl+s", "open_settings", "Impostazioni"),
        ("ctrl+q", "quit_app", "Esci"),
    ]

    hw_mode: reactive[str] = reactive("rilevamento...")
    pi_connected: reactive[bool] = reactive(False)
    current_model: reactive[str | None] = reactive(None)
    pi_ip: reactive[str] = reactive("10.42.0.2")
    available_models: reactive[list[str]] = reactive(list)

    def __init__(self, bus: EventBus, pi_ip: str, model: str | None) -> None:
        super().__init__()
        self._bus = bus
        self._queue = bus.subscribe()
        self.pi_ip = pi_ip
        self.current_model = model

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="chat-log", markup=True, wrap=True, highlight=True)
        yield Static(self._status_text(), id="status-bar")
        yield Input(placeholder=f"{USER_IDENTITY}> scrivi un messaggio...", id="chat-input")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "raspyCode"
        self.sub_title = USER_IDENTITY
        self.query_one("#chat-input", Input).focus()
        self.run_worker(self._consume_bus(), exclusive=False)

    def _status_text(self) -> str:
        pi_status = (
            "[green]Pi collegato[/]" if self.pi_connected else "[bold red]Pi non collegato[/]"
        )
        model_status = (
            f"[cyan]{self.current_model}[/]"
            if self.current_model
            else "[bold yellow]Nessun modello selezionato[/]"
        )
        return (
            f" HW: {self.hw_mode}  ·  {pi_status} ({self.pi_ip})  ·  "
            f"Modello: {model_status}  ·  Ctrl+S impostazioni  ·  Ctrl+Q esci"
        )

    def _refresh_status(self) -> None:
        # Correzione S110: contextlib.suppress al posto di try-except-pass
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
                        log.write(f"[bold green]raspyCode[/] {current_response}")
                    current_response = ""
            elif isinstance(event, LLMToolCallEvent):
                log.write(f"[yellow]tool_call[/] {event.tool_name} {event.arguments}")
            elif isinstance(event, ToolResultEvent):
                style = "red" if event.is_error else "green"
                log.write(f"[{style}]{event.tool_name}[/] {event.result_output}")
            elif isinstance(event, StatusEvent):
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
        self.query_one("#chat-log", RichLog).write(f"[bold cyan]{USER_IDENTITY}>[/] {text}")
        self.publish_from_ui(UserMessageEvent(sender_name=USER_IDENTITY, content=text))

    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen(self.pi_ip, self.current_model, self.available_models))

    def action_quit_app(self) -> None:
        self.exit()

    def publish_from_ui(self, event: Event) -> None:
        asyncio.get_running_loop().create_task(self._bus.publish(event))
