"""Modello dati del pannello: strutture immutabili condivise da sorgenti, renderer e server."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class WeatherNow:
    """Condizioni attuali."""

    temperature: float
    code: int
    apparent: float | None = None
    precipitation_mm: float | None = None
    wind_kmh: float | None = None


@dataclass(frozen=True)
class DayForecast:
    """Previsione giornaliera (minima/massima e codice WMO)."""

    day: date
    code: int
    t_min: float
    t_max: float


@dataclass(frozen=True)
class Weather:
    now: WeatherNow
    days: tuple[DayForecast, ...]


@dataclass(frozen=True)
class CalEvent:
    """Evento di calendario, già nel fuso locale del pannello."""

    start: datetime
    summary: str
    all_day: bool = False
    end: datetime | None = None


@dataclass(frozen=True)
class CallAt:
    """Fermata intermedia di un treno, con l'orario previsto."""

    name: str
    when: datetime


@dataclass(frozen=True)
class Departure:
    """Partenza ferroviaria: orario programmato, orario atteso e binario."""

    scheduled: datetime
    expected: datetime
    line: str
    destination: str
    track: str | None = None
    cancelled: bool = False
    realtime: bool = False
    trip_id: str = ""
    stops: tuple[CallAt, ...] = ()

    @property
    def delay_minutes(self) -> int:
        return round((self.expected - self.scheduled).total_seconds() / 60)


@dataclass(frozen=True)
class Sync:
    """Esito del caricamento di una sezione.

    ``stale`` è vero quando i dati mostrati vengono dalla cache perché l'ultima chiamata è fallita.
    """

    updated_at: datetime | None = None
    error: str | None = None
    stale: bool = False


@dataclass(frozen=True)
class PanelData:
    """Tutto ciò che serve a disegnare un fotogramma del pannello."""

    generated_at: datetime
    timezone: str
    weather: Weather | None = None
    weather_sync: Sync = field(default_factory=Sync)
    events: tuple[CalEvent, ...] = ()
    events_sync: Sync = field(default_factory=Sync)
    departures: tuple[Departure, ...] = ()
    departures_sync: Sync = field(default_factory=Sync)
    location_name: str = ""
    board_name: str = ""
