"""Ingestione RAG per raspyCode.

Questo script va eseguito sul laptop, cioe' sulla stessa macchina che ospita
RAGService e il database SQLite. Gli embedding vengono generati dal Raspberry
Pi tramite Ollama sulla rete Ethernet dedicata.

Architettura intenzionale:
  laptop (questo script) -> HTTP -> Pi/Ollama
  laptop (questo script) -> SQLite -> ~/.raspycode/raspycode_rag.db

Non esiste una copia del DB sul Pi e non serve alcuna sincronizzazione via
SSH/SCP. L'ingestion costruisce un DB temporaneo nella stessa directory del
DB finale e lo sostituisce atomicamente solo quando tutti i file sono stati
processati. In questo modo un errore di rete o di Ollama non lascia il DB
attivo in uno stato parzialmente ricostruito.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import httpx
import numpy as np
import pymupdf

DB_PATH = Path(
    os.path.expanduser(
        os.environ.get(
            "RASPY_RAG_DB", str(Path.home() / ".raspycode" / "raspycode_rag.db")
        )
    )
)
OLLAMA_URL = os.environ.get("RASPY_OLLAMA_URL", "http://10.42.0.2:11434/api/embeddings")
EMBEDDING_MODEL = os.environ.get("RASPY_EMBEDDING_MODEL", "nomic-embed-text")
DOCS_DIR = Path(os.environ.get("RASPY_DOCS_DIR", "docs_rag"))
CHUNK_SIZE = 1000  # Caratteri circa per frammento
REQUEST_TIMEOUT = float(os.environ.get("RASPY_EMBEDDING_TIMEOUT", "120"))


def init_db(db_path: Path) -> sqlite3.Connection:
    """Crea lo schema del DB di destinazione e restituisce la connessione."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            content TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def get_embedding(text: str) -> np.ndarray:
    """Richiede a Ollama sul Pi l'embedding del testo."""
    response = httpx.post(
        OLLAMA_URL,
        json={"model": EMBEDDING_MODEL, "prompt": text},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return np.array(response.json()["embedding"], dtype=np.float32)


def extract_text(filepath: Path) -> str:
    """Estrae il testo in modo resiliente; i file illeggibili vengono saltati."""
    if filepath.suffix.lower() == ".pdf":
        text_content = []
        try:
            with pymupdf.open(filepath) as doc:
                for page in doc:
                    text_content.append(page.get_text("text"))
            return "\n".join(text_content)
        except Exception as exc:
            print(f"      [!] PyMuPDF ha fallito su {filepath.name}: {exc}")
            return ""

    try:
        return filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return filepath.read_text(encoding="latin-1")
        except Exception as exc:
            print(f"      [!] Impossibile leggere {filepath.name}: {exc}")
            return ""
    except Exception as exc:
        print(f"      [!] Impossibile leggere {filepath.name}: {exc}")
        return ""


def chunk_text(text: str, chunk_size: int) -> list[str]:
    """Divide il testo in chunk basati sulla lunghezza approssimativa."""
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0

    for word in words:
        current_chunk.append(word)
        current_length += len(word) + 1
        if current_length >= chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_length = 0

    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks


def ingest() -> int:
    """Costruisce un nuovo DB RAG e lo pubblica atomicamente.

    Restituisce il numero di chunk inseriti. Se l'ingestion fallisce, il DB
    esistente non viene toccato.
    """
    if not DOCS_DIR.exists():
        raise FileNotFoundError(f"Cartella {DOCS_DIR} non trovata.")

    files = sorted(path for path in DOCS_DIR.glob("*") if path.is_file())
    if not files:
        raise RuntimeError(f"Nessun file da processare in {DOCS_DIR}.")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    conn: sqlite3.Connection | None = None
    inserted_chunks = 0

    try:
        # Il file temporaneo vive nella stessa directory del DB finale:
        # os.replace() resta quindi atomico anche su filesystem normali.
        with tempfile.NamedTemporaryFile(
            prefix=f".{DB_PATH.stem}.",
            suffix=".tmp",
            dir=DB_PATH.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

        conn = init_db(temp_path)
        cursor = conn.cursor()

        print(f"[*] Ollama embedding: {OLLAMA_URL}")
        print(f"[*] Modello: {EMBEDDING_MODEL}")
        print(f"[*] DB finale: {DB_PATH}")
        print(f"[*] Trovati {len(files)} file da processare in {DOCS_DIR}...")

        for filepath in files:
            print(f"\n[*] Elaborazione: {filepath.name}")
            full_text = extract_text(filepath).strip()

            if not full_text:
                print("    -> Saltato (vuoto o illeggibile)")
                continue

            chunks = chunk_text(full_text, CHUNK_SIZE)
            print(f"    -> Diviso in {len(chunks)} chunk. Generazione embedding...")

            for i, chunk in enumerate(chunks):
                vector = get_embedding(chunk)
                cursor.execute(
                    "INSERT INTO documents (filename, content, embedding) VALUES (?, ?, ?)",
                    (f"{filepath.name} (Part {i + 1})", chunk, vector.tobytes()),
                )
                inserted_chunks += 1
                print(f"      - Chunk {i + 1}/{len(chunks)} salvato.")

            conn.commit()

        # Assicura che il file sia completamente scritto prima della sostituzione.
        conn.commit()
        conn.close()
        conn = None

        os.replace(temp_path, DB_PATH)
        temp_path = None
        print(
            f"\n[OK] Database RAG aggiornato atomicamente: {DB_PATH} "
            f"({inserted_chunks} chunk)."
        )
        return inserted_chunks

    except Exception:
        if conn is not None:
            conn.rollback()
            conn.close()
        raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main() -> None:
    try:
        ingest()
    except Exception as exc:
        print(f"\n[ERRORE] Ingestion fallita: {exc}")
        print("[INFO] Il database RAG precedente non e' stato modificato.")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
