"""Test del renderer: dimensioni, contenuto non vuoto e robustezza con dati mancanti."""

from __future__ import annotations

from datetime import date, datetime

from kindle_dashboard.model import (
    CalEvent,
    CallAt,
    DayForecast,
    Departure,
    PanelData,
    Sync,
    Weather,
    WeatherNow,
)
from kindle_dashboard.render import fonts
from kindle_dashboard.render.panel import _clock_label, _stop_label, _stop_line, render_panel
from kindle_dashboard.timezone_utils import zone

TZ = zone("Europe/Rome")
NOW = datetime(2026, 10, 31, 18, 42, tzinfo=TZ)


def full_panel() -> PanelData:
    return PanelData(
        generated_at=NOW,
        timezone="Europe/Rome",
        location_name="Genova",
        board_name="Genova Brignole",
        weather=Weather(
            now=WeatherNow(temperature=16.6, code=2, apparent=15.9, wind_kmh=8.4),
            days=(
                DayForecast(day=date(2026, 10, 31), code=2, t_min=12.0, t_max=19.1),
                DayForecast(day=date(2026, 11, 1), code=3, t_min=11.3, t_max=17.4),
                DayForecast(day=date(2026, 11, 2), code=61, t_min=9.5, t_max=15.0),
            ),
        ),
        weather_sync=Sync(updated_at=NOW),
        events=(
            CalEvent(start=NOW, summary="Palestra"),
            CalEvent(start=datetime(2026, 11, 1, 0, 0, tzinfo=TZ), summary="Ponte", all_day=True),
        ),
        events_sync=Sync(updated_at=NOW),
        departures=(
            Departure(
                scheduled=NOW,
                expected=NOW,
                line="IC 673",
                destination="LIVORNO CENTRALE",
                track="9",
                realtime=True,
            ),
            Departure(
                scheduled=NOW,
                expected=NOW.replace(minute=48),
                line="RV 2140",
                destination="TORINO PORTA NUOVA",
                track="11",
            ),
            Departure(
                scheduled=NOW,
                expected=NOW,
                line="REG 12138",
                destination="ACQUI TERME",
                track="1 TRONCO",
                cancelled=True,
            ),
        ),
        departures_sync=Sync(updated_at=NOW),
    )


def test_render_uses_kindle_resolution_and_grayscale():
    image = render_panel(full_panel())

    assert image.size == (600, 800)
    assert image.mode == "L"


def test_render_paints_something_and_is_deterministic():
    image = render_panel(full_panel())

    darkest, _ = image.getextrema()
    assert darkest == 0
    assert image.tobytes() == render_panel(full_panel()).tobytes()


def test_render_survives_empty_sections():
    image = render_panel(PanelData(generated_at=NOW, timezone="Europe/Rome"))

    assert image.size == (600, 800)
    assert image.getextrema()[0] == 0


def test_render_scales_to_other_resolutions():
    assert render_panel(full_panel(), (1072, 1448)).size == (1072, 1448)


def test_render_truncates_long_text_without_raising():
    data = full_panel()
    long_text = "Riunione di allineamento con tutto il team " * 3
    panel = PanelData(
        generated_at=data.generated_at,
        timezone=data.timezone,
        events=(CalEvent(start=NOW, summary=long_text),),
        departures=(
            Departure(
                scheduled=NOW, expected=NOW, line="X" * 40, destination=long_text, track="12345"
            ),
        ),
    )

    image = render_panel(panel)

    assert image.size == (600, 800)


def test_stale_sections_are_marked():
    data = full_panel()
    panel = PanelData(
        generated_at=data.generated_at,
        timezone=data.timezone,
        weather=data.weather,
        weather_sync=Sync(updated_at=NOW, error="HTTP 503", stale=True),
        events_sync=Sync(error="calendario non configurato"),
        departures_sync=Sync(updated_at=NOW, stale=True),
    )

    empty = render_panel(PanelData(generated_at=NOW, timezone="Europe/Rome"))

    assert render_panel(panel).tobytes() != empty.tobytes()


def test_clock_label_switches_to_night_mode():
    day = PanelData(generated_at=NOW, timezone="Europe/Rome", rendered_at=NOW)
    night = PanelData(generated_at=NOW, timezone="Europe/Rome", rendered_at=NOW, night=True)

    assert _clock_label(day) == "18:42"
    assert _clock_label(night) == "NOTTE"
    assert render_panel(night).size == (600, 800)


def test_stop_label_drops_the_city_prefix():
    assert _stop_label("ROMA S.PIETRO") == "S.Pietro"
    assert _stop_label("ROMA OSTIENSE") == "Ostiense"
    assert _stop_label("CIVITAVECCHIA") == "Civitavecchia"


def test_stop_line_keeps_priority_stops_when_space_is_short():
    tokens = [
        ("Aurelia 22:17", False),
        ("S.Pietro 22:24", True),
        ("Trastevere 22:29", True),
        ("Ostiense 22:36", False),
        ("Tuscolana 22:41", False),
    ]
    font = fonts.load(16)

    wide = _stop_line(tokens, font, 1000)
    narrow = _stop_line(tokens, font, 320)

    assert wide == (
        "Aurelia 22:17 · S.Pietro 22:24 · Trastevere 22:29 · Ostiense 22:36 · Tuscolana 22:41"
    )
    assert "S.Pietro 22:24" in narrow
    assert "Trastevere 22:29" in narrow
    assert "Tuscolana" not in narrow
    assert font.getlength(narrow) <= 320


def test_panel_with_intermediate_stops_stays_inside_the_canvas():
    panel = PanelData(
        generated_at=NOW,
        timezone="Europe/Rome",
        board_name="Santa Marinella",
        departures=tuple(
            Departure(
                scheduled=NOW,
                expected=NOW,
                line=f"REG 125{index}",
                destination="ROMA TERMINI",
                track="3",
                stops=(
                    CallAt(name="ROMA S.PIETRO", when=NOW),
                    CallAt(name="ROMA TRASTEVERE", when=NOW),
                    CallAt(name="ROMA OSTIENSE", when=NOW),
                ),
            )
            for index in range(3)
        ),
    )

    image = render_panel(panel)

    assert image.size == (600, 800)
    assert image.getextrema()[0] == 0
