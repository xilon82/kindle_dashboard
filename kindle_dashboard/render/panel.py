"""Composizione del pannello: header, meteo, calendario, differenziata, treni, footer.

Tutte le misure derivano da ``height / 800``: cambiando risoluzione il layout scala, anche se è
tarato sulle proporzioni del Kindle 4 (600x800).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from PIL import Image, ImageDraw

from ..model import CalEvent, Departure, PanelData, Sea, SeaDay, Sync, Weather
from ..sources import marine as marine_source
from ..sources import weather as weather_source
from . import fonts, icons
from .fonts import Font
from .layout import compass, date_label, divider, fit_text, relative_day, waste_day_label

DEFAULT_SIZE = (600, 800)
_BASE_HEIGHT = 800
_TITLE_ROW_PX = 50
_CALENDAR_ROW_PX = 44
_TRAIN_ROW_PX = 44
_STOPS_ROW_PX = 26
# Riga delle condizioni: l'icona sostituisce la parola ("percepiti", "vento") e libera spazio.
_INLINE_GAP_PX = 6
_HEADER_GAP_PX = 10
# Separatore di sezione e distanza dal primo contenuto: la striscia meteo non ha titolo (le
# icone la identificano) e parte subito, guadagnando una riga intera.
_RULE_TOP_PX = 14
_RULE_GAP_PX = 22
# Seconda riga della striscia previsioni: sta nello slack della prima (icona 32 px in una riga
# da 54), quindi il costo verticale è di pochi pixel.
_SEA_ROW_TOP_PX = 34
_FORECAST_ROW_PX = 54
_FORECAST_ROW_SEA_PX = 58
# Spazio fra le due colonne dell'agenda e quota lasciata al calendario eventi: la differenziata
# sta in piedi con "DOMANI" + un materiale, gli eventi hanno bisogno di più caratteri.
_COLUMN_GUTTER_PX = 16
_EVENTS_SHARE = 0.6


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


@dataclass(frozen=True)
class _Segment:
    """Pezzo di una riga mista: o un testo, o un glifo.

    ``required`` falso significa "si può togliere se lo spazio non basta": è così che la
    direzione del vento o l'altezza dell'onda cedono il posto senza deformare il resto.
    """

    text: str = ""
    icon: str = ""
    required: bool = True


def _text(value: str, *, required: bool = True) -> _Segment:
    return _Segment(text=value, required=required)


def _icon(kind: str, *, required: bool = True) -> _Segment:
    return _Segment(icon=kind, required=required)


def _inline_width(segments: Sequence[_Segment], font: Font, icon_size: int, gap: int) -> int:
    """Larghezza della riga: icone a misura fissa, testi misurati con ``getlength``."""
    total = 0
    for index, segment in enumerate(segments):
        if index:
            total += gap
        total += icon_size if segment.icon else round(font.getlength(segment.text))
    return total


def _fit_inline(
    segments: Sequence[_Segment], font: Font, icon_size: int, gap: int, budget: float
) -> tuple[_Segment, ...]:
    """Toglie i pezzi non obbligatori dal fondo, poi accorcia l'ultimo testo con l'ellissi."""
    current = list(segments)
    while _inline_width(current, font, icon_size, gap) > budget:
        droppable = [index for index, segment in enumerate(current) if not segment.required]
        if not droppable:
            break
        current.pop(droppable[-1])
    width = _inline_width(current, font, icon_size, gap)
    if width > budget:
        for index in range(len(current) - 1, -1, -1):
            if not current[index].icon:
                others = width - round(font.getlength(current[index].text))
                current[index] = _text(fit_text(current[index].text, font, budget - others))
                break
    return tuple(current)


def _icon_top(font: Font, text_top: float, icon_size: int) -> int:
    """Top dell'icona perché il suo centro coincida con quello dell'inchiostro del testo.

    ``draw.text`` posiziona l'ascender: sopra le maiuscole c'è "cielo" tipografico (8 px su un
    font da 20), quindi un glifo disegnato a filo del riquadro sembra sollevato rispetto alle
    lettere. Lo scarto viene dal font, non da un numero scelto a occhio.
    """
    _, cap_top, _, cap_bottom = font.getbbox("H")
    return round(text_top + (cap_top + cap_bottom) / 2 - icon_size / 2)


def _draw_inline(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    segments: Sequence[_Segment],
    left: float,
    top: int,
    *,
    font: Font,
    icon_size: int,
) -> int:
    """Disegna i pezzi da sinistra a destra e restituisce la larghezza occupata."""
    gap = style.px(_INLINE_GAP_PX)
    x = left
    icon_y = _icon_top(font, top, icon_size)
    for index, segment in enumerate(segments):
        if index:
            x += gap
        if segment.icon:
            icons.draw_icon(
                draw, segment.icon, (round(x), icon_y, round(x) + icon_size, icon_y + icon_size)
            )
            x += icon_size
        else:
            draw.text((x, top), segment.text, font=font, fill="black")
            x += font.getlength(segment.text)
    return round(x - left) if segments else 0


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
    y = _draw_agenda(draw, style, data, y, footer_top - trains_height)
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


def _moment(data: PanelData) -> datetime:
    """Istante da mostrare all'orologio: il render se c'è, altrimenti la raccolta dati."""
    return data.rendered_at or data.generated_at


def _clock_label(data: PanelData) -> str:
    """Di notte l'ora sarebbe vecchia fino a un'ora: al suo posto si dichiara la modalità."""
    return "NOTTE" if data.night else _moment(data).strftime("%H:%M")


def _draw_header(draw: ImageDraw.ImageDraw, style: _Style, data: PanelData) -> int:
    moment = _moment(data)
    top = style.px(20)
    draw.text((style.margin, top), date_label(moment.date()), font=style.date_font, fill="black")
    if data.location_name:
        label = data.location_name.upper()
        draw.text(
            (style.right - style.small_font.getlength(label), top + style.px(8)),
            label,
            font=style.small_font,
            fill="black",
        )

    clock_top = top + style.px(28)
    draw.text(
        (style.margin, clock_top),
        _clock_label(data),
        font=style.clock_font,
        fill="black",
    )
    if data.weather is not None:
        _draw_weather_now(draw, style, data.weather, clock_top)

    status_top = clock_top + style.px(94)
    _draw_status_line(draw, style, data, status_top)
    return status_top + style.px(30)


def _draw_status_line(draw: ImageDraw.ImageDraw, style: _Style, data: PanelData, top: int) -> None:
    """Riga condizioni: testo a sinistra, mare attuale allineato a destra.

    Prima si misura il meteo — che non deve perdere pezzi, la direzione del vento è
    obbligatoria — poi il mare riceve lo spazio che resta: è il mare a cedere, non il vento.
    """
    icon_size = style.px(20)
    gap = style.px(_INLINE_GAP_PX)
    if data.weather is not None:
        segments = _condition_segments(data.weather)
    else:
        segments = (_text(_section_text(data.weather_sync, "meteo non disponibile")),)

    needed = _inline_width(segments, style.text_font, icon_size, gap)
    sea_segments = _status_sea_segments(data)
    sea_width = 0
    if sea_segments:
        sea_budget = style.content_width - needed - style.px(_HEADER_GAP_PX)
        fitted_sea = _fit_inline(sea_segments, style.text_font, icon_size, gap, sea_budget)
        sea_width = _inline_width(fitted_sea, style.text_font, icon_size, gap)
        _draw_inline(
            draw,
            style,
            fitted_sea,
            style.right - sea_width,
            top,
            font=style.text_font,
            icon_size=icon_size,
        )

    budget = style.content_width - sea_width - (style.px(_HEADER_GAP_PX) if sea_width else 0)
    fitted = _fit_inline(segments, style.text_font, icon_size, gap, budget)
    _draw_inline(draw, style, fitted, style.margin, top, font=style.text_font, icon_size=icon_size)


def _status_sea_segments(data: PanelData) -> tuple[_Segment, ...]:
    """Blocco mare della riga condizioni; vuoto quando la sezione è spenta."""
    if data.sea is not None:
        return _sea_segments(data.sea)
    if data.sea_sync.error:
        # Sezione configurata ma senza dati: si dichiara in tre parole, senza rubare una riga.
        return (_text("mare n.d."),)
    return ()


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


def _condition_segments(weather: Weather) -> tuple[_Segment, ...]:
    """Condizioni attuali: le icone sostituiscono le parole "percepiti" e "vento"."""
    segments = [_text(weather_source.label(weather.now.code))]
    if weather.now.apparent is not None:
        segments += [_icon("person"), _text(f"{weather.now.apparent:.0f}°")]
    if weather.now.wind_kn is not None:
        segments += [_icon("wind"), _text(f"{weather.now.wind_kn:.0f} kn")]
        cardinal = compass(weather.now.wind_direction)
        if cardinal:
            # "15 kn NNE": la convenzione dei bollettini, senza il "da". Obbligatorio, perché
            # è il mare a dover cedere spazio quando la riga si stringe.
            segments.append(_text(cardinal))
    return tuple(segments)


def _sea_segments(sea: Sea) -> tuple[_Segment, ...]:
    """Mare attuale: stato in parole, altezza d'onda e temperatura dell'acqua (che cede)."""
    height = sea.now.wave_height
    segments = [
        _icon(marine_source.state_kind(height)),
        _text(marine_source.state_label(height)),
        _text(marine_source.height_label(height)),
    ]
    if sea.now.water_temperature is not None:
        segments.append(_text(f"{sea.now.water_temperature:.0f}°", required=False))
    return tuple(segments)


def _sea_day_segments(
    day: SeaDay, wind_kn: float | None, wind_direction: int | None
) -> tuple[_Segment, ...]:
    """Riga sotto la previsione: forza Douglas, altezza d'onda, vento in nodi e direzione.

    La forza ("F3", 15 px) al posto delle parole ("poco mosso", 75 px) è ciò che fa entrare
    altezza e direzione nella colonna da 185 px. La direzione è l'unico pezzo che può cedere.
    """
    height = day.wave_height_max
    segments = [
        _icon(marine_source.state_kind(height)),
        _text(f"F{marine_source.state_force(height)}"),
        _text(marine_source.height_label(height)),
    ]
    if wind_kn is not None:
        segments += [_icon("wind"), _text(f"{wind_kn:.0f} kn")]
        cardinal = compass(wind_direction)
        if cardinal:
            segments.append(_text(cardinal, required=False))
    return tuple(segments)


def _draw_forecast(draw: ImageDraw.ImageDraw, style: _Style, data: PanelData, y: int) -> int:
    # Niente titolo "METEO": la striscia si riconosce dalle icone e la riga guadagna ~25 px.
    y = _section_rule(draw, style, y)
    weather = data.weather
    if weather is None:
        return _message(draw, style, y, _section_text(data.weather_sync, "meteo non disponibile"))

    days = weather.days[:3]
    column_width = style.content_width / len(days)
    icon_size = style.px(32)
    today = _moment(data).date()
    # Accoppiamento per data e non per indice: un giorno mancante non sposta le colonne.
    sea_by_day = {item.day: item for item in data.sea.days} if data.sea is not None else {}
    sea_icon = style.px(16)
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
        sea_day = sea_by_day.get(forecast.day)
        if sea_day is not None:
            _draw_inline(
                draw,
                style,
                _fit_inline(
                    _sea_day_segments(sea_day, forecast.wind_kn, forecast.wind_direction),
                    style.small_font,
                    sea_icon,
                    style.px(_INLINE_GAP_PX),
                    column_width - style.px(6),
                ),
                left,
                y + style.px(_SEA_ROW_TOP_PX),
                font=style.small_font,
                icon_size=sea_icon,
            )
    return y + style.px(_FORECAST_ROW_SEA_PX if sea_by_day else _FORECAST_ROW_PX)


def _draw_agenda(
    draw: ImageDraw.ImageDraw, style: _Style, data: PanelData, y: int, bottom: int
) -> int:
    """Calendario eventi e, se configurata, la raccolta differenziata in una colonna a destra.

    Senza ``[waste]`` la sezione resta a tutta larghezza come prima: la colonna in più è un dato
    che si aggiunge, non un layout diverso da mantenere.
    """
    divider(draw, style.margin, style.right, y + style.px(_RULE_TOP_PX), thickness=style.px(2))
    title_top = y + style.px(28)
    rows_top = y + style.px(_TITLE_ROW_PX)

    if data.waste is None:
        _column_title(
            draw, style, style.margin, title_top, "CALENDARIO", data.events_sync, style.content_width
        )
        return _draw_events(draw, style, data, rows_top, bottom, style.margin, style.right)

    gutter = style.px(_COLUMN_GUTTER_PX)
    events_right = style.margin + round((style.content_width - gutter) * _EVENTS_SHARE)
    waste_left = events_right + gutter
    events_width = events_right - style.margin
    waste_width = style.right - waste_left

    _column_title(draw, style, style.margin, title_top, "CALENDARIO", data.events_sync, events_width)
    _column_title(draw, style, waste_left, title_top, "DIFFERENZIATA", data.waste_sync, waste_width)
    events_bottom = _draw_events(draw, style, data, rows_top, bottom, style.margin, events_right)
    waste_bottom = _draw_waste(draw, style, data, rows_top, bottom, waste_left, style.right)

    separator = events_right + gutter // 2
    line_bottom = max(events_bottom, waste_bottom) - style.px(8)
    draw.rectangle(
        [separator, title_top, separator + max(1, style.px(1)), line_bottom], fill="black"
    )
    return max(events_bottom, waste_bottom)


def _draw_events(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    data: PanelData,
    y: int,
    bottom: int,
    left: int,
    right: int,
) -> int:
    if not data.events:
        return _message(
            draw,
            style,
            y,
            _section_text(data.events_sync, "nessun evento in vista"),
            left=left,
            width=right - left,
        )

    today = _moment(data).date()
    row = style.px(_CALENDAR_ROW_PX)
    for event in data.events:
        if y + row > bottom:
            break
        when = _event_when(event, today)
        when_width = max(style.px(52), style.body_font.getlength(when) + style.px(10))
        draw.text((left, y), when, font=style.body_font, fill="black")
        draw.text(
            (left + when_width, y),
            fit_text(event.summary, style.text_font, right - left - when_width),
            font=style.text_font,
            fill="black",
        )
        y += row
    return y


def _draw_waste(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    data: PanelData,
    y: int,
    bottom: int,
    left: int,
    right: int,
) -> int:
    """Un giorno per riga: ``niente`` dice che oggi non si porta fuori nulla."""
    days = data.waste or ()
    if not days:
        return _message(
            draw,
            style,
            y,
            _section_text(data.waste_sync, "nessuna raccolta"),
            left=left,
            width=right - left,
        )

    today = _moment(data).date()
    row = style.px(_CALENDAR_ROW_PX)
    for item in days:
        if y + row > bottom:
            break
        label = waste_day_label(item.day, today)
        draw.text((left, y), label, font=style.body_font, fill="black")
        kinds = ", ".join(item.kinds) if item.kinds else "niente"
        available = right - left - style.body_font.getlength(label) - style.px(10)
        kinds = fit_text(kinds, style.text_font, available)
        draw.text(
            (right - style.text_font.getlength(kinds), y + style.px(2)),
            kinds,
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
    parts = [f"dati {data.generated_at.strftime('%H:%M')}"]
    if any(item.realtime for item in data.departures):
        parts.append("treni in tempo reale")
    if (
        data.weather_sync.stale
        or data.sea_sync.stale
        or data.events_sync.stale
        or data.waste_sync.stale
        or data.departures_sync.stale
    ):
        parts.append("alcuni dati dalla cache")
    draw.text(
        (style.margin, style.height - style.margin - style.px(14)),
        fit_text(" · ".join(parts), style.small_font, style.content_width),
        font=style.small_font,
        fill="black",
    )


def _section_rule(draw: ImageDraw.ImageDraw, style: _Style, y: int) -> int:
    """Separatore di sezione senza titolo: il contenuto parte subito dopo, senza riga sprecata."""
    divider(draw, style.margin, style.right, y + style.px(_RULE_TOP_PX), thickness=style.px(2))
    return y + style.px(_RULE_GAP_PX)


def _section_title(
    draw: ImageDraw.ImageDraw, style: _Style, y: int, title: str, sync: Sync
) -> int:
    divider(draw, style.margin, style.right, y + style.px(_RULE_TOP_PX), thickness=style.px(2))
    _column_title(draw, style, style.margin, y + style.px(28), title, sync, style.content_width)
    return y + style.px(_TITLE_ROW_PX)


def _column_title(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    x: float,
    top: int,
    title: str,
    sync: Sync,
    width: float,
) -> None:
    """Titolo di sezione o di colonna: il suffisso "agg." compare solo se ci sta nella larghezza."""
    text = title
    if sync.stale and sync.updated_at is not None:
        text = f"{title} · agg. {sync.updated_at.strftime('%H:%M')}"
    draw.text(
        (x, top), fit_text(text, style.title_font, width), font=style.title_font, fill="black"
    )


def _message(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    y: int,
    text: str,
    *,
    left: float | None = None,
    width: float | None = None,
) -> int:
    draw.text(
        (style.margin if left is None else left, y),
        fit_text(text, style.text_font, style.content_width if width is None else width),
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


