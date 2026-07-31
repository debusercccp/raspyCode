import sqlite3
from typing import List, Tuple

import httpx
import numpy as np

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import EnrichedChatEvent


class RAGService:
    """
    Microservizio per Retrieval-Augmented Generation (RAG) su SQLite.
    Genera embedding via Ollama (nomic-embed-text) e arricchisce il contesto
    degli eventi diretti all'LLM.
    """

    def __init__(
        self,
        bus: EventBus,
        db_path: str = "raspycode_rag.db",
        ollama_host: str = "http://10.42.0.2:11434",
    ):
        self.bus = bus
        self.db_path = db_path
        self.ollama_host = ollama_host
        self.model_name = "nomic-embed-text"
        self._queue = self.bus.subscribe()
        self._init_db()

    def _init_db(self):
        """Inizializza la tabella SQLite per i chunk e gli embedding."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL
                )
            """)
            conn.commit()

    async def get_embedding(self, text: str) -> np.ndarray:
        """Chiama l'API di Ollama per ottenere il vettore di embedding."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.ollama_host}/api/embeddings",
                json={"model": self.model_name, "prompt": text},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            return np.array(data["embedding"], dtype=np.float32)

    def insert_document(self, content: str, embedding: np.ndarray):
        """Salva un documento e il suo embedding quantizzato come BLOB in SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO documents (content, embedding) VALUES (?, ?)",
                (content, embedding.tobytes()),
            )
            conn.commit()

    def search_similar(
        self, query_emb: np.ndarray, top_k: int = 3
    ) -> List[Tuple[str, float]]:
        """
        Calcola la similarità del coseno tra la query e i documenti in SQLite.
        Utilizza numpy per efficienza su ARM64 senza richiedere estensioni esterne complesse.
        """
        results = []
        query_norm = np.linalg.norm(query_emb)
        if query_norm == 0:
            return results

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content, embedding FROM documents")
            for content, emb_blob in cursor.fetchall():
                doc_emb = np.frombuffer(emb_blob, dtype=np.float32)
                doc_norm = np.linalg.norm(doc_emb)
                if doc_norm > 0:
                    sim = np.dot(query_emb, doc_emb) / (query_norm * doc_norm)
                    results.append((content, float(sim)))

        # Ordina per score di similarità decrescente e restituisce i primi K
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def run(self):
        """Loop principale: intercetta le chat e inietta il contesto RAG nel bus."""
        while True:
            event = await self._queue.get()
            if hasattr(event, "query"):
                try:
                    query_emb = await self.get_embedding(event.query)
                    top_docs = self.search_similar(query_emb, top_k=2)

                    context_text = "\n".join(
                        [f"- {doc[0]} (score: {doc[1]:.2f})" for doc in top_docs]
                    )

                    # Pubblica un nuovo evento arricchito per LLMGatewayService
                    enriched_prompt = f"Contesto RAG:\n{context_text}\n\nDomanda utente: {event.query}"
                    await self.bus.publish(EnrichedChatEvent(prompt=enriched_prompt))
                except Exception:
                    # Fallback elegante in caso di errore (es. Ollama offline o DB vuoto)
                    await self.bus.publish(EnrichedChatEvent(prompt=event.query))
            self._queue.task_done()
