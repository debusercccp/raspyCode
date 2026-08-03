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

> **Nota:** non usare gli script forniti dai produttori (es. `LCD35-show` di
> Waveshare). Su Raspberry Pi OS Lite 64-bit (Debian 13 Trixie) questi script
> sovrascrivono `/boot/firmware/config.txt` con parametri 32-bit incompatibili
> col kernel ARM64 e possono bloccare il boot; inoltre il `.dtbo` che si
> aspettano spesso non è presente in `/boot/firmware/overlays/`, quindi il
> framebuffer del TFT non viene mai creato. Il kernel include già un overlay
> nativo (`piscreen`) compatibile con i controller ILI9486/ILI9341 via SPI —
> è la via pulita e va usata al posto dei driver di terze parti.

> **Architettura attuale (nuova):** il rendering custom Python è stato
> rimosso (prima locale via Pillow/numpy, poi lo stream TCP laptop → Pi con
> `TFTDisplayService` + `fb_listener.py` — entrambi eliminati dal repo). Il
> TFT ora mostra `htop` in esecuzione **direttamente sul Pi**, agganciando
> una console Linux (`fbcon`) al framebuffer del TFT e lanciandoci sopra
> `htop` via un servizio systemd indipendente da raspyCode. Nessuna
> dipendenza Pillow/numpy, nessun socket da mantenere.

### 4a. Setup hardware sul Pi

- [ ] Collegare fisicamente il TFT 3.5" ILI9486 sui pin SPI/GPIO
- [ ] Editare `/boot/firmware/config.txt` (`sudo nano /boot/firmware/config.txt`),
      assicurandosi che SPI sia abilitato e aggiungendo l'overlay nativo sotto `[all]`:
```ini
  dtparam=spi=on

  [all]
  dtoverlay=piscreen,speed=16000000,rotate=90
```
  (`speed=16000000` = 16 MHz, per stabilità del segnale senza artefatti;
  `rotate=90` = landscape — valori accettati: `0`, `90`, `180`, `270`)
- [ ] `sudo reboot`
- [ ] Verificare che compaia `/dev/fb0`: `ls -la /dev/fb*`, `crw-rw---- root video`
- [ ] `sudo usermod -a -G spi,gpio,video,tty noya`
- [ ] `newgrp video` (o logout/login/reboot) perché il gruppo abbia effetto
      nella sessione corrente
- [ ] Test rumore casuale su `/dev/fb0` (risoluzione 320x480, RGB565), solo
      per confermare che il framebuffer scrive correttamente sul TFT:
```bash
  python3 -c 'import numpy as np; open("/dev/fb0", "wb").write((np.random.rand(320, 480, 1) * 65535).astype("<u2").tobytes())'
```
  Esito positivo: pixel colorati casuali ("effetto neve") sullo schermo.
  Questo test usa numpy solo temporaneamente sul Pi (`pip install
  --break-system-packages numpy`); non serve per l'esecuzione normale.
- [ ] Test reset a nero:
```bash
  python3 -c 'open("/dev/fb0", "wb").write(bytes(320 * 480 * 2))'
```
  Esito positivo: schermo torna nero immediatamente.

### 4b. Console `htop` sul framebuffer TFT (gestita da Mbarocc)

Task lasciato volutamente a carico dell'utente una volta arrivato l'hardware
(dipende da dettagli hardware/kernel non verificabili senza il Pi fisico):

- [ ] Installare `htop` e `con2fbmap`: `sudo apt install -y htop con2fbmap`
- [ ] Verificare il mapping VT → framebuffer con `con2fbmap <vt> <fb>`
      (es. `sudo con2fbmap 7 0` per legare la VT7 a `/dev/fb0`)
- [ ] Creare il servizio systemd che lega una VT dedicata al framebuffer del
      TFT e ci lancia `htop` in autologin/autostart (vedi bozza di unit file
      discussa in chat, da adattare a `fb0` invece di `fb1` e all'utente
      `noya`)
- [ ] Abilitare e avviare il servizio, verificare `systemctl status`
- [ ] Confermare che `htop` resti visibile e aggiornato sul TFT anche se
      `raspycode` non è in esecuzione o crasha (è il punto di questa
      architettura: indipendenza dal processo dell'agente)
- [ ] Verificare leggibilità del testo di `htop` a 480x320 sulla console
      reale (dimensione font, eventuale necessità di `setfont`)

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

## 8. Laptop — Stack RAG (SQLite locale + Ollama Embedding sul Pi)

- [ ] Verificare che il link Ethernet diretto laptop → Pi sia attivo e che
      `http://10.42.0.2:11434` sia raggiungibile dal laptop.
- [ ] Scaricare il modello di embedding sul Pi:
  ```bash
  ollama pull nomic-embed-text
  ```
- [ ] Verificare l'endpoint di embedding dal laptop:
  ```bash
  curl http://10.42.0.2:11434/api/embeddings -d '{
    "model": "nomic-embed-text",
    "prompt": "Test sequenza genomica AGCT"
  }'
  ```
- [ ] Mettere i documenti da indicizzare nella directory `docs_rag/` sul
      laptop.
- [ ] Eseguire l'ingestion dal laptop:
  ```bash
  python3 ingest.py
  ```
- [ ] Verificare che il DB finale sia presente sul laptop in
      `~/.raspycode/raspycode_rag.db` (o nel percorso configurato con
      `RASPY_RAG_DB`).
- [ ] Verificare che il DB venga ricostruito atomicamente: se Ollama viene
      spento durante l'ingestion, il DB precedente deve rimanere utilizzabile.
- [ ] Non creare una copia del DB sul Pi e non usare sincronizzazioni via
      `scp`/SSH: il Pi ospita Ollama e i modelli, il laptop ospita lo stato
      applicativo RAG.
- [ ] Registrare il nuovo microservizio `RAGService` all'interno di
      `raspyCode/main.py` agganciandolo al loop `asyncio` e al bus condiviso.
- [ ] Popolare il database SQLite (`~/.raspycode/raspycode_rag.db`) tramite
      `ingest.py`, che legge i documenti dal laptop e inserisce i BLOB vettoriali
      nella tabella `documents` usando Ollama remoto sul Pi.

## 9. Raspberry Pi — Esposizione bioCli come MCP Server (Model Context Protocol)

* [ ] Installare l'SDK Python ufficiale MCP nel virtual environment:
```bash
# ATTENZIONE: da un certo punto in poi `pip install mcp` installa di default
# la v2 dell'SDK, che ha rifatto l'API e rimosso `mcp.server.fastmcp`
# (mcp_server.py e' scritto contro la v1.x). Pinnare la major version:
pip install "mcp>=1.28,<2"
# equivalente con l'extra dichiarato in pyproject.toml:
pip install -e ".[mcp]"

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
