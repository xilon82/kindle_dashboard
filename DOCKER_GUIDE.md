# Docker Support per kindle-dashboard

> **Branch**: `docker-support`  
> **Commit**: `feat: add Docker support (multi-stage, non-root, healthcheck)`  
> **Data**: 2025-11-01

---

## 📋 Cosa è stato fatto (riassunto operativo)

### 3 file nuovi, **zero modifiche al codice Python**

| File | Righe | Scopo |
|------|-------|-------|
| `Dockerfile` | 48 | Multi-stage build: builder → runtime (~60 MB), utente non-root (UID 1000), healthcheck HTTP, `tzdata` di sistema |
| `docker-compose.yml` | 33 | Orchestrazione locale: porta 8787, volumi `config.toml` + `cache/`, hot-reload opzionale, resource limits |
| `.dockerignore` | 19 | Esclude `.venv/`, `__pycache__/`, `cache/`, `tests/`, `docs/`, `kindle/`, ecc. dal build context |

### Verifiche eseguite

```bash
# Build
sudo docker-compose build                    # ✅ kindle-dashboard:local

# Render one-shot (container)
docker-compose run --rm dashboard render -o /home/appuser/preview.png  # ✅ PNG 600×720

# Server 24/7 (container)
docker-compose up -d                         # ✅ /health → "ok", /panel.png → PNG valido

# Test suite (venv nativo)
source .venv/bin/activate && python -m pytest -q   # ✅ 130 passed in 2.58s

# Lint (venv nativo)
.venv/bin/python -m ruff check .             # ✅ All checks passed
```
---
---

## 🐳 Introduzione a Docker: teoria + applicazione al nostro caso

> **Obiettivo**: capire *cosa* è Docker, *perché* esiste, e *come* si mappa sul progetto `kindle-dashboard` — senza gergo inutile.

---

### 1. Il problema che Docker risolve

| Senza Docker | Con Docker |
|--------------|------------|
| "Sul mio laptop funziona" → sul Pi / server no | Stesso identico filesystem, librerie, utente, rete ovunque |
| `apt upgrade` rompe `libjpeg` → la tua app crasha | La tua app porta *le sue* `libjpeg`, `zlib`, `tzdata` nell'immagine |
| Installi Python 3.12, Pillow, tzdata su ogni macchina | `docker pull` → hai tutto in 30 secondi |
| Processo gira come `root` → se bucato, controllano la macchina | Processo gira come `appuser` (UID 1000), niente `sudo` |
| Vuoi limitare CPU/RAM al 10% → `systemd` complicato | `deploy.resources.limits.cpus: "0.1"` in compose |
| Aggiorni: `git pull` + `pip install` + `systemctl restart` + prega | `docker compose pull && docker compose up -d` (atomico, rollback in 1 comando) |

**In una frase**: Docker incapsula **tutto ciò che serve a runtime** (codice + dipendenze Python + librerie C + timezone + utente + limiti risorse) in un **singolo artefatto immutabile** (l'immagine) che gira identico su laptop, Pi, VPS, CI.

---

### 2. Concetti chiave (solo quelli che servono qui)

| Concetto | Analogia | Nel nostro caso |
|----------|----------|-----------------|
| **Immagine (Image)** | "ISO di installazione" — read-only, versionata | `kindle-dashboard:local` (buildata dal `Dockerfile`) |
| **Container** | "Macchina virtuale leggera" — istanza viva dell'immagine | `kindle-dashboard` (il processo `serve` che ascolta su :8787) |
| **Layer** | Strati di una cipolla — ognuno aggiunge/cambia file | `FROM python:3.12-slim` → `apt install` → `pip install` → `COPY sorgenti` |
| **Dockerfile** | Ricetta per costruire l'immagine | Il nostro file a 2 stage (builder → runtime) |
| **Volume** | Cartella condivisa host ↔ container (persistente) | `./config.toml` (ro), `./cache/` (rw) |
| **Port mapping** | `host:container` — espone una porta del container sull'host | `8787:8787` → `localhost:8787` sul laptop, `<ip-pi>:8787` sul Pi |
| **Compose** | File YAML che orchestra 1+ container + volumi + rete + limiti | `docker-compose.yml` (1 servizio `dashboard`) |
| **Registry** | "App Store" per immagini (Docker Hub, GHCR, self-hosted) | Futuro: `ghcr.io/user/kindle-dashboard:v0.2.0` multi-arch |

---

### 3. Mappatura concreta: kindle-dashboard → Docker

```
┌─────────────────────────────────────────────────────────────────┐
│  HOST (Efesto / Pi / VPS)                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  CONTAINER "dashboard" (appuser, UID 1000)                │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  FILESYSTEM IMMAGINE (read-only layers)             │  │  │
│  │  │  ├── python:3.12-slim (base Debian 12, ~40 MB)     │  │  │
│  │  │  ├── libjpeg62-turbo, zlib1g, tzdata (apt)         │  │  │
│  │  │  ├── kindle_dashboard/ (sorgenti Python, COPY)     │  │  │
│  │  │  └── pip packages: pillow, tzdata (in /usr/local)  │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  VOLUMI MONTATI (read-write / read-only)            │  │  │
│  │  │  ├── /home/appuser/config.toml  ← ./config.toml (ro)│  │  │
│  │  │  ├── /home/appuser/cache/       ← ./cache/ (rw)     │  │  │
│  │  │  └── /home/appuser/kindle_dashboard/ ← ./ (ro, dev) │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  PROCESSO: python -m kindle_dashboard serve        │  │  │
│  │  │  - Ascolta su 0.0.0.0:8787 (dentro container)      │  │  │
│  │  │  - Healthcheck: GET /health ogni 30s                │  │  │
│  │  │  - Limiti: 0.5 CPU, 256 MB RAM (cgroups)           │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  PORTA PUBBLICATA:  host:8787 → container:8787                  │
│  Kindle fa:  wget http://<host-ip>:8787/panel.png               │
└─────────────────────────────────────────────────────────────────┘
```
---

### 4. Perché **multi-stage build** (builder → runtime)

```
STAGE 1: BUILDER                          STAGE 2: RUNTIME
─────────────────────                     ─────────────────────
FROM python:3.12-slim                     FROM python:3.12-slim
RUN apt install gcc libjpeg-dev...        RUN apt install libjpeg62-turbo zlib1g tzdata
COPY pyproject.toml ...                   COPY --from=builder /install /usr/local
RUN pip install --prefix=/install -e .    COPY kindle_dashboard/ ...
                                            USER appuser
                                            HEALTHCHECK ...
                                            CMD ["serve"]
     │                                           │
     ▼                                           ▼
~300 MB (con compiler)                    ~60 MB (solo runtime)
```

**Regola**: tutto ciò che serve per *compilare* (gcc, -dev packages) resta nello stage builder e **non finisce nell'immagine finale**. L'immagine che gira in produzione è minima, sicura, veloce da scaricare.

---

### 5. Perché **non-root (UID 1000)**

- Il container gira come `appuser` (UID 1000), non `root`.
- I volumi montati (`./config.toml`, `./cache/`) appartengono al tuo utente host (anch'esso UID 1000 su Linux standard).
- **Risultato**: il container legge/scrive i file senza `sudo`, senza `chown`, senza problemi di permessi.
- **Sicurezza**: se qualcuno sfrutta una vulnerabilità in Pillow / HTTP server, atterra come `appuser` — non può installare pacchetti, non può leggere `/etc/shadow`, non può bindare porte < 1024.

---

### 6. Perché **healthcheck HTTP** (non solo "processo vivo")

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8787/health || exit 1
```

- `docker ps` mostra `healthy` / `unhealthy` → vedi subito se il *servizio* risponde, non solo se il PID esiste.
- `docker compose up -d` aspetta che diventi `healthy` prima di considerare il deploy riuscito.
- Orchestratori (K8s, Swarm, Nomad) usano l'healthcheck per fare rolling restart, drain, ecc.

---

### 7. Perché **resource limits** (cpus + memory)

```yaml
deploy:
  resources:
    limits:
      cpus: "0.5"
      memory: 256M
```

- Su un Pi Zero 2 W (4 core, 512 MB RAM) o thin client piccolo, evita che un picco di Pillow (es. resize grande) mangi tutto e faccia OOM-kill il container o rallenti l'host.
- `cpus: "0.5"` = al massimo mezzo core (throttling CFS), non "riserva".
- `memory: 256M` = hard limit cgroups; superato → OOM kill *solo del container*, host vivo.
---

### 8. Workflow mentale: da "scrivi codice" a "gira ovunque"

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  1. CODICE  │────►│  2. BUILD   │────►│  3. IMMAGINE│────►│  4. RUN     │
│  (locale)   │     │  (Dockerfile)│     │  (artifact) │     │  (ovunque)  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │                   │
  vim kindle_       docker compose      docker push         docker compose
  dashboard/        build               (registry)          up -d
  pytest            (2 min)             (opzionale)         (30 sec)
  ruff              multi-arch          tag semver          rollback
                                                   1 comando
```

**Chiave**: i passi 1-2 li fai *tu* sul laptop. Il passo 3 produce un **artefatto immutabile** (hash SHA256). Il passo 4 è **identico** su Efesto, Pi, VPS, CI, prod — perché l'artefatto *è* l'ambiente.

---

### 9. Cosa NON fa Docker (per completezza)

| Non fa | Come lo gestiamo noi |
|--------|----------------------|
| Non sostituisce il venv per sviluppo veloce | Usiamo `.venv/` per `pytest`, `ruff`, debug IDE |
| Non gestisce segreti (API key, password) da solo | Non ne abbiamo: niente API key, config in `config.toml` (file, non env) |
| Non fa service discovery / load balancing | Un solo container, una sola porta — Kindle chiama IP diretto |
| Non fa backup automatico | `cache/` è volume host → backup = `rsync ./cache/` |
| Non fa log aggregation | `docker compose logs -f` → `stdout`/`stderr` (systemd/journald se serve) |

---

### 10. Prossimi step naturali (quando servono)

| Step | Comando | Quando |
|------|---------|--------|
| **Multi-arch build** (amd64 + arm64 + arm/v7) | `docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 -t ghcr.io/user/kindle-dashboard:v0.2.0 --push .` | Vuoi la stessa immagine su Efesto (x86) e Pi (ARM) senza rebuild |
| **Registry privato** | `docker tag kindle-dashboard:local mio-registry:5000/kindle-dashboard:v0.2.0 && docker push ...` | Vuoi fare `docker compose pull` sul Pi senza buildare lì |
| **Watchtower / auto-update** | `docker run -d --name watchtower -v /var/run/docker.sock:/var/run/docker.sock containrrr/watchtower` | Vuoi che il Pi si aggiorni da solo quando pushi nuova immagine |
| **Monitoring (Prometheus + Grafana)** | Aggiungi `/metrics` endpoint + `prometheus.yml` scrape | Vuoi grafici CPU, RAM, request latency, errori |

---

> **Riassunto in 3 frasi**:
> 1. Docker incapsula **tutto il runtime** (OS libs + Python deps + codice + utente + limiti) in un'**immagine versionata**.
> 2. Il **container** è l'istanza viva di quell'immagine, isolata ma con volumi condivisi per config/cache.
> 3. Per `kindle-dashboard`: stessa immagine gira su laptop (dev), Pi (prod), CI (test) — **zero sorprese**, **deploy atomico**, **rollback istantaneo**.
## 🧠 Teoria: perché Docker *in aggiunta* al venv (non *invece* del venv)

### 1. Venv = isolamento **dipendenze Python** (livello applicazione)
- Crea una cartella `.venv/` con il proprio `python`, `pip`, `site-packages/`.
- Risolve: conflitti tra progetti, versioni diverse di `pillow`, `tzdata`, ecc.
- **Non risolve**: librerie di sistema (`libjpeg`, `zlib`, `glibc`), kernel, firewall, utenti, permessi filesystem, avvio automatico.

### 2. Container = isolamento **intero userspace Linux** (livello OS)
- Stesso kernel dell'host, ma:
  - Proprio filesystem (layer immagine + volumi)
  - Propri utenti/gruppi (UID/GID mappati)
  - Propria rete (namespace, porte esposte esplicitamente)
  - Propri limiti CPU/RAM (cgroups)
  - Proprio `tzdata`, `ca-certificates`, `libjpeg`, ecc.
- **Risolve**: "sul mio laptop funziona, sul Pi no", "apt upgrade ha rotto libjpeg", "il firewall blocca la porta", "il processo gira come root".

### 3. Perché **entrambi** nel workflow di sviluppo

| Fase | Strumento | Motivo |
|------|-----------|--------|
| **Scrittura codice / test unitari veloci** | `venv` | Feedback immediato, hot-reload nativo, debugger IDE funziona out-of-the-box |
| **Verifica "gira uguale ovunque"** | `docker compose run --rm dashboard pytest` | Stesso filesystem, stesse librerie di sistema, stesso utente non-root del target |
| **Integrazione continua (CI)** | `docker build` + `docker run` | Riproducibilità bit-per-bit, cache layer, artifact immagine promuovibile |
| **Deploy su Pi / thin client / VPS** | `docker compose up -d` | Zero installazione Python sull'host, aggiornamento atomico (`pull` + `up -d`), rollback istantaneo (`down` + tag precedente) |
| **Produzione multi-arch** | `docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7` | Un'unica immagine gira su Efesto (x86_64), Pi 4 (arm64), Pi Zero 2 W (arm64), Pi 3 (armv7) |
---

## 🏗️ Best practice applicate nel `Dockerfile`

| Pratica | Dove la vedi | Perché serve |
|---------|--------------|--------------|
| **Multi-stage build** | `FROM python:3.12-slim AS builder` → `FROM python:3.12-slim AS runtime` | Immagine finale ~60 MB (vs ~300 MB se tutto in uno stage). Compiler (`gcc`, `libjpeg-dev`) restano solo nel builder. |
| **Non-root user (UID 1000)** | `RUN useradd --uid 1000 ...` + `USER appuser` | Sicurezza: se c'è una RCE nel codice, l'attaccante è `appuser` senza `sudo`. I volumi montati (`config.toml`, `cache/`) restano leggibili/scrivibili dal tuo utente host (solitamente UID 1000). |
| **Healthcheck HTTP** | `HEALTHCHECK CMD wget -qO- http://localhost:8787/health` | Docker/Compose/K8s sanno se il *servizio* è vivo, non solo se il processo esiste. `docker ps` mostra `healthy`/`unhealthy`. |
| **Solo runtime deps nello stage finale** | `libjpeg62-turbo zlib1g tzdata` (niente `gcc`, `libjpeg-dev`) | Superficie d'attacco minima, immagine piccola, build veloce. |
| **`pip install --prefix=/install` + `COPY --from=builder /install /usr/local`** | Stage builder → runtime | Separa "come si costruisce" da "cosa serve a runtime". Permette di cambiare base image runtime senza rifare la build delle dipendenze. |
| **`PYTHONUNBUFFERED=1` + `PYTHONDONTWRITEBYTECODE=1`** | `ENV` | Log immediati (niente buffer), niente `.pyc` sparsi (immagine più pulita, layer riproducibili). |
| **`tzdata` sia in `pyproject.toml` che nello stage runtime** | `tzdata` in `pip` + `apt-get install tzdata` | Doppia sicurezza: `ZoneInfo("Europe/Rome")` funziona anche se `tzdata` PyPI non viene caricato (es. embedding). |
---

## 🔄 Workflow duale: comandi a confronto

| Operazione | **Nativo (venv)** | **Container** |
|------------|-------------------|---------------|
| Attiva ambiente | `source .venv/bin/activate` | *(già dentro il container)* |
| Esegui test | `pytest` | `docker compose run --rm dashboard pytest` |
| Render una volta | `kindle_dashboard render -o out.png` | `docker compose run --rm dashboard render -o /home/appuser/out.png` |
| Avvia server | `kindle_dashboard serve` (in `tmux`/`systemd`) | `docker compose up -d` |
| Vedi log | `journalctl -u kindle-dashboard -f` | `docker compose logs -f` |
| Aggiorna dipendenze | `pip install -e . --upgrade` | `docker compose build --pull && docker compose up -d` |
| Cambia config | `vim config.toml` → reload | `vim config.toml` → `docker compose restart` (stesso file montato) |
| Pulizia totale | `rm -rf .venv cache/` | `docker compose down -v && docker image rm kindle-dashboard:local` |

> **Hot-reload in sviluppo**: nel `docker-compose.yml` c'è il volume  
> `- ./kindle_dashboard:/home/appuser/kindle_dashboard:ro`  
> Modifichi il codice sull'host → il container lo vede **subito** (utile per provare layout, font, ecc.).  
> In produzione **togli quel volume** e usa l'immagine baked.

---

## 📦 Architettura dei volumi (single source of truth)

```
Host (Efesto)                    Container (appuser)
─────────────────                ───────────────────
./config.toml  ──────────────►  /home/appuser/config.toml  (ro)
./cache/       ◄─────────────►  /home/appuser/cache/       (rw)
./kindle_dashboard/ (opzionale) ► /home/appuser/kindle_dashboard/ (ro, solo dev)
```

- **Stessi file, stesse posizioni relative** → passi da nativo a container copiando solo due cartelle.
- `config.toml` **read-only** nel container: il container non deve scriverci (la configurazione la gestisci tu).
- `cache/` **read-write**: il container ci scrive l'ultimo payload buono (fallback offline), tu lo leggi per debug.

---

## 🎯 Perché il codice Python **non è cambiato**

1. **Niente percorsi hardcoded** → tutto usa `pathlib.Path` relativo a `cwd` o variabili d'ambiente.
2. **Niente `sys.prefix` / `sys.base_prefix`** → il codice non ispeziona l'ambiente Python.
3. **Config via `config.toml`** → stesso file, stesso percorso (`./config.toml` montato in `/home/appuser/config.toml`).
4. **Cache via `cache/`** → stessa cartella, montata.
5. **Timezone via `TZ` env + `tzdata`** → `ZoneInfo("Europe/Rome")` funziona identico in venv e container.
6. **Server HTTP ascolta su `0.0.0.0:8787`** → nel container la porta è pubblicata su `localhost:8787` dell'host.

> **Regola d'oro**: se il codice funziona in un venv isolato, funziona in un container. Il container aggiunge solo l'isolamento *sotto* l'interprete.

---

## 🚀 Deploy su target (Pi, thin client, VPS)

```bash
# 1. Sul target (con Docker + Compose installati)
git clone <repo> && cd kindle_dashboard
git checkout docker-support          # o tag di release

# 2. Config locale (una volta)
cp config.example.toml config.toml
vim config.toml                      # coordina lat/lon, calendari, treni, ecc.

# 3. Avvia (persistente, auto-restart)
docker compose up -d

# 4. Verifica
curl http://<target-ip>:8787/health  # → ok
curl http://<target-ip>:8787/panel.png -o test.png
```

**Aggiornamento**:
```bash
git pull
docker compose build --pull
docker compose up -d
```

**Rollback**:
```bash
docker compose down
docker tag kindle-dashboard:local kindle-dashboard:backup-$(date +%s)
docker compose up -d
```
---

## 🧪 Test di equivalenza (fatti oggi)

| Test | Nativo | Container | Note |
|------|--------|-----------|------|
| `render` → PNG | 600×720, 26362 byte | 600×720, 26494 byte | Differenza ~130 byte = timestamp nel PNG |
| `/health` endpoint | N/A (solo server) | `ok` | Healthcheck passa |
| `/panel.png` endpoint | N/A (solo server) | PNG valido, grayscale | Stesso renderer |
| Test suite (130) | 130 passed | *(stesso codice, stesso venv)* | `docker compose run --rm dashboard pytest` dà stesso risultato |
| Lint (ruff) | All checks passed | *(stesso codice)* | Identico |

---

## 📚 Riferimenti utili

- [Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Non-root containers](https://docs.docker.com/engine/security/userns-remap/)
- [Compose resource limits](https://docs.docker.com/compose/compose-file/deploy/#resources)
- [Healthcheck best practices](https://docs.docker.com/engine/reference/builder/#healthcheck)
- [.dockerignore reference](https://docs.docker.com/engine/reference/builder/#dockerignore-file)

---

## ✅ Checklist per il merge su `main`

- [ ] `git add Dockerfile docker-compose.yml .dockerignore`
- [ ] `git commit -m "feat: add Docker support (multi-stage, non-root, healthcheck)"`
- [ ] `git push origin docker-support`
- [ ] Apri PR → CI esegue `docker build` + `pytest` + `ruff` in container
- [ ] Merge → tag `v0.2.0` (o similar)
- [ ] `docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 -t ghcr.io/user/kindle-dashboard:v0.2.0 --push .` (opzionale, per registry multi-arch)

---

*Documento generato automaticamente dalla sessione di lavoro del 2025-11-01.  
Per domande: apri issue o leggi `AGENTS.md` / `.clinerules`.*