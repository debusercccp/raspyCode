# raspyCode

Agente locale a microservizi (asyncio + event bus) per bioinformatica, con
frontend TUI full-screen in `Textual`, tool-calling verso `bioCli/`, e telemetria opzionale
su display TFT via framebuffer (`raspyDisplay`).

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
| `TFTDisplayService` | `services/display_service.py` | Gira sul laptop: compone i frame di stato (Pillow/numpy) e li streamma via TCP a `fb_listener.py` sul Pi, che li scrive su `/dev/fb0` (ILI9486 480x320) |
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
├── fb_listener.py               <- Demone TCP da eseguire sul Pi: riceve i frame
│                                   dal laptop e li scrive su /dev/fb0 (vedi sotto)
└── raspyCode/                  <- Pacchetto Python effettivo
    ├── __init__.py
    ├── main.py                 <- Entry point (start())
    ├── mcp_server.py           <- Server MCP, generato dal ToolRegistry condiviso
    ├── core/                   <- Infrastruttura eventi
    │   ├── event_bus.py
    │   └── events.py
    ├── services/               <- Microservizi backend
    │   ├── connectivity_service.py
    │   ├── display_service.py
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

## Note su raspyDisplay (streaming TCP laptop → Pi)

A differenza della versione iniziale (in cui `TFTDisplayService` scriveva
direttamente su `/dev/fb1` locale), l'architettura attuale sposta il
**rendering sul laptop** e la **scrittura sul framebuffer sul Pi**,
collegati da un semplice stream TCP sulla porta `9999`:

```text
Laptop (orion)                              Raspberry Pi 5
┌──────────────────────────┐                 ┌───────────────────────────┐
│ TFTDisplayService        │   TCP :9999     │ fb_listener.py            │
│ (Pillow + numpy → RGB565)│ ─────────────▶  │ (systemd service)         │
│ services/display_service │  frame 307200B  │ scrive su /dev/fb0        │
└──────────────────────────┘                 └───────────────────────────┘
```

Motivazione: il laptop ha CPU/RAM abbondanti per comporre i frame (testo di
stato, ultima query, tool in esecuzione, statistiche di sistema da
`SystemStatsService`), mentre il Pi si limita a un demone leggero che scrive
i byte ricevuti sul framebuffer — nessuna dipendenza da Pillow/numpy lato Pi.

### Lato laptop: `TFTDisplayService`

* Mantiene una connessione TCP persistente verso il Pi in un thread separato
  (`_maintain_connection`), con riconnessione automatica ogni 3s se cade.
* Ad ogni evento rilevante (`UserMessageEvent`, `StatusEvent`,
  `LLMToolCallEvent`, `ToolResultEvent`, `SystemStatsEvent`) ricompone il
  canvas e lo invia in un thread "fire-and-forget" (`_send_frame`), per non
  bloccare mai il loop `asyncio` principale.
* Se `Pillow`/`numpy` non sono installati nel venv del laptop, si disabilita
  da solo (nessun crash).
* **Dipendenze da installare nel venv `pipx` del laptop** (non sono nelle
  dipendenze core del pacchetto, dato che servono solo per il rendering):

  ```bash
  pipx inject raspycode pillow numpy
  ```

### Lato Pi: `fb_listener.py` + servizio systemd

`fb_listener.py` (nella root del repo) è un demone standalone, senza
dipendenze esterne, da eseguire **sul Raspberry Pi**:

```bash
# copia lo script sul Pi, es. in /home/noya/fb_listener.py
scp fb_listener.py noya@10.42.0.2:/home/noya/
```

Per farlo partire automaticamente al boot del Pi, usa lo unit file già
tracciato nel repo (`systemd/fb_listener.service`) invece di ricopiarlo a
mano:

```bash
# dal laptop, copia anche lo unit file sul Pi
scp systemd/fb_listener.service noya@10.42.0.2:/tmp/

# sul Pi
sudo mv /tmp/fb_listener.service /etc/systemd/system/fb_listener.service
sudo systemctl daemon-reload
sudo systemctl enable fb_listener.service
sudo systemctl start fb_listener.service

# verifica che sia attivo
sudo systemctl status fb_listener.service
```

Contenuto di riferimento di `systemd/fb_listener.service`:

```ini
[Unit]
Description=raspyCode TFT Framebuffer Socket Listener
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /home/noya/fb_listener.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`User=root` è necessario perché la scrittura diretta su `/dev/fb0` richiede
permessi che l'appartenenza ai gruppi `spi,gpio,video` da sola non copre in
tutte le configurazioni; in alternativa si può provare a far girare il
servizio come `noya` con i permessi sul framebuffer regolati via `udev`
(`SUBSYSTEM=="graphics", KERNEL=="fb0", GROUP="video", MODE="0660"`), ma
`root` resta l'opzione più semplice per un demone locale su una macchina non
esposta.

### Comandi di pronto soccorso (Pi)

Se la porta `9999` resta occupata da una connessione zombie, o Ollama va in
stallo (bloccando indirettamente anche il caricamento del modello per la
chat):

```bash
sudo fuser -k 9999/tcp         # libera la porta TCP del listener
sudo systemctl restart fb_listener.service
sudo systemctl restart ollama  # riavvia il backend LLM
```

### Config hardware di riferimento (TFT 3.5" ILI9486, 480x320)

```
# /boot/firmware/config.txt
dtparam=spi=on
dtoverlay=tft35a:rotate=90
```

```bash
sudo usermod -a -G spi,gpio,video noya
```
