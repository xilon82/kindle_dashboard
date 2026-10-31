"""Orchestrazione: raccoglie le tre sezioni e degrada su cache quando una fonte non risponde."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .cache import Cache
from .config import Config
from .exceptions import SourceError
from .model import CalEvent, Departure, PanelData, Sync, Weather
from .sources import calendar as calendar_source
from .sources import trains as trains_source
from .sources import weather as weather_source
from .timezone_utils import zone


def collect(config: Config, cache: Cache, now: datetime | None = None) -> PanelData:
    """Legge tutte le sezioni; ogni sezione fallisce in modo indipendente dalle altre."""
    tz = zone(config.timezone)
    moment = now.astimezone(tz) if now is not None else datetime.now(tz)

    weather, weather_sync = _weather(config, cache, moment, tz)
    events, events_sync = _events(config, cache, moment, tz)
    departures, departures_sync = _departures(config, cache, moment)

    return PanelData(
        generated_at=moment,
        timezone=config.timezone,
        weather=weather,
        weather_sync=weather_sync,
        events=events,
        events_sync=events_sync,
        departures=departures,
        departures_sync=departures_sync,
        location_name=config.location.name if config.location else "",
        board_name=config.trains.station,
    )


def _weather(
    config: Config, cache: Cache, moment: datetime, tz: ZoneInfo
) -> tuple[Weather | None, Sync]:
    if config.location is None:
        return None, Sync(error="posizione non configurata")
    try:
        payload = weather_source.fetch_payload(
            config.location.latitude,
            config.location.longitude,
            days=config.weather.days,
            timezone=config.timezone,
        )
        weather = weather_source.parse(payload, days=config.weather.days)
    except SourceError as exc:
        return _weather_from_cache(cache, config, exc)
    cache.store("weather", payload, moment)
    return weather, Sync(updated_at=moment)


def _weather_from_cache(
    cache: Cache, config: Config, error: SourceError
) -> tuple[Weather | None, Sync]:
    cached = cache.load("weather")
    if cached is None:
        return None, Sync(error=str(error))
    payload, saved_at = cached
    try:
        return weather_source.parse(payload, days=config.weather.days), Sync(
            updated_at=saved_at, error=str(error), stale=True
        )
    except SourceError:
        return None, Sync(error=str(error))


def _events(
    config: Config, cache: Cache, moment: datetime, tz: ZoneInfo
) -> tuple[tuple[CalEvent, ...], Sync]:
    if not config.calendar.enabled:
        return (), Sync(error="calendario non configurato")
    try:
        payload = calendar_source.fetch_payload(config.calendar.ics_url)
        events = _parse_calendar(payload, config, moment, tz)
    except SourceError as exc:
        cached = cache.load("calendar")
        if cached is None:
            return (), Sync(error=str(exc))
        cached_payload, saved_at = cached
        try:
            return _parse_calendar(str(cached_payload), config, moment, tz), Sync(
                updated_at=saved_at, error=str(exc), stale=True
            )
        except SourceError:
            return (), Sync(error=str(exc))
    cache.store("calendar", payload, moment)
    return events, Sync(updated_at=moment)


def _departures(
    config: Config, cache: Cache, moment: datetime
) -> tuple[tuple[Departure, ...], Sync]:
    if not config.trains.enabled:
        return (), Sync(error="treni non configurati")
    try:
        payload = trains_source.fetch_payload(
            config.trains.base_url, config.trains.stop_id, wanted=config.trains.max_departures
        )
        departures = _parse_departures(payload, config, moment)
    except SourceError as exc:
        cached = cache.load("departures")
        if cached is None:
            return (), Sync(error=str(exc))
        cached_payload, saved_at = cached
        try:
            departures = _parse_departures(cached_payload, config, moment)
        except SourceError:
            return (), Sync(error=str(exc))
        return (
            _attach_stops(config, departures),
            Sync(updated_at=saved_at, error=str(exc), stale=True),
        )
    cache.store("departures", payload, moment)
    return _attach_stops(config, departures), Sync(updated_at=moment)


def _attach_stops(config: Config, departures: tuple[Departure, ...]) -> tuple[Departure, ...]:
    """Aggiunge le fermate intermedie: una richiesta per treno, e un treno senza fermate resta valido."""
    if not config.trains.stop_details:
        return departures
    enriched: list[Departure] = []
    for departure in departures:
        if not departure.trip_id:
            enriched.append(departure)
            continue
        try:
            stops = trains_source.fetch_trip_stops(
                config.trains.base_url, departure.trip_id, timezone=config.timezone
            )
        except SourceError:
            enriched.append(departure)
            continue
        relevant = trains_source.matching_stops(stops, config.trains.destinations)
        enriched.append(replace(departure, stops=relevant))
    return tuple(enriched)


def _parse_calendar(
    payload: str, config: Config, moment: datetime, tz: ZoneInfo
) -> tuple[CalEvent, ...]:
    return calendar_source.parse_events(
        payload,
        start=moment,
        end=moment + timedelta(days=config.calendar.days_ahead),
        tz=tz,
        limit=config.calendar.max_events,
    )


def _parse_departures(
    payload: Any, config: Config, moment: datetime
) -> tuple[Departure, ...]:
    return trains_source.parse(
        payload,
        now=moment,
        limit=config.trains.max_departures,
        timezone=config.timezone,
        destinations=config.trains.destinations,
    )
