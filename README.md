# raspyCode

Agente locale a microservizi (asyncio + event bus) per bioinformatica, con
frontend TUI in `rich`, tool-calling verso `bioCli/`, e telemetria opzionale
su display TFT via framebuffer (`raspyDisplay`).

## Architettura

```
Laptop (10.42.0.1) ───eth0 cablato───▶ Raspberry Pi 5 (10.42.0.2:11434, Ollama)
                                        └── wlan0 verso router (apt/ollama pull/NTP)
```

Il pacchetto e' organizzato a microservizi, tutti collegati a un unico
`EventBus` fan-out (ogni servizio riceve una copia di ogni evento e filtra
per tipo):

| Servizio | File | Ruolo |
|---|---|---|
| `FrontendService` | `frontend_service.py` | TUI `rich`: input utente, streaming risposte, log tool-call/risultati |
| `LLMGatewayService` | `llm_gateway_service.py` | Client Ollama (`/api/chat`, streaming + tool-calling) |
| `ToolExecutorService` | `tool_executor_service.py` | Esegue gli script `bioCli/` e `system_run_cmd` (allow-list) |
| `TFTDisplayService` | `display_service.py` | Rendering di stato su `/dev/fb1` (ILI9486 480x320), si autodisabilita se il framebuffer non c'e' |
| `HardwareDetectionService` | `hardware.py` | Rileva ROCm / CUDA / CPU-only all'avvio |
| `EventBus` | `event_bus.py` | Bus pub/sub asyncio, una coda per subscriber |

## Struttura cartelle

```
raspyCode/                 <- pacchetto Python (questo repo)
├── __init__.py
├── main.py                 entry point
├── event_bus.py
├── events.py
├── frontend_service.py
├── llm_gateway_service.py
├── tool_executor_service.py
├── display_service.py
├── hardware.py
├── clean_pycache.sh
├── requirements.txt
└── bioCli/                 script bioinformatica (NON un pacchetto Python,
    ├── sequence/            invocati via subprocess da ToolExecutorService)
    ├── assembly/
    ├── search/
    ├── io/
    ├── synthesis/
    └── bioPipeLine.py
```

`bioCli/` e' sibling dei moduli del pacchetto: `ToolExecutorService` calcola
il suo path in automatico con `Path(__file__).resolve().parent / "bioCli"`,
quindi funziona a prescindere da dove clonate il progetto. Per puntare a
un'altra posizione, sovrascrivi con la variabile d'ambiente `BIOTOOLKIT_ROOT`.

## Requisiti

- Python 3.11+ (testato su 3.13)
- Ollama in esecuzione sul Raspberry Pi, raggiungibile su `10.42.0.2:11434`
  (o l'IP configurato via `RASPY_PI_IP`)
- Solo sul Raspberry Pi con TFT collegato: `Pillow` e `numpy` (decommentare
  in `requirements.txt`), utente nei gruppi `spi,gpio,video`

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Esecuzione

**Importante:** il modulo usa import relativi, quindi va lanciato come
pacchetto dalla cartella **padre** di `raspyCode/`, non da dentro la cartella
stessa:

```bash
cd ~/progetti          # la cartella che CONTIENE raspyCode/
python3 -m raspyCode.main
```

Comandi da dentro la TUI: `/quit` o `/exit` per uscire (o `Ctrl-D`/`Ctrl-C`).

### Variabili d'ambiente

| Variabile | Default | Descrizione |
|---|---|---|
| `RASPY_PI_IP` | `10.42.0.2` | IP del Raspberry Pi su cui gira Ollama |
| `RASPY_MODEL` | `gemma:e4b` | Modello Ollama da usare per il tool-calling |
| `BIOTOOLKIT_ROOT` | `<raspyCode>/bioCli` | Path della cartella script bioinformatica |

Esempio:

```bash
RASPY_PI_IP=10.42.0.2 RASPY_MODEL=qwen3:4b python3 -m raspyCode.main
```

## Tool disponibili al modello

Ogni script in `bioCli/` e' esposto come tool `biotoolkit_<nome>` che accetta
`args: list[str]` (passati cosi' come sono come argomenti CLI allo script).
Il mapping completo nome-tool -> script e' in
`tool_executor_service.BIOTOOLKIT_SCRIPTS`.

In piu':
- `biotoolkit_run_genetic_sim`: simulazione genetica con seed random isolato
  per chiamata (istanziato dentro l'handler, mai a livello di modulo).
- `system_run_cmd`: esecuzione di comandi di sistema, **limitata a
  un'allow-list** (`ls, cat, df, free, uname, whoami, pwd, head, tail, wc`)
  in `tool_executor_service.SYSTEM_CMD_ALLOWLIST`. Estendere solo con binari
  read-only: dare shell libera a un LLM resta un vettore di rischio anche
  in un agente locale.

## Pulizia __pycache__

```bash
./clean_pycache.sh              # pulisce a partire dalla cwd
./clean_pycache.sh /altro/path  # oppure specifica un path
```

Rimuove ricorsivamente tutte le cartelle `__pycache__` e i `.pyc` orfani.

## Note su raspyDisplay

`TFTDisplayService` scrive direttamente su `/dev/fb1` convertendo un canvas
Pillow in RGB565 via `numpy`, senza script Bash o file temporanei intermedi.
Se il framebuffer non esiste (laptop, o Pi senza HAT collegato) il servizio
si disabilita da solo e continua a drenare la coda eventi senza mai far
crashare il resto dell'agente.

Config hardware di riferimento (TFT 3.5" ILI9486, 480x320):

```
# /boot/firmware/config.txt
dtparam=spi=on
dtoverlay=tft35a:rotate=90
```

```bash
sudo usermod -a -G spi,gpio,video noya
```
