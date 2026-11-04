"""Test del renderer: dimensioni, contenuto non vuoto e robustezza con dati mancanti."""

from __future__ import annotations

from datetime import date, datetime

import pytest

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
from kindle_dashboard.render import fonts
from kindle_dashboard.render.layout import compass, waste_day_label, wind_name
from kindle_dashboard.render.panel import (
    _clock_label,
    _fit_inline,
    _icon_top,
    _inline_width,
    _now_detail_segments,
    _sea_day_segments,
    _sea_segments,
    _stop_label,
    _stop_line,
    _sun_segments,
    _text,
    _wind_segments,
    render_panel,
)
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
            now=WeatherNow(
                temperature=16.6,
                code=2,
                apparent=15.9,
                wind_kn=8.4,
                wind_direction=18,
                rain_probability=40,
            ),
            days=(
                DayForecast(
                    day=date(2026, 10, 31),
                    code=2,
                    t_min=12.0,
                    t_max=19.1,
                    wind_kn=11.1,
                    wind_direction=13,
                    sunrise=datetime(2026, 10, 31, 6, 47, tzinfo=TZ),
                    sunset=datetime(2026, 10, 31, 17, 2, tzinfo=TZ),
                ),
                DayForecast(
                    day=date(2026, 11, 1),
                    code=3,
                    t_min=11.3,
                    t_max=17.4,
                    wind_kn=17.9,
                    wind_direction=6,
                ),
                DayForecast(
                    day=date(2026, 11, 2),
                    code=61,
                    t_min=9.5,
                    t_max=15.0,
                    wind_kn=7.2,
                    wind_direction=355,
                ),
            ),
        ),
        weather_sync=Sync(updated_at=NOW),
        sea=Sea(
            now=SeaNow(wave_height=0.48, water_temperature=20.6),
            days=(
                SeaDay(day=date(2026, 10, 31), wave_height_max=0.54),
                SeaDay(day=date(2026, 11, 1), wave_height_max=0.52),
                SeaDay(day=date(2026, 11, 2), wave_height_max=1.3),
            ),
        ),
        sea_sync=Sync(updated_at=NOW),
        events=(
            CalEvent(start=NOW, summary="Palestra"),
            CalEvent(start=datetime(2026, 11, 1, 0, 0, tzinfo=TZ), summary="Ponte", all_day=True),
        ),
        events_sync=Sync(updated_at=NOW),
        waste=(
            WasteDay(day=date(2026, 10, 31), kinds=("Umido",)),
            WasteDay(day=date(2026, 11, 1)),
            WasteDay(day=date(2026, 11, 2), kinds=("Secco",)),
        ),
        waste_sync=Sync(updated_at=NOW),
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


def test_waste_column_changes_the_layout_but_stays_on_canvas():
    data = full_panel()
    single_column = PanelData(
        generated_at=data.generated_at,
        timezone=data.timezone,
        events=data.events,
        events_sync=data.events_sync,
    )

    with_waste = render_panel(data)
    without_waste = render_panel(single_column)

    assert with_waste.size == (600, 800)
    assert with_waste.tobytes() != without_waste.tobytes()


def test_waste_day_labels_are_relative():
    today = date(2026, 10, 31)

    assert waste_day_label(today, today) == "OGGI"
    assert waste_day_label(date(2026, 11, 1), today) == "DOMANI"
    assert waste_day_label(date(2026, 11, 2), today) == "LUN"


def test_long_waste_material_is_truncated_without_raising():
    panel = PanelData(
        generated_at=NOW,
        timezone="Europe/Rome",
        waste=(WasteDay(day=date(2026, 10, 31), kinds=("Plastica e metalli " * 4,)),),
        waste_sync=Sync(updated_at=NOW),
    )

    assert render_panel(panel).size == (600, 800)


def test_configured_but_empty_waste_section_shows_its_message():
    panel = PanelData(
        generated_at=NOW,
        timezone="Europe/Rome",
        waste=(),
        waste_sync=Sync(error="calendar.example: HTTP 500"),
    )
    empty = PanelData(generated_at=NOW, timezone="Europe/Rome")

    image = render_panel(panel)

    assert image.size == (600, 800)
    assert image.tobytes() != render_panel(empty).tobytes()


def test_panel_with_sea_differs_from_panel_without_it():
    data = full_panel()
    without_sea = PanelData(
        generated_at=data.generated_at,
        timezone=data.timezone,
        weather=data.weather,
        weather_sync=data.weather_sync,
    )

    with_sea = render_panel(data)

    assert with_sea.size == (600, 800)
    assert with_sea.tobytes() != render_panel(without_sea).tobytes()


def test_failed_sea_section_is_declared_in_the_status_line_only():
    """Sezione configurata ma caduta: "mare n.d." sulla riga condizioni, nessuna riga in più."""
    weather = full_panel().weather
    failed = PanelData(
        generated_at=NOW,
        timezone="Europe/Rome",
        weather=weather,
        weather_sync=Sync(updated_at=NOW),
        sea_sync=Sync(error="marine-api.open-meteo.com: HTTP 503"),
    )
    plain = PanelData(
        generated_at=NOW,
        timezone="Europe/Rome",
        weather=weather,
        weather_sync=Sync(updated_at=NOW),
    )

    image = render_panel(failed)

    assert image.size == (600, 800)
    assert image.tobytes() != render_panel(plain).tobytes()


@pytest.mark.parametrize(
    ("degrees", "expected"),
    [
        (0, "N"),
        (18, "NNE"),
        (45, "NE"),
        (90, "E"),
        (137, "SE"),
        (180, "S"),
        (270, "O"),
        (343, "NNO"),
        (359, "N"),
        (None, ""),
    ],
)
def test_compass_uses_sixteen_sectors(degrees, expected):
    assert compass(degrees) == expected


def test_fit_inline_drops_optional_pieces_before_truncating():
    font = fonts.load(20)
    segments = (
        _text("poco mosso"),
        _text("0.6m", required=False),
        _text("da SE", required=False),
    )

    wide = _fit_inline(segments, font, 18, 6, 1000)
    narrow = _fit_inline(segments, font, 18, 6, 120)

    assert [segment.text for segment in wide] == ["poco mosso", "0.6m", "da SE"]
    assert [segment.text for segment in narrow] == ["poco mosso"]
    assert _inline_width(narrow, font, 18, 6) <= 120


def test_fit_inline_truncates_the_last_text_when_nothing_can_be_dropped():
    font = fonts.load(20)

    fitted = _fit_inline((_text("pioggia forte e vento"),), font, 18, 6, 60)

    assert fitted[0].text.endswith("…")
    assert _inline_width(fitted, font, 18, 6) <= 60


def test_wind_segments_keep_the_direction_and_add_the_traditional_name():
    """Il vento non perde la direzione; il nome tradizionale è il pezzo che può cedere."""
    weather = Weather(
        now=WeatherNow(temperature=16.6, code=2, apparent=9.0, wind_kn=15.0, wind_direction=18),
        days=(),
    )

    segments = _wind_segments(weather)

    assert segments[0].icon == "wind"
    assert [segment.text for segment in segments if segment.text] == [
        "15 kn",
        "NNE",
        "· Tramontana",
    ]
    # La sigla resta obbligatoria; il nome è il di più che si toglie per primo.
    assert [segment.required for segment in segments if segment.text] == [True, True, False]


def test_now_details_pair_apparent_with_rain_probability():
    weather = Weather(
        now=WeatherNow(temperature=16.6, code=2, apparent=15.9, rain_probability=40),
        days=(),
    )

    segments = _now_detail_segments(weather)
    without_rain = _now_detail_segments(weather, with_rain=False)

    # Il percepito usa il glifo "persona": è quello che sente il corpo, non un termometro.
    assert [segment.icon for segment in segments if segment.icon] == ["person", "umbrella"]
    assert [segment.text for segment in segments if segment.text] == ["16°", "40%"]
    assert [segment.text for segment in without_rain if segment.text] == ["16°"]


def test_now_details_are_empty_when_the_weather_has_no_extras():
    weather = Weather(now=WeatherNow(temperature=16.6, code=2), days=())

    assert _now_detail_segments(weather) == ()


def test_sun_segments_show_both_times_with_arrows():
    day = DayForecast(
        day=date(2026, 10, 31),
        code=2,
        t_min=12.0,
        t_max=19.1,
        sunrise=datetime(2026, 10, 31, 6, 47, tzinfo=TZ),
        sunset=datetime(2026, 10, 31, 17, 2, tzinfo=TZ),
    )

    segments = _sun_segments(day)

    assert [segment.icon for segment in segments if segment.icon] == [
        "sunrise",
        "arrow_up",
        "sunset",
        "arrow_down",
    ]
    assert [segment.text for segment in segments if segment.text] == ["06:47", "17:02"]
    # Le frecce sono l'unico pezzo che può cedere: gli orari restano.
    assert [segment.required for segment in segments if segment.icon] == [
        True,
        False,
        True,
        False,
    ]


def test_sun_segments_are_empty_without_a_forecast():
    assert _sun_segments(None) == ()


@pytest.mark.parametrize(
    ("degrees", "expected"),
    [
        (0, "Tramontana"),
        (18, "Tramontana"),
        (45, "Grecale"),
        (90, "Levante"),
        (137, "Scirocco"),
        (180, "Ostro"),
        (225, "Libeccio"),
        (270, "Ponente"),
        (315, "Maestrale"),
        (None, ""),
    ],
)
def test_wind_name_uses_the_eight_traditional_winds(degrees, expected):
    assert wind_name(degrees) == expected


def test_sea_block_shows_state_height_and_water_temperature():
    sea = Sea(now=SeaNow(wave_height=0.48, water_temperature=20.6), days=())

    segments = _sea_segments(sea)

    assert segments[0].icon == "sea_slight"
    assert [segment.text for segment in segments if segment.text] == ["poco mosso", "0.5m", "21°"]
    # L'acqua è l'unico pezzo che può cedere.
    assert [segment.required for segment in segments if segment.text] == [True, True, False]


def test_sea_day_row_uses_the_douglas_force():
    day = SeaDay(day=date(2026, 11, 2), wave_height_max=1.3)

    segments = _sea_day_segments(day, 17.3, 13)

    assert segments[0].icon == "sea_moderate"
    assert [segment.text for segment in segments if segment.text] == ["F3", "1.3m", "17 kn", "NNE"]
    assert segments[-1].required is False


def test_icon_is_centred_on_the_text_ink():
    """Il glifo si allinea al centro dell'inchiostro, non al bordo del riquadro del font."""
    font = fonts.load(20)
    _, cap_top, _, cap_bottom = font.getbbox("H")

    top = _icon_top(font, 100, 18)

    assert top + 18 / 2 == pytest.approx(100 + (cap_top + cap_bottom) / 2, abs=0.5)
