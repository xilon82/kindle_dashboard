"""Ricerca dei font TTF: font di sistema con override da configurazione.

Su e-ink i tratti sottili spariscono, quindi anche il "regular" usa pesi semibold quando ci sono.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

from PIL import ImageFont

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

_REGULAR_CANDIDATES = ("seguisb.ttf", "verdana.ttf", "segoeui.ttf", "arial.ttf", "tahoma.ttf")
_BOLD_CANDIDATES = ("seguisb.ttf", "segoeuib.ttf", "verdanab.ttf", "arialbd.ttf", "tahomabd.ttf")


def font_directory() -> Path:
    """Cartella dei font di sistema (Windows: %WINDIR%\\Fonts)."""
    root = os.environ.get("WINDIR") or os.environ.get("SYSTEMROOT") or "C:/Windows"
    return Path(root) / "Fonts"


@cache
def load(size: int, *, bold: bool = False, override: str = "") -> Font:
    """Carica il miglior font disponibile alla dimensione richiesta, senza mai fallire."""
    names = _BOLD_CANDIDATES if bold else _REGULAR_CANDIDATES
    candidates = [override] if override else []
    candidates.extend(str(font_directory() / name) for name in names)
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)
