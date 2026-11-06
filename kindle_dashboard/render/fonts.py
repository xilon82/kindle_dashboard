"""Ricerca dei font TTF: font di sistema con override da configurazione.

Su e-ink i tratti sottili spariscono, quindi fra i ripieghi Windows il "regular" usa il peso semibold
(`seguisb.ttf`); il font primario è invece Liberation Sans Regular, che ha un inchiostro misurato del
6,9% e per questo regge anche senza semibold.

La ricerca è **multipiattaforma**: limitarla a `%WINDIR%\\Fonts` faceva ricadere il container Linux
sul font incorporato di Pillow, che non ha le accentate né il segno di moltiplicazione: sul PNG
comparivano dei quadratini. La scelta non è però solo di copertura: le colonne del pannello si
dimensionano con `font.getlength`, quindi il font dell'anteprima deve essere **lo stesso** che il
device mostra. Per questo il primo candidato su ogni piattaforma è Liberation Sans, quello che il
`Dockerfile` installa: un font più stretto non regala spazio, si limita a nascondere il troncamento
che il Kindle mostrerà.
"""

from __future__ import annotations

import os
import sys
from functools import cache
from pathlib import Path

from PIL import ImageFont

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

# Il primo nome è il font che il `Dockerfile` installa — Liberation Sans. Sviluppo e container devono
# **misurare** lo stesso testo, non solo somigliarsi: prima l'ordine partiva dal Segoe UI Semibold di
# Windows, più stretto di ~1,09-1,15x, e l'anteprima era ottimistica rispetto al device. Lo stesso
# `REG 12519` misura 89 px in Segoe UI Semibold e 102 px in Liberation: una riga che in anteprima
# stava appena dentro sul Kindle diventava ellissi, difetto che il PC non mostrava. Segoe resta come
# seconda voce (è il peso semibold: su e-ink il tratto sottile sparisce), poi Verdana, Arial, Tahoma e
# infine i font Linux più larghi (DejaVu, Noto) come riserva di copertura dei glifi.
_REGULAR_CANDIDATES = (
    "LiberationSans-Regular.ttf",
    "seguisb.ttf",
    "verdana.ttf",
    "segoeui.ttf",
    "arial.ttf",
    "tahoma.ttf",
    "DejaVuSans.ttf",
    "NotoSans-Regular.ttf",
)
_BOLD_CANDIDATES = (
    "LiberationSans-Bold.ttf",
    "seguisb.ttf",
    "segoeuib.ttf",
    "verdanab.ttf",
    "arialbd.ttf",
    "tahomabd.ttf",
    "DejaVuSans-Bold.ttf",
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

    Il primo candidato è il font che il container installa, così anteprima e device misurano lo
    stesso testo; le voci successive sono fallback per le piattaforme dove non è presente (un
    Windows appena installato non ha Liberation Sans).

    Fra i candidati si preferisce il primo che copre `REQUIRED_GLYPHS`: uno che li copre solo in
    parte disegnerebbe dei quadrati al posto delle accentate.

    L'ordine è **per nome, poi per cartella** (``name`` esterno, ``directory`` interno): iterando
    prima le cartelle vinceva la prima cartella di `font_directories()` — su Debian ``dejavu`` viene
    prima di ``liberation`` — e la lista dei nomi diventava inutile nel container.
    """
    names = _BOLD_CANDIDATES if bold else _REGULAR_CANDIDATES
    candidates = [Path(override)] if override else []
    candidates.extend(directory / name for name in names for directory in font_directories())
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
