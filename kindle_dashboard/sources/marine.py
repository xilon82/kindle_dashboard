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

# Scala Douglas ufficiale (gradi 0-9): soglia inferiore in metri, grado, parola e famiglia di
# glifo. Una sola tabella e tre letture (forza, parola, glifo): la striscia usa la forza perché in
# una colonna da 185 px "F3" costa 15 px contro i 75 di "poco mosso". Il confronto è ">=", quindi
# 0.50 m è già "mosso" (F3) e 0.10 m è già "poco mosso" (F2). I due estremi stanno fuori tabella
# perché il bollettino li scrive aperti: oltre 14 m c'è il grado 9, e il grado 0 è "fino a 2 cm
# inclusi" — Open-Meteo Marine non scende sotto 0.02 m, quindi il fondo scala del modello *è* il
# suo "0 m".
_STATES: tuple[tuple[float, int, str, str], ...] = (
    (0.10, 2, "poco mosso", "sea_slight"),
    (0.50, 3, "mosso", "sea_moderate"),
    (1.25, 4, "molto mosso", "sea_rough"),
    (2.50, 5, "agitato", "sea_rough"),
    (4.00, 6, "molto agitato", "sea_rough"),
    (6.00, 7, "grosso", "sea_rough"),
    (9.00, 8, "molto grosso", "sea_rough"),
)
_CALM = (0, "calmo", "sea_calm")
_CALM_TO_M = 0.02
_QUASI_CALM = (1, "quasi calmo", "sea_calm")
_TEMPESTUOUS = (9, "tempestoso", "sea_rough")
_TEMPESTUOUS_FROM_M = 14.0


def state_force(height: float) -> int:
    """Grado Douglas (0-9) dell'altezza d'onda: ``F3`` nella striscia delle previsioni."""
    return _state(height)[0]


def state_label(height: float) -> str:
    """Descrizione italiana dello stato del mare (scala Douglas ufficiale)."""
    return _state(height)[1]


def state_kind(height: float) -> str:
    """Chiave del glifo da disegnare (vedi ``render.icons``)."""
    return _state(height)[2]


def height_label(height: float) -> str:
    """Altezza d'onda compatta per lo schermo: ``0.6m``, ma ``8cm`` sotto i 10 cm.

    Le fasce dei gradi 1 e 2 sono larghe 10 e 40 cm, quindi un decimale in metri basta da 0,10 m in
    su; sotto, il modello lavora a passi da 2 cm e ``0.08 m`` stampato ``0.1m`` uscirebbe dalla
    fascia "quasi calmo" (< 0,10 m). In centimetri il numero resta esatto e costa due caratteri in
    meno, che nella colonna da 185 px sono la direzione del vento.
    """
    if height < 0.10:
        return f"{round(height * 100)}cm"
    return f"{height:.1f}m"


def _state(height: float) -> tuple[int, str, str]:
    """Classifica l'altezza del dato, non quella stampata sul pannello.

    Le fasce dei gradi 0-2 sono larghe 10 e 40 cm, meno di un passo di visualizzazione:
    arrotondando, "quasi calmo" sarebbe irraggiungibile (0,08 m si scrive ``0.1m``) e i primi
    5 cm di ogni fascia finirebbero nel grado superiore (0,46 m letto "mosso"). Il grado 0 arriva
    a 0,02 m inclusi perché è il minimo che il modello sa rappresentare: chiamarlo "calmo" è più
    onesto che far apparire "quasi calmo" l'unico valore di fondo scala.
    """
    if height <= _CALM_TO_M:
        return _CALM
    if height > _TEMPESTUOUS_FROM_M:
        return _TEMPESTUOUS
    chosen = _QUASI_CALM
    for lower, force, label, kind in _STATES:
        if height < lower:
            break
        chosen = (force, label, kind)
    return chosen


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
