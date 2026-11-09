# Docker per kindle-dashboard: guida didattica

> Cosa risolve Docker in questo progetto, come si usa, dove stanno le trappole.
> Docker è l'ambiente di **deploy**; il venv ([docs/venv.md](venv.md)) resta l'ambiente di
> **sviluppo e test**.

## 1. Quando conviene il container (e quando no)

| Esigenza | Strumento |
|---|---|
| Scrivere codice, test, lint con feedback immediato | venv |
| Debug passo-passo nell'IDE | venv |
| Far girare il server 24/7 su un Raspberry Pi o un VPS | container |
| Essere sicuri che il comportamento sia identico su un'altra macchina | container |
| Limitare CPU/RAM del servizio senza toccare il resto dell'host | container |

Il container non sostituisce il venv: il venv isola i **pacchetti Python**, il container isola
**l'intero userspace Linux** (librerie C, utente, rete, limiti di risorse). Per il confronto
completo vedi [docs/venv.md](venv.md).

## 2. Prerequisiti e verifica

```bash
docker --version
docker compose version     # Compose v2 è un plugin: il comando è "docker compose"
docker info                # se fallisce, il daemon non è in esecuzione
```

| Sistema | Installazione |
|---|---|
| Windows / macOS | Docker Desktop **avviato**: senza daemon ogni comando risponde "Cannot connect to the Docker daemon" |
| Linux | Docker Engine + plugin Compose v2 (`docker-compose-v2` su Ubuntu recente, `docker-compose-plugin` dal repository Docker); utente nel gruppo `docker` per evitare `sudo` |

`docker-compose` con il trattino è la vecchia Compose v1, deprecata: qui si usa `docker compose`
(v2), l'unico comando che conviene imparare. Il progetto non ha bisogno di Kubernetes né di un
registry: un solo servizio, una sola porta.

Se `docker compose version` risponde `docker: unknown command: docker compose`, il client Docker
c'è ma il **plugin** no. Installalo a livello utente, senza sudo:

```bash
arch=$(uname -m)
case "$arch" in
  x86_64) asset=x86_64 ;;
  aarch64|arm64) asset=aarch64 ;;
  armv7l) asset=armv7 ;;
  armv6l) asset=armv6 ;;
  *) echo "architettura non gestita: $arch"; exit 1 ;;
esac
mkdir -p ~/.docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$asset" \
  -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
docker compose version
```

In alternativa, **se hai aggiunto il repository apt di Docker** (`download.docker.com`, non quello di
Mint/Ubuntu dove il pacchetto non esiste): `sudo apt-get install docker-compose-plugin`; su Ubuntu
24.04 c'è anche `docker-compose-v2`. Nel frattempo un riavvio si fa lo stesso con `docker restart
kindle-dashboard`: il nome del container è fissato da `container_name`, quindi equivale a
`docker compose restart`.

## 3. I tre file del progetto

| File | Righe | Cosa fa |
|---|---|---|
| `Dockerfile` | 49 | costruisce l'immagine in due stage, utente non-root, healthcheck, `ENTRYPOINT python -m kindle_dashboard` |
| `docker-compose.yml` | 34 | orchestra il servizio: porta 8787, volumi, variabili d'ambiente, limiti di risorse |
| `.dockerignore` | 21 | esclude dal build context `.venv/`, `cache/`, `tests/`, `docs/`, `kindle/`, `.git/`, i PNG e i `config*.toml` locali (contengono l'URL iCal segreto) |

Il *build context* è ciò che Docker invia al daemon per costruire l'immagine: tenerlo piccolo rende
la build più veloce ed evita di spedire cache e segreti. `config.toml` è **escluso** dal contesto
(contiene l'URL iCal segreto) e non viene copiato dal `Dockerfile`: entra a runtime come volume
(sezione 5). `docker-compose.override.yml` è escluso: puoi usarlo per modifiche locali senza toccare
l'immagine.

### Chi è chi: project, service, container, image

Compose è un modo **dichiarativo** di avviare container: il `docker-compose.yml` descrive *cosa*
deve esistere. Quattro nomi da non confondere:

| Nome | Nel progetto | Cosa è |
|---|---|---|
| **image** | `kindle-dashboard:local` | la ricetta costruita dal `Dockerfile` (`docker compose build`) |
| **project** | `kindleretractor` | il prefisso che Compose ricava dalla cartella del compose: raggruppa container, rete e volumi |
| **service** | `dashboard` | la voce sotto `services:`: immagine, volumi, porte, ambiente, healthcheck |
| **container** | `kindle-dashboard` | l'istanza creata da `docker compose up`: il nome è fissato da `container_name` (senza, sarebbe `kindleretractor-dashboard-1`) |

Compose crea anche la rete `kindleretractor_default` (i container del progetto si parlano per nome).
Le opzioni di `docker run` — `-p`, `-v`, `-e`, `--restart`, l'healthcheck — non si digitano più: sono
nel file e vengono applicate **a ogni** container del servizio, quindi non puoi dimenticarti il
volume di `config.toml`.

Per questo `docker run kindle-dashboard:local` (o il pulsante **Run** di Docker Desktop) non è
equivalente: crea un container "nudo", senza volume né porta né variabili, che esce subito con
`configurazione non trovata: config.toml`. `docker compose run --rm dashboard <comando>` invece usa
la **stessa** definizione del servizio (volumi compresi), crea un container usa-e-getta
`kindleretractor-dashboard-run-<hash>` e lo elimina all'uscita: è la via per i comandi one-shot.

Ciclo di vita: `up -d` crea o **ricrea** solo ciò che è cambiato ed è idempotente; `restart` riavvia
il processo senza ricreare il container (il codice Python in memoria cambia solo così); `down`
rimuove container e rete ma **non** l'immagine né `config.toml`/`cache/`, che stanno sull'host.

Due cose che `up -d` **non** fa, e che fanno sembrare «la modifica non ha effetto»:

- **non aggiorna il codice in memoria**: il volume monta `./kindle_dashboard`, quindi il file su disco
  è nuovo ma il processo ha ancora il modulo vecchio — serve `restart` (o `up -d`, che ricrea);
- **non tocca i container nati da un altro progetto compose**. Se `docker ps` mostra un nome tipo
  `144aa401ba4d_kindle-dashboard` con `kindle-dashboard:local`, quel container viene da un progetto
  con un nome diverso e compose non lo riconosce come suo: `up -d` ne crea un secondo e la porta
  resta occupata dal primo. Rimedio: `docker rm -f <nome>` e poi `docker compose up -d`.

I **font** stanno nell'immagine, non nel volume: dopo aver cambiato il `Dockerfile` serve ricreare il
container (`docker build` da solo lascia in vita quello vecchio, che continua a disegnare col font
precedente). Diagnosi: `docker ps --format '{{.Names}} {{.Image}}'` confrontato con
`docker images`, e `docker exec <nome> ls /usr/share/fonts/truetype` — se manca `liberation`, il
container è vecchio.

### Dockerfile: due stage

| Stage | Base | Contenuto | A cosa serve |
|---|---|---|---|
| `builder` | `python:3.12-slim` | `gcc`, `libjpeg-dev`, `zlib1g-dev`, `pip install --prefix=/install -e .` | compilare le dipendenze |
| `runtime` | `python:3.12-slim` | `libjpeg62-turbo`, `zlib1g`, `tzdata`, **`fonts-liberation`** + `fonts-dejavu-core`, i sorgenti in `/home/appuser`, `/install` | far girare il servizio |

Tutto ciò che serve a *compilare* resta nel `builder` e non finisce nell'immagine finale: il
risultato è molto più piccolo e ha meno superficie d'attacco. Nel runtime entrano solo le librerie
necessarie a `pillow` e `tzdata`; `tzdata` è installato anche a livello di sistema perché `ZoneInfo`
lo usa senza passare da Python.

I due pacchetti di font non sono decorazione: le colonne del pannello si dimensionano con
`font.getlength`, quindi il font decide **quanto testo entra** nel PNG. `fonts-liberation` è la
scelta primaria perché ha la metrica di Arial (1,05-1,08x il Segoe UI Semibold di sviluppo), mentre
`DejaVuSans-Bold` è largo ~1,30x e con quello il pannello perdeva `REG 12519`, l'altezza dell'onda e
due eventi su tre. `fonts-dejavu-core` resta installato solo come riserva di copertura dei glifi: se
un carattere nuovo del pannello mancasse a Liberation, `fonts.load()` ricade su DejaVu invece che sul
font incorporato di Pillow (che stampa quadratini).

L'`ENTRYPOINT` è `python -m kindle_dashboard` e il `CMD` è `serve`: il container parte già come
server, dalla cartella di lavoro `/home/appuser` dove sono copiati i sorgenti. Per un comando
diverso si sostituisce il `CMD`:

```bash
docker compose run --rm -v "${PWD}:/out" dashboard render -o /out/preview.png
```

### Perché un utente non-root (UID 1000)

Il container gira come `appuser` (UID 1000). Se una vulnerabilità di `pillow` o del server HTTP
permette di eseguire codice, l'attaccante atterra come `appuser`: non può installare pacchetti, non
può leggere `/etc/shadow`, non può aprire porte privilegiate. Su Linux standard il tuo utente host
è anch'esso UID 1000, quindi i volumi montati (`config.toml`, `cache/`) restano leggibili e
scrivibili senza `sudo`.

### Perché un healthcheck HTTP

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/health').status == 200 else 1)"
```

Il healthcheck risponde alla domanda "il **servizio** risponde?", non solo "il processo esiste".
`docker compose ps` mostra `healthy`/`unhealthy` e un orchestratore può riavviare un container vivo
ma bloccato.

**Perché non `wget`**: `python:3.12-slim` non include né `wget` né `curl` (verificato con
`docker run --rm python:3.12-slim sh -c "command -v wget"`). Un controllo basato su `wget` rende il
container `unhealthy` anche quando il servizio funziona: il test deve usare qualcosa che
nell'immagine c'è per certo, cioè Python. In alternativa si aggiunge `wget` allo stage `runtime`,
ma è un pacchetto in più per una riga di codice.

Il compose definisce lo stesso controllo: se cambi uno dei due, cambia anche l'altro.

### Perché limiti di risorse

```yaml
deploy:
  resources:
    limits:
      cpus: "0.5"
      memory: 256M
    reservations:
      cpus: "0.1"
      memory: 64M
```

Su un Raspberry Pi o un thin client piccolo, un picco di `pillow` può mangiare tutta la RAM
dell'host. Il limite `memory` è applicato dai cgroup: superato, viene terminato **solo il
container** (OOM kill) e l'host resta vivo. `cpus: "0.5"` è un tetto, non una prenotazione.

## 4. Comandi

```bash
# 1. Il file di configurazione deve esistere PRIMA del primo up (vedi sezione 5)
cp config.example.toml config.toml
# ... e va adattato: coordinate, calendari, stazione dei treni

# 2. Build: prima volta, o dopo modifiche a Dockerfile/pyproject.toml
docker compose build

# 3. Avvio in background
docker compose up -d

# 4. Verifica
docker compose ps                            # STATE: running, e healthy
curl http://localhost:8787/health            # ok
curl -s http://localhost:8787/panel.png -o panel.png   # un PNG
```

Cosa aspettarsi con il `config.example.toml` (verificato su questa immagine):

| Controllo | Atteso |
|---|---|
| `docker compose ps` | `running`, poi `healthy` (start period 10 s + primo intervallo) |
| `curl -s http://localhost:8787/health` | `ok` |
| `curl -s .../panel.png -o panel.png` | HTTP 200 e un PNG **600x720 in scala di grigi** (modalità `L`) |
| `docker compose run ... render` | stampa `pannello 600x720 scritto in ...` e crea il file |

L'esempio attiva il mare e i dettagli dei treni (`stop_details = true`), quindi il primo render fa
più chiamate: meteo, mare, tabellone e una per treno mostrato. Senza rete il PNG si disegna lo stesso,
con le sezioni vuote o con l'ultima cache: nessuna di queste richieste è obbligatoria.

| Operazione | Comando |
|---|---|
| Log live | `docker compose logs -f` |
| Stato e salute | `docker compose ps` |
| Ferma (mantiene il container) | `docker compose stop` |
| Riavvia | `docker compose start` |
| Rileggi `config.toml` | `docker compose restart` |
| Rimuovi container e rete (i volumi restano) | `docker compose down` |
| Rimuovi anche i volumi anonimi | `docker compose down -v` |
| Render one-shot (senza server) | `docker compose run --rm -v "${PWD}:/out" dashboard render -o /out/preview.png` |

Il render one-shot merita una riga in più: senza il volume `-v`, il PNG viene scritto dentro il
container e sparisce con `--rm`. Montando la cartella corrente su `/out` lo ritrovi sull'host. In
PowerShell `"${PWD}:/out"` funziona; su Linux/macOS `"$(pwd):/out"` è l'equivalente.

### Test e lint: restano nel venv

`docker compose run --rm dashboard pytest` **non funziona**, per due motivi indipendenti:

1. l'`ENTRYPOINT` è `python -m kindle_dashboard`, quindi `pytest` viene interpretato come
   sottocomando della CLI (`invalid choice: 'pytest'`);
2. `.dockerignore` esclude `tests/` e l'immagine non installa `pytest`: i test non sono dentro
   l'artefatto, per scelta (l'immagine è il runtime di produzione, non un ambiente di sviluppo).

Quindi test e lint si eseguono nel venv: `python -m pytest -q` e `python -m ruff check .`. Se ti
serve davvero un container per i test, costruiscilo a parte: è un altro Dockerfile, con `tests/` nel
contesto e `pytest` fra le dipendenze. Non piegare l'immagine di produzione a fare anche da
ambiente di test.

## 5. Volumi, configurazione, segreti

| Host | Container | Modalità | Perché |
|---|---|---|---|
| `./config.toml` | `/home/appuser/config.toml` | read-only | la configurazione la gestisci tu; il container non deve riscriverla |
| `./cache/` | `/home/appuser/cache/` | read-write | l'ultimo payload buono, usato come fallback quando una fonte cade |
| `./kindle_dashboard/` | `/home/appuser/kindle_dashboard/` | read-only, solo sviluppo | vedere subito le modifiche (ma vedi sezione 6) |

Due dettagli spiegano perché il codice non è cambiato:

- `cache.dir` è risolto **rispetto al file di configurazione** (`config.py`: `config_path.parent /
  dir`), non rispetto alla directory corrente. Con `config.toml` montato in `/home/appuser`,
  `cache/` finisce in `/home/appuser/cache`, esattamente dove punta il volume.
- La configurazione si legge all'avvio: `load_config()` è chiamato una volta dal comando `serve`.
  Dopo aver modificato `config.toml` serve `docker compose restart`.

### La trappola del bind mount: `config.toml` deve esistere

Se il percorso host di un bind mount non esiste, Docker crea una **directory** vuota con quel nome.
L'applicazione poi trova una directory dove si aspetta un file e fallisce con
`configurazione non trovata: config.toml — copia config.example.toml in config.toml`.
Copia il file prima del primo `up`: è l'errore più comune con questo `docker-compose.yml`.

### Segreti: `KDASH_ICS_URL`

`config.py` usa `KDASH_ICS_URL` **solo se** `[calendar] ics_url` è vuoto nel file. Il compose la
inoltra con `${KDASH_ICS_URL:-}`: utile per tenere l'URL iCal segreto fuori dal file montato,
mentre il file resta la fonte di verità per tutto il resto. Se metti l'URL nel TOML, la variabile
d'ambiente viene ignorata.

### `TZ=Europe/Rome`

Il codice non legge `TZ`: il fuso arriva da `[weather] timezone` e da `ZoneInfo` (in
`timezone_utils.zone()`). `TZ` resta utile per tenere coerenti log e timestamp degli strumenti di
sistema. Se cambi fuso, il valore che conta è quello in `config.toml`.

### Rete

Il server ascolta su `0.0.0.0:8787` (default di `[server]`) e il compose pubblica `8787:8787`:
l'host vede `http://localhost:8787`, il Kindle `http://<ip-del-pc>:8787`. Sul PC Windows il primo
bind può far comparire il prompt del firewall: la regola vale solo per il profilo di rete attivo,
e un profilo `Public` non applica una regola `Private` (vedi `.clinerules`, regola 7).

## 6. Il volume di sviluppo e il riavvio obbligatorio

Il compose monta `./kindle_dashboard` sopra la copia presente nell'immagine. Il container *vede*
subito i file nuovi, ma il processo Python tiene i moduli già importati in memoria: finché non
riavvii, continua a servire il codice vecchio. Dopo una modifica ai sorgenti:

```bash
docker compose restart
```

È lo stesso comportamento del server avviato a mano (vedi `.clinerules`, regola 15): il codice si
ricarica al riavvio del processo, non a ogni richiesta. Se ti aspetti che "hot-reload" significhi
"senza restart", non lo è.

In produzione togli quel volume: il codice deve essere quello cotto nell'immagine, altrimenti
l'artefatto non è più immutabile e due host con la stessa immagine possono comportarsi diversamente.

## 7. Aggiornare e tornare indietro

```bash
# 1. Salva l'immagine attualmente in uso, PRIMA di ricostruire
docker tag kindle-dashboard:local kindle-dashboard:backup

# 2. Aggiorna il codice e ricostruisci
git pull
docker compose build --pull
docker compose up -d

# 3. Verifica
docker compose ps && curl http://localhost:8787/health
```

Se l'aggiornamento va storto:

```bash
docker compose down
docker tag kindle-dashboard:backup kindle-dashboard:local
docker compose up -d
```

L'ordine conta: il tag di backup va preso **prima** della build. Se lo prendi dopo, stai salvando
l'immagine nuova (quella che vuoi scartare) e il rollback non torna indietro. Senza un registry il
rollback è possibile solo se l'immagine precedente è ancora in locale: se ricostruisci due volte di
fila, il backup va rifatto ogni volta.

### Aggiornare un server di casa via SSH

Su un host remoto (Raspberry, mini PC, VPS) si aggiorna dalla shell, con in più il fetch dei tag, la
verifica di cosa sta girando e la cache da svuotare quando cambiano i campi delle fonti:

```bash
ssh <utente>@<ip-server>
cd <cartella-del-clone>                  # es. ~/kindle_dashboard

# 1. Raggiungi il rilascio: main segue l'ultimo merge, il tag dice cosa gira
git fetch --all --prune --tags
git checkout main
git pull --ff-only
git describe --tags --always             # es. v0.2.0

# 2. Backup dell'immagine PRIMA della build, poi ricostruisci
docker tag kindle-dashboard:local kindle-dashboard:backup 2>/dev/null || true
docker compose build --pull
docker compose up -d

# 3. Verifica
docker compose ps                                            # running → healthy
curl -fsS http://127.0.0.1:8787/health && echo               # ok
curl -fsS http://127.0.0.1:8787/panel.png -o /tmp/panel.png
file /tmp/panel.png                                          # PNG ... 600 x 720
rm -f cache/weather.json                                     # solo se sono cambiati i campi

# 4. Se qualcosa non torna
docker compose logs --tail=80 -f
```

`git pull --ff-only` si ferma invece di creare un merge se l'host ha modifiche locali: è il
comportamento che vuoi su un host di deploy.

**Cache e campi nuovi.** Una cache scritta dalla versione precedente non ha i campi aggiunti dopo
(per esempio `sunrise`, `sunset`, `precipitation_probability`): il parsing è tollerante, ma finché
non c'è un fetch riuscito il pannello mostra il fallback. `rm -f cache/weather.json` forza la
riscrittura alla richiesta successiva; non serve riavviare.

**Rilascio pinnato (opzionale).** Per non seguire `main`: `git checkout v0.2.0` (HEAD staccato) e,
per aggiornare, `git fetch --tags` + `git checkout <nuovo-tag>`. Per un server di casa `main` è più
comodo; il tag serve a sapere cosa sta girando.

**Dopo il reboot.** `restart: unless-stopped` riavvia il container, ma solo se il daemon parte:
`systemctl enable docker` una volta sola. Se il servizio non risponde dall'esterno, controlla il
firewall dell'host (`ufw allow 8787/tcp`) e la rete (il Kindle 4 non ha radio a 5 GHz).

**Architettura.** La build è locale: su ARM (Raspberry) funziona, ma non trasferire l'immagine
costruita su un PC x86, non girerebbe.

## 8. Cosa Docker non fa

| Non fa | Come lo gestiamo qui |
|---|---|
| Non sostituisce il venv per lo sviluppo | test, lint e anteprime restano nel venv ([docs/venv.md](venv.md)) |
| Non gestisce i segreti da solo | `config.toml` (montato, ignorato da git) o `KDASH_ICS_URL` |
| Non fa backup | `cache/` è sull'host: `rsync` o `Copy-Item -Recurse` della cartella |
| Non fa rotazione dei log | `docker compose logs`; il driver `json-file` cresce, si limita con `logging.options` se serve |
| Non fa service discovery o load balancing | un solo container, una sola porta: il Kindle chiama l'IP diretto |

## 9. Troubleshooting

| Sintomo | Causa probabile | Rimedio |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop spento o servizio non avviato | avvia Docker Desktop, oppure `sudo systemctl start docker` su Linux |
| `port is already allocated` | un'altra istanza (o un altro programma) occupa la 8787 | `docker compose down`; su Windows `Get-NetTCPConnection -LocalPort 8787 -State Listen`, su Linux `ss -ltnp \| grep 8787` |
| `configurazione non trovata: config.toml` | il bind mount ha creato una directory al posto del file | crea `config.toml` da `config.example.toml` e riavvia |
| Container `Exited (2)` con `configurazione non trovata` | immagine avviata **fuori da Compose** (`docker run` o pulsante Run): manca il volume di `config.toml` | `docker compose up -d`; per un one-shot `docker run --rm -v "$PWD/config.toml:/home/appuser/config.toml:ro" kindle-dashboard:local render` |
| container `unhealthy` | healthcheck fallito: il servizio non risponde (o risponde male) entro i tentativi | `docker compose logs`, poi `docker compose exec dashboard python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8787/health').status)"`; se serve alza `start_period` |
| `permission denied` su `cache/` | UID del container diverso dal proprietario della cartella (host non-UID 1000) | `chown` della cartella o `user:` in un override |
| Il pannello mostra la versione vecchia | il processo ha il codice vecchio in memoria | `docker compose restart` (o togli il volume di sviluppo e ricostruisci) |
| Il Kindle non raggiunge il PC | regola firewall non applicata al profilo di rete in uso | controlla `Get-NetConnectionProfile` e apri la 8787 sul profilo attivo |

## 10. Riferimenti

- [Docker: multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Compose file: `deploy.resources`](https://docs.docker.com/compose/compose-file/deploy/#resources)
- [Dockerfile: `HEALTHCHECK`](https://docs.docker.com/reference/dockerfile/#healthcheck)
- [`.dockerignore`](https://docs.docker.com/reference/dockerfile/#dockerignore-file)
- [Docker Engine security](https://docs.docker.com/engine/security/)
