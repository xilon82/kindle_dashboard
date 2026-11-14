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
# I rami del `case "$1" in` sono indentati di quattro spazi e finiscono con ``)``.
_COMMAND_PATTERN = re.compile(r"^    ([a-z]+)\)$", re.MULTILINE)


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
