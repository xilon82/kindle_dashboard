"""Glifi meteo disegnati con primitive: niente emoji (font non garantiti, resa a colori)."""

from __future__ import annotations

from PIL import ImageDraw

_STROKE_DIVISOR = 14


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
