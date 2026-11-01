"""Mare da Open-Meteo Marine: servizio pubblico, nessuna API key.

``fetch_payload`` restituisce il JSON grezzo (così può essere messo in cache e ri-analizzato),
``parse`` lo trasforma nel modello di dominio. Lo stato del mare è la scala Douglas, la stessa
che si legge sui bollettini italiani.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..exceptions import SourceError
from ..model import Sea, SeaDay, SeaNow
from .http import DEFAULT_TIMEOUT, get_json
from .values import optional_float

API_URL = "https://marine-api.open-meteo.com/v1/marine"

_CURRENT_FIELDS = "wave_height,sea_surface_temperature"
_DAILY_FIELDS = "wave_height_max"

# Scala Douglas: soglia superiore in metri, forza, descrizione italiana e famiglia di glifo.
# Una sola tabella e tre letture (forza, parola, glifo): la striscia usa la forza perché in una
# colonna da 185 px "F3" costa 15 px contro i 75 di "poco mosso".
_STATES: tuple[tuple[float, int, str, str], ...] = (
    (0.1, 0, "calmo", "sea_calm"),
    (0.5, 1, "quasi calmo", "sea_calm"),
    (1.25, 2, "poco mosso", "sea_slight"),
    (2.5, 3, "mosso", "sea_moderate"),
    (4.0, 4, "molto mosso", "sea_rough"),
    (6.0, 5, "agitato", "sea_rough"),
    (9.0, 6, "molto agitato", "sea_rough"),
)
_ROUGHEST = (7, "grosso", "sea_rough")


def state_force(height: float) -> int:
    """Grado Douglas (0-9) dell'altezza d'onda: ``F3`` nella striscia delle previsioni."""
    return _state(height)[0]


def state_label(height: float) -> str:
    """Descrizione italiana dello stato del mare (scala Douglas)."""
    return _state(height)[1]


def state_kind(height: float) -> str:
    """Chiave del glifo da disegnare (vedi ``render.icons``)."""
    return _state(height)[2]


def height_label(height: float) -> str:
    """Altezza d'onda compatta per lo schermo: ``0.6m``."""
    return f"{height:.1f}m"


def _state(height: float) -> tuple[int, str, str]:
    """Classifica sull'altezza arrotondata a un decimale, la stessa che si legge sul pannello.

    Altrimenti ``0.48 m`` verrebbe scritto ``0.5m`` e classificato "quasi calmo", mentre ``0.50 m``
    è "poco mosso": due stati diversi dietro lo stesso numero mostrato.
    """
    shown = round(height, 1)
    for limit, force, label, kind in _STATES:
        if shown < limit:
            return force, label, kind
    return _ROUGHEST


def fetch_payload(
    latitude: float,
    longitude: float,
    *,
    days: int,
    timezone: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    payload = get_json(
        API_URL,
        [
            ("latitude", f"{latitude:.4f}"),
            ("longitude", f"{longitude:.4f}"),
            ("current", _CURRENT_FIELDS),
            ("daily", _DAILY_FIELDS),
            ("timezone", timezone),
            ("forecast_days", days),
        ],
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        raise SourceError("mare: risposta inattesa (non è un oggetto JSON)")
    return payload


def parse(payload: dict[str, Any], *, days: int) -> Sea:
    """Costruisce il modello dal JSON Open-Meteo Marine, con errori espliciti se mancano campi."""
    try:
        current = payload["current"]
        daily = payload["daily"]
        now = SeaNow(
            wave_height=float(current["wave_height"]),
            water_temperature=optional_float(current.get("sea_surface_temperature")),
        )
        forecasts = tuple(
            SeaDay(
                day=date.fromisoformat(str(daily["time"][index])),
                wave_height_max=float(daily["wave_height_max"][index]),
            )
            for index in range(min(days, len(daily["time"])))
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SourceError(f"mare: risposta incompleta ({exc})") from exc
    if not forecasts:
        raise SourceError("mare: nessuna previsione giornaliera nella risposta")
    return Sea(now=now, days=forecasts)
