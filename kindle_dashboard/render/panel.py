"""Composizione del pannello: header, meteo, calendario, differenziata, treni, footer.

Tutte le misure derivano da ``height / 800``: cambiando risoluzione il layout scala, anche se è
tarato sulle proporzioni del Kindle 4 (600x800).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from PIL import Image, ImageDraw

from ..model import CalEvent, DayForecast, Departure, PanelData, Sea, SeaDay, Sync, Weather
from ..sources import marine as marine_source
from ..sources import weather as weather_source
from . import fonts, icons
from .fonts import Font
from .layout import (
    compass,
    date_label,
    divider,
    fit_text,
    relative_day,
    waste_day_label,
    wind_name,
    wrap_text,
)

DEFAULT_SIZE = (600, 800)
_BASE_HEIGHT = 800
_TITLE_ROW_PX = 56
_CALENDAR_ROW_PX = 44
# Passo fra le righe di un evento su due righe. Il riassunto va a capo solo quando la riga in più
# sta sopra `bottom`: allargare la riga senza questo limite farebbe sparire un evento intero, che
# è peggio di un'ellissi.
_CALENDAR_LINE_PX = 26
_TRAIN_ROW_PX = 44
_STOPS_ROW_PX = 26
# Riga del messaggio "nessuna partenza in vista": serve anche a `_trains_height`, perché il
# blocco è ancorato al fondo e senza questa riga il messaggio finirebbe sotto la barra del footer.
_MESSAGE_ROW_PX = 28
# Icona accanto al titolo di sezione: sta dentro la riga del titolo, quindi non costa altezza;
# cede però quando il titolo (con "· agg. HH:MM") non lascerebbe spazio sufficiente.
_TITLE_ICON_PX = 22
# Riga delle condizioni: l'icona sostituisce la parola ("percepiti", "vento") e libera spazio.
_INLINE_GAP_PX = 6
_HEADER_GAP_PX = 10
# Separatore di sezione e distanza dal primo contenuto: la striscia meteo non ha titolo (le
# icone la identificano) e parte subito, guadagnando una riga intera.
_RULE_TOP_PX = 14
_RULE_GAP_PX = 22
# Intestazione: la fascia dell'orologio copre le righe 2-4 della griglia; percepita e probabilità
# di pioggia stanno nello slack sotto la temperatura grande, quindi non costano una riga in più.
_CLOCK_BAND_PX = 94
_NOW_DETAILS_TOP_PX = 60
# Righe 5 e 6: alba/tramonto e vento a sinistra, descrizione e mare a destra. Il mare non divide
# più la riga con il vento, così ognuno ha la sua colonna e nessuno dei due deve cedere all'altro.
_STATUS_ROW_PX = 26
_STATUS_BOTTOM_PX = 30
# Seconda riga della striscia previsioni: sta nello slack della prima (icona 32 px in una riga
# da 54), quindi il costo verticale è di pochi pixel.
_SEA_ROW_TOP_PX = 34
_FORECAST_ROW_PX = 54
_FORECAST_ROW_SEA_PX = 58
# Spazio fra le due colonne dell'agenda e quota lasciata al calendario eventi: la differenziata
# deve contenere "DIFFERENZIATA · agg. HH:MM", gli eventi hanno bisogno di più caratteri.
_COLUMN_GUTTER_PX = 16
_EVENTS_SHARE = 0.60


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
    # Riga dei dettagli del meteo (umidità, pioggia, percepita): sta nello slack sotto la
    # temperatura grande, dove c'è spazio, e a 16 px si leggeva male sul e-ink.
    detail_font: Font

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

    # Il treno è il dato con la scadenza più stretta: il blocco sta **ancorato al fondo**, così
    # l'agenda riceve lo spazio che resta e i treni non «galleggiano» a metà pagina quando gli
    # eventi sono pochi. Se il calendario non ci sta si troncano le sue righe, non i treni.
    footer_top = style.height - style.margin - style.px(16)
    trains_top = footer_top - _trains_height(style, data.departures)

    y = _draw_header(draw, style, data)
    y = _draw_forecast(draw, style, data, y)
    _draw_agenda(draw, style, data, y, trains_top)
    _draw_trains(draw, style, data, trains_top, stop_priority)
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
        title_font=bold(19),
        detail_font=bold(20),
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
    clock = _clock_label(data)
    draw.text((style.margin, clock_top), clock, font=style.clock_font, fill="black")
    clock_right = style.margin + round(style.clock_font.getlength(clock))
    if data.weather is not None:
        _draw_weather_now(draw, style, data.weather, clock_top)
        _draw_now_details(
            draw, style, data.weather, clock_top + style.px(_NOW_DETAILS_TOP_PX), clock_right
        )

    return _draw_status_rows(draw, style, data, clock_top + style.px(_CLOCK_BAND_PX))


def _draw_status_rows(draw: ImageDraw.ImageDraw, style: _Style, data: PanelData, top: int) -> int:
    """Righe 5 e 6: alba/tramonto e vento a sinistra, descrizione e mare a destra.

    Ogni blocco ha la sua colonna, quindi vento e mare non si contendono più la stessa riga:
    l'ordine verticale dei bollettini (vento prima del mare) si legge in orizzontale.
    """
    row = style.px(_STATUS_ROW_PX)
    weather = data.weather
    if weather is None:
        _message(draw, style, top, _section_text(data.weather_sync, "meteo non disponibile"))
        _draw_balanced_row(draw, style, (), _status_sea_segments(data), top + row)
        return top + style.px(_STATUS_ROW_PX + _STATUS_BOTTOM_PX)

    today = _today_forecast(weather, _moment(data))
    sun = _sun_segments(today)
    label = _text(weather_source.label(weather.now.code))
    # La descrizione va nella colonna destra quando gli orari del sole occupano la sinistra; se
    # mancano (cache scritta prima dei campi nuovi) resta a sinistra, come prima del restyling.
    description: tuple[_Segment, ...] = (label,) if sun else ()
    _draw_balanced_row(draw, style, sun or (label,), description, top)
    _draw_balanced_row(draw, style, _wind_segments(weather), _status_sea_segments(data), top + row)
    return top + style.px(_STATUS_ROW_PX + _STATUS_BOTTOM_PX)


def _status_sea_segments(data: PanelData) -> tuple[_Segment, ...]:
    """Blocco mare della riga di stato; vuoto quando la sezione è spenta."""
    if data.sea is not None:
        return _sea_segments(data.sea)
    if data.sea_sync.error:
        # Sezione configurata ma senza dati: si dichiara in tre parole, senza rubare una riga.
        return (_text("mare n.d."),)
    return ()


def _draw_balanced_row(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    left: Sequence[_Segment],
    right: Sequence[_Segment],
    top: int,
) -> None:
    """Riga a due colonne: il blocco sinistro ha la precedenza, il destro riceve il resto.

    Serve al vento: ``Tramontana-Maestrale`` è lungo e con una quota fissa a metà riga verrebbe
    scartato. Il destro scende sotto metà larghezza solo quando il sinistro la occupa davvero, e
    a cedere è la temperatura dell'acqua, non il nome del vento.
    """
    icon_size = style.px(20)
    gap = style.px(_INLINE_GAP_PX)
    gutter = style.px(_HEADER_GAP_PX)
    share = style.content_width / 2
    wanted_left = _inline_width(left, style.text_font, icon_size, gap)
    right_budget = min(share, max(0.0, style.content_width - wanted_left - gutter))
    fitted_right = _fit_inline(right, style.text_font, icon_size, gap, right_budget)
    right_width = _inline_width(fitted_right, style.text_font, icon_size, gap)
    left_budget = style.content_width - right_width - gutter
    fitted_left = _fit_inline(left, style.text_font, icon_size, gap, left_budget)
    _draw_inline(draw, style, fitted_left, style.margin, top, font=style.text_font, icon_size=icon_size)
    _draw_inline(
        draw,
        style,
        fitted_right,
        style.right - right_width,
        top,
        font=style.text_font,
        icon_size=icon_size,
    )


def _today_forecast(weather: Weather, moment: datetime) -> DayForecast | None:
    """Previsione di oggi: alba e tramonto stanno lì, accoppiati per data e non per indice."""
    return next((day for day in weather.days if day.day == moment.date()), None)


def _sun_segments(day: DayForecast | None) -> tuple[_Segment, ...]:
    """Alba e tramonto su una riga: sole sul filo dell'orizzonte e freccia su/giù.

    Le frecce sono l'unico pezzo che può cedere: senza di loro glifo e orario restano leggibili,
    mentre troncare un orario non lo è.
    """
    if day is None:
        return ()
    segments: list[_Segment] = []
    if day.sunrise is not None:
        segments += [
            _icon("sunrise"),
            _text(day.sunrise.strftime("%H:%M")),
            _icon("arrow_up", required=False),
        ]
    if day.sunset is not None:
        segments += [
            _icon("sunset"),
            _text(day.sunset.strftime("%H:%M")),
            _icon("arrow_down", required=False),
        ]
    return tuple(segments)


def _wind_segments(weather: Weather) -> tuple[_Segment, ...]:
    """Vento attuale: nodi, direzione obbligatoria e nome tradizionale che può cedere.

    La sigla resta obbligatoria (il vento non perde la direzione); il nome è un di più che si
    toglie quando la colonna si stringe.
    """
    if weather.now.wind_kn is None:
        return ()
    segments: list[_Segment] = [_icon("wind"), _text(f"{weather.now.wind_kn:.0f} kn")]
    cardinal = compass(weather.now.wind_direction)
    if cardinal:
        segments.append(_text(cardinal))
        name = wind_name(weather.now.wind_direction)
        if name:
            segments.append(_text(f"· {name}", required=False))
    return tuple(segments)


def _now_detail_segments(
    weather: Weather, *, with_apparent: bool = True, with_rain: bool = True
) -> tuple[_Segment, ...]:
    """Umidità, pioggia e percepita, nell'ordine in cui si leggono sotto la temperatura.

    La percepita è il pezzo che si perde per primo: la temperatura reale è già scritta grande
    sopra la riga. L'umidità fa da ancora, così la riga non resta mai vuota.
    """
    segments: list[_Segment] = []
    if weather.now.humidity is not None:
        segments += [_icon("humidity"), _text(f"{weather.now.humidity}%")]
    if with_rain and weather.now.rain_probability is not None:
        segments += [_icon("umbrella"), _text(f"{weather.now.rain_probability}%")]
    if with_apparent and weather.now.apparent is not None:
        segments += [_icon("person"), _text(f"{weather.now.apparent:.0f}°")]
    return tuple(segments)


def _draw_now_details(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    weather: Weather,
    top: int,
    clock_right: int,
) -> None:
    """Umidità, pioggia e percepita allineate a destra, nello spazio fra orologio e bordo.

    I pezzi cadono a coppie intere (icona + numero) e in ordine di importanza: prima la
    percepita, poi la pioggia, mentre l'umidità resta. Il cedimento è deciso qui e non dai
    singoli ``required``: lasciandolo al fit resterebbe un'icona senza valore accanto.
    """
    icon_size = style.px(20)
    gap = style.px(_INLINE_GAP_PX)
    available = style.right - clock_right - style.px(_HEADER_GAP_PX)
    segments = _now_detail_segments(weather)
    if _inline_width(segments, style.detail_font, icon_size, gap) > available:
        segments = _now_detail_segments(weather, with_apparent=False)
    if _inline_width(segments, style.detail_font, icon_size, gap) > available:
        segments = _now_detail_segments(weather, with_rain=False, with_apparent=False)
    fitted = _fit_inline(segments, style.detail_font, icon_size, gap, available)
    width = _inline_width(fitted, style.detail_font, icon_size, gap)
    _draw_inline(
        draw,
        style,
        fitted,
        style.right - width,
        top,
        font=style.detail_font,
        icon_size=icon_size,
    )


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
) -> None:
    """Calendario eventi e, se configurata, la raccolta differenziata in una colonna a destra.

    Senza ``[waste]`` la sezione resta a tutta larghezza come prima: la colonna in più è un dato
    che si aggiunge, non un layout diverso da mantenere.
    """
    divider(draw, style.margin, style.right, y + style.px(_RULE_TOP_PX), thickness=style.px(2))
    title_top = y + style.px(28)
    rows_top = y + style.px(_TITLE_ROW_PX)

    if data.waste is None:
        _column_title(
            draw,
            style,
            style.margin,
            title_top,
            "CALENDARIO",
            data.events_sync,
            style.content_width,
            icon="calendar",
        )
        _draw_events(draw, style, data, rows_top, bottom, style.margin, style.right)
        return

    gutter = style.px(_COLUMN_GUTTER_PX)
    events_right = style.margin + round((style.content_width - gutter) * _EVENTS_SHARE)
    waste_left = events_right + gutter
    events_width = events_right - style.margin
    waste_width = style.right - waste_left

    _column_title(
        draw,
        style,
        style.margin,
        title_top,
        "CALENDARIO",
        data.events_sync,
        events_width,
        icon="calendar",
    )
    _column_title(
        draw,
        style,
        waste_left,
        title_top,
        "DIFFERENZIATA",
        data.waste_sync,
        waste_width,
        icon="waste",
    )
    _draw_events(draw, style, data, rows_top, bottom, style.margin, events_right)
    _draw_waste(draw, style, data, rows_top, bottom, waste_left, style.right)

    # La linea chiude la colonna e tocca la regola orizzontale della sezione treni: così si vede
    # dove finisce l'agenda anche quando le due colonne hanno un numero diverso di righe.
    separator = events_right + gutter // 2
    line_bottom = bottom + style.px(_RULE_TOP_PX)
    draw.rectangle(
        [separator, title_top, separator + max(1, style.px(1)), line_bottom], fill="black"
    )


def _draw_events(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    data: PanelData,
    y: int,
    bottom: int,
    left: int,
    right: int,
) -> None:
    if not data.events:
        _message(
            draw,
            style,
            y,
            _section_text(data.events_sync, "nessun evento in vista"),
            left=left,
            width=right - left,
        )
        return

    today = _moment(data).date()
    row = style.px(_CALENDAR_ROW_PX)
    step = style.px(_CALENDAR_LINE_PX)
    # Prima si contano gli eventi che ci starebbero su una riga sola: quel numero è il pavimento,
    # e le righe in più del riassunto si prendono solo dallo spazio che avanza. Così il testo lungo
    # non può far sparire l'evento successivo (peggio dell'ellissi che si voleva evitare).
    room = bottom - y
    count = min(len(data.events), max(0, room // row))
    for index, event in enumerate(data.events[:count]):
        when = _event_when(event, today)
        when_width = max(style.px(52), style.body_font.getlength(when) + style.px(10))
        summary_width = right - left - when_width
        lines = wrap_text(event.summary, style.text_font, summary_width)
        height = row + max(0, len(lines) - 1) * step
        reserved = (count - index - 1) * row
        if height > room - reserved:
            lines = wrap_text(event.summary, style.text_font, summary_width, lines=1)
            height = row
        draw.text((left, y), when, font=style.body_font, fill="black")
        for offset, line in enumerate(lines):
            draw.text(
                (left + when_width, y + offset * step), line, font=style.text_font, fill="black"
            )
        y += height
        room -= height


def _draw_waste(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    data: PanelData,
    y: int,
    bottom: int,
    left: int,
    right: int,
) -> None:
    """Un giorno per riga: ``niente`` dice che oggi non si porta fuori nulla."""
    days = data.waste or ()
    if not days:
        _message(
            draw,
            style,
            y,
            _section_text(data.waste_sync, "nessuna raccolta"),
            left=left,
            width=right - left,
        )
        return

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


@dataclass(frozen=True)
class _Columns:
    """Larghezze delle colonne treni, misurate sul font reale (non su pixel a occhio)."""

    time: int
    line: int


def _trains_height(style: _Style, departures: Sequence[Departure]) -> int:
    """Altezza del blocco treni: titolo, una riga per partenza, una riga di fermate dove ci sono.

    Con l'elenco vuoto si conta anche la riga del messaggio: il blocco è ancorato al fondo, e
    senza quel conto "nessuna partenza in vista" finirebbe sotto il footer.
    """
    if not departures:
        return style.px(_TITLE_ROW_PX) + style.px(_MESSAGE_ROW_PX)
    rows = sum(
        style.px(_TRAIN_ROW_PX) + (style.px(_STOPS_ROW_PX) if item.stops else 0)
        for item in departures
    )
    return style.px(_TITLE_ROW_PX) + rows


def _draw_trains(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    data: PanelData,
    top: int,
    stop_priority: Sequence[str],
) -> None:
    title = "TRENI" if not data.board_name else f"TRENI · {data.board_name.upper()}"
    y = _section_title(draw, style, top, title, data.departures_sync, icon="train")
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
    draw: ImageDraw.ImageDraw,
    style: _Style,
    y: int,
    title: str,
    sync: Sync,
    *,
    icon: str = "",
) -> int:
    divider(draw, style.margin, style.right, y + style.px(_RULE_TOP_PX), thickness=style.px(2))
    _column_title(
        draw, style, style.margin, y + style.px(28), title, sync, style.content_width, icon=icon
    )
    return y + style.px(_TITLE_ROW_PX)


def _title_icon(style: _Style, text: str, width: float, icon: str) -> tuple[int, int]:
    """Lato dell'icona di titolo e spazio da lasciarle: ``(0, 0)`` quando il testo non ci sta.

    L'icona è decorazione e cede per prima: il titolo porta l'informazione, compreso il
    ``· agg. HH:MM`` che dice da quando i dati vengono dalla cache.
    """
    if not icon:
        return 0, 0
    size = style.px(_TITLE_ICON_PX)
    offset = size + style.px(_INLINE_GAP_PX)
    if style.title_font.getlength(text) + offset > width:
        return 0, 0
    return size, offset


def _column_title(
    draw: ImageDraw.ImageDraw,
    style: _Style,
    x: float,
    top: int,
    title: str,
    sync: Sync,
    width: float,
    *,
    icon: str = "",
) -> None:
    """Titolo di sezione o di colonna: icona se c'è spazio, "agg." se ci sta nella larghezza."""
    text = title
    if sync.stale and sync.updated_at is not None:
        text = f"{title} · agg. {sync.updated_at.strftime('%H:%M')}"
    icon_size, offset = _title_icon(style, text, width, icon)
    if icon_size:
        icon_top = _icon_top(style.title_font, top, icon_size)
        left = round(x)
        icons.draw_icon(draw, icon, (left, icon_top, left + icon_size, icon_top + icon_size))
    draw.text(
        (x + offset, top),
        fit_text(text, style.title_font, width - offset),
        font=style.title_font,
        fill="black",
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
    return y + style.px(_MESSAGE_ROW_PX)


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


