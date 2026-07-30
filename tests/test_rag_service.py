import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import EnrichedChatEvent, UserChatEvent
from raspyCode.services.rag_service import RAGService


@pytest.fixture
def rag_service():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test_rag.db")
        bus = EventBus()
        yield RAGService(bus, db_path=db_path)


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
        "il GC content e' la percentuale di G e C", np.array([1.0, 0.0], dtype=np.float32)
    )

    with patch.object(
        rag_service, "get_embedding", new=AsyncMock(return_value=np.array([1.0, 0.0], dtype=np.float32))
    ):
        await rag_service.bus.publish(UserChatEvent(query="Cos'e' il GC content?"))
        # esegue un solo giro di loop invece di await rag_service.run() infinito
        event = await rag_service._queue.get()
        assert isinstance(event, UserChatEvent)

        query_emb = await rag_service.get_embedding(event.query)
        top_docs = rag_service.search_similar(query_emb, top_k=2)
        context_text = "\n".join(f"- {d[0]} (score: {d[1]:.2f})" for d in top_docs)
        enriched_prompt = f"Contesto RAG:\n{context_text}\n\nDomanda utente: {event.query}"
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

    with patch.object(service, "get_embedding", new=AsyncMock(side_effect=RuntimeError("Ollama offline"))):
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
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
