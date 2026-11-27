"""Gli script del device e le voci KUAL devono restare allineati.

Una voce di menu che chiama un parametro inesistente non produce un errore visibile: KUAL esegue
`dashboard.sh` con quel parametro, lo script risponde con l'uso ed esce con codice 2, e a schermo
sembra semplicemente che «non faccia niente». Il test confronta `menu.json` con i rami del `case`
del template e impone i finali di riga LF, senza eseguire nulla sul device.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTENSION = REPO_ROOT / "kindle" / "extensions" / "dashboard"
TEMPLATE = EXTENSION / "dashboard.sh.template"
MENU = EXTENSION / "menu.json"
DEPLOYED_ACTION = "/mnt/us/extensions/dashboard/dashboard.sh"
DEPLOY = REPO_ROOT / "kindle" / "deploy.ps1"
# I rami del `case "$1" in` sono indentati di quattro spazi e finiscono con ``)``.
# Accettiamo lettere minuscole e underscore (es. wifi_off, wifi_on).
_COMMAND_PATTERN = re.compile(r"^    ([a-z_]+)\)$", re.MULTILINE)


def _commands() -> set[str]:
    return set(_COMMAND_PATTERN.findall(TEMPLATE.read_text(encoding="utf-8")))


def _menu_items() -> list[dict[str, str]]:
    return json.loads(MENU.read_text(encoding="utf-8"))["items"]


def test_every_menu_entry_calls_a_real_command() -> None:
    commands = _commands()
    for item in _menu_items():
        command = item["params"].split()[0]
        assert command in commands, f"{item['name']}: comando '{command}' assente nel template"


def test_every_command_has_a_menu_entry() -> None:
    """Un comando senza voce di menu è quasi sempre codice morto: non lo raggiunge nessuno."""
    assert _commands() == {item["params"].split()[0] for item in _menu_items()}


def test_menu_actions_point_to_the_deployed_script() -> None:
    for item in _menu_items():
        assert item["action"] == DEPLOYED_ACTION


def test_template_uses_lf_and_ends_with_newline() -> None:
    """`sh` non tollera `\\r`: un file scritto da Windows senza questa regola non parte affatto."""
    raw = TEMPLATE.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")


def test_function_braces_are_balanced() -> None:
    """Una `}` dimenticata non produce nessun errore visibile sul device: `sh` esce subito con
    «syntax error: unexpected end of file» e KUAL torna al menu, quindi sembra che il comando non
    faccia niente. È già successo con `inventory`; qui si controlla il bilanciamento delle graffe
    nello stile del file (`nome() {` a inizio riga, `}` da solo a chiudere).
    """
    depth = 0
    for number, line in enumerate(TEMPLATE.read_text(encoding="utf-8").splitlines(), start=1):
        if line.endswith("() {") and line[0].isalpha():
            depth += 1
        elif line == "}":
            depth -= 1
            assert depth >= 0, f"graffa di chiusura in più alla riga {number}"
    assert depth == 0, f"{depth} funzione/i non chiusa/e nel template"


def _code_lines() -> str:
    """Il template senza i commenti: le regole su BusyBox valgono per il codice eseguito, e i
    commenti citano apposta le opzioni assenti."""
    return "\n".join(
        line
        for line in TEMPLATE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_template_only_uses_options_that_busybox_171_has() -> None:
    """BusyBox 1.7.2 non ha `wget -T`, `grep -E` né `command -v`: un'opzione in più è un comando che
    sul device fallisce, e lo si scoprirebbe solo dopo il deploy."""
    code = _code_lines()
    for forbidden in ("wget -T", "grep -E", "command -v"):
        assert forbidden not in code, f"BusyBox 1.7.2 non ha {forbidden!r}"


def test_template_has_one_placeholder_per_rendered_value() -> None:
    """Un segnaposto duplicato produrrebbe uno script che usa il valore sbagliato a seconda del ramo."""
    template = TEMPLATE.read_text(encoding="utf-8")
    for placeholder in ("__HOST__", "__PORT__", "__REFRESH__"):
        assert template.count(f'"{placeholder}"') == 1, placeholder
    # Il failover multi-host è stato provato il 2026-11-15 ed è stato tolto: non deve rientrare qui
    # per caso, perché con un host spento in testa costava 15 s di watchdog a ogni giro.
    assert "HOSTS" not in template


def test_deploy_renders_host_port_and_cadence_from_config() -> None:
    """`deploy.ps1` è l'unico punto in cui l'indirizzo del device diventa testo: se non legge
    `device_host` e `refresh_seconds` da config.toml, il Kindle torna a puntare all'IP del momento."""
    deploy = DEPLOY.read_text(encoding="utf-8-sig")
    for placeholder in ("__HOST__", "__PORT__", "__REFRESH__"):
        assert f'.Replace("{placeholder}"' in deploy, placeholder
    assert "c.server.device_host" in deploy
    assert "c.panel.refresh_seconds" in deploy


def test_the_native_cycle_is_the_first_menu_entry() -> None:
    """La promozione a visualizzazione predefinita è un ordine di menu: se davanti c'è una voce di
    test, «finale» non è. Le priorità devono restare uniche, altrimenti l'ordine è ambiguo."""
    items = _menu_items()
    assert len({item["priority"] for item in items}) == len(items)
    assert min(items, key=lambda item: item["priority"])["params"] == "cycle"


def test_cycle_falls_back_to_the_daily_cadence_and_backs_off() -> None:
    """Con il server spento il ciclo non deve svegliare il device ogni 30 s per ore: usa la cadenza
    di `[panel] refresh_seconds` e poi attese crescenti con un tetto. `sh` non si esegue nei test,
    quindi la prova è nel codice del template."""
    template = TEMPLATE.read_text(encoding="utf-8")
    assert 'wait_s="$(next_seconds)" || wait_s="$REFRESH_SECONDS"' in template
    assert 'REFRESH_SECONDS="__REFRESH__"' in template
    assert "FAILS_BEFORE_BACKOFF" in template
    assert "BACKOFF_MAX" in template
    # Il ciclo deve contare i download falliti: senza il contatore il backoff non si attiva mai.
    assert "fails=$((fails + 1))" in template
