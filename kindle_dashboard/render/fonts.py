"""Font TTF: Liberation Sans incluso nel pacchetto, con override e ricerca di sistema come ripieghi.

Su e-ink i tratti sottili spariscono, quindi fra i ripieghi Windows il "regular" usa il peso semibold
(`seguisb.ttf`); il font primario è invece Liberation Sans Regular, che ha un inchiostro misurato del
6,9% e per questo regge anche senza semibold.

Il font è **dentro il repo** (`render/fonts/`), non solo installato nel sistema: le colonne del
pannello si dimensionano con `font.getlength`, quindi anteprima e device devono usare **lo stesso
file**, non due versioni che si somigliano. Con Liberation in fondo alla lista dei nomi il PC
sceglieva il Segoe UI Semibold (89 px su `REG 12519` contro 102 px) e l'anteprima mostrava righe
integre che il Kindle troncava. La ricerca multipiattaforma resta come ripiego per quando il TTF
incluso manca (installazione non fatta dal pacchetto) e come riserva di copertura dei glifi.
"""

from __future__ import annotations

import os
import sys
from functools import cache
from pathlib import Path

from PIL import ImageFont

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

# Font spedito con il pannello: sono i TTF che il container installa (`fonts-liberation` di Debian),
# copiati nel repo perché anteprima e device disegnino lo stesso file invece di due versioni che si
# somigliano. Licenza SIL OFL 1.1 in `fonts/OFL.txt`, obbligatoria accanto ai binari: il font non si
# rinomina e non si vende da solo.
_FONT_DIR = Path(__file__).parent / "fonts"
_BUNDLED_FILENAMES = {"regular": "LiberationSans-Regular.ttf", "bold": "LiberationSans-Bold.ttf"}

# Ripieghi di sistema, nell'ordine in cui vengono provati quando il TTF spedito manca o non copre un
# glifo. Il primo nome è lo stesso file incluso (`LiberationSans-*.ttf`), quindi un'installazione senza
# package data che ha Liberation di sistema ottiene comunque lo stesso font; poi il Segoe UI Semibold
# di Windows (peso semibold: su e-ink il tratto sottile sparisce), Verdana, Arial, Tahoma e infine i
# font Linux più larghi (DejaVu, Noto). Lo stesso `REG 12519` misura 89 px in Segoe e 102 px in
# Liberation: scegliere il primo per errore non regala spazio, nasconde il troncamento che il Kindle
# mostra.
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


def shipped_font(*, bold: bool = False) -> Path:
    """Il TTF incluso nel pacchetto: la prima scelta di `load()`, identica su ogni piattaforma."""
    return _FONT_DIR / _BUNDLED_FILENAMES["bold" if bold else "regular"]


def missing_glyphs(font: Font, text: str) -> str:
    """Caratteri di ``text`` che il font disegna come glifo mancante (il quadratino)."""
    probe = font.getbbox(_MISSING_PROBE)
    return "".join(char for char in text if char.strip() and font.getbbox(char) == probe)


@cache
def load(size: int, *, bold: bool = False, override: str = "") -> Font:
    """Carica il miglior font disponibile alla dimensione richiesta, senza mai fallire.

    L'ordine è: ``override`` di configurazione, poi il TTF spedito con il pannello, poi la ricerca
    di sistema. L'override viene prima perché è una scelta esplicita (`[render] font`), il TTF incluso
    subito dopo perché è **lo stesso file** che il container installa: anteprima e device devono
    misurare lo stesso testo, e i ripieghi coprono le installazioni in cui il pacchetto è stato
    copiato senza i suoi dati (un Windows appena installato non ha Liberation Sans).

    Fra i candidati si preferisce il primo che copre `REQUIRED_GLYPHS`: uno che li copre solo in
    parte disegnerebbe dei quadrati al posto delle accentate.

    Nella ricerca di sistema l'ordine è **per nome, poi per cartella** (``name`` esterno,
    ``directory`` interno): iterando prima le cartelle vinceva la prima cartella di
    `font_directories()` — su Debian ``dejavu`` viene prima di ``liberation`` — e la lista dei nomi
    diventava inutile nel container.
    """
    names = _BOLD_CANDIDATES if bold else _REGULAR_CANDIDATES
    candidates = [Path(override)] if override else []
    candidates.append(shipped_font(bold=bold))
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
