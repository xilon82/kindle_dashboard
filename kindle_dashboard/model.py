"""Modello dati del pannello: strutture immutabili condivise da sorgenti, renderer e server."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class WeatherNow:
    """Condizioni attuali.

    Il vento è in nodi (unità nautica: il pannello è pensato per chi guarda il mare) e
    ``wind_direction`` è la direzione **di provenienza** in gradi, come da convenzione
    meteorologica.
    """

    temperature: float
    code: int
    apparent: float | None = None
    precipitation_mm: float | None = None
    wind_kn: float | None = None
    wind_direction: int | None = None
    # Probabilità massima di pioggia nelle prossime ore: il dato orario di Open-Meteo ridotto a
    # un numero, così il renderer non deve leggere serie temporali.
    rain_probability: int | None = None


@dataclass(frozen=True)
class DayForecast:
    """Previsione giornaliera: temperature, codice WMO e vento massimo in nodi."""

    day: date
    code: int
    t_min: float
    t_max: float
    wind_kn: float | None = None
    wind_direction: int | None = None
    # Alba e tramonto aware, nel fuso di ``config.weather.timezone``: il renderer formatta e basta.
    sunrise: datetime | None = None
    sunset: datetime | None = None


@dataclass(frozen=True)
class Weather:
    now: WeatherNow
    days: tuple[DayForecast, ...]


@dataclass(frozen=True)
class SeaNow:
    """Condizioni del mare attuali: altezza d'onda in metri e temperatura dell'acqua."""

    wave_height: float
    water_temperature: float | None = None


@dataclass(frozen=True)
class SeaDay:
    """Previsione giornaliera del mare: solo l'altezza massima dell'onda.

    Lo stato (parola o forza Douglas) si ricava dall'altezza: tenerlo anche qui sarebbe una
    seconda verità da mantenere allineata.
    """

    day: date
    wave_height_max: float


@dataclass(frozen=True)
class Sea:
    now: SeaNow
    days: tuple[SeaDay, ...]


@dataclass(frozen=True)
class CalEvent:
    """Evento di calendario, già nel fuso locale del pannello."""

    start: datetime
    summary: str
    all_day: bool = False
    end: datetime | None = None


@dataclass(frozen=True)
class WasteDay:
    """Un giorno del calendario rifiuti; ``kinds`` vuoto significa nessuna raccolta quel giorno."""

    day: date
    kinds: tuple[str, ...] = ()


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
    rendered_at: datetime | None = None
    night: bool = False
    weather: Weather | None = None
    weather_sync: Sync = field(default_factory=Sync)
    # None = sezione mare spenta o senza dati: il renderer non disegna il blocco né la riga
    # sotto le previsioni, così "spenta" e "vuota" restano distinguibili dal testo dell'errore.
    sea: Sea | None = None
    sea_sync: Sync = field(default_factory=Sync)
    events: tuple[CalEvent, ...] = ()
    events_sync: Sync = field(default_factory=Sync)
    # None = sezione non configurata (la colonna destra non viene disegnata); () = configurata
    # ma senza dati utilizzabili, così il renderer distingue "spenta" da "vuota" senza leggere
    # il testo dell'errore.
    waste: tuple[WasteDay, ...] | None = None
    waste_sync: Sync = field(default_factory=Sync)
    departures: tuple[Departure, ...] = ()
    departures_sync: Sync = field(default_factory=Sync)
    location_name: str = ""
    board_name: str = ""
