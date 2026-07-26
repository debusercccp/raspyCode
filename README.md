Ecco il README aggiornato. Ho integrato l'alberatura a sottomoduli, il passaggio all'interfaccia `Textual`, l'aggiunta del `ConnectivityService` per l'healthcheck, e il nuovo sistema di installazione/esecuzione tramite `pyproject.toml`.

---

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
| `ToolExecutorService` | `services/tool_executor_service.py` | Esegue gli script `bioCli/` e `system_run_cmd` (allow-list) |
| `ConnectivityService` | `services/connectivity_service.py` | Healthcheck periodico verso Ollama (`/api/tags`) e fetch modelli disponibili |
| `TFTDisplayService` | `services/display_service.py` | Rendering di stato su `/dev/fb1` (ILI9486 480x320), auto-disabilitante |
| `HardwareDetectionService` | `services/hardware.py` | Rileva ROCm / CUDA / CPU-only all'avvio |
| `EventBus` | `core/event_bus.py` | Bus pub/sub asyncio, una coda per subscriber |

## Struttura cartelle

```text
.
├── pyproject.toml              <- Configurazione per installazione locale
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
    └── bioCli/                 <- Script bioinformatica (subprocess)
        ├── sequence/
        ├── assembly/
        ├── search/
        ├── io/
        ├── synthesis/
        └── bioPipeLine.py

```

`bioCli/` è incluso nel namespace ma trattato come script standalone: `ToolExecutorService` calcola
il suo path in automatico con `Path(__file__).resolve().parent.parent / "bioCli"`,
quindi funziona a prescindere da dove il pacchetto viene clonato. Per puntare a
un'altra posizione, sovrascrivi con la variabile d'ambiente `BIOTOOLKIT_ROOT`.

## Requisiti e Installazione

* Python 3.11+ (testato su 3.13)
* Ollama in esecuzione sul Raspberry Pi, raggiungibile su `10.42.0.2:11434` (modificabile a runtime da UI)
* Solo sul Raspberry Pi con TFT collegato: `Pillow` e `numpy` (installabili tramite extra `[tft]`), utente nei gruppi `spi,gpio,video`

Grazie al `pyproject.toml`, il progetto si installa in modalità editabile, rendendolo accessibile globalmente nel virtual environment senza conflitti di `PYTHONPATH`:

```bash
python3 -m venv .venv
source .venv/bin/activate

# Installazione base (Laptop)
pip install -e .

# Installazione con dipendenze opzionali per il display (Raspberry Pi)
pip install -e ".[tft]"

```

## Esecuzione

L'installazione crea automaticamente un alias eseguibile nel tuo ambiente. Puoi lanciare l'agente da **qualsiasi directory**:

```bash
raspycode

```

Comandi principali da dentro la TUI:

* **`Ctrl+S`**: Apre il pannello impostazioni per instradare l'IP e selezionare il modello rilevato.
* **`Ctrl+Q`** (o `/quit`, `/exit`): Termina in modo pulito tutti i servizi ed esce.

### Variabili d'ambiente

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `RASPY_PI_IP` | `10.42.0.2` | IP di default per il routing verso Ollama (sovrascrivibile da UI) |
| `RASPY_MODEL` | `None` | Modello di avvio (se assente, la TUI ti inviterà a selezionarlo con `Ctrl+S`) |
| `BIOTOOLKIT_ROOT` | `<raspyCode>/bioCli` | Path assoluto della cartella script bioinformatica |

Esempio di avvio pre-configurato:

```bash
RASPY_PI_IP=10.42.0.2 RASPY_MODEL=qwen3:4b raspycode

```

## Tool disponibili al modello

Ogni script in `bioCli/` è esposto come tool `biotoolkit_<nome>` che accetta
`args: list[str]` (passati così come sono come argomenti CLI allo script).
Il mapping completo nome-tool -> script è in
`tool_executor_service.BIOTOOLKIT_SCRIPTS`.

In più:

* `biotoolkit_run_genetic_sim`: simulazione genetica con seed random isolato
per chiamata (istanziato dentro l'handler, mai a livello di modulo).
* `system_run_cmd`: esecuzione di comandi di sistema, **limitata a
un'allow-list** (`ls, cat, df, free, uname, whoami, pwd, head, tail, wc`)
in `tool_executor_service.SYSTEM_CMD_ALLOWLIST`. Estendere solo con binari
read-only: dare shell libera a un LLM resta un vettore di rischio anche
in un agente locale.

## Pulizia **pycache**

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
