"""Glifi meteo disegnati con primitive: niente emoji (font non garantiti, resa a colori)."""

from __future__ import annotations

import math

from PIL import ImageDraw

_STROKE_DIVISOR = 14
# Livello di "agitazione" del glifo per ciascuno stato del mare (vedi ``sources.marine``).
_SEA_KINDS = {"sea_calm": 1, "sea_slight": 2, "sea_moderate": 3, "sea_rough": 4}


def draw_icon(draw: ImageDraw.ImageDraw, kind: str, box: tuple[int, int, int, int]) -> None:
    """Disegna il glifo ``kind`` dentro ``box`` (quadrato), in nero pieno."""
    left, top, right, bottom = box
    size = min(right - left, bottom - top)
    if size <= 0:
        return
    stroke = max(3, size // _STROKE_DIVISOR, 2)
    if kind == "sun":
        _sun(draw, left, top, size, stroke)
    elif kind == "partly":
        _sun(draw, left, top, int(size * 0.72), stroke)
        _cloud(draw, left + size * 0.2, top + size * 0.42, size * 0.8, size * 0.5)
    elif kind == "fog":
        _fog(draw, left, top, size, stroke)
    elif kind == "snow":
        _cloud(draw, left, top, size, size * 0.6)
        _snowflakes(draw, left, top + size * 0.68, size, stroke)
    elif kind == "storm":
        _cloud(draw, left, top, size, size * 0.62)
        draw.polygon(
            [
                (left + size * 0.54, top + size * 0.56),
                (left + size * 0.32, top + size * 0.88),
                (left + size * 0.48, top + size * 0.88),
                (left + size * 0.40, top + size),
                (left + size * 0.66, top + size * 0.78),
                (left + size * 0.50, top + size * 0.78),
                (left + size * 0.60, top + size * 0.56),
            ],
            fill="black",
        )
    elif kind in {"rain", "drizzle"}:
        share = 0.62 if kind == "rain" else 0.72
        _cloud(draw, left, top, size, size * share)
        _rain(draw, left, top + size * share, size, stroke, drops=3 if kind == "rain" else 2)
    elif kind in _SEA_KINDS:
        _waves(draw, left, top, size, stroke, level=_SEA_KINDS[kind])
    elif kind == "wind":
        _wind(draw, left, top, size, stroke)
    elif kind == "person":
        _person(draw, left, top, size)
    elif kind == "sunrise":
        _horizon_sun(draw, left, top, size, stroke)
    elif kind == "sunset":
        _horizon_sun(draw, left, top, size, stroke, setting=True)
    elif kind in {"arrow_up", "arrow_down"}:
        _arrow(draw, left, top, size, stroke, up=kind == "arrow_up")
    elif kind == "umbrella":
        _umbrella(draw, left, top, size, stroke)
    else:
        _cloud(draw, left, top, size, size * 0.8)


def _sun(draw: ImageDraw.ImageDraw, left: int, top: int, size: int, stroke: int) -> None:
    radius = size * 0.24
    center_x = left + size / 2
    center_y = top + size / 2
    draw.ellipse(
        [center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill="black"
    )
    inner = radius * 1.45
    outer = radius * 2.02
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)):
        draw.line(
            [
                center_x + dx * inner,
                center_y + dy * inner,
                center_x + dx * outer,
                center_y + dy * outer,
            ],
            fill="black",
            width=stroke,
        )


def _cloud(
    draw: ImageDraw.ImageDraw, left: float, top: float, width: float, height: float
) -> None:
    """Nuvola piena: due cerchi più una base arrotondata."""
    radius = height * 0.42
    base_top = top + height - radius
    draw.ellipse(
        [left + width * 0.02, base_top, left + width * 0.02 + 2 * radius, top + height],
        fill="black",
    )
    draw.ellipse(
        [left + width - 2 * radius - width * 0.04, top + height * 0.06,
         left + width - width * 0.04, top + height * 0.06 + 2 * radius],
        fill="black",
    )
    draw.rounded_rectangle(
        [left + radius * 0.75, top + height * 0.42, left + width - radius * 0.75, top + height],
        radius=radius * 0.7,
        fill="black",
    )


def _rain(
    draw: ImageDraw.ImageDraw, left: float, top: float, size: int, stroke: int, *, drops: int
) -> None:
    share = (1.0 - top / size) if size else 0.0
    length = max(stroke * 2, size * min(0.24, share * 0.5))
    step = size / (drops + 1)
    for index in range(1, drops + 1):
        x = left + step * index
        draw.line([x, top, x - length * 0.25, top + length], fill="black", width=stroke)


def _snowflakes(draw: ImageDraw.ImageDraw, left: float, top: float, size: int, stroke: int) -> None:
    arm = max(stroke * 2, size * 0.1)
    step = size / 4
    for index in range(1, 4):
        center_x = left + step * index
        center_y = top
        draw.line(
            [center_x - arm, center_y - arm, center_x + arm, center_y + arm],
            fill="black",
            width=stroke,
        )
        draw.line(
            [center_x - arm, center_y + arm, center_x + arm, center_y - arm],
            fill="black",
            width=stroke,
        )


def _fog(draw: ImageDraw.ImageDraw, left: int, top: int, size: int, stroke: int) -> None:
    rows = (0.2, 0.45, 0.7, 0.9)
    for index, fraction in enumerate(rows):
        inset = size * (0.18 if index % 2 else 0.06)
        draw.line(
            [left + inset, top + size * fraction, left + size - inset, top + size * fraction],
            fill="black",
            width=stroke,
        )


def _waves(draw: ImageDraw.ImageDraw, left: float, top: float, size: int, stroke: int, *, level: int) -> None:
    """Due creste piene: l'ampiezza cresce con lo stato del mare, così il glifo resta leggibile."""
    # A 14-16 px un tratto da 3 px mangia l'ampiezza dell'onda: si assottiglia invece di scurire.
    width = stroke if size >= 20 else max(2, stroke - 1)
    amplitude = size * (0.04 + 0.04 * level)
    step = size / 12
    for row in range(2):
        base = top + size * (0.36 + 0.30 * row)
        points = [
            (left + step * index, base + amplitude * math.sin(index * math.pi / 4))
            for index in range(13)
        ]
        draw.line(points, fill="black", width=width, joint="curve")


def _wind(draw: ImageDraw.ImageDraw, left: float, top: float, size: int, stroke: int) -> None:
    """Freccia con due raffi: si legge come vento anche a 14 px, dove tre righe sarebbero una macchia."""
    mid = top + size * 0.52
    draw.line([left + size * 0.10, mid, left + size * 0.70, mid], fill="black", width=stroke)
    draw.polygon(
        [
            (left + size * 0.68, mid - size * 0.18),
            (left + size, mid),
            (left + size * 0.68, mid + size * 0.18),
        ],
        fill="black",
    )
    thin = max(2, stroke - 1)
    draw.line(
        [left + size * 0.06, top + size * 0.24, left + size * 0.42, top + size * 0.24],
        fill="black",
        width=thin,
    )
    draw.line(
        [left + size * 0.06, top + size * 0.80, left + size * 0.30, top + size * 0.80],
        fill="black",
        width=thin,
    )


def _horizon_sun(
    draw: ImageDraw.ImageDraw, left: float, top: float, size: int, stroke: int, *, setting: bool = False
) -> None:
    """Sole sul filo dell'orizzonte: semicerchio pieno sopra una linea di terreno.

    Alba e tramonto condividono il glifo e si distinguono per l'altezza dell'orizzonte più la
    freccia nella riga: a 16-20 px un sole intero con i raggi sarebbe una macchia.
    """
    radius = size * 0.28
    center_x = left + size * 0.5
    ground = top + size * (0.62 if setting else 0.80)
    draw.pieslice(
        [center_x - radius, ground - radius, center_x + radius, ground + radius],
        180,
        360,
        fill="black",
    )
    draw.line([left + size * 0.02, ground, left + size * 0.98, ground], fill="black", width=stroke)
    thin = max(2, stroke - 1)
    for dx in (-1.0, 0.0, 1.0):
        draw.line(
            [
                center_x + dx * radius * 1.45,
                ground - radius * 1.35,
                center_x + dx * radius * 2.05,
                ground - radius * 2.0,
            ],
            fill="black",
            width=thin,
        )


def _arrow(draw: ImageDraw.ImageDraw, left: float, top: float, size: int, stroke: int, *, up: bool) -> None:
    """Freccia verticale: dice se il sole sale (alba) o scende (tramonto)."""
    mid_x = left + size * 0.5
    head = size * 0.26
    if up:
        draw.line([mid_x, top + size * 0.20, mid_x, top + size * 0.78], fill="black", width=stroke)
        draw.polygon(
            [(mid_x - head, top + size * 0.32), (mid_x + head, top + size * 0.32),
             (mid_x, top + size * 0.06)],
            fill="black",
        )
    else:
        draw.line([mid_x, top + size * 0.22, mid_x, top + size * 0.80], fill="black", width=stroke)
        draw.polygon(
            [(mid_x - head, top + size * 0.68), (mid_x + head, top + size * 0.68),
             (mid_x, top + size * 0.94)],
            fill="black",
        )


def _umbrella(draw: ImageDraw.ImageDraw, left: float, top: float, size: int, stroke: int) -> None:
    """Ombrello: calotta a semicerchio, asta centrale e manico corto."""
    canopy_top = top + size * 0.12
    canopy_height = size * 0.42
    draw.pieslice(
        [
            left + size * 0.06,
            canopy_top,
            left + size * 0.94,
            canopy_top + canopy_height * 2,
        ],
        180,
        360,
        fill="black",
    )
    shaft_x = left + size * 0.5
    shaft_bottom = top + size * 0.86
    draw.line(
        [shaft_x, canopy_top + canopy_height, shaft_x, shaft_bottom], fill="black", width=stroke
    )
    draw.arc(
        [
            shaft_x - size * 0.16,
            shaft_bottom - size * 0.14,
            shaft_x,
            shaft_bottom + size * 0.14,
        ],
        0,
        180,
        fill="black",
        width=stroke,
    )


def _person(draw: ImageDraw.ImageDraw, left: float, top: float, size: int) -> None:
    """Busto stilizzato (testa + spalle) per la temperatura percepita: a 18 px una figura
    intera sarebbe una macchia."""
    center = left + size * 0.5
    head = size * 0.19
    draw.ellipse(
        [center - head, top + size * 0.04, center + head, top + size * 0.04 + 2 * head],
        fill="black",
    )
    # Spalle come semicerchio pieno: il lato piatto cade sul fondo del riquadro, senza sbordare.
    draw.pieslice(
        [left + size * 0.12, top + size * 0.52, left + size * 0.88, top + size * 1.48],
        180,
        360,
        fill="black",
    )
