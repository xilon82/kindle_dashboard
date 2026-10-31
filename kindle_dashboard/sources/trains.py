"""Partenze ferroviarie da Transitous (MOTIS), servizio pubblico senza API key.

ViaggiaTreno non è utilizzabile da script (Akamai Bot Manager risponde 400 anche con sessione
valida): Transitous espone gli stessi dati Trenitalia via GTFS/GTFS-RT, con binario e ritardo.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from ..exceptions import SourceError
from ..model import CallAt, Departure
from ..timezone_utils import parse_instant, zone
from .http import DEFAULT_TIMEOUT, get_json

DEFAULT_BASE_URL = "https://api.transitous.org"
_REALTIME_REASONS = {"OBSERVED", "PREDICTED"}


def resolve_stations(
    query: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    limit: int = 6,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[tuple[str, str], ...]:
    """Cerca fermate per nome: restituisce coppie ``(nome, stop_id)``."""
    payload = get_json(
        f"{base_url}/api/v1/geocode",
        [("text", query), ("type", "STOP")],
        timeout=timeout,
    )
    if not isinstance(payload, list):
        raise SourceError("treni: risposta geocode inattesa")
    results: list[tuple[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        stop_id = str(item.get("id") or "").strip()
        if name and stop_id:
            results.append((name, stop_id))
    return tuple(results[:limit])


def fetch_payload(
    base_url: str,
    stop_id: str,
    *,
    wanted: int,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Scarica le partenze imminenti; si chiede più del necessario per poter filtrare."""
    payload = get_json(
        f"{base_url}/api/v1/stoptimes",
        [("stopId", stop_id), ("n", max(wanted * 3, 10))],
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        raise SourceError("treni: risposta inattesa (non è un oggetto JSON)")
    return payload


def parse(
    payload: dict[str, Any],
    *,
    now: datetime,
    limit: int,
    timezone: str,
    destinations: Sequence[str] = (),
) -> tuple[Departure, ...]:
    rows = payload.get("stopTimes")
    if not isinstance(rows, list):
        raise SourceError("treni: risposta senza elenco 'stopTimes'")

    departures: list[Departure] = []
    unreadable = 0
    for row in rows:
        if not isinstance(row, dict):
            unreadable += 1
            continue
        place = row.get("place") if isinstance(row.get("place"), dict) else {}
        scheduled = _instant(place.get("scheduledDeparture"), place, timezone)
        expected = _instant(place.get("departure") or place.get("scheduledDeparture"), place, timezone)
        if scheduled is None or expected is None:
            unreadable += 1
            continue
        if expected < now - timedelta(seconds=60):
            continue  # già partito
        destination = _text((row.get("tripTo") or {}).get("name")) or _text(row.get("headsign"))
        if destinations and destination is not None and not _matches(destination, destinations):
            continue
        departures.append(
            Departure(
                scheduled=scheduled,
                expected=expected,
                line=_line(row),
                destination=destination or "destinazione n/d",
                track=_text(place.get("track")),
                cancelled=_truthy(place.get("cancelled"))
                or _truthy(row.get("cancelled"))
                or _truthy(row.get("tripCancelled")),
                realtime=_is_realtime(row, place),
                trip_id=_text(row.get("tripId")) or "",
            )
        )

    if not departures and unreadable:
        raise SourceError(f"treni: {unreadable} partenze illeggibili nella risposta")

    departures.sort(key=lambda item: item.expected)
    return tuple(departures[:limit])


def fetch_trip_stops(
    base_url: str,
    trip_id: str,
    *,
    timezone: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[CallAt, ...]:
    """Fermate intermedie di una corsa: costa una richiesta HTTP per treno."""
    payload = get_json(f"{base_url}/api/v1/trip", [("tripId", trip_id)], timeout=timeout)
    legs = payload.get("legs") if isinstance(payload, dict) else None
    if not isinstance(legs, list) or not legs:
        raise SourceError(f"treni: corsa {trip_id} senza fermate")
    stops: list[CallAt] = []
    for raw in legs[0].get("intermediateStops") or []:
        if not isinstance(raw, dict):
            continue
        name = _text(raw.get("name"))
        when = _instant(raw.get("arrival") or raw.get("departure"), raw, timezone)
        if name is not None and when is not None:
            stops.append(CallAt(name=name, when=when))
    if not stops:
        raise SourceError(f"treni: corsa {trip_id} senza fermate leggibili")
    return tuple(stops)


def matching_stops(stops: Sequence[CallAt], keywords: Sequence[str]) -> tuple[CallAt, ...]:
    """Filtra le fermate per nome; lista di parole chiave vuota = tutte."""
    if not keywords:
        return stops
    return tuple(stop for stop in stops if _matches(stop.name, keywords))


def _instant(value: object, place: dict[str, Any], fallback_timezone: str) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        row_tz = zone(str(place.get("tz") or fallback_timezone))
        return parse_instant(value).astimezone(row_tz)
    except (ValueError, RuntimeError):
        return None


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _line(row: dict[str, Any]) -> str:
    for key in ("displayName", "routeShortName", "routeLongName"):
        value = _text(row.get(key))
        if value is not None:
            return value
    return "?"


def _matches(destination: str, wanted: Sequence[str]) -> bool:
    haystack = destination.casefold()
    return any(item.casefold() in haystack for item in wanted)


def _truthy(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _is_realtime(row: dict[str, Any], place: dict[str, Any]) -> bool:
    if row.get("realTime") is True:
        return True
    for source in (place, row):
        reason = _text(source.get("departureTimestampReason"))
        if reason is not None and reason.upper() in _REALTIME_REASONS:
            return True
    return False
