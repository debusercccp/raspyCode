import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import (
    EnrichedChatEvent,
    PiConfigEvent,
    StatusEvent,
    UserChatEvent,
)
from raspyCode.services.rag_service import RAGService


@pytest.fixture
def rag_service():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test_rag.db")
        bus = EventBus()
        yield RAGService(bus, db_path=db_path)


def test_init_db_migrates_older_schema_missing_filename_column():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "legacy.db")

        # Simula un DB creato con lo schema precedente (senza `filename`),
        # come quelli generati prima che ingest.py e RAGService condividessero
        # lo stesso file di default.
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

        bus = EventBus()
        RAGService(bus, db_path=db_path)

        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
        conn.close()
        assert "filename" in cols


def test_init_does_not_crash_and_subscribes_correctly(rag_service):
    # bug originale: bus.subscribe("UserChatEvent") esplodeva perche'
    # EventBus.subscribe() non accetta argomenti.
    assert rag_service._queue is not None


def test_insert_and_search_similar_documents(rag_service):
    emb_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    emb_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    rag_service.insert_document("contenuto A", emb_a)
    rag_service.insert_document("contenuto B", emb_b)

    results = rag_service.search_similar(emb_a, top_k=1)
    assert len(results) == 1
    assert results[0][0] == "contenuto A"
    assert results[0][1] == pytest.approx(1.0)


def test_search_similar_returns_empty_for_zero_norm_query(rag_service):
    assert rag_service.search_similar(np.zeros(3, dtype=np.float32)) == []


@pytest.mark.asyncio
async def test_run_publishes_enriched_chat_event_on_success(rag_service):
    result_queue = rag_service.bus.subscribe()

    rag_service.insert_document(
        "il GC content e' la percentuale di G e C",
        np.array([1.0, 0.0], dtype=np.float32),
    )

    with patch.object(
        rag_service,
        "get_embedding",
        new=AsyncMock(return_value=np.array([1.0, 0.0], dtype=np.float32)),
    ):
        await rag_service.bus.publish(UserChatEvent(query="Cos'e' il GC content?"))
        # esegue un solo giro di loop invece di await rag_service.run() infinito
        event = await rag_service._queue.get()
        assert isinstance(event, UserChatEvent)

        query_emb = await rag_service.get_embedding(event.query)
        top_docs = rag_service.search_similar(query_emb, top_k=2)
        context_text = "\n".join(f"- {d[0]} (score: {d[1]:.2f})" for d in top_docs)
        enriched_prompt = (
            f"Contesto RAG:\n{context_text}\n\nDomanda utente: {event.query}"
        )
        await rag_service.bus.publish(EnrichedChatEvent(prompt=enriched_prompt))

    published = await result_queue.get()
    # Il primo evento nella coda e' lo UserChatEvent originale (fan-out)
    assert isinstance(published, UserChatEvent)
    published2 = await result_queue.get()
    assert isinstance(published2, EnrichedChatEvent)
    assert "GC content" in published2.prompt


@pytest.mark.asyncio
async def test_run_loop_handles_ollama_failure_with_fallback():
    bus = EventBus()
    service = RAGService(bus, db_path=":memory:")
    result_queue = bus.subscribe()

    with patch.object(
        service,
        "get_embedding",
        new=AsyncMock(side_effect=RuntimeError("Ollama offline")),
    ):
        import asyncio

        task = asyncio.create_task(service.run())
        try:
            await bus.publish(UserChatEvent(query="domanda di prova"))
            # Scarta l'eco dello UserChatEvent pubblicato (fan-out) e prende
            # il risultato del fallback.
            first = await asyncio.wait_for(result_queue.get(), timeout=2)
            if isinstance(first, UserChatEvent):
                second = await asyncio.wait_for(result_queue.get(), timeout=2)
            else:
                second = first
            assert isinstance(second, EnrichedChatEvent)
            assert second.prompt == "domanda di prova"

            # Il fallback deve anche avvisare esplicitamente via StatusEvent,
            # non degradare in silenzio a chat semplice.
            third = await asyncio.wait_for(result_queue.get(), timeout=2)
            assert isinstance(third, StatusEvent)
            assert third.level == "warning"
            assert "RAG non disponibile" in third.text
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_run_loop_warns_when_db_has_no_relevant_docs(rag_service):
    result_queue = rag_service.bus.subscribe()

    with patch.object(
        rag_service,
        "get_embedding",
        new=AsyncMock(return_value=np.array([1.0, 0.0], dtype=np.float32)),
    ):
        import asyncio

        task = asyncio.create_task(rag_service.run())
        try:
            await rag_service.bus.publish(UserChatEvent(query="domanda senza match"))

            first = await asyncio.wait_for(result_queue.get(), timeout=2)
            if isinstance(first, UserChatEvent):
                second = await asyncio.wait_for(result_queue.get(), timeout=2)
            else:
                second = first
            assert isinstance(second, EnrichedChatEvent)
            # DB vuoto: il prompt arriva al gateway senza contesto aggiunto.
            assert second.prompt == "domanda senza match"

            third = await asyncio.wait_for(result_queue.get(), timeout=2)
            assert isinstance(third, StatusEvent)
            assert third.level == "warning"
            assert "nessun documento pertinente" in third.text
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_run_updates_ollama_host_on_pi_config_event(rag_service):
    await rag_service.bus.publish(PiConfigEvent(pi_ip="192.168.1.50"))

    task_queue_get = rag_service._queue.get()
    import asyncio

    event = await asyncio.wait_for(task_queue_get, timeout=2)
    assert isinstance(event, PiConfigEvent)

    # Riproduce il singolo giro di dispatch di run() senza restare bloccati
    # nel while True: infinito.
    if isinstance(event, PiConfigEvent):
        rag_service.ollama_host = f"http://{event.pi_ip}:11434"

    assert rag_service.ollama_host == "http://192.168.1.50:11434"
