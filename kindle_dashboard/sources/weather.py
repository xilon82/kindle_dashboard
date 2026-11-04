"""Meteo da Open-Meteo: servizio pubblico, nessuna API key.

``fetch_payload`` restituisce il JSON grezzo (così può essere messo in cache e ri-analizzato),
``parse`` lo trasforma nel modello di dominio. Il vento si chiede in **nodi**: il pannello è
nautico e l'unità non si converte nel renderer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..exceptions import SourceError
from ..model import DayForecast, Weather, WeatherNow
from ..timezone_utils import zone
from .http import DEFAULT_TIMEOUT, get_json
from .values import optional_float, optional_int, series_float, series_int, series_text

API_URL = "https://api.open-meteo.com/v1/forecast"

_CURRENT_FIELDS = (
    "temperature_2m,weather_code,apparent_temperature,precipitation,"
    "wind_speed_10m,wind_direction_10m"
)
_DAILY_FIELDS = (
    "weather_code,temperature_2m_max,temperature_2m_min,"
    "wind_speed_10m_max,wind_direction_10m_dominant,sunrise,sunset"
)
_HOURLY_FIELDS = "precipitation_probability"
# Finestra della probabilità di pioggia mostrata accanto alla temperatura: le prossime ore e non
# la giornata intera, altrimenti un temporale serale si leggerebbe come "piove adesso".
_RAIN_WINDOW_HOURS = 6

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
            ("hourly", _HOURLY_FIELDS),
            ("timezone", timezone),
            ("forecast_days", days),
            ("temperature_unit", "celsius"),
            # Nodi e non km/h: il pannello è nautico e il mare è misurato in nodi.
            ("wind_speed_unit", "kn"),
            ("precipitation_unit", "mm"),
        ],
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        raise SourceError("meteo: risposta inattesa (non è un oggetto JSON)")
    return payload


def parse(payload: dict[str, Any], *, days: int, timezone: str) -> Weather:
    """Costruisce il modello dal JSON Open-Meteo, con errori espliciti se mancano campi.

    ``timezone`` serve a rendere aware alba e tramonto: Open-Meteo li restituisce come ora locale
    senza offset, quindi l'unico modo per rispettare l'invariante sui fusi è riattaccarci il
    ``ZoneInfo`` di configurazione.
    """
    tz = zone(timezone)
    try:
        current = payload["current"]
        daily = payload["daily"]
        now = WeatherNow(
            temperature=float(current["temperature_2m"]),
            code=int(current["weather_code"]),
            apparent=optional_float(current.get("apparent_temperature")),
            precipitation_mm=optional_float(current.get("precipitation")),
            wind_kn=optional_float(current.get("wind_speed_10m")),
            wind_direction=optional_int(current.get("wind_direction_10m")),
            rain_probability=_rain_probability(payload.get("hourly"), current.get("time")),
        )
        wind_series = daily.get("wind_speed_10m_max")
        wind_directions = daily.get("wind_direction_10m_dominant")
        forecasts = tuple(
            DayForecast(
                day=date.fromisoformat(str(daily["time"][index])),
                code=int(daily["weather_code"][index]),
                t_max=float(daily["temperature_2m_max"][index]),
                t_min=float(daily["temperature_2m_min"][index]),
                wind_kn=series_float(wind_series, index),
                wind_direction=series_int(wind_directions, index),
                sunrise=_daily_instant(daily, "sunrise", index, tz),
                sunset=_daily_instant(daily, "sunset", index, tz),
            )
            for index in range(min(days, len(daily["time"])))
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SourceError(f"meteo: risposta incompleta ({exc})") from exc
    if not forecasts:
        raise SourceError("meteo: nessuna previsione giornaliera nella risposta")
    return Weather(now=now, days=forecasts)


def _daily_instant(
    daily: dict[str, Any], field: str, index: int, tz: ZoneInfo
) -> datetime | None:
    """Alba/tramonto come istante aware; ``None`` se il campo manca o non è un orario."""
    text = series_text(daily.get(field), index)
    if text is None:
        return None
    try:
        # Il cambio di ora legale rende ambigua un'ora all'anno: ``replace`` sceglie la prima
        # occorrenza, che è quella che interessa a un pannello informativo.
        return datetime.fromisoformat(text).replace(tzinfo=tz)
    except ValueError:
        return None


def _rain_probability(hourly: object, moment: object) -> int | None:
    """Massimo di ``precipitation_probability`` nelle prossime ore dalla corrente.

    Le serie orarie arrivano già nel fuso richiesto: confrontare il prefisso ISO di data+ora
    (``2026-11-04T18``) basta a trovare l'ora corrente, senza interpretare date né fusi.
    """
    if not isinstance(hourly, dict) or not isinstance(moment, str):
        return None
    times = hourly.get("time")
    values = hourly.get("precipitation_probability")
    if not isinstance(times, list) or not isinstance(values, list):
        return None
    hour = moment[:13]
    start = next(
        (
            index
            for index, stamp in enumerate(times)
            if isinstance(stamp, str) and stamp[:13] == hour
        ),
        None,
    )
    if start is None:
        return None
    end = min(start + _RAIN_WINDOW_HOURS, len(values))
    window = [optional_int(values[index]) for index in range(start, end)]
    present = [value for value in window if value is not None]
    return max(present) if present else None
