# kindle-dashboard

Pannello e-ink per un Kindle jailbroken: **meteo**, **Google Calendar** e **partenze dei treni**
vengono raccolti sul PC e disegnati in un PNG da 600x800 (risoluzione nativa del Kindle 4/Touch).
Il Kindle non esegue codice del progetto: scarica il PNG via WiFi e lo mostra a schermo intero con
FBInk. Un pannello non deve mai bloccarsi, quindi ogni sezione ha un fallback.

## Requisiti

- PC acceso con Python 3.11+ (verificato su Windows 11, Python 3.13).
- Kindle jailbroken con **KUAL** installato e **KOReader** (fornisce il binario `fbink`), collegato
  alla stessa rete del PC. Verificato su un Kindle 4 (`reader.lua` riporta `device Kindle4`,
  600x800 @ 167 dpi). Attenzione: il Kindle 4 ha solo Wi-Fi **2.4 GHz**, quindi il PC deve essere
  raggiungibile da quell'SSID (stessa subnet).
- Nessuna API key: meteo da Open-Meteo, treni da Transitous.

## Installazione

```powershell
python -m pip install -e .
```

Su Windows il pacchetto `tzdata` è obbligatorio: il sistema non fornisce il database dei fusi
orari usato da `zoneinfo`. È dichiarato in `pyproject.toml`, non serve installarlo a mano.

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
| `weather` | `days` | 3 | giorni di previsione disegnati (max 7) |
| `weather` | `timezone` | `Europe/Rome` | fuso usato per orari, calendario e treni |
| `calendar` | `ics_url` | vuoto | URL iCal segreto di Google Calendar |
| `calendar` | `max_events`, `days_ahead` | 4, 7 | quanti eventi e su quanti giorni |
| `trains` | `station`, `stop_id` | — | stazione del tabellone (assente = niente treni) |
| `trains` | `max_departures` | 4 | partenze mostrate |
| `trains` | `destinations` | `[]` | filtro per sottostringa (vuoto = tutte) |
| `trains` | `stop_details` | `false` | seconda riga per treno con le fermate che corrispondono a `destinations` (una richiesta HTTP per treno) |
| `trains` | `stop_priority` | `[]` | fermate da tenere sempre quando la riga non basta: le altre vengono ridotte |
| `render` | `font`, `font_bold` | vuoto | percorsi TTF alternativi a quelli di sistema |
| `server` | `host`, `port` | `0.0.0.0`, 8787 | dove ascolta il PC |
| `server` | `data_ttl_seconds` | 300 | per quanto il server riusa i dati raccolti prima di richiamare le API |
| `cache` | `dir` | `cache` | ultimo payload buono, mostrato quando una fonte cade |

### Google Calendar

Google Calendar > Impostazioni del calendario > *Indirizzo segreto in formato iCal*: incolla l'URL
in `calendar.ics_url`. In alternativa usa la variabile d'ambiente `KDASH_ICS_URL`, che ha la
precedenza solo se il file non specifica nulla: utile per non scrivere la credenziale su disco.

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

La pagina mostra il PNG e si **ricarica da sola** ogni `refresh_seconds`. Non serve installare nulla
sul device e non si tocca il framework: l'unità USB resta disponibile, il Kindle si comporta
normalmente e per fermare il pannello basta uscire dal browser.

Per tenerlo visibile: alimentazione da caricatore (non dalla porta USB del PC) e timeout schermo al
massimo nelle impostazioni. Se compare il salvascherino, un tocco riporta la pagina.

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

Architettura, invarianti e come estendere il progetto: [AGENTS.md](AGENTS.md).
