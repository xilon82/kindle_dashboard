"""Test del renderer: dimensioni, contenuto non vuoto e robustezza con dati mancanti."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest
from PIL import Image, ImageDraw

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
from kindle_dashboard.render import fonts, icons
from kindle_dashboard.render.layout import (
    COMPASS_POINTS,
    WIND_NAMES,
    compass,
    waste_day_label,
    wind_name,
    wrap_text,
)
from kindle_dashboard.render.panel import (
    _CALENDAR_ROW_PX,
    _TITLE_ROW_PX,
    _build_style,
    _clock_label,
    _draw_events,
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
    _title_icon,
    _trains_height,
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
                humidity=62,
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
        "· Tramontana-Grecale",
    ]
    # La sigla resta obbligatoria; il nome è il di più che si toglie per primo.
    assert [segment.required for segment in segments if segment.text] == [True, True, False]


def test_now_details_show_humidity_rain_and_apparent_temperature():
    weather = Weather(
        now=WeatherNow(temperature=16.6, code=2, apparent=15.9, rain_probability=40, humidity=63),
        days=(),
    )

    segments = _now_detail_segments(weather)
    without_apparent = _now_detail_segments(weather, with_apparent=False)

    # Ordine di lettura: umidità, pioggia, percepita (l'umidità ha la goccia, la percezione il
    # glifo "persona": è quello che sente il corpo, non un termometro).
    assert [segment.icon for segment in segments if segment.icon] == [
        "humidity",
        "umbrella",
        "person",
    ]
    assert [segment.text for segment in segments if segment.text] == ["63%", "40%", "16°"]
    assert [segment.text for segment in without_apparent if segment.text] == ["63%", "40%"]


def test_now_details_drop_the_apparent_temperature_before_the_rain():
    """La percepita è il pezzo più sacrificabile: la temperatura reale è già grande sopra la riga."""
    weather = Weather(
        now=WeatherNow(temperature=16.6, code=2, apparent=15.9, rain_probability=40, humidity=63),
        days=(),
    )

    humidity_only = _now_detail_segments(weather, with_rain=False, with_apparent=False)

    assert [segment.text for segment in humidity_only if segment.text] == ["63%"]


def test_now_details_survive_a_cache_without_humidity():
    weather = Weather(
        now=WeatherNow(temperature=16.6, code=2, apparent=15.9, rain_probability=40),
        days=(),
    )

    assert [segment.text for segment in _now_detail_segments(weather) if segment.text] == [
        "40%",
        "16°",
    ]


def test_detail_font_is_bigger_than_the_small_font():
    """La riga dei dettagli è ingrandita: se qualcuno la riporta a ``small_font``, questo cade."""
    style = _build_style((600, 800), "", "")

    assert style.detail_font.getlength("0123456789") > style.small_font.getlength("0123456789")


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
        (18, "Tramontana-Grecale"),
        (45, "Grecale"),
        (68, "Levante-Grecale"),
        (90, "Levante"),
        (113, "Levante-Scirocco"),
        (137, "Scirocco"),
        (158, "Ostro-Scirocco"),
        (180, "Ostro"),
        (203, "Ostro-Libeccio"),
        (225, "Libeccio"),
        (248, "Ponente-Libeccio"),
        (270, "Ponente"),
        (293, "Ponente-Maestrale"),
        (315, "Maestrale"),
        (340, "Tramontana-Maestrale"),
        (359, "Tramontana"),
        (None, ""),
    ],
)
def test_wind_name_covers_all_sixteen_sectors(degrees, expected):
    assert wind_name(degrees) == expected


def test_intermediate_wind_names_follow_the_letters_of_the_compass_point():
    """La prima lettera della sigla dà il primo nome, il resto il secondo (``OSO`` = Ponente-Libeccio).

    La regola si verifica contro gli otto venti principali della stessa tabella: se qualcuno riordina
    una coppia a occhio, il test cade e le due grafie non possono divergere.
    """
    main_winds = {COMPASS_POINTS[index]: WIND_NAMES[index] for index in range(0, 16, 2)}

    for index in range(1, 16, 2):
        point = COMPASS_POINTS[index]
        assert WIND_NAMES[index] == f"{main_winds[point[0]]}-{main_winds[point[1:]]}"


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


def test_title_icon_yields_when_the_title_does_not_fit():
    """L'icona di sezione è decorazione: cede prima del testo, che porta anche il "· agg."."""
    style = _build_style((600, 800), "", "")
    text = "DIFFERENZIATA · agg. 21:35"
    size = style.px(22)
    offset = size + style.px(6)
    needed = style.title_font.getlength(text)

    assert _title_icon(style, text, needed + offset - 1, "waste") == (0, 0)
    assert _title_icon(style, text, needed + offset + 1, "waste") == (size, offset)


def test_title_icon_is_absent_when_no_icon_is_asked():
    style = _build_style((600, 800), "", "")

    assert _title_icon(style, "CALENDARIO", 400, "") == (0, 0)


@pytest.mark.parametrize("kind", ["calendar", "waste", "train", "partly", "storm"])
def test_section_and_weather_icons_paint_ink(kind):
    image = Image.new("L", (32, 32), "white")

    icons.draw_icon(ImageDraw.Draw(image), kind, (0, 0, 32, 32))

    assert image.getextrema()[0] < 200


@pytest.mark.parametrize("kind", ["partly", "storm", "cloud", "rain", "drizzle", "snow", "fog"])
def test_secondary_elements_use_a_second_tone(kind):
    """Il secondo tono separa le forme: sole dietro la nuvola, lampo, seconda nuvola, nebbia."""
    image = Image.new("L", (32, 32), "white")

    icons.draw_icon(ImageDraw.Draw(image), kind, (0, 0, 32, 32))

    levels = set(image.tobytes())
    assert 0 in levels
    assert 0x8C in levels


def test_section_title_rows_are_taller_than_content_rows():
    """Si ingrandiscono le intestazioni, non il contenuto: la riga del titolo resta la più alta."""
    assert _TITLE_ROW_PX > _CALENDAR_ROW_PX


def test_the_column_separator_reaches_the_trains_rule():
    """La linea fra calendario e differenziata scende fino alla regola dei treni."""
    style = _build_style((600, 800), "", "")
    data = full_panel()
    footer_top = 800 - style.margin - style.px(16)
    trains_top = footer_top - _trains_height(style, data.departures)

    image = render_panel(data, (600, 800))

    band = image.crop(
        (style.margin + style.px(240), trains_top + style.px(4), style.right, trains_top + style.px(6))
    )
    assert band.getextrema()[0] == 0


def test_trains_height_counts_title_rows_stops_and_message():
    style = _build_style((600, 720), "", "")
    plain = Departure(scheduled=NOW, expected=NOW, line="RV 4137", destination="Roma Termini")
    with_stops = replace(plain, stops=(CallAt(name="ROMA S.PIETRO", when=NOW),))

    assert _trains_height(style, ()) == style.px(56) + style.px(28)
    assert _trains_height(style, (plain,)) == style.px(56) + style.px(44)
    assert _trains_height(style, (plain, with_stops)) == (
        style.px(56) + 2 * style.px(44) + style.px(26)
    )


def test_trains_block_is_anchored_to_the_bottom():
    """Con l'agenda vuota i treni stanno in fondo, non a metà pagina con il vuoto sotto."""
    style = _build_style((600, 800), "", "")
    footer_top = 800 - style.margin - style.px(16)
    panel = PanelData(
        generated_at=NOW,
        timezone="Europe/Rome",
        departures=(
            Departure(scheduled=NOW, expected=NOW, line="RV 4137", destination="Roma Termini"),
            Departure(scheduled=NOW, expected=NOW, line="RV 4142", destination="Roma Ostiense"),
        ),
        departures_sync=Sync(updated_at=NOW),
    )

    image = render_panel(panel, (600, 800))

    band = image.crop((0, footer_top - style.px(60), 600, footer_top))
    assert band.getextrema()[0] == 0


class _RecordingDraw:
    """Finto ``ImageDraw``: registra le sole chiamate a `text`, che è tutto ciò che serve qui."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float, str]] = []

    def text(self, xy: tuple[float, float], text: str, **_kwargs: object) -> None:
        self.calls.append((xy[0], xy[1], text))

    def summaries(self, style) -> list[tuple[float, str]]:
        """Testi disegnati a destra dell'ora, cioè le righe del titolo dell'evento."""
        return [(y, text) for x, y, text in self.calls if x > style.margin]

    def whens(self, style) -> list[str]:
        """Le colonne dell'ora: una per evento disegnato (stanno tutte sul margine sinistro)."""
        return [text for x, _, text in self.calls if x == style.margin]


def _agenda_panel(summaries: list[str]) -> PanelData:
    events = tuple(
        CalEvent(start=datetime(2026, 10, 31, 18, 42, tzinfo=TZ), summary=text)
        for text in summaries
    )
    return PanelData(
        generated_at=NOW,
        timezone="Europe/Rome",
        events=events,
        events_sync=Sync(updated_at=NOW),
    )


def test_wrap_text_keeps_a_short_summary_on_one_line():
    font = fonts.load(20)

    assert wrap_text("Ale incontro yoga", font, 1000) == ("Ale incontro yoga",)


def test_wrap_text_splits_on_a_space_and_never_inside_a_word():
    font = fonts.load(20)

    lines = wrap_text("Visita casa xmare", font, font.getlength("Visita casa"))

    assert lines == ("Visita casa", "xmare")


def test_wrap_text_never_exceeds_the_requested_lines():
    font = fonts.load(20)
    long_summary = "Mamma e papà a pranzo fuori con gli amici e i parenti"

    assert len(wrap_text(long_summary, font, 120, lines=1)) == 1
    assert len(wrap_text(long_summary, font, 120, lines=2)) == 2
    assert wrap_text(long_summary, font, 120, lines=1)[0].endswith("…")


def test_agenda_wraps_a_long_summary_instead_of_cutting_it():
    """Due righe quando lo spazio verticale c'è: nessuna parola persa e nessuna ellissi."""
    style = _build_style((600, 800), "", "")
    data = _agenda_panel(["Mamma e papà a pranzo fuori"])
    draw = _RecordingDraw()
    when_width = max(style.px(52), style.body_font.getlength("18:42") + style.px(10))
    line_width = style.text_font.getlength("Mamma e papà a pranzo") + 1

    _draw_events(
        draw, style, data, 0, style.px(400), style.margin, style.margin + when_width + line_width
    )

    lines = [text for _, text in draw.summaries(style)]
    assert len(lines) == 2
    assert not any(line.endswith("…") for line in lines)
    assert " ".join(lines) == "Mamma e papà a pranzo fuori"
    # La seconda riga sta sotto la prima, con il passo dichiarato.
    assert [y for y, _ in draw.summaries(style)] == [0, style.px(26)]


def test_agenda_falls_back_to_one_line_when_the_second_would_not_fit():
    """Se la seconda riga non ci sta si torna all'ellissi: meglio un testo corto che un evento perso."""
    style = _build_style((600, 800), "", "")
    data = _agenda_panel(["Mamma e papà a pranzo fuori con gli amici"])
    draw = _RecordingDraw()

    _draw_events(draw, style, data, 0, style.px(48), style.margin, style.margin + style.px(300))

    lines = [text for _, text in draw.summaries(style)]
    assert len(lines) == 1
    assert lines[0].endswith("…")
    assert draw.whens(style) == ["18:42"]


def test_agenda_does_not_lose_events_to_make_room_for_a_second_line():
    """Con tre eventi e lo spazio contato restano tutti: il testo lungo non ruba la riga altrui."""
    style = _build_style((600, 800), "", "")
    data = _agenda_panel(
        [
            "Visita casa xmamma e papà",
            "Mamma e papà a pranzo fuori",
            "Ale incontro yoga",
        ]
    )
    draw = _RecordingDraw()
    bottom = style.px(150)

    _draw_events(draw, style, data, 0, bottom, style.margin, style.margin + style.px(300))

    assert len(draw.whens(style)) == 3
    # Nessuna riga esce dal blocco: la seconda riga non sfonda `bottom`.
    assert max(y for _, y, _ in draw.calls) < bottom
