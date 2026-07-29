# TODO — Setup raspyCode end-to-end

Checklist operativa per portare l'infrastruttura da zero a funzionante:
Raspberry Pi (inferenza Ollama + display TFT) e laptop (agente raspyCode +
eventuale training).

---

## 1. Raspberry Pi — sistema base

- [ ] Flash Raspberry Pi OS Lite 64-bit (Debian 13 Trixie) su NVMe
- [ ] Primo boot, `sudo raspi-config`: hostname, timezone, espansione filesystem
- [ ] `sudo apt update && sudo apt full-upgrade -y`
- [ ] Creare/verificare utente `noya`, aggiungerlo a `sudo`
- [ ] `sudo apt install -y ufw git curl python3-venv`

## 2. Raspberry Pi — networking dual-stack

- [ ] Collegare il link cablato diretto laptop <-> Pi su `eth0`
- [ ] Configurare IP statico su `eth0` del Pi: `10.42.0.2/24` (gateway assente,
      e' un link punto-punto)
  ```bash
  # /etc/network/interfaces.d/eth0 o via nmcli/netplan a seconda del setup
  ```
- [ ] Configurare IP statico lato laptop su `eth0`: `10.42.0.1/24`
- [ ] Verificare che `wlan0` resti connesso al router di casa (per
      `apt`, `ollama pull`, NTP) — non toccare il default gateway su `wlan0`
- [ ] `ping 10.42.0.2` dal laptop e `ping 10.42.0.1` dal Pi: entrambi ok
- [ ] `sudo ufw default deny incoming`
- [ ] `sudo ufw allow from 10.42.0.1 to any port 11434 proto tcp`
- [ ] `sudo ufw allow ssh` (se serve accesso remoto dal wifi/LAN di casa)
- [ ] `sudo ufw enable` e `sudo ufw status verbose` per confermare le regole
- [ ] Testare che dalla LAN wifi (non da `10.42.0.1`) la porta 11434 **non**
      risponda (`nc -zv <ip-pi-wifi> 11434` deve fallire)

## 3. Raspberry Pi — Ollama

- [ ] Installare Ollama: `curl -fsSL https://ollama.com/install.sh | sh`
- [ ] `sudo systemctl edit ollama.service` e aggiungere:
  ```ini
  [Service]
  Environment="OLLAMA_HOST=0.0.0.0:11434"
  Nice=-5
  Restart=always
  RestartSec=3
  ```
- [ ] `sudo systemctl daemon-reload && sudo systemctl restart ollama`
- [ ] `sudo systemctl enable ollama` (avvio automatico al boot)
- [ ] `sudo systemctl status ollama` — verificare `active (running)`
- [ ] Scaricare i modelli (via `wlan0`, non impegna il link cablato):
  ```bash
  ollama pull gemma:e4b     # primary, tool-calling
  ollama pull qwen3:4b      # fallback, alta tolleranza JSON
  ```
- [ ] Dal laptop: `curl http://10.42.0.2:11434/api/tags` → deve rispondere
      con la lista modelli (conferma che routing + firewall funzionano)
- [ ] (Opzionale) `ollama list` sul Pi per confermare spazio disco/modelli

## 4. Raspberry Pi — display TFT (opzionale, solo se collegato)

- [ ] Collegare fisicamente il TFT 3.5" ILI9486 sui pin SPI/GPIO
- [ ] Editare `/boot/firmware/config.txt`:
  ```
  dtparam=spi=on
  dtoverlay=tft35a:rotate=90
  ```
- [ ] `sudo reboot`
- [ ] Verificare che compaia `/dev/fb1`: `ls -la /dev/fb1`
- [ ] `sudo usermod -a -G spi,gpio,video noya`
- [ ] Logout/login (o reboot) perche' i gruppi abbiano effetto
- [ ] Installare le dipendenze di rendering sul Pi:
  ```bash
  pip install --break-system-packages pillow numpy
  # oppure, se raspyCode gira anche sul Pi: pipx install ".[tft]"
  ```
- [ ] Test rapido di scrittura sul framebuffer (senza passare da raspyCode):
  ```python
  import numpy as np
  buf = (np.random.rand(320, 480, 1) * 65535).astype("<u2").tobytes()
  open("/dev/fb1", "wb").write(buf)
  ```
  Se lo schermo mostra rumore colorato, il framebuffer funziona.

## 5. Laptop — installazione raspyCode

- [ ] Clonare il repo raspyCode sul laptop
- [ ] Installare `pipx` se non presente (`sudo apt install pipx` o `pip
      install --user pipx`), poi `pipx ensurepath`
- [ ] Dalla root del repo: `pipx install .`
- [ ] `raspycode` deve avviarsi da qualunque directory, senza venv attivo
- [ ] Nella TUI, `Ctrl+S` → impostare l'IP del Pi (default `10.42.0.2`,
      gia' corretto se la rete e' configurata come sopra) e selezionare un
      modello dalla lista (compare solo se il Pi e' raggiungibile — vedi
      punto 3)
- [ ] Verificare che la status bar mostri "Pi collegato" e il modello scelto
- [ ] Mandare un messaggio di prova che richieda un tool bioCli (es. "calcola
      il GC content di ATGC") e controllare che il risultato torni in chat

## 6. Laptop — training pipeline (opzionale, solo se si fa fine-tuning)

- [ ] Installare ROCm per la GPU AMD Radeon (segui la guida ufficiale AMD
      per la versione di kernel/driver in uso)
- [ ] `rocm-smi` deve rispondere senza errori (verifica anche che
      `HardwareDetectionService` rilevi `GPU_AMD_ROCm` all'avvio di raspyCode)
- [ ] Creare un venv dedicato al training (separato da quello di raspyCode)
      e installare Unsloth: `pip install unsloth`
- [ ] Eseguire il fine-tuning e esportare i pesi quantizzati in `.gguf`
- [ ] Trasferire il modello sul Pi via link cablato diretto:
  ```bash
  scp model.gguf noya@10.42.0.2:/home/noya/models/
  ```
- [ ] Sul Pi, creare il `Modelfile` e registrare il modello:
  ```bash
  ollama create custom-model -f Modelfile
  ```
- [ ] Verificare che compaia in `ollama list` e nella SettingsScreen di
      raspyCode (Ctrl+S) dopo il prossimo healthcheck

## 7. Verifica end-to-end

- [ ] Riavviare il Pi da zero e controllare che Ollama parta da solo
      (`systemctl is-enabled ollama` → `enabled`)
- [ ] Scollegare/ricollegare il link cablato e verificare che raspyCode
      mostri "Pi non collegato" e poi torni a "Pi collegato" senza dover
      riavviare l'agente
- [ ] Spegnere Ollama sul Pi (`sudo systemctl stop ollama`) e controllare che
      un messaggio in chat produca lo StatusEvent di errore invece di un
      crash
- [ ] (Se TFT collegato) controllare che il display mostri lo stato dei
      tool-call durante una richiesta con tool bioCli
- [ ] `./cleanCache.sh` sul repo prima di ogni commit, per non versionare
      `__pycache__`
- [ ] `ruff check .` e `pytest tests/ -v` puliti prima di ogni push (la CI
      in `.github/workflows/ci.yml` li rilancia comunque su ogni PR)

## 8. Raspberry Pi — Stack RAG (Ollama Embedding + SQLite DB locale)

- [ ] Scaricare il modello di embedding leggero su Ollama (tramite wlan0):
  ```bash
  ollama pull nomic-embed-text
  ```

* [ ] Installare le dipendenze necessarie per il calcolo vettoriale in locale nel venv:
```bash
pip install numpy httpx

```

* [ ] Verificare le prestazioni del servizio di embedding sul Pi da laptop:
```bash
curl [http://10.42.0.2:11434/api/embeddings](http://10.42.0.2:11434/api/embeddings) -d '{
  "model": "nomic-embed-text",
  "prompt": "Test sequenza genomica AGCT"
}'

```

* [ ] Registrare il nuovo microservizio `RAGService` all'interno di `raspyCode/main.py` agganciandolo al loop `asyncio` e al bus condiviso.
* [ ] Popolare il database SQLite (`raspycode_rag.db`) tramite un piccolo script di ingestione che legga file di testo/documentazione e inserisca i BLOB vettoriali quantizzati nella tabella `documents`.

## 9. Raspberry Pi — Esposizione bioCli come MCP Server (Model Context Protocol)

* [ ] Installare l'SDK Python ufficiale MCP nel virtual environment:
```bash
pip install mcp

```

* [ ] Copiare il file `raspyCode/mcp_server.py` ed eseguirlo come server locale per verificare la corretta esposizione su `stdio`:
```bash
python -m raspyCode.mcp_server

```

* [ ] Configurare il client all'interno di `ToolExecutorService` per connettersi al processo MCP anziché eseguire il routing statico via `if/elif`.

## 10. Laptop / Orchestrazione — Integrazione RAG e MCP sull'EventBus

* [ ] Assicurarsi che `LLMGatewayService` sottoscriva gli eventi `EnrichedChatEvent` (prodotti da `RAGService`) al posto del semplice `UserChatEvent`.
* [ ] Verificare che in caso di fallimento o database SQLite vuoto, il `RAGService` inoltri comunque la domanda utente senza interruzioni di servizio.
* [ ] Eseguire la suite di test locali con `pytest tests/ -v` per garantire che l'inserimento dei nuovi servizi non causi regressioni nelle code di `EventBus`.

```
---

Per aiutarti a visualizzare come si comporterà `RAGService` sul tuo Raspberry Pi prima di avviare il loop in Python, ho configurato una simulazione interattiva. Puoi modificare il prompt di test per verificare come il punteggio di similarità (coseno) selezioni e ordini i segmenti biologici all'interno del database SQLite locale.

```json?chameleon
{"component":"LlmGeneratedComponent","props":{"height":"600px","prompt":"Create an interactive educational simulator in Italian titled 'Simulatore RAGService (SQLite + Ollama Embedding)'. The simulator explains how the RAG microservice converts an input prompt into vector embeddings and matches them against SQLite records using cosine similarity. Use standard layout. Include a text input field for 'Domanda Utente' pre-filled with 'Come si calcola la percentuale di Guanina e Citosina?'. Include a slider to set the similarity threshold (from 0.00 to 1.00, default 0.65). Include a dynamic table or list representing SQLite DB records with sample genomics/bioinformatics chunks (e.g. GC content definitions, Hamming distance explanations, DNA to RNA transcription rules). When the user changes the query or threshold, dynamically compute and display simulated cosine similarity scores for each DB chunk, highlighting the chunks that exceed the threshold and are injected into the 'EnrichedChatEvent' for the LLM. Add clean visual differentiation for selected vs rejected chunks.","id":"im_0e533bf4040a7cae"}}

```
