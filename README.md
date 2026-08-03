# raspyCode

Agente locale a microservizi (asyncio + event bus) per bioinformatica, con
frontend TUI full-screen in `Textual` e tool-calling verso `bioCli/`. Il
display TFT del Raspberry Pi non è pilotato da raspyCode: mostra `htop` in
continuo tramite un servizio systemd indipendente (vedi sotto).

## Architettura

```text
Laptop (10.42.0.1) ───eth0 cablato───▶ Raspberry Pi 5 (10.42.0.2:11434, Ollama)

```

Il pacchetto è organizzato a microservizi (Domain-Driven), tutti collegati a un unico
`EventBus` fan-out (ogni servizio riceve una copia di ogni evento e filtra per tipo):

| Servizio | Modello | Ruolo |
| --- | --- | --- |
| `RaspyCodeApp` | `ui/frontend_service.py` | TUI `Textual` full-screen: input utente, log, status bar e UI impostazioni |
| `LLMGatewayService` | `services/llm_gateway_service.py` | Client Ollama (`/api/chat`, streaming + tool-calling) |
| `ToolExecutorService` | `services/tool_executor_service.py` | Esegue i tool tramite il `ToolRegistry` condiviso (`tools/`), gestendo timeout e pubblicazione risultati |
| `ConnectivityService` | `services/connectivity_service.py` | Healthcheck periodico verso Ollama (`/api/tags`) e fetch modelli disponibili |
| `HardwareDetectionService` | `services/hardware.py` | Rileva ROCm / CUDA / CPU-only all'avvio |
| `EventBus` | `core/event_bus.py` | Bus pub/sub asyncio, sottoscrizione tipizzata opzionale, backpressure via code con maxsize |
| `ToolRegistry` | `tools/registry.py` | Unica fonte di verita' sui tool disponibili: schema Ollama, esecuzione ed esposizione MCP derivano tutte da qui |

## Struttura cartelle

```text
.
├── pyproject.toml              <- Configurazione di packaging (usata anche da pipx)
├── README.md
├── requirements.txt
├── cleanCache.sh
└── raspyCode/                  <- Pacchetto Python effettivo
    ├── __init__.py
    ├── main.py                 <- Entry point (start())
    ├── mcp_server.py           <- Server MCP, generato dal ToolRegistry condiviso
    ├── core/                   <- Infrastruttura eventi
    │   ├── event_bus.py
    │   └── events.py
    ├── services/               <- Microservizi backend
    │   ├── connectivity_service.py
    │   ├── hardware.py
    │   ├── llm_gateway_service.py
    │   ├── rag_service.py
    │   └── tool_executor_service.py
    ├── tools/                  <- Tool Registry: unica fonte di verita' su nome/schema/handler
    │   ├── __init__.py         <- build_default_registry()
    │   ├── registry.py         <- ToolDefinition, ToolRegistry
    │   ├── bio.py              <- Wrapper dei tool biotoolkit_* su bioCli/
    │   └── system.py           <- system_run_cmd: allow-list, validazione path, timeout+kill
    ├── ui/                     <- Interfaccia utente Textual
    │   └── frontend_service.py
    └── bioCli/                 <- Funzioni pure di bioinformatica, importate in-process
        ├── __init__.py         <- Espone tutte le funzioni (gc_content, rev_comp, ...)
        ├── sequence.py
        ├── assembly.py
        ├── search.py
        ├── io_utils.py
        └── synthesis.py

```

`bioCli/` e' un sottopacchetto vero e proprio di funzioni pure. Il
`ToolRegistry` (`tools/`) e' l'unica fonte di verita' su quali tool esistono,
come sono descritti al modello e come vengono eseguiti: prima del refactor,
`LLMGatewayService` e `ToolExecutorService` mantenevano due elenchi separati
tenuti allineati manualmente (con il rischio di dichiarare al modello un
tool che l'Executor non sapeva eseguire, o viceversa); ora entrambi — e
anche `mcp_server.py` — derivano dallo stesso `ToolRegistry`. L'unico tool
eseguito come processo esterno resta `system_run_cmd`, limitato
all'allow-list descritta più sotto.

## Requisiti e Installazione

* Python 3.11+ (testato su 3.13)
* Ollama in esecuzione sul Raspberry Pi, raggiungibile su `10.42.0.2:11434` (modificabile a runtime da UI)
* Solo sul Raspberry Pi con TFT collegato: `Pillow` e `numpy` (installabili tramite extra `[tft]`), utente nei gruppi `spi,gpio,video`
* [`pipx`](https://pipx.pypa.io/) per l'installazione system-wide (consigliato — vedi sotto)

### Installazione con pipx (consigliata)

`pipx` installa `raspycode` in un venv isolato e dedicato, ma espone il comando
`raspycode` globalmente sul `PATH`: niente più `source .venv/bin/activate`
prima di ogni avvio.

```bash
# dalla root del repo (dove sta pyproject.toml)
pipx install .

# variante Raspberry Pi con TFT collegato (dipendenze Pillow/numpy incluse)
pipx install ".[tft]"
```

Se `pipx` non è ancora sul `PATH` della shell:

```bash
pipx ensurepath
# poi riapri il terminale (o: source ~/.bashrc / ~/.zshrc)
```

Da qui in poi, da **qualsiasi directory** e senza attivare nulla:

```bash
raspycode
```

**Aggiornare dopo un `git pull`:**

```bash
pipx install --force .
```

**Disinstallare:**

```bash
pipx uninstall raspyCode
```

**Modalità sviluppo** (il comando `raspycode` punta ai file sorgente, le modifiche
sono effettive subito senza reinstallare):

```bash
pipx install --editable .
```

### Alternativa: venv manuale

Se preferisci non usare pipx (es. per un ambiente di sviluppo con altri tool):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# oppure, sul Raspberry Pi:
pip install -e ".[tft]"
```

## Esecuzione

Comandi principali da dentro la TUI:

* **`Ctrl+S`**: Apre il pannello impostazioni per instradare l'IP e selezionare il modello rilevato.
* **`Ctrl+Q`** (o `/quit`, `/exit`): Termina in modo pulito tutti i servizi ed esce.

### Variabili d'ambiente

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `RASPY_PI_IP` | `10.42.0.2` | IP di default per il routing verso Ollama (sovrascrivibile da UI) |
| `RASPY_MODEL` | `None` | Modello di avvio (se assente, la TUI ti inviterà a selezionarlo con `Ctrl+S`) |

Con `pipx`, le variabili d'ambiente si passano normalmente prima del comando:

```bash
RASPY_PI_IP=10.42.0.2 RASPY_MODEL=qwen3:4b raspycode
```

## Tool disponibili al modello

Ogni tool e' definito una sola volta in `tools/` (vedi `ToolRegistry`) e da
li' derivano sia lo schema inviato a Ollama sia l'esecuzione lato
`ToolExecutorService` sia, per un sottoinsieme, l'esposizione via
`mcp_server.py`. La maggior parte delle funzioni di `bioCli/` e' esposta
come tool `biotoolkit_<nome>` (es. `biotoolkit_gc_content`,
`biotoolkit_rev_comp`, `biotoolkit_dna_to_rna`, `biotoolkit_protein_stretch_finder`,
`biotoolkit_greedy_kmer_assembly`, `biotoolkit_fasta_sampler`, ...). Alcuni
nomi si discostano deliberatamente da quelli originali di `bioCli/` per
essere onesti sulla semantica effettiva (es. `protein_stretch_finder` non
e' un vero ORF finder su DNA/RNA, `greedy_kmer_assembly` non e' un
assembler genomico accurato) — vedi i docstring in `bioCli/` per i dettagli.

In più:

* `biotoolkit_run_genetic_sim`: simulazione genetica con seed random isolato
per chiamata (istanziato dentro l'handler, mai a livello di modulo).
* `system_run_cmd`: esecuzione di comandi di sistema, limitata su due assi
  indipendenti:
  - **quale programma**: allow-list (`ls, cat, df, free, uname, whoami, pwd,
    head, tail, wc`) in `tools.system.SYSTEM_CMD_ALLOWLIST`. Estendere
    solo con binari read-only.
  - **quali dati**: qualunque argomento non-flag (es. il file passato a `cat`)
    deve risolvere dentro la directory di lavoro corrente
    (`tools.system.SYSTEM_CMD_ALLOWED_ROOT`), altrimenti viene rifiutato —
    l'allow-list da sola protegge il binario ma non impedirebbe
    `cat ~/.ssh/id_rsa` o `cat /etc/shadow`. Output limitato a
    `MAX_OUTPUT_BYTES` (64KB) e timeout di `SYSTEM_CMD_TIMEOUT_SECONDS`
    (15s, kill effettivo del processo allo scadere).
  Dare shell libera a un LLM resta un vettore di rischio anche in un agente
  locale: questi limiti riducono ma non eliminano la superficie d'attacco.
  **Non e' esposto via MCP** (vedi `mcp_server.py`): un client MCP esterno
  non deve poter eseguire comandi di sistema sulla macchina che ospita
  raspyCode.

## Note su RAG (SQLite) e ingestion dal laptop

`RAGService` legge un DB **SQLite locale** sulla macchina che esegue raspyCode.
Il database non e' un servizio di rete: deve quindi esistere fisicamente sul
laptop, dove gira la TUI e dove viene eseguito `RAGService`.

Il percorso predefinito e':

```text
~/.raspycode/raspycode_rag.db
```

Sovrascrivibile con `RASPY_RAG_DB=/percorso/custom.db`.

### Architettura consigliata

L'ingestion viene eseguita **sul laptop**. Gli embedding vengono richiesti al
modello `nomic-embed-text` eseguito da Ollama sul Raspberry Pi tramite il link
Ethernet dedicato:

```text
Laptop                         Raspberry Pi
  |                                 |
  | -- HTTP embedding request ----> | Ollama :11434
  | <--------- vector ------------- |
  |                                 |
  +--> ~/.raspycode/raspycode_rag.db
```

In questo modo:

- il DB viene scritto direttamente nella sua posizione definitiva;
- non esiste una seconda copia del DB sul Pi;
- non servono `scp`, SSH o script di sincronizzazione;
- non e' possibile dimenticare una sincronizzazione e usare dati RAG obsoleti;
- una nuova ingestion sostituisce il DB solo quando e' stata completata con
  successo.

### Eseguire l'ingestion

Dal laptop, nella root del repository, con i documenti dentro `docs_rag/`:

```bash
python3 ingest.py
```

Per personalizzare il setup:

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `RASPY_RAG_DB` | `~/.raspycode/raspycode_rag.db` | Percorso del DB SQLite sul laptop |
| `RASPY_OLLAMA_URL` | `http://10.42.0.2:11434/api/embeddings` | Endpoint Ollama sul Pi |
| `RASPY_EMBEDDING_MODEL` | `nomic-embed-text` | Modello usato per gli embedding |
| `RASPY_DOCS_DIR` | `docs_rag` | Directory locale dei documenti da indicizzare |
| `RASPY_EMBEDDING_TIMEOUT` | `120` | Timeout HTTP per singola richiesta, in secondi |

Lo script costruisce un DB temporaneo nella stessa directory del DB finale e
lo pubblica con una sostituzione atomica al termine. Se Ollama non e'
raggiungibile o un documento causa un errore, il DB RAG precedente rimane
intatto.

`ingest.py` ricostruisce il DB da zero a ogni esecuzione: rieseguire il comando
e' quindi sicuro e non crea duplicati dei chunk precedenti.

Il file `scripts/sync_rag_db.sh` e' stato rimosso perche' non fa piu' parte
dell'architettura: il DB non viene mai generato sul Pi e non deve essere
sincronizzato.

## Pulizia __pycache__

```bash
./cleanCache.sh               # pulisce a partire dalla cwd
./cleanCache.sh /altro/path   # oppure specifica un path
```

Rimuove ricorsivamente tutte le cartelle `__pycache__` e i `.pyc` orfani.

## Note sul display TFT (htop, non pilotato da raspyCode)

Il rendering custom (prima locale via Pillow/numpy, poi lo stream TCP
laptop → Pi con `TFTDisplayService` + `fb_listener.py`) è stato rimosso:
troppa superficie di manutenzione (conversione RGB565, gestione socket,
dipendenze Pillow/numpy) per un beneficio marginale.

Il TFT ora mostra semplicemente `htop` in esecuzione **direttamente sul
Raspberry Pi**, tramite la console Linux (`fbcon`) mappata sul framebuffer,
gestita da un servizio systemd indipendente da raspyCode: se l'agente non è
in esecuzione, o crasha, il display continua comunque a mostrare lo stato
del sistema.

### Config hardware di riferimento (TFT 3.5" ILI9486, 480x320)

```
# /boot/firmware/config.txt
dtparam=spi=on
dtoverlay=tft35a:rotate=90
```

```bash
sudo usermod -a -G spi,gpio,video,tty noya
```

Setup del servizio `htop` sulla console mappata sul framebuffer: vedi
TODO.md, sezione 4.
