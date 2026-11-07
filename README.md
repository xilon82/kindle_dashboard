# kindle-dashboard

Pannello e-ink per un Kindle jailbroken: **meteo**, **mare**, **Google Calendar**, **raccolta
differenziata** e **partenze dei treni** vengono raccolti sul PC e disegnati in un PNG da 600x800
(risoluzione nativa del Kindle 4/Touch).
Il Kindle non esegue codice del progetto: scarica il PNG via WiFi e lo mostra a schermo intero con
FBInk. Un pannello non deve mai bloccarsi, quindi ogni sezione ha un fallback.

## Requisiti

- PC acceso con **Python 3.11+** (verificato su Windows 11, Python 3.13) — *oppure* **Docker + Compose** (vedi [Avvio con Docker](#avvio-con-docker-alternativa-al-venv)).
- Kindle jailbroken con **KUAL** installato e **KOReader** (fornisce il binario `fbink`), collegato
  alla stessa rete del PC. Verificato su un Kindle 4 (`reader.lua` riporta `device Kindle4`,
  600x800 @ 167 dpi). Attenzione: il Kindle 4 ha solo Wi-Fi **2.4 GHz**, quindi il PC deve essere
  raggiungibile da quell'SSID (stessa subnet).
- Nessuna API key: meteo e mare da Open-Meteo, treni da Transitous.

## Installazione (venv nativo)

Da un venv dedicato, così le dipendenze non finiscono nell'ambiente globale:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Su Windows il pacchetto `tzdata` è obbligatorio: il sistema non fornisce il database dei fusi
orari usato da `zoneinfo`. È dichiarato in `pyproject.toml`, non serve installarlo a mano.

Perché il venv, come ricrearlo, vantaggi e limiti rispetto a Docker: [docs/venv.md](docs/venv.md).

## Configurazione

```powershell
Copy-Item config.example.toml config.toml
```

`config.toml` è ignorato da git perché contiene l'URL iCal segreto del calendario.

| Sezione | Chiave | Default | Significato |
|---|---|---|---|
| `panel` | `width` / `height` | 600 / 800 | risoluzione nativa del Kindle |
| `panel` | `refresh_seconds` | 90 | ogni quanto la pagina si ricarica: il PNG è ridisegnato a ogni richiesta, quindi l'orologio resta preciso |
| `location` | `name`, `latitude`, `longitude` | — | posizione per il meteo (assente = niente meteo) |
| `weather` | `days` | 3 | giorni di previsione disegnati (max 7); il vento è in **nodi** |
| `weather` | `timezone` | `Europe/Rome` | fuso usato per orari, calendario e treni |
| `sea` | `enabled` | `false` | condizioni del mare dalle stesse coordinate di `[location]`: stato, altezza d'onda e temperatura dell'acqua |
| `sea` | `days` | 3 | giorni di mare nella striscia delle previsioni, accoppiati **per data** al meteo |
| `calendar` | `ics_url` | vuoto | URL iCal segreto di Google Calendar |
| `calendar` | `max_events`, `days_ahead` | 4, 7 | quanti eventi e su quanti giorni |
| `waste` | `ics_url` | vuoto | URL iCal **pubblico** del calendario della raccolta differenziata (vuoto = colonna destra assente) |
| `waste` | `days` | 3 | giorni mostrati nella colonna: oggi, domani e il successivo |
| `trains` | `station`, `stop_id` | — | stazione del tabellone (assente = niente treni) |
| `trains` | `max_departures` | 3 | partenze mostrate |
| `trains` | `destinations` | `[]` | filtro per sottostringa (vuoto = tutte) |
| `trains` | `stop_details` | `false` | seconda riga per treno con le fermate che corrispondono a `destinations` (una richiesta HTTP per treno) |
| `trains` | `stop_priority` | `[]` | fermate da tenere sempre quando la riga non basta: le altre vengono ridotte |
| `render` | `font`, `font_bold` | vuoto | percorsi TTF alternativi a Liberation Sans, che viaggia nel pacchetto (`kindle_dashboard/render/fonts/`) |
| `server` | `host`, `port` | `0.0.0.0`, 8787 | dove ascolta il PC |
| `schedule` | `night_start`, `night_end` | `23:00`, `06:30` | fascia notturna (finestra anche a cavallo di mezzanotte) |
| `schedule` | `night_refresh_seconds` | `3600` | ricarica di notte; di notte l'ora è sostituita da `NOTTE` |
| `cache` | `dir` | `cache` | ultimo payload buono, mostrato quando una fonte cade |

### Google Calendar

Google Calendar > Impostazioni del calendario > *Indirizzo segreto in formato iCal*: incolla l'URL
in `calendar.ics_url`. In alternativa usa la variabile d'ambiente `KDASH_ICS_URL`, che ha la
precedenza solo se il file non specifica nulla: utile per non scrivere la credenziale su disco.

Il titolo dell'evento che non entra nella colonna **va a capo su una seconda riga**, rientrata sotto
il titolo; il taglio cade sempre su uno spazio, mai dentro una parola. La seconda riga si prende solo
lo spazio che avanza: se non basta si torna a una riga sola con i puntini, e il numero di eventi
mostrati resta quello di prima — un evento lungo non può far sparire quello successivo.

### Raccolta differenziata

Se il comune pubblica i giorni di raccolta come calendario iCal (un evento all-day per giorno, il
materiale nel titolo: `Umido`, `Secco`, `Plastica`, `Carta`), incolla l'URL **pubblico** in
`waste.ics_url`. Con quella sezione configurata il blocco del calendario si divide in **due colonne**:
gli eventi a sinistra e la differenziata a destra con oggi, domani e il giorno successivo (`days`).
I giorni senza raccolta mostrano `niente`, così si vede subito che oggi non va messo fuori nulla;
se il calendario è spento la colonna sparisce e gli eventi tornano a tutta larghezza.

L'URL è pubblico e non è una credenziale, quindi niente variabile d'ambiente. Attenzione
all'intervallo coperto dal calendario: quello di Santa Marinella arriva dal 01/06/2026 al 31/12/2026,
quindi fuori da quelle date la colonna mostra solo `niente` finché il comune non lo aggiorna.

### Intestazione

La parte alta del pannello è a due colonne:

- a sinistra data e orologio; sotto, **alba e tramonto** con il sole sul filo dell'orizzonte e la
  freccia su/giù, poi il **vento** in nodi con direzione e nome tradizionale (`6 kn ESE · Levante`);
- a destra il luogo, l'icona del meteo con la temperatura e, sulla riga dei dettagli ingrandita,
  **umidità** (goccia), **probabilità di pioggia** nelle prossime sei ore (ombrello) e **percepita**
  (persona); sotto, la descrizione e il mare.

Se la riga dei dettagli si stringe cede prima la **percepita** — la temperatura reale è già scritta
grande sopra — e poi la **pioggia**: l'umidità resta come ancora. I pezzi cadono sempre a coppie
intere, icona e numero insieme, mai un'icona senza valore.

Le icone del meteo usano **due toni**: nel *poco nuvoloso* il sole dietro la nuvola è grigio, così le
due forme non si fondono in una macchia nera (lo stesso vale per il lampo del temporale).
I titoli delle sezioni hanno la loro icona — calendario, bidone della differenziata, treno — ma è
decorazione: se il titolo è lungo (con `· agg. HH:MM` perché quei dati vengono dalla cache) l'icona
cede e resta il testo.

Il nome del vento segue la rosa a 16 settori: ogni direzione ha il suo nome e gli intermedi prendono
il nome dei due venti principali **nell'ordine delle lettere della sigla** (`OSO` = Ponente-Libeccio,
`NNO` = Tramontana-Maestrale): leggendo la sigla si sa sempre a quale punto cardinale il nome è
legato. Se la fonte non fornisce alba/tramonto (cache scritta prima di questi campi) la descrizione
torna al posto degli orari, così la riga non resta vuota.

### Mare

Con `sea.enabled = true` il pannello aggiunge le condizioni del mare dalle **stesse coordinate di
`[location]`** (Open-Meteo Marine API, nessuna chiave):

- nella riga del vento, nella colonna di destra: stato in parole, altezza d'onda e temperatura
  dell'acqua (`poco mosso 0.6m 21°`);
- sotto ciascuna delle tre giornate: **forza Douglas** (`F3`), altezza d'onda, vento massimo in nodi
  e direzione (`F3 1.3m 21 kn NNE`). La forza costa 15 px contro i 75 di `poco mosso`: è ciò che fa
  entrare altezza, unità e direzione nella colonna da 185 px.

La scala Douglas è quella dei bollettini italiani: 0 calmo, 1 quasi calmo, 2 poco mosso, 3 mosso,
4 molto mosso, 5 agitato, 6 molto agitato, 7 grosso. La classificazione usa l'altezza arrotondata al
decimale mostrato, così `0.5m` non può comparire come "quasi calmo". Se la fonte cade il pannello
mostra `mare n.d.` senza occupare una riga in più, e il footer segnala che alcuni dati vengono dalla
cache. Per una località lontana dal mare conviene lasciare la sezione spenta.

### Stazione dei treni

```powershell
python -m kindle_dashboard resolve-station "Genova Brignole"
```

Stampa coppie `NOME  ->  stop_id`; copia lo `stop_id` in `trains.stop_id`.

## Uso

Anteprima sul PC (nessun device richiesto):

```powershell
python -m kindle_dashboard render -o preview.png
```

Server per il Kindle:

```powershell
python -m kindle_dashboard serve
# pannello: http://localhost:8787/panel.png
```

Estensione KUAL sul Kindle collegato via USB:

```powershell
.\kindle\deploy.ps1 -DryRun                            # mostra cosa farebbe
.\kindle\deploy.ps1                                    # copia in <unita'>:\extensions\dashboard
powershell -ExecutionPolicy Bypass -File .\kindle\allow-lan.ps1   # da amministratore: rete + firewall
```

`deploy.ps1` rileva da solo l'unità del Kindle (quella con `documents\` e `system\`), l'IP del PC e
legge porta e cadenza da `config.toml`.

### Vederlo sul Kindle: il browser

Sul Kindle apri il browser (**Home → Menu → Browser**) e digita:

```
http://<ip-del-pc>:8787/panel.html
```

La pagina mostra il PNG e si **ricarica da sola** ogni `refresh_seconds`, e a ogni ricarica il
pannello viene **ridisegnato con l'ora corrente** e i dati raccolti in quel momento: non c'è un TTL
separato, quindi orologio e dati non possono disallinearsi. Non serve installare nulla
sul device e non si tocca il framework: l'unità USB resta disponibile, il Kindle si comporta
normalmente e per fermare il pannello basta uscire dal browser.

Di notte (finestra `[schedule]`, default **23:00–06:30**) la pagina si ricarica ogni
`night_refresh_seconds` e al posto dell'ora compare **`NOTTE`**: l'ora sarebbe vecchia fino a un'ora,
mentre il footer `dati HH:MM` continua a dire quando i dati sono stati raccolti. L'intervallo non
supera mai il cambio di fascia, quindi alle 06:29 la pagina si ricarica entro pochi secondi e torna
alla cadenza diurna. Per vedere l'anteprima notturna senza aspettare le 23: `render --night`.

Per tenerlo visibile: alimentazione da caricatore (non dalla porta USB del PC) e timeout schermo al
massimo nelle impostazioni. Se compare il salvascherino, un tocco riporta la pagina.

### Avvio con Docker (alternativa al venv)

Se preferisci non installare Python e dipendenze sull'host, puoi usare Docker.  
Requisiti: **Docker Engine + plugin Compose v2** (`docker compose`; su Ubuntu recente il pacchetto
è `docker-compose-v2`, oppure si installa il plugin dal repository Docker). Su Windows/macOS basta
Docker Desktop avviato.

Guida didattica completa (scelte, volumi, trappole, rollback): [docs/docker.md](docs/docker.md).

```bash
# 1. Build immagine (prima volta o dopo modifiche a Dockerfile/pyproject.toml)
docker compose build

# 2. Avvia server in background (porta 8787)
docker compose up -d

# 3. Verifica
curl http://localhost:8787/health      # → ok
curl http://localhost:8787/panel.png -o /tmp/test.png && file /tmp/test.png
```

**Comandi utili**

| Operazione | Comando |
|------------|---------|
| Log live | `docker compose logs -f` |
| Ferma (mantieni container) | `docker compose stop` |
| Riavvia | `docker compose start` |
| Ricarica config cambiata | `docker compose restart` |
| Rimuovi tutto (container + network) | `docker compose down` |
| Render one-shot (senza server) | `docker compose run --rm -v "${PWD}:/out" dashboard render -o /out/preview.png` |

**Volumi montati** (stessi file del venv):
- `./config.toml` → `/home/appuser/config.toml` (read-only)
- `./cache/` → `/home/appuser/cache/` (read-write)
- `./kindle_dashboard/` → `/home/appuser/kindle_dashboard/` (read-only, solo sviluppo: dopo una
  modifica ai sorgenti serve `docker compose restart`, il processo tiene il codice in memoria)

> **Nota**: il file `config.toml` deve esistere prima del primo `up`. Copialo da `config.example.toml` e modificalo.

> **Non avviare l'immagine da sola.** L'immagine non contiene `config.toml` (è un segreto, escluso da
> `.dockerignore`): il file arriva **solo** dal volume montato da Compose. Con `docker run
> kindle-dashboard:local` o col pulsante **Run** di Docker Desktop il processo esce subito con
> `errore di configurazione: configurazione non trovata: config.toml` (exit code 2) e il container
> resta lì come `Exited`. Il comando giusto è `docker compose up -d`. Per un comando one-shot
> esplicito: `docker run --rm -v "$PWD/config.toml:/home/appuser/config.toml:ro"
> kindle-dashboard:local render`.

---

### Deploy su target remoto (Raspberry Pi, thin client, VPS)

```bash
# Sul target
git clone <repo-url> kindle_dashboard
cd kindle_dashboard
git checkout docker-support        # o tag di release
cp config.example.toml config.toml
vim config.toml                    # lat/lon, calendari, treni, ecc.
docker compose up -d
```
Il Kindle punterà a `http://<ip-target>:8787/panel.html`.

Gli aggiornamenti successivi (fetch dei tag, backup dell'immagine, build, verifica, rollback) sono in
[docs/docker.md §7](docs/docker.md#aggiornare-un-server-di-casa-via-ssh).

---

### Avvio automatico del server (senza Docker)

Il pannello si aggiorna solo se il server sul PC è acceso. Per non lanciarlo a mano:

```powershell
powershell -ExecutionPolicy Bypass -File .\kindle\autostart.ps1 -Enable    # attiva
powershell -ExecutionPolicy Bypass -File .\kindle\autostart.ps1 -Disable   # disattiva
powershell -ExecutionPolicy Bypass -File .\kindle\autostart.ps1            # stato
```

Come funziona: `-Enable` crea la scorciatoia **`kindle-dashboard.lnk`** nella cartella *Esecuzione
automatica* dell'utente (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`), che lancia
`kindle\serve.ps1` con finestra nascosta. Niente privilegi di amministratore, niente servizi di
sistema: `-Disable` cancella la scorciatoia e l'avvio automatico sparisce.

- Ha effetto **dal prossimo accesso a Windows**. Per avviarlo subito:
  `powershell -ExecutionPolicy Bypass -File .\kindle\serve.ps1` (o `python -m kindle_dashboard serve`
  se vuoi vedere l'output nel terminale).
- I messaggi del server finiscono in **`cache\server.log`**, compresi gli errori come *"porta 8787 non
  disponibile: chiudi l'istanza già in ascolto"*.
- `-Status` dice anche se il server è in ascolto e con quale PID.
- Per fermarlo senza disattivare l'avvio automatico:
  `Get-NetTCPConnection -LocalPort 8787 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess }`.

### Estensione KUAL (diagnostica)

L'estensione in `kindle/extensions/dashboard/` non disegna nulla: serve a capire perché il Kindle non
raggiunge il PC. Voci:

| Voce | Cosa fa |
|---|---|
| Verifica server | scarica `/panel.png` e scrive esito e dimensione in `/mnt/us/dashboard/dashboard.log` |
| Diagnostica | kernel, percorsi di `wget`/`eips`, batteria, URL e poi la verifica server |
| Tieni schermo acceso | `lipc-set-prop com.lab126.powerd preventScreenSaver 1`: niente salvascherino mentre guardi il pannello |
| Riattiva salvascherino | riporta la proprietà a `0` quando hai finito |

Con il pannello aperto nel browser il Kindle va in salvascherino dopo il timeout di inattività: usa
**Tieni schermo acceso** (vale fino al riavvio del device) e, se serve, aumenta il timeout schermo
nelle impostazioni. L'esito del comando finisce nel log, così si vede subito se il firmware lo accetta.

Il motivo per cui il disegno nativo non è la strada predefinita è documentato nei "Limiti noti".

## Comandi

| Comando | Cosa fa |
|---|---|
| `python -m kindle_dashboard render [-o preview.png]` | genera il PNG una volta |
| `python -m kindle_dashboard serve` | serve `/panel.png` e `/health` |
| `python -m kindle_dashboard resolve-station "Genova Brignole"` | trova lo `stop_id` |
| `.\kindle\deploy.ps1` | copia l'estensione KUAL sul Kindle |

Tutti accettano `--config <file>` dopo il sottocomando.

## Troubleshooting

| Sintomo | Causa e rimedio |
|---|---|
| `fuso orario 'Europe/Rome' non disponibile` | manca `tzdata`: `python -m pip install tzdata` |
| Nel pannello compaiono quadratini al posto delle accentate o del segno di moltiplicazione | il font scelto non ha quei caratteri: succede dove non è installato nessun TTF, e Pillow usa un font incorporato incompleto | installa un font di sistema (su Debian/Ubuntu `fonts-liberation`, `fonts-dejavu-core` come riserva) oppure indica un `.ttf` in `[render] font` e `font_bold` |
| Nel container le righe finiscono con `…` (`REG 12…`, `SAB 18°/…`, `poco mosso`) mentre l'anteprima sul PC è integra | l'anteprima e il device misurano font diversi: le colonne, misurate con `font.getlength`, tagliano il testo | il PC non sta usando il TTF incluso nel pacchetto. Diagnosi: `python -c "from kindle_dashboard.render import fonts; print(fonts.load(19).path)"` deve stampare un percorso dentro `kindle_dashboard/render/fonts/`, non `C:\WINDOWS\Fonts\…`; se esce dal repo, reinstalla (`python -m pip install -e .`) o togli l'override in `[render] font`/`font_bold`. Se il PC è a posto, è il container a essere vecchio: `docker compose build` + `docker rm -f kindle-dashboard` + `docker compose up -d`. Per il confronto usa `python -m kindle_dashboard render -o preview.png` |
| Voglio cambiare o aggiornare il font del pannello | i TTF stanno nel repo (`kindle_dashboard/render/fonts/`), così PC e device usano lo stesso file | sostituisci `LiberationSans-Regular.ttf`/`LiberationSans-Bold.ttf` (e `OFL.txt` se cambi famiglia: la licenza deve viaggiare con i binari) e rifai **tutte** le misure: `python -m pytest -q`, `python -m kindle_dashboard render -o preview.png`, poi guarda il PNG. Per il container serve ricostruire **e** ricreare (`docker compose build` + `docker rm -f kindle-dashboard` + `docker compose up -d`) |
| Il Kindle non scarica nulla | verifica `http://<ip>:8787/panel.png` dal PC, poi dallo stesso URL nel browser del Kindle; controlla la regola firewall sulla rete privata |
| Dal browser del Kindle "impossibile connettersi" | la rete è classificata **Public** da Windows e la regola `Private` non si applica: lancia `kindle\allow-lan.ps1` come amministratore (riclassifica la rete e apre la porta). Se alterni 2.4/5 GHz, usa `-AnyProfile`: il profilo firewall è per SSID, quindi cambiando banda la regola `Private` smetterebbe di valere |
| Il Kindle non vede la rete Wi-Fi del PC | SSID a 5 GHz: il Kindle 4 ha solo radio 2.4 GHz, collegalo all'SSID 2.4 GHz dello stesso router (stessa subnet, senza "AP isolation") |
| PNG scaricato ma schermo bianco/nero | `fbink` non parte: prova a mano sul device `fbink -q -c -g file=/mnt/us/dashboard/panel.png -W GC16` e leggi `/mnt/us/dashboard/dashboard.log` |
| Il pannello si ferma da solo | standby del Kindle o estensione fermata: rilancia da KUAL e verifica che `lipc-set-prop com.lab126.powerd preventScreenSaver 1` non dia errore |
| Funziona anche con la regola assente | qualcos'altro sta aprendo la porta: vedi il comando sotto la tabella. Una regola `python.exe` su profilo `Public` è più larga di `kindle-dashboard PORT`, che apre una sola porta |
| Si vede ancora la versione vecchia del pannello | il server in ascolto è un'istanza precedente: `Get-NetTCPConnection -LocalPort 8787 -State Listen` e chiudi quel PID; in più ricarica la pagina (l'HTML referenzia `/panel.png?t=<timestamp>` per evitare la cache del browser) |
| `download fallito` nel log | PC spento, IP cambiato (DHCP) o server non avviato: riserva un IP fisso al PC |
| Non vedo "Dashboard" in KUAL | `config.xml` deve dichiarare il menu con `<menus><menu type="json" dynamic="true">menu.json</menu></menus>`: senza quel blocco KUAL non elenca l'estensione (confronta con `extensions/koreader/config.xml`, che funziona). Dopo la copia riapri KUAL; se resta invisibile, riavvia il Kindle |
| Nel calendario vedo solo "URL pubblico" e "iframe" | il calendario non è tuo (lo sottoscrivi): Google non fornisce a chi lo sottoscrive l'indirizzo iCal. Chiedi al proprietario di passarti l'URL segreto o di rendere il calendario pubblico (allora vale `.../ical/<id>/public/basic.ics`), altrimenti serve l'API Google con OAuth |
| Calendario vuoto | `calendar.ics_url` mancante o URL revocato (Google lo rigenera) |
| La colonna della differenziata non compare | `[waste] ics_url` è vuoto: la sezione è spenta e il calendario resta a tutta larghezza |
| Differenziata tutta "niente" | il calendario pubblico copre solo un intervallo di date (Santa Marinella: 01/06/2026–31/12/2026) oppure `waste.ics_url` punta a un altro calendario |

Log del device: `/mnt/us/dashboard/dashboard.log`.

Per capire chi apre davvero la porta (Windows e non solo la regola del progetto):

```powershell
Get-NetFirewallApplicationFilter | Where-Object { $_.Program -like '*python*' } | Get-NetFirewallRule | Select-Object DisplayName,Profile,Direction
```

## Limiti noti

- Layout tarato su 600x800: altre risoluzioni scalano, ma non sono state provate sul campo.
- **Il disegno nativo a schermo intero non è utilizzabile su questo device**: il `fbink` incluso in
  KOReader è compilato senza supporto immagini e `eips` (in `/usr/sbin`) resta bianco con PNG in
  scala di grigi, RGB, 1-bit e JPEG. Fermare il framework per liberare lo schermo porta a schermo
  bianco, unità USB non più esposta e riavvii. Per questo il pannello si guarda nel browser.
- Ricorrenze supportate: `FREQ` DAILY/WEEKLY/MONTHLY/YEARLY con `INTERVAL`, `COUNT`, `UNTIL` e
  `BYDAY` (solo settimanale). Altri `BY*` sono ignorati; un `TZID` sconosciuto ricade sul fuso del
  pannello.
- I treni arrivano da Transitous (MOTIS), servizio comunitario senza API key: se cambia, la sezione
  mostra i dati in cache. ViaggiaTreno non è utilizzabile da script (Akamai Bot Manager).
- Il ritardo è orario atteso meno programmato; i treni senza dati in tempo reale mostrano l'orario
  programmato.
- La destinazione mostrata è l'**etichetta commerciale** del treno (`tripTo`), non l'elenco delle
  fermate: su questa linea molte corse etichettate "Roma Termini" risultano fermare a Roma S.Pietro,
  Trastevere, Ostiense o Tuscolana. Con `trains.stop_details = true` quelle fermate compaiono su **una
  riga** sotto il treno: se non ci stanno si scartano prima quelle non elencate in
  `trains.stop_priority` (una richiesta HTTP per treno mostrato).
- Lo script lato device (`dashboard.sh`) è stato provato con `deploy.ps1 -DryRun` e non ancora su
  schermo: `fbink`, `wget` e `lipc-set-prop` vanno confermati sul singolo firmware.

## Sviluppo

```powershell
python -m ruff check .
python -m pytest -q
```

I due comandi girano nel venv ([docs/venv.md](docs/venv.md)); Docker serve al deploy, non al gate
([docs/docker.md](docs/docker.md)).

Architettura, invarianti e come estendere il progetto: [AGENTS.md](AGENTS.md).
Percorso tecnico narrato (come funziona e perché, con i bug realmente incontrati):
[docs/technical-walkthrough.md](docs/technical-walkthrough.md).
