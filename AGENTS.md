# Mappa tecnica — kindle-dashboard

> I vincoli operativi **non** sono qui: stanno in `.clinerules`.
> Questo file descrive architettura, invarianti e come intervenire senza romperli.

## Architettura

Flusso unidirezionale, nessun ciclo:

```
config.toml -> collect() -> PanelData -> render_panel() -> PNG / HTTP
                   ^
      sources/* (fetch_payload -> parse) + Cache (fallback)
```

| Modulo | Responsabilità | Non deve fare |
|---|---|---|
| `config.py` | leggere/validare il TOML, risolvere i percorsi | chiamare la rete |
| `schedule.py` | decidere fascia giorno/notte e intervallo (con clamp al confine) | leggere config o disegnare |
| `collect.py` | orchestra le tre sezioni, gestisce cache e `Sync` | disegnare |
| `sources/*` | `fetch_payload` (solo rete) + `parse` (solo trasformazione) | formattare per lo schermo |
| `cache.py` | persistere l'ultimo payload buono | contenere modelli |
| `model.py` | dataclass immutabili | importare Pillow |
| `render/*` | disegnare `PanelData` | fare I/O di rete |
| `server.py` | HTTP + cache del PNG in memoria | contenere layout |
| `__main__.py` | CLI sottile | logica di dominio |

### Invarianti

1. **`fetch_payload` e `parse` restano separati** in ogni sorgente: è ciò che permette di salvare il
   payload grezzo in cache e ri-analizzarlo quando la fonte cade. Non unirli.
2. **Ogni sezione è indipendente**: un errore su una fonte non impedisce il disegno delle altre. Il
   fallimento si rappresenta con `Sync(error=..., stale=...)`, non con un'eccezione che risale.
3. **Tutti gli orari sono aware e nel fuso di `config.weather.timezone`**; `ZoneInfo` si crea solo in
   `timezone_utils.zone()`.
4. **L'ora mostrata è quella del PC** (baked nel PNG): il clock del Kindle non viene mai letto.
5. **Il renderer produce un'immagine "L"** alla risoluzione `panel.width/height` e non ridimensiona:
   il device non deve scalare nulla.
6. **Le larghezze di colonna si misurano con `font.getlength`**, mai con pixel fissi.
7. **L'intervallo di aggiornamento si calcola solo in `schedule.py`**: fascia corrente e clamp al
   prossimo cambio. Server e renderer leggono quel risultato, non lo ricalcolano.

### Configurazione

TOML con sezioni `panel`, `location`, `weather`, `calendar`, `trains`, `render`, `server`, `cache`.
`load_config()` restituisce dataclass immutabili; un valore non valido produce `ConfigError` con il
nome della sezione coinvolta. `calendar.ics_url` può arrivare da `KDASH_ICS_URL` solo se il file non
lo specifica. Una sezione assente disattiva la relativa parte del pannello, non è un errore.

## Come estendere

### Nuova fonte dati
1. `sources/<nome>.py`: `fetch_payload(...)` (usa `sources/http.get_json`/`get_text`) e
   `parse(payload, ...)` che restituisce dataclass di `model.py` o lancia `SourceError`.
2. Modello in `model.py` (frozen) + campo in `PanelData` e relativo `Sync`.
3. Sezione TOML in `config.py` (dataclass + helper `_str`/`_int`/`_number`) e in `config.example.toml`.
4. `collect.py`: `_<nome>(config, cache, moment)` sul modello di `_weather` (fetch → store → parse,
   `except SourceError` → cache), poi valorizza `PanelData`.
5. Blocco di disegno in `render/panel.py` e chiamata dentro `render_panel`.
6. `tests/test_<nome>.py` con fixture registrata.

### Nuovo blocco nel pannello
1. `_draw_<blocco>(draw, style, data, y) -> int` in `render/panel.py`.
2. Usa `style.px()` per le misure e `fit_text()` per i testi: righe e larghezze dai font.
3. Rispetta il budget verticale (`_TITLE_ROW_PX` per il titolo, costante di riga dedicata) e la
   regola "i treni hanno lo spazio riservato in fondo".
4. Aggiorna `tests/test_render.py` e rigenera `preview.png`.
5. Il blocco agenda (`_draw_agenda`) ha due colonne solo quando `PanelData.waste` non è `None`: le
   larghezze vengono da `_EVENTS_SHARE` e `_COLUMN_GUTTER_PX`, non da pixel scelti a occhio.

### Nuovo comando CLI
1. `commands.add_parser(..., parents=[common])` in `_build_parser()` (il parent fornisce `--config`).
2. `_cmd_<nome>(args) -> int` con `set_defaults(handler=...)`; errori utente su stderr e exit code
   diverso da zero.

### Nuova opzione di configurazione
Aggiungila alla dataclass, a `config.example.toml` e alla tabella in `README.md`: le tre cose devono
restare allineate.

## Test e verifica

| Comando | Cosa copre |
|---|---|
| `python -m pytest -q` | 87 test: parsing, ricorrenze ICS, raccolta differenziata, config, pianificazione giorno/notte, cache, render, HTTP |
| `python -m ruff check .` | stile (line-length 110, regole E/F/I/UP/B/SIM/RUF) |
| `python -m kindle_dashboard render -o preview.png` | verifica visiva reale |

- Fixture in `tests/fixtures/`; `conftest.py` espone `read_fixture`, `load_json`, `rome`.
- Isolamento obbligatorio: `monkeypatch` di `fetch_payload`/`get_json`, `tmp_path` per la cache,
  `FakeService` + `build_server()` per l'HTTP. Niente rete, niente filesystem utente, niente `G:\`.
- I test del renderer asseriscono dimensioni, mode e contenuto: niente snapshot fragili sui pixel.

## Verifiche sul device (aggiornato alle prove reali)

Confermato su un Kindle 4 (`Linux kindle 2.6.31-rt11-lab126`, FBInk lo identifica come
`Tequila on Yoshi`):

- `wget` presente (`/usr/bin/wget`): il download del PNG funziona.
- `eips` esiste ma in **`/usr/sbin/eips`** (non `/usr/bin`), e **non mostra immagini**: con quattro
  formati (grigi, RGB, 1-bit, JPEG) lo schermo resta bianco pur con exit code 0.
- il `fbink` incluso in KOReader è **MINIMAL**: `[FBInk] Image support is disabled in this FBInk
  build!`.
- `/etc/init.d/framework stop` libera lo schermo ma porta a **schermo bianco, unità USB non più
  esposta e riavvio** del device: non è una strada percorribile qui.
- KUAL elenca l'estensione solo se `config.xml` contiene
  `<menus><menu type="json" dynamic="true">menu.json</menu></menus>`.

Conseguenza di progetto: **la visualizzazione passa dal browser** (`/panel.html` con meta refresh);
l'estensione KUAL è solo diagnostica (`Verifica server`, `Diagnostica`). Non reintrodurre il disegno
nativo su questo hardware senza una prova concreta che funzioni.

Ancora da confermare: comportamento della batteria con la pagina aperta per ore.

## File → per chi

| File | Destinatario |
|---|---|
| `README.md` | utente: installazione, configurazione, troubleshooting |
| `.clinerules` | chi scrive codice: vincoli e gate di commit |
| `AGENTS.md` | agenti/sviluppatori: architettura, estensioni, mappa dei test |
| `docs/technical-walkthrough.md` | chi studia il progetto: percorso tecnico narrato, con i bug reali |
| `config.example.toml` | utente: modello di configurazione commentato |
| `tests/` | sviluppatori: comportamento atteso, da aggiornare con le modifiche |
| `kindle/` | deploy: estensione KUAL + script host |
