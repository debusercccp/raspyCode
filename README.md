# raspyCode

Agente locale a microservizi (asyncio + event bus) per bioinformatica, con
frontend TUI full-screen in `Textual`, tool-calling verso `bioCli/`, e telemetria opzionale
su display TFT via framebuffer (`raspyDisplay`).

## Architettura

```text
Laptop (10.42.0.1) ───eth0 cablato───▶ Raspberry Pi 5 (10.42.0.2:11434, Ollama)
                                        └── wlan0 verso router (apt/ollama pull/NTP)

```

Il pacchetto è organizzato a microservizi (Domain-Driven), tutti collegati a un unico
`EventBus` fan-out (ogni servizio riceve una copia di ogni evento e filtra per tipo):

| Servizio | Modello | Ruolo |
| --- | --- | --- |
| `RaspyCodeApp` | `ui/frontend_service.py` | TUI `Textual` full-screen: input utente, log, status bar e UI impostazioni |
| `LLMGatewayService` | `services/llm_gateway_service.py` | Client Ollama (`/api/chat`, streaming + tool-calling) |
| `ToolExecutorService` | `services/tool_executor_service.py` | Chiama le funzioni pure di `bioCli/` (in-process) e `system_run_cmd` (subprocess, allow-list) |
| `ConnectivityService` | `services/connectivity_service.py` | Healthcheck periodico verso Ollama (`/api/tags`) e fetch modelli disponibili |
| `TFTDisplayService` | `services/display_service.py` | Rendering di stato su `/dev/fb1` (ILI9486 480x320), auto-disabilitante |
| `HardwareDetectionService` | `services/hardware.py` | Rileva ROCm / CUDA / CPU-only all'avvio |
| `EventBus` | `core/event_bus.py` | Bus pub/sub asyncio, una coda per subscriber |

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
    ├── core/                   <- Infrastruttura eventi
    │   ├── event_bus.py
    │   └── events.py
    ├── services/               <- Microservizi backend
    │   ├── connectivity_service.py
    │   ├── display_service.py
    │   ├── hardware.py
    │   ├── llm_gateway_service.py
    │   └── tool_executor_service.py
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

`bioCli/` è un sottopacchetto vero e proprio: `ToolExecutorService` importa
direttamente `raspyCode.bioCli` e chiama le sue funzioni pure (nessun subprocess,
nessun path da risolvere a runtime). L'unico tool eseguito come processo esterno
resta `system_run_cmd`, limitato all'allow-list descritta più sotto.

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

Ogni funzione di `bioCli/` è esposta al modello come tool `biotoolkit_<nome>`
(es. `biotoolkit_gc_content`, `biotoolkit_rev_comp`, `biotoolkit_dna_to_rna`, ...),
chiamata direttamente in-process da `ToolExecutorService._execute`.

In più:

* `biotoolkit_run_genetic_sim`: simulazione genetica con seed random isolato
per chiamata (istanziato dentro l'handler, mai a livello di modulo).
* `system_run_cmd`: esecuzione di comandi di sistema, **limitata a
un'allow-list** (`ls, cat, df, free, uname, whoami, pwd, head, tail, wc`)
in `tool_executor_service.SYSTEM_CMD_ALLOWLIST`. Estendere solo con binari
read-only: dare shell libera a un LLM resta un vettore di rischio anche
in un agente locale.

## Pulizia __pycache__

```bash
./cleanCache.sh               # pulisce a partire dalla cwd
./cleanCache.sh /altro/path   # oppure specifica un path
```

Rimuove ricorsivamente tutte le cartelle `__pycache__` e i `.pyc` orfani.

## Note su raspyDisplay

`TFTDisplayService` scrive direttamente su `/dev/fb1` convertendo un canvas
Pillow in RGB565 via `numpy`, senza script Bash o file temporanei intermedi.
Se il framebuffer non esiste (es. esecuzione su laptop, o Pi senza HAT) il servizio
si disabilita da solo, continuando a drenare la coda eventi senza mai far
crashare l'agente o accumulare memoria zombie.

Config hardware di riferimento (TFT 3.5" ILI9486, 480x320):

```
# /boot/firmware/config.txt
dtparam=spi=on
dtoverlay=tft35a:rotate=90

```

```bash
sudo usermod -a -G spi,gpio,video noya
```
