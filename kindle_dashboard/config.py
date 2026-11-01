"""Caricamento e validazione di config.toml (solo stdlib: tomllib)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any

from .exceptions import ConfigError
from .schedule import Schedule
from .timezone_utils import DEFAULT_TIMEZONE

EXAMPLE_CONFIG_FILENAME = "config.example.toml"
LOCAL_CONFIG_FILENAME = "config.toml"
ICS_URL_ENV = "KDASH_ICS_URL"


@dataclass(frozen=True)
class PanelConfig:
    width: int = 600
    height: int = 720
    refresh_seconds: int = 90


@dataclass(frozen=True)
class LocationConfig:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class WeatherConfig:
    days: int = 3
    timezone: str = DEFAULT_TIMEZONE


@dataclass(frozen=True)
class SeaConfig:
    """Condizioni del mare: usa le coordinate di ``[location]``, non ne ha di proprie."""

    enabled: bool = False
    days: int = 3


@dataclass(frozen=True)
class CalendarConfig:
    ics_url: str = ""
    max_events: int = 4
    days_ahead: int = 7

    @property
    def enabled(self) -> bool:
        return bool(self.ics_url)


@dataclass(frozen=True)
class WasteConfig:
    """Calendario comunale della raccolta differenziata: un iCal pubblico, un evento per giorno."""

    ics_url: str = ""
    days: int = 3

    @property
    def enabled(self) -> bool:
        return bool(self.ics_url)


@dataclass(frozen=True)
class TrainsConfig:
    base_url: str = "https://api.transitous.org"
    station: str = ""
    stop_id: str = ""
    max_departures: int = 4
    destinations: tuple[str, ...] = ()
    stop_details: bool = False
    stop_priority: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.stop_id)


@dataclass(frozen=True)
class RenderConfig:
    font: str = ""
    font_bold: str = ""


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8787


@dataclass(frozen=True)
class Config:
    panel: PanelConfig = field(default_factory=PanelConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    sea: SeaConfig = field(default_factory=SeaConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    waste: WasteConfig = field(default_factory=WasteConfig)
    trains: TrainsConfig = field(default_factory=TrainsConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    schedule: Schedule = field(
        default_factory=lambda: Schedule(
            night_start=time(23, 0), night_end=time(6, 30), day_seconds=90, night_seconds=3600
        )
    )
    cache_dir: Path = Path("cache")
    location: LocationConfig | None = None
    source_path: Path | None = None

    @property
    def timezone(self) -> str:
        return self.weather.timezone


def load_config(path: Path | str = LOCAL_CONFIG_FILENAME) -> Config:
    """Legge il file di configurazione; i percorsi relativi sono risolti rispetto al file."""
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(
            f"configurazione non trovata: {config_path} — copia {EXAMPLE_CONFIG_FILENAME} "
            f"in {LOCAL_CONFIG_FILENAME}"
        )
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path}: TOML non valido ({exc})") from exc

    panel = _section(data, "panel")
    weather = _section(data, "weather")
    sea = _section(data, "sea")
    calendar = _section(data, "calendar")
    waste = _section(data, "waste")
    trains = _section(data, "trains")
    render = _section(data, "render")
    server = _section(data, "server")
    schedule_table = _section(data, "schedule")
    cache = _section(data, "cache")
    location_table = _section(data, "location")

    location = None
    if location_table is not None:
        name = _str(location_table, "name", "", where="location").strip()
        if not name:
            raise ConfigError("[location] name è obbligatorio quando [location] è presente")
        location = LocationConfig(
            name=name,
            latitude=_number(location_table, "latitude", where="location", low=-90.0, high=90.0),
            longitude=_number(location_table, "longitude", where="location", low=-180.0, high=180.0),
        )

    ics_url = _str(calendar, "ics_url", "", where="calendar").strip()
    if not ics_url:
        # L'URL iCal segreto è una credenziale: l'ambiente vince sul file, così non finisce su disco.
        ics_url = os.environ.get(ICS_URL_ENV, "").strip()

    panel_config = PanelConfig(
        width=_int(panel, "width", 600, where="panel", minimum=200),
        height=_int(panel, "height", 720, where="panel", minimum=200),
        refresh_seconds=_int(panel, "refresh_seconds", 90, where="panel", minimum=30),
    )
    night_start = _clock(schedule_table, "night_start", time(23, 0), where="schedule")
    night_end = _clock(schedule_table, "night_end", time(6, 30), where="schedule")
    if night_start == night_end:
        raise ConfigError("[schedule] night_start e night_end non possono coincidere")
    schedule_config = Schedule(
        night_start=night_start,
        night_end=night_end,
        day_seconds=panel_config.refresh_seconds,
        night_seconds=_int(
            schedule_table, "night_refresh_seconds", 3600, where="schedule", minimum=60
        ),
    )

    return Config(
        panel=panel_config,
        weather=WeatherConfig(
            days=_int(weather, "days", 3, where="weather", minimum=1, maximum=7),
            timezone=_str(weather, "timezone", DEFAULT_TIMEZONE, where="weather").strip(),
        ),
        sea=SeaConfig(
            enabled=_bool(sea, "enabled", False, where="sea"),
            days=_int(sea, "days", 3, where="sea", minimum=1, maximum=7),
        ),
        calendar=CalendarConfig(
            ics_url=ics_url,
            max_events=_int(calendar, "max_events", 4, where="calendar", minimum=1, maximum=20),
            days_ahead=_int(calendar, "days_ahead", 7, where="calendar", minimum=1, maximum=60),
        ),
        waste=WasteConfig(
            ics_url=_str(waste, "ics_url", "", where="waste").strip(),
            days=_int(waste, "days", 3, where="waste", minimum=1, maximum=7),
        ),
        trains=TrainsConfig(
            base_url=_str(trains, "base_url", "https://api.transitous.org", where="trains").rstrip(
                "/"
            ),
            station=_str(trains, "station", "", where="trains").strip(),
            stop_id=_str(trains, "stop_id", "", where="trains").strip(),
            max_departures=_int(
                trains, "max_departures", 4, where="trains", minimum=1, maximum=20
            ),
            destinations=_str_tuple(trains, "destinations", where="trains"),
            stop_details=_bool(trains, "stop_details", False, where="trains"),
            stop_priority=_str_tuple(trains, "stop_priority", where="trains"),
        ),
        render=RenderConfig(
            font=_str(render, "font", "", where="render").strip(),
            font_bold=_str(render, "font_bold", "", where="render").strip(),
        ),
        server=ServerConfig(
            host=_str(server, "host", "0.0.0.0", where="server").strip(),
            port=_int(server, "port", 8787, where="server", minimum=1, maximum=65535),
        ),
        schedule=schedule_config,
        cache_dir=config_path.parent / _str(cache, "dir", "cache", where="cache").strip(),
        location=location,
        source_path=config_path,
    )


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] deve essere una tabella TOML")
    return value


def _str(section: dict[str, Any], key: str, default: str, *, where: str) -> str:
    value = section.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"[{where}] {key} deve essere una stringa")
    return value


def _int(
    section: dict[str, Any],
    key: str,
    default: int,
    *,
    where: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"[{where}] {key} deve essere un intero")
    if minimum is not None and value < minimum:
        raise ConfigError(f"[{where}] {key} deve essere >= {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"[{where}] {key} deve essere <= {maximum}")
    return value


def _number(
    section: dict[str, Any],
    key: str,
    *,
    where: str,
    low: float | None = None,
    high: float | None = None,
) -> float:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"[{where}] {key} deve essere un numero")
    number = float(value)
    if low is not None and number < low:
        raise ConfigError(f"[{where}] {key} deve essere >= {low}")
    if high is not None and number > high:
        raise ConfigError(f"[{where}] {key} deve essere <= {high}")
    return number


def _clock(section: dict[str, Any], key: str, default: time, *, where: str) -> time:
    """Orario nel formato ``HH:MM``."""
    value = section.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"[{where}] {key} deve essere una stringa nel formato HH:MM")
    hours, _, minutes = value.strip().partition(":")
    try:
        return time(int(hours), int(minutes))
    except ValueError as exc:
        raise ConfigError(f"[{where}] {key} deve essere nel formato HH:MM") from exc


def _bool(section: dict[str, Any], key: str, default: bool, *, where: str) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"[{where}] {key} deve essere true o false")
    return value


def _str_tuple(section: dict[str, Any], key: str, *, where: str) -> tuple[str, ...]:
    value = section.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"[{where}] {key} deve essere una lista di stringhe")
    return tuple(item.strip() for item in value if item.strip())

