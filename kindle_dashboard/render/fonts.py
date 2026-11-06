"""Ricerca dei font TTF: font di sistema con override da configurazione.

Su e-ink i tratti sottili spariscono, quindi anche il "regular" usa pesi semibold quando ci sono.

La ricerca è **multipiattaforma**: limitarla a `%WINDIR%\\Fonts` faceva ricadere il container Linux
sul font incorporato di Pillow, che non ha le accentate né il segno di moltiplicazione: sul PNG
comparivano dei quadratini.
"""

from __future__ import annotations

import os
import sys
from functools import cache
from pathlib import Path

from PIL import ImageFont

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

# Prima i pesi semibold (su e-ink il tratto sottile sparisce), poi i bold; in coda i font che su
# Linux si trovano davvero, nell'ordine in cui `fonts-dejavu-core` li installa.
_REGULAR_CANDIDATES = (
    "seguisb.ttf",
    "verdana.ttf",
    "segoeui.ttf",
    "arial.ttf",
    "tahoma.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Regular.ttf",
    "NotoSans-Regular.ttf",
)
_BOLD_CANDIDATES = (
    "seguisb.ttf",
    "segoeuib.ttf",
    "verdanab.ttf",
    "arialbd.ttf",
    "tahomabd.ttf",
    "DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",
    "NotoSans-Bold.ttf",
)
# Caratteri che il pannello usa davvero (gradi, separatori, ellissi, accenti italiani, segno di
# moltiplicazione scritto come escape per non confonderlo con una "x"). Un font che non li copre
# disegna dei quadrati sul PNG: è successo nel container, senza TTF installati.
REQUIRED_GLYPHS = "°·…\u00d7àèéìòù"
# Codepoint che nessun font del pannello definisce: Pillow disegna lo stesso bitmap per ogni
# codepoint assente, quindi confrontare i bounding box è il modo per riconoscere il "quadratino".
_MISSING_PROBE = "\ue000"


def font_directories() -> tuple[Path, ...]:
    """Cartelle dei font di sistema, per piattaforma (Windows, macOS, Linux)."""
    if sys.platform.startswith("win"):
        root = os.environ.get("WINDIR") or os.environ.get("SYSTEMROOT") or "C:/Windows"
        return (Path(root) / "Fonts",)
    if sys.platform == "darwin":
        return (Path("/System/Library/Fonts"), Path("/Library/Fonts"))
    return (
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/usr/share/fonts/truetype/noto"),
        Path("/usr/share/fonts/TTF"),
        Path("/usr/local/share/fonts"),
    )


def missing_glyphs(font: Font, text: str) -> str:
    """Caratteri di ``text`` che il font disegna come glifo mancante (il quadratino)."""
    probe = font.getbbox(_MISSING_PROBE)
    return "".join(char for char in text if char.strip() and font.getbbox(char) == probe)


@cache
def load(size: int, *, bold: bool = False, override: str = "") -> Font:
    """Carica il miglior font disponibile alla dimensione richiesta, senza mai fallire.

    Fra i candidati si preferisce il primo che copre `REQUIRED_GLYPHS`: uno che li copre solo in
    parte disegnerebbe dei quadrati al posto delle accentate.
    """
    names = _BOLD_CANDIDATES if bold else _REGULAR_CANDIDATES
    candidates = [Path(override)] if override else []
    candidates.extend(directory / name for directory in font_directories() for name in names)
    partial: Font | None = None
    for path in candidates:
        if not path.is_file():
            continue
        try:
            font = ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
        if not missing_glyphs(font, REQUIRED_GLYPHS):
            return font
        if partial is None:
            partial = font
    if partial is not None:
        return partial
    return ImageFont.load_default(size=size)
