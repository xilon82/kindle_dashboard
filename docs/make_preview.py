"""Genera l'anteprima del README: pannello completo con dati **inventati**.

L'immagine versionata in ``docs/preview.png`` serve solo a mostrare il layout, quindi nessun
valore viene da una fonte reale: eventi, località, stazione, temperature e partenze sono di
esempio. Così il README può stare in un repository pubblico senza esporre il calendario
personale (né la località o la stazione) di chi usa il pannello.

Si rigenera **offline**, senza rete e senza ``config.toml`` (serve solo il pacchetto installato,
come dice il README):

    python docs/make_preview.py
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from kindle_dashboard.model import (
    CalEvent,
    CallAt,
    DayForecast,
    Departure,
    PanelData,
    Sea,
    SeaDay,
    SeaNow,
    Sync,
    WasteDay,
    Weather,
    WeatherNow,
)
from kindle_dashboard.render.panel import render_panel
from kindle_dashboard.timezone_utils import zone

TZ = zone("Europe/Rome")
OUTPUT = Path(__file__).resolve().parent / "preview.png"
# Ora fissa, non "adesso": l'anteprima deve raccontare un pomeriggio con gli eventi ancora da
# fare, e rigenerarla alle 03:00 non deve produrre un pannello di eventi passati (o `NOTTE`).
PREVIEW_CLOCK = (18, 42)
# Alba e tramonto sono valori fissi come tutto il resto: il layout li mostra, la veridicità
# astronomica non è un requisito di un'immagine di documentazione.
SUNRISE = (7, 12)
SUNSET = (17, 18)


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def sample_panel(moment: datetime) -> PanelData:
    """Pannello completo con valori plausibili ma inventati, relativi al giorno di ``moment``."""
    today = moment.date()
    days = [today + timedelta(days=offset) for offset in range(3)]

    weather = Weather(
        # Vento da nord-est (``Grecale``): nome corto e sigla a due lettere, così la temperatura
        # dell'acqua — un pezzo che il renderer sacrifica quando la colonna si stringe — resta
        # nell'anteprima, dove invece si deve vedere.
        now=WeatherNow(
            temperature=17.4,
            code=2,
            apparent=16.2,
            precipitation_mm=0.0,
            wind_kn=8.4,
            wind_direction=45,
            rain_probability=20,
            humidity=64,
        ),
        days=(
            DayForecast(
                day=days[0],
                code=2,
                t_min=12.4,
                t_max=18.1,
                wind_kn=8.4,
                wind_direction=45,
                sunrise=_at(days[0], *SUNRISE),
                sunset=_at(days[0], *SUNSET),
            ),
            DayForecast(
                day=days[1],
                code=3,
                t_min=11.8,
                t_max=16.5,
                wind_kn=17.4,
                wind_direction=225,
            ),
            DayForecast(
                day=days[2],
                code=61,
                t_min=9.7,
                t_max=14.2,
                wind_kn=6.8,
                wind_direction=355,
            ),
        ),
    )

    sea = Sea(
        now=SeaNow(wave_height=0.58, water_temperature=19.8),
        days=(
            SeaDay(day=days[0], wave_height_max=0.62),
            SeaDay(day=days[1], wave_height_max=0.54),
            SeaDay(day=days[2], wave_height_max=1.3),
        ),
    )

    # Tre eventi, non quattro: l'agenda riceve solo lo spazio che avanza dai treni, e un quarto
    # verrebbe troncato. Il secondo è lungo apposta, per mostrare l'andata a capo sulla seconda
    # riga; il terzo è di più giorni e nella colonna stretta prende il giorno della settimana.
    events = (
        CalEvent(start=_at(today, 19, 15), summary="Palestra"),
        CalEvent(start=_at(today, 21, 0), summary="Cena con amici in centro e rientro tardi"),
        CalEvent(start=_at(days[2], 0, 0), summary="Gita fuori porta", all_day=True),
    )

    waste = (
        WasteDay(day=days[0], kinds=("Umido",)),
        WasteDay(day=days[1]),
        WasteDay(day=days[2], kinds=("Secco",)),
    )

    departures = (
        Departure(
            scheduled=_at(today, 19, 14),
            expected=_at(today, 19, 19),
            line="IC 673",
            destination="ROMA TERMINI",
            track="9",
            realtime=True,
            stops=(
                CallAt(name="GENOVA SESTRI P.", when=_at(today, 19, 26)),
                CallAt(name="SAVONA", when=_at(today, 19, 49)),
                CallAt(name="LA SPEZIA C.", when=_at(today, 20, 22)),
            ),
        ),
        Departure(
            scheduled=_at(today, 19, 32),
            expected=_at(today, 19, 32),
            line="REG 2140",
            destination="SAVONA",
            track="11",
            stops=(
                CallAt(name="GENOVA P.P.", when=_at(today, 19, 41)),
                CallAt(name="VARAZZE", when=_at(today, 19, 58)),
            ),
        ),
        Departure(
            scheduled=_at(today, 19, 58),
            expected=_at(today, 19, 58),
            line="REG 12138",
            destination="ACQUI TERME",
            track="1 TRONCO",
            cancelled=True,
            stops=(
                CallAt(name="GENOVA SAMP.", when=_at(today, 20, 9)),
                CallAt(name="OVADA", when=_at(today, 20, 44)),
            ),
        ),
    )

    sync = Sync(updated_at=moment)
    return PanelData(
        generated_at=moment,
        timezone="Europe/Rome",
        # Un'anteprima con `NOTTE` al posto dell'ora non mostrerebbe l'orologio: è la fascia
        # notturna che il pannello reale sceglie da sé, non un dato da illustrare qui.
        night=False,
        weather=weather,
        weather_sync=sync,
        sea=sea,
        sea_sync=sync,
        events=events,
        events_sync=sync,
        waste=waste,
        waste_sync=sync,
        departures=departures,
        departures_sync=sync,
        location_name="Genova",
        board_name="Genova Brignole",
    )


def main() -> int:
    moment = datetime.now(TZ).replace(
        hour=PREVIEW_CLOCK[0], minute=PREVIEW_CLOCK[1], second=0, microsecond=0
    )
    image = render_panel(sample_panel(moment))
    image.save(OUTPUT, format="PNG", optimize=True)
    print(f"anteprima {image.width}x{image.height} scritta in {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
