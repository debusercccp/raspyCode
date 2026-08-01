import os
import sqlite3
from pathlib import Path
from typing import List, Tuple

import httpx
import numpy as np

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import EnrichedChatEvent, PiConfigEvent, StatusEvent

# Percorso di default FISSO (non relativo alla cwd del processo). RAGService
# e ingest.py in precedenza usavano entrambi "raspycode_rag.db" relativo:
# se il servizio viene avviato da una cwd diversa da quella in cui e' stato
# lanciato ingest.py (es. via pipx, o da $HOME invece che dalla repo),
# ciascuno crea/legge un file *diverso*, e il DB popolato non viene mai
# trovato dal servizio in esecuzione. Override possibile con la variabile
# d'ambiente RASPY_RAG_DB per chi vuole comunque un percorso custom (es. la
# cartella della repo, per chi ha gia' popolato il DB li').
DEFAULT_RAG_DB_PATH = os.path.expanduser(
    os.environ.get("RASPY_RAG_DB", str(Path.home() / ".raspycode" / "raspycode_rag.db"))
)


class RAGService:
    """
    Microservizio per Retrieval-Augmented Generation (RAG) su SQLite.
    Genera embedding via Ollama (nomic-embed-text) e arricchisce il contesto
    degli eventi diretti all'LLM.
    """

    def __init__(
        self,
        bus: EventBus,
        db_path: str | None = None,
        ollama_host: str = "http://10.42.0.2:11434",
    ):
        self.bus = bus
        self.db_path = db_path or DEFAULT_RAG_DB_PATH
        self.ollama_host = ollama_host
        self.model_name = "nomic-embed-text"
        self._queue = self.bus.subscribe()
        self._init_db()

    def _init_db(self):
        """Inizializza la tabella SQLite per i chunk e gli embedding.

        Schema allineato a quello usato da ingest.py (colonna `filename`
        inclusa) dato che entrambi puntano ora allo stesso file di default:
        se questo servizio parte prima di un qualunque ingest, la tabella
        deve gia' avere la colonna che ingest.py si aspetta di poter
        popolare, altrimenti l'INSERT di ingest.py fallirebbe con
        'no such column: filename'.
        """
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL
                )
            """)
            # Migrazione per DB creati con lo schema precedente (senza
            # `filename`), cosi' i database gia' esistenti non si rompono.
            cursor.execute("PRAGMA table_info(documents)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            if "filename" not in existing_cols:
                cursor.execute("ALTER TABLE documents ADD COLUMN filename TEXT")
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
            if isinstance(event, PiConfigEvent):
                self.ollama_host = f"http://{event.pi_ip}:11434"
            elif hasattr(event, "query"):
                await self._handle_query(event.query)
            self._queue.task_done()

    async def _handle_query(self, query: str) -> None:
        try:
            query_emb = await self.get_embedding(query)
            top_docs = self.search_similar(query_emb, top_k=2)

            if not top_docs:
                # Embedding riuscito ma il DB e' vuoto o senza match utili:
                # non e' un errore, ma l'utente deve sapere che il prompt
                # e' passato al modello senza alcun contesto aggiuntivo.
                await self.bus.publish(EnrichedChatEvent(prompt=query))
                await self.bus.publish(
                    StatusEvent(
                        text="RAG: nessun documento pertinente nel DB, "
                        "domanda inviata senza contesto aggiuntivo.",
                        level="warning",
                    )
                )
                return

            context_text = "\n".join(
                [f"- {doc[0]} (score: {doc[1]:.2f})" for doc in top_docs]
            )
            enriched_prompt = (
                f"Contesto RAG:\n{context_text}\n\nDomanda utente: {query}"
            )
            await self.bus.publish(EnrichedChatEvent(prompt=enriched_prompt))
            await self.bus.publish(
                StatusEvent(
                    text=f"RAG: {len(top_docs)} chunk pertinenti trovati e "
                    "iniettati nel contesto.",
                    level="info",
                )
            )
        except Exception as exc:
            # Fallback elegante in caso di errore (es. Ollama offline o DB
            # vuoto): il prompt originale arriva comunque al gateway, ma
            # ora lo segnaliamo esplicitamente invece di degradare in
            # silenzio a chat semplice senza che l'utente lo sappia.
            await self.bus.publish(EnrichedChatEvent(prompt=query))
            await self.bus.publish(
                StatusEvent(
                    text=f"RAG non disponibile ({exc}): domanda inviata "
                    "senza contesto.",
                    level="warning",
                )
            )
