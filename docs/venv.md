# Il virtual environment (venv): guida didattica

> Cosa isola un `venv`, perché serve, come si crea, quali sono i suoi limiti.
> In `kindle-dashboard` il venv è l'ambiente di **sviluppo e test**; il container
> ([docs/docker.md](docker.md)) è l'ambiente di **deploy**.

## 1. Il problema: un solo `site-packages` per tutto il sistema

Un'installazione Python "normale" ha una sola cartella di pacchetti condivisa da tutte le
applicazioni della macchina. Basta poco perché si rompa:

| Situazione | Cosa succede senza venv |
|---|---|
| Due progetti chiedono versioni diverse di `pillow` | vince l'ultima installata: uno dei due si rompe |
| `pip install --upgrade` su una libreria condivisa | un altro script che la usava smette di funzionare |
| Python 3.13 e 3.14 installati insieme | `python` e `pip` puntano a interpreti diversi e i pacchetti finiscono "nel posto sbagliato" |
| Vuoi ricreare l'ambiente su un altro PC | senza un elenco delle versioni non sai cosa reinstallare |

In questo progetto le dipendenze sono poche ma pesanti: `pillow` (estensioni C compilate) e
`tzdata` (database IANA dei fusi orari, obbligatorio su Windows: senza, `ZoneInfo("Europe/Rome")`
fallisce). Un `pip install` globale che sovrascrive la `pillow` di un altro progetto è esattamente
l'incidente che il venv evita.

## 2. Cosa è (e cosa non è) un venv

`python -m venv .venv` crea una cartella che contiene:

- un **interprete** (su Windows una copia, su Linux un link al `python` di sistema);
- un `pip` proprio, legato a quell'interprete;
- un `site-packages/` proprio, dove finiscono i pacchetti installati;
- gli script di attivazione (`Activate.ps1` su Windows, `activate` su Linux/macOS), che mettono
  quel `python` in testa al `PATH`.

Non è una macchina virtuale: condivide kernel, sistema operativo, driver e librerie di sistema.
Isola **solo** i pacchetti Python. Da questa distinzione nasce la divisione dei compiti con Docker:

| Risorsa | Il venv la isola? |
|---|---|
| Pacchetti Python (`pillow`, `tzdata`, `pytest`) | sì |
| Versione dell'interprete | parzialmente (quella con cui crei il venv) |
| Librerie C di sistema (`libjpeg`, `zlib`, `glibc`) | no |
| Kernel, driver, servizi, firewall, utenti | no |

## 3. Creazione, attivazione, disattivazione

Dalla radice del repository:

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

- `.venv` è il nome convenzionale: lo riconoscono VS Code e la maggior parte dei tool, ed è già in
  `.gitignore`, quindi non finisce nel repository.
- `pip install -e .` è un'installazione *editable*: i sorgenti restano dove sono e le modifiche sono
  attive subito. Le dipendenze (`pillow`, `tzdata`) arrivano da `pyproject.toml`.
- Verifica: `python -c "import sys; print(sys.prefix)"` deve stampare il percorso di `.venv`; se
  stampa un percorso di sistema l'attivazione non ha funzionato.
- Uscita: `deactivate`.

### Perché `python -m pip` e non `pip`

`python -m pip` esegue il `pip` **dell'interprete che hai davanti**. Il comando `pip` nudo, invece,
può essere un altro script nel `PATH` (o l'alias del Microsoft Store): installi nell'ambiente
sbagliato e non te ne accorgi. Vale per tutti gli strumenti: `python -m ruff`, `python -m pytest`.

### Errori tipici su Windows

| Sintomo | Causa | Rimedio |
|---|---|---|
| `Activate.ps1 ... non può essere caricato` | Execution Policy blocca gli script | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (vale solo per la sessione) |
| `python` apre il Microsoft Store | alias "App execution" di Windows | usa `py -3.13 -m venv .venv` oppure disattiva gli alias in Impostazioni > App > Alias di esecuzione app |
| `pip` installa fuori da `.venv` | ambiente non attivato, o `pip` di un altro interprete | usa `python -m pip` e verifica `sys.prefix` |
| VS Code non vede il venv | interprete non selezionato | "Python: Select Interpreter" → `.venv\Scripts\python.exe` |

### Dipendenze di sviluppo

`pyproject.toml` dichiara solo le dipendenze di runtime. Gli strumenti del gate (`pytest`, `ruff`)
vanno installati **nel venv**, così non finiscono nell'ambiente globale:

```powershell
python -m pip install pytest ruff
```

Se vuoi che siano dichiarati una volta per tutte, il posto naturale è un extra
`[project.optional-dependencies] dev = [...]` in `pyproject.toml`: è una modifica da concordare,
perché cambia il contratto di installazione del progetto.

## 4. Vantaggi e svantaggi

| Vantaggi | Svantaggi |
|---|---|
| Isola i pacchetti Python: due progetti, due versioni di `pillow`, nessun conflitto | Non isola le librerie di sistema: se manca `libjpeg` il venv non aiuta |
| Nessun privilegio: niente `sudo`/amministratore, tutto in una cartella di progetto | Va attivato a ogni sessione: dimenticarlo è la causa più comune di errori |
| Ricreabile: cancelli `.venv`, reinstalli, torni allo stesso stato | Occupa spazio per ogni progetto (qui poche decine di MB) |
| Debugger dell'IDE e reload automatico funzionano senza configurazione | Non garantisce la stessa versione di Python su macchine diverse (servono pyenv/uv o un container) |
| Stesso `pyproject.toml` del container: sviluppo e deploy condividono le dipendenze | Non riproduce differenze di OS, kernel o librerie C |

In una frase: il venv risolve i conflitti **fra applicazioni Python sulla stessa macchina**; non
risolve le differenze **fra macchine**. Per quelle serve il container.

## 5. Ricreare l'ambiente da zero

Un venv è monouso: se si corrompe, si butta. Dalla radice del repository:

```powershell
Remove-Item -Recurse -Force .venv    # distruttivo: cancella solo l'ambiente, non i sorgenti
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install pytest ruff
```

```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install pytest ruff
```

Nel `.venv` non c'è nulla di tuo: sorgenti, `config.toml` e `cache/` stanno fuori. La cancellazione
è quindi sicura, ma va confermata: `Remove-Item -Recurse -Force` e `rm -rf` non chiedono permesso.

## 6. Venv o Docker? Chi fa cosa in questo progetto

| Esigenza | Strumento | Comando |
|---|---|---|
| Scrivere codice, test, lint con feedback immediato | venv | `python -m ruff check .` / `python -m pytest -q` |
| Anteprima del pannello | venv | `python -m kindle_dashboard render -o preview.png` |
| Server 24/7 su un dispositivo dedicato | container | `docker compose up -d` |
| Verificare che giri identico su un'altra macchina | container | `docker compose build && docker compose up -d` |

Il venv è l'ambiente di sviluppo; il container è l'artefatto di deploy. Non sono alternativi: sono
due livelli di isolamento diversi. Dettagli in [docs/docker.md](docker.md).

## 7. Il gate di qualità

Prima di ogni commit, con il venv attivo:

```powershell
python -m ruff check .
python -m pytest -q
```

Sono i due comandi del progetto (vedi `.clinerules`): stile e comportamento. I test girano offline,
con fixture registrate e `monkeypatch` delle chiamate di rete, quindi il venv non ha bisogno di
credenziali né di connessione.

## 8. Riferimenti

- [venv — Creation of virtual environments](https://docs.python.org/3/library/venv.html)
- [pip: installazioni locali in modalità editable](https://pip.pypa.io/en/stable/topics/local-project-installs/)
- [VS Code: Python environments](https://code.visualstudio.com/docs/python/environments)
