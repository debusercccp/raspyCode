"""Eventi che transitano sull'EventBus di raspyCode.

Ogni microservizio pubblica/consuma un sottoinsieme di questi tipi.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    """Base per tutti gli eventi del bus."""


@dataclass
class UserMessageEvent(Event):
    sender_name: str
    content: str


@dataclass
class AssistantTokenEvent(Event):
    """Chunk di streaming testuale dal modello. done=True marca fine risposta."""

    content: str
    done: bool = False


@dataclass
class LLMToolCallEvent(Event):
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass
class ToolResultEvent(Event):
    call_id: str
    tool_name: str
    result_output: str
    is_error: bool = False


@dataclass
class StatusEvent(Event):
    """Stato di sistema, consumato dalla TUI."""

    text: str
    level: str = "info"  # info | warning | error


@dataclass
class ConnectionStatusEvent(Event):
    """Esito dell'ultimo healthcheck verso Ollama sul Raspberry Pi."""

    connected: bool
    detail: str = ""


@dataclass
class ModelListEvent(Event):
    """Modelli disponibili sul Pi, letti da /api/tags durante l'healthcheck."""

    models: list[str] = field(default_factory=list)


@dataclass
class ModelSelectedEvent(Event):
    """L'utente ha scelto un modello dalle impostazioni."""

    model: str


@dataclass
class PiConfigEvent(Event):
    """L'utente ha cambiato l'IP del Raspberry Pi dalle impostazioni (routing)."""

    pi_ip: str


@dataclass
class UserChatEvent(Event):
    """Domanda utente grezza, in ingresso a RAGService per l'arricchimento."""

    query: str


@dataclass
class EnrichedChatEvent(Event):
    """Prompt arricchito col contesto RAG, prodotto da RAGService per il gateway LLM."""

    prompt: str


@dataclass
class SystemStatsEvent(Event):
    """Statistiche hardware periodiche del nodo (Pi o laptop)."""

    cpu_load_1min: float
    cpu_temp_c: float | None
    mem_used_mb: float
    mem_total_mb: float


@dataclass
class ClearHistoryEvent:
    """Richiede il reset immediato della cronologia di chat nel gateway e nella UI."""

    pass


@dataclass
class BackendSourceEvent(Event):
    """Segnala quale host Ollama sta effettivamente rispondendo alle
    richieste (Raspberry Pi o fallback locale), pubblicato da
    ConnectivityService dopo ogni healthcheck riuscito."""
    host: str
    is_local: bool = False
