"""Meteo da Open-Meteo: servizio pubblico, nessuna API key.

``fetch_payload`` restituisce il JSON grezzo (così può essere messo in cache e ri-analizzato),
``parse`` lo trasforma nel modello di dominio.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..exceptions import SourceError
from ..model import DayForecast, Weather, WeatherNow
from .http import DEFAULT_TIMEOUT, get_json

API_URL = "https://api.open-meteo.com/v1/forecast"

_CURRENT_FIELDS = "temperature_2m,weather_code,apparent_temperature,precipitation,wind_speed_10m"
_DAILY_FIELDS = "weather_code,temperature_2m_max,temperature_2m_min"

_LABELS: dict[int, str] = {
    0: "sereno",
    1: "quasi sereno",
    2: "poco nuvoloso",
    3: "coperto",
    45: "nebbia",
    48: "nebbia con brina",
    51: "pioviggine",
    53: "pioviggine",
    55: "pioviggine forte",
    56: "pioviggine gelata",
    57: "pioviggine gelata",
    61: "pioggia debole",
    63: "pioggia",
    65: "pioggia forte",
    66: "pioggia gelata",
    67: "pioggia gelata",
    71: "neve debole",
    73: "neve",
    75: "neve forte",
    77: "granelli di neve",
    80: "rovesci",
    81: "rovesci",
    82: "rovesci violenti",
    85: "rovesci di neve",
    86: "rovesci di neve",
    95: "temporale",
    96: "temporale con grandine",
    99: "temporale con grandine",
}

_ICON_GROUPS: tuple[tuple[str, frozenset[int]], ...] = (
    ("sun", frozenset({0, 1})),
    ("partly", frozenset({2})),
    ("fog", frozenset({45, 48})),
    ("storm", frozenset({95, 96, 97, 98, 99})),
    ("snow", frozenset({71, 73, 75, 77, 85, 86})),
    ("rain", frozenset({61, 63, 65, 66, 67, 80, 81, 82})),
    ("drizzle", frozenset({51, 53, 55, 56, 57})),
    ("cloud", frozenset({3})),
)


def label(code: int) -> str:
    """Descrizione italiana del codice WMO."""
    return _LABELS.get(code, "non disponibile")


def icon_kind(code: int) -> str:
    """Chiave del glifo da disegnare (vedi ``render.icons``)."""
    for kind, codes in _ICON_GROUPS:
        if code in codes:
            return kind
    return "cloud"


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
            ("temperature_unit", "celsius"),
            ("wind_speed_unit", "kmh"),
            ("precipitation_unit", "mm"),
        ],
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        raise SourceError("meteo: risposta inattesa (non è un oggetto JSON)")
    return payload


def parse(payload: dict[str, Any], *, days: int) -> Weather:
    """Costruisce il modello dal JSON Open-Meteo, con errori espliciti se mancano campi."""
    try:
        current = payload["current"]
        daily = payload["daily"]
        now = WeatherNow(
            temperature=float(current["temperature_2m"]),
            code=int(current["weather_code"]),
            apparent=_optional_float(current.get("apparent_temperature")),
            precipitation_mm=_optional_float(current.get("precipitation")),
            wind_kmh=_optional_float(current.get("wind_speed_10m")),
        )
        forecasts = tuple(
            DayForecast(
                day=date.fromisoformat(str(daily["time"][index])),
                code=int(daily["weather_code"][index]),
                t_max=float(daily["temperature_2m_max"][index]),
                t_min=float(daily["temperature_2m_min"][index]),
            )
            for index in range(min(days, len(daily["time"])))
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SourceError(f"meteo: risposta incompleta ({exc})") from exc
    if not forecasts:
        raise SourceError("meteo: nessuna previsione giornaliera nella risposta")
    return Weather(now=now, days=forecasts)


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
