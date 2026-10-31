"""Composizione del pannello: header, meteo, calendario, treni, footer.

Tutte le misure derivano da ``height / 800``: cambiando risoluzione il layout scala, anche se è
tarato sulle proporzioni del Kindle 4 (600x800).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from PIL import Image, ImageDraw

from ..model import CalEvent, Departure, PanelData, Sync, Weather
from ..sources import weather as weather_source
from . import fonts, icons
from .fonts import Font
from .layout import date_label, divider, fit_text, relative_day

DEFAULT_SIZE = (600, 800)
_BASE_HEIGHT = 800
_TITLE_ROW_PX = 50
_CALENDAR_ROW_PX = 40
_TRAIN_ROW_PX = 40
_STOPS_ROW_PX = 26


@dataclass(frozen=True)
class _Style:
    width: int
    height: int
    margin: int
    scale: float
    date_font: Font
    clock_font: Font
    temp_font: Font
    body_font: Font
    text_font: Font
    small_font: Font
    title_font: Font

    @property
    def content_width(self) -> int:
        return self.width - 2 * self.margin

    @property
    def right(self) -> int:
        return self.width - self.margin

    def px(self, value: float) -> int:
        return max(1, round(value * self.scale))


def render_panel(
    data: PanelData,
    size: tuple[int, int] = DEFAULT_SIZE,
    *,
    font_override: str = "",
    bold_override: str = "",
    stop_priority: Sequence[str] = (),
) -> Image.Image:
    """Disegna il pannello e restituisce un'immagine in scala di grigi (per la resa e-ink)."""
    style = _build_style(size, font_override, bold_override)
    image = Image.new("L", size, "white")
    draw = ImageDraw.Draw(image)

    # Il treno è il dato con la scadenza più stretta: gli si riserva spazio in fondo e il
    # calendario si tronca se non ci sta, invece di spingere i treni fuori dallo schermo.
    footer_top = style.height - style.margin - style.px(16)
    trains_height = style.px(_TITLE_ROW_PX) + sum(
        style.px(_TRAIN_ROW_PX) + (style.px(_STOPS_ROW_PX) if item.stops else 0)
        for item in data.departures
    )

    y = _draw_header(draw, style, data)
    y = _draw_forecast(draw, style, data, y)
    y = _draw_calendar(draw, style, data, y, footer_top - trains_height)
    _draw_trains(draw, style, data, y, stop_priority)
    _draw_footer(draw, style, data)
    return image


def _build_style(size: tuple[int, int], font_override: str, bold_override: str) -> _Style:
    width, height = size
    scale = height / _BASE_HEIGHT

    def bold(size_px: float) -> Font:
        return fonts.load(max(8, round(size_px * scale)), bold=True, override=bold_override)

    def regular(size_px: float) -> Font:
        return fonts.load(max(8, round(size_px * scale)), override=font_override)

    return _Style(
        width=width,
        height=height,
        margin=round(width * 0.037),
        scale=scale,
        date_font=bold(26),
        clock_font=bold(84),
        temp_font=bold(50),
        body_font=bold(23),
        text_font=regular(22),
        small_font=regular(16),
        title_font=bold(17),
    )


def _draw_header(draw: ImageDraw.ImageDraw, style: _Style, data: PanelData) -> int:
    top = style.px(20)
    draw.text((style.margin, top), date_label(data.generated_at.date()), font=style.date_font, fill="black")
    if data.location_name:
        label = data.location_name.upper()
        draw.text(
            (style.right - style.small_font.getlength(label), top + style.px(8)),
            label,
            font=style.small_font,
            fill="black",
        )

    clock_top = top + style.px(36)
    draw.text(
        (style.margin, clock_top),
        data.generated_at.strftime("%H:%M"),
        font=style.clock_font,
        fill="black",
    )
    if data.weather is not None:
        _draw_weather_now(draw, style, data.weather, clock_top)
        conditions = _conditions_text(data.weather)
    else:
        conditions = _section_text(data.weather_sync, "meteo non disponibile")

    status_top = clock_top + style.px(86)
    draw.text(
        (style.margin, status_top),
        fit_text(conditions, style.text_font, style.content_width),
        font=style.text_font,
        fill="black",
    )
    return status_top + style.px(30)


def _draw_weather_now(draw: ImageDraw.ImageDraw, style: _Style, weather: Weather, top: int) -> None:
    text = f"{weather.now.temperature:.0f}°"
    text_width = style.temp_font.getlength(text)
    draw.text((style.right - text_width, top + style.px(6)), text, font=style.temp_font, fill="black")
    icon_size = style.px(52)
    icon_left = style.right - text_width - style.px(12) - icon_size
    icon_top = round(top + style.px(4))
    icons.draw_icon(
        draw,
        weather_source.icon_kind(weather.now.code),
        (round(icon_left), icon_top, round(icon_left + icon_size), icon_top + icon_size),
    )


def _conditions_text(weather: Weather) -> str:
    parts = [weather_source.label(weather.now.code)]
    if weather.now.apparent is not None:
        parts.append(f"percepiti {weather.now.apparent:.0f}°")
    if weather.now.wind_kmh is not None:
        parts.append(f"vento {weather.now.wind_kmh:.0f} km/h")
    return " · ".join(parts)


def _draw_forecast(draw: ImageDraw.ImageDraw, style: _Style, data: PanelData, y: int) -> int:
    y = _section_title(draw, style, y, "METEO", data.weather_sync)
    weather = data.weather
    if weather is None:
        return _message(draw, style, y, _section_text(data.weather_sync, "meteo non disponibile"))

    days = weather.days[:3]
    column_width = style.content_width / len(days)
    icon_size = style.px(32)
    today = data.generated_at.date()
    for index, forecast in enumerate(days):
        left = style.margin + index * column_width
        icons.draw_icon(
            draw,
            weather_source.icon_kind(forecast.code),
            (round(left), y, round(left) + icon_size, y + icon_size),
        )
        label = f"{relative_day(forecast.day, today)} {forecast.t_max:.0f}°/{forecast.t_min:.0f}°"
        draw.text(
            (left + icon_size + style.px(7), y + style.px(4)),
            fit_text(label, style.body_font, column_width - icon_size - style.px(10)),
            font=style.body_font,
            fill="black",
        )
    return y + style.px(54)


def _draw_calendar(
    draw: ImageDraw.ImageDraw, style: _Style, data: PanelData, y: int, bottom: int
) -> int:
    y = _section_title(draw, style, y, "CALENDARIO", data.events_sync)
    if not data.events:
        return _message(draw, style, y, _section_text(data.events_sync, "nessun evento in vista"))

    today = data.generated_at.date()
    row = style.px(_CALENDAR_ROW_PX)
    for event in data.events:
        if y + row > bottom:
            break
        when = _event_when(event, today)
        when_width = max(style.px(52), style.body_font.getlength(when) + style.px(10))
        draw.text((style.margin, y), when, font=style.body_font, fill="black")
        draw.text(
            (style.margin + when_width, y),
            fit_text(event.summary, style.text_font, style.right - style.margin - when_width),
            font=style.text_font,
            fill="black",
        )
        y += row
    return y


@dataclass(frozen=True)
class _Columns:
    """Larghezze delle colonne treni, misurate sul font reale (non su pixel a occhio)."""

    time: int
    line: int


def _draw_trains(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    data: PanelData,
    top: int,
    stop_priority: Sequence[str],
) -> None:
    title = "TRENI" if not data.board_name else f"TRENI · {data.board_name.upper()}"
    y = _section_title(draw, style, top, title, data.departures_sync)
    if not data.departures:
        _message(draw, style, y, _section_text(data.departures_sync, "nessuna partenza in vista"))
        return

    # La destinazione resta su ogni riga: distingue il capolinea romano (Termini, Tiburtina, Ostiense).
    columns = _measure_columns(style, data.departures)
    for departure in data.departures:
        _draw_departure(draw, style, departure, y, columns, stop_priority)
        y += style.px(_TRAIN_ROW_PX) + (style.px(_STOPS_ROW_PX) if departure.stops else 0)


def _measure_columns(style: _Style, departures: Sequence[Departure]) -> _Columns:
    time_width = round(style.body_font.getlength("00:00")) + style.px(8)
    widest_line = max(style.body_font.getlength(item.line) for item in departures)
    line_width = min(round(widest_line) + style.px(10), round(style.content_width * 0.24))
    return _Columns(time=time_width, line=line_width)


def _draw_departure(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    departure: Departure,
    y: int,
    columns: _Columns,
    stop_priority: Sequence[str],
) -> None:
    status = "ANN." if departure.cancelled else _delay_text(departure)
    status_width = style.body_font.getlength(status) if status else 0
    draw.text(
        (style.margin, y), departure.expected.strftime("%H:%M"), font=style.body_font, fill="black"
    )

    line_left = style.margin + columns.time
    draw.text(
        (line_left, y),
        fit_text(departure.line, style.body_font, columns.line - style.px(6)),
        font=style.body_font,
        fill="black",
    )

    track = f"b.{departure.track}" if departure.track else ""
    track_width = style.text_font.getlength(track) if track else 0
    cursor = style.right
    if status:
        cursor -= status_width
        draw.text((cursor, y), status, font=style.body_font, fill="black")
        cursor -= style.px(8)
    if track:
        cursor -= track_width
        draw.text((cursor, y + style.px(2)), track, font=style.text_font, fill="black")
        cursor -= style.px(8)

    destination_left = line_left + columns.line
    draw.text(
        (destination_left, y),
        fit_text(departure.destination.title(), style.text_font, cursor - destination_left),
        font=style.text_font,
        fill="black",
    )

    if departure.stops:
        tokens = [
            (
                f"{_stop_label(stop.name)} {stop.when.strftime('%H:%M')}",
                _is_priority(stop.name, stop_priority),
            )
            for stop in departure.stops
        ]
        line = _stop_line(tokens, style.small_font, style.right - line_left)
        if line:
            draw.text((line_left, y + style.px(22)), line, font=style.small_font, fill="black")


def _is_priority(name: str, keywords: Sequence[str]) -> bool:
    haystack = name.casefold()
    return any(keyword.casefold() in haystack for keyword in keywords)


def _stop_line(tokens: Sequence[tuple[str, bool]], font: Font, max_width: float) -> str:
    """Una sola riga di fermate: se non ci stanno si scartano prima quelle non prioritarie."""
    current = list(tokens)
    while current:
        text = " · ".join(token for token, _ in current)
        if font.getlength(text) <= max_width:
            return text
        removable = [index for index, (_, priority) in enumerate(current) if not priority]
        current.pop(removable[-1] if removable else len(current) - 1)
    return ""


def _stop_label(name: str) -> str:
    """``ROMA S.PIETRO`` diventa ``S.Pietro``: il prefisso città è già nel titolo della sezione."""
    cleaned = name.strip()
    if cleaned.upper().startswith("ROMA "):
        cleaned = cleaned[5:]
    return cleaned.title()


def _draw_footer(draw: ImageDraw.ImageDraw, style: _Style, data: PanelData) -> None:
    parts = [f"agg. {data.generated_at.strftime('%H:%M')}"]
    if any(item.realtime for item in data.departures):
        parts.append("treni in tempo reale")
    if data.weather_sync.stale or data.events_sync.stale or data.departures_sync.stale:
        parts.append("alcuni dati dalla cache")
    draw.text(
        (style.margin, style.height - style.margin - style.px(14)),
        fit_text(" · ".join(parts), style.small_font, style.content_width),
        font=style.small_font,
        fill="black",
    )


def _section_title(
    draw: ImageDraw.ImageDraw, style: _Style, y: int, title: str, sync: Sync
) -> int:
    divider(draw, style.margin, style.right, y + style.px(16), thickness=style.px(2))
    top = y + style.px(28)
    text = title
    if sync.stale and sync.updated_at is not None:
        text = f"{title} · agg. {sync.updated_at.strftime('%H:%M')}"
    draw.text((style.margin, top), text, font=style.title_font, fill="black")
    return y + style.px(_TITLE_ROW_PX)


def _message(draw: ImageDraw.ImageDraw, style: _Style, y: int, text: str) -> int:
    draw.text(
        (style.margin, y),
        fit_text(text, style.text_font, style.content_width),
        font=style.text_font,
        fill="black",
    )
    return y + style.px(28)


def _section_text(sync: Sync, fallback: str) -> str:
    """Messaggio di sezione: l'errore reale vince sul testo generico."""
    return sync.error or fallback


def _event_when(event: CalEvent, today: date) -> str:
    start = event.start
    if event.all_day:
        return relative_day(start.date(), today)
    if start.date() == today:
        return start.strftime("%H:%M")
    return f"{relative_day(start.date(), today)} {start.strftime('%H:%M')}"


def _delay_text(departure: Departure) -> str:
    minutes = departure.delay_minutes
    return f"+{minutes}'" if minutes > 0 else ""


