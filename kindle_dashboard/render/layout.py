"""Helper di impaginazione: troncamento, separatori, etichette di data."""

from __future__ import annotations

from datetime import date

from PIL import ImageDraw

from .fonts import Font

ELLIPSIS = "…"
WEEKDAYS = ("LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM")
MONTHS = ("GEN", "FEB", "MAR", "APR", "MAG", "GIU", "LUG", "AGO", "SET", "OTT", "NOV", "DIC")


def fit_text(text: str, font: Font, max_width: float) -> str:
    """Accorcia il testo con un ellissi per rientrare in ``max_width``."""
    if max_width <= 0:
        return ""
    if font.getlength(text) <= max_width:
        return text
    trimmed = text
    while trimmed and font.getlength(trimmed + ELLIPSIS) > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed.rstrip()}{ELLIPSIS}" if trimmed else ""


def divider(
    draw: ImageDraw.ImageDraw, left: float, right: float, y: float, thickness: int = 2
) -> None:
    draw.rectangle([left, y, right, y + max(1, thickness)], fill="black")


def date_label(day: date) -> str:
    """Es. ``SAB 31 OTT 2026``."""
    return f"{WEEKDAYS[day.weekday()]} {day.day:02d} {MONTHS[day.month - 1]} {day.year}"


def relative_day(day: date, today: date) -> str:
    """``OGGI``/``DOM``: compatto per le colonne strette."""
    return "OGGI" if day == today else WEEKDAYS[day.weekday()]
