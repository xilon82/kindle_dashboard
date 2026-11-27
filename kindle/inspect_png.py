"""Ispeziona un'immagine: formato, dimensione, modo, profondità e interlacciamento.

Nasce dall'indagine sul Kindle 4: `eips` restituiva **exit code 0 e schermo bianco**, quindi prima
di incolpare il layout o il decoder serve sapere *cosa* gli si sta passando (RGB? trasparenza?
palette indicizzata? Adam7?). Il file viene solo letto: nessuna conversione, nessun salvataggio.

    python kindle/inspect_png.py panel.png cache/testimages/test_l.png

Uscita (una riga per file)::

    panel.png: PNG 600x720 mode=L bit_depth=8 color_type=0(grayscale) interlace=none 21530B
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from PIL import Image

# IHDR: i 13 byte di contenuto stanno dopo firma (8) + lunghezza (4) + tipo del chunk (4), cioè a
# offset 16. Larghezza, altezza e i cinque campi che contano per un decoder minimale come `eips`.
_IHDR = ">IIBBBBB"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_COLOR_TYPES = {
    0: "grayscale",
    2: "truecolor",
    3: "indexed",
    4: "grayscale+alpha",
    6: "truecolor+alpha",
}
_PNG_INTERLACE = {0: "none", 1: "adam7"}


def _png_fields(raw: bytes) -> list[str]:
    """Campi dell'IHDR che decidono se un decoder minimale sa leggere il file."""
    if not raw.startswith(_PNG_SIGNATURE):
        return ["png_header=missing"]
    _width, _height, depth, color_type, _compression, _filter, interlace = struct.unpack(
        _IHDR, raw[16:29]
    )
    return [
        f"bit_depth={depth}",
        f"color_type={color_type}({_PNG_COLOR_TYPES.get(color_type, '?')})",
        f"interlace={_PNG_INTERLACE.get(interlace, interlace)}",
    ]


def describe(path: Path) -> str:
    """Riga descrittiva dell'immagine; solleva `OSError` se il file non è leggibile."""
    raw = path.read_bytes()
    with Image.open(path) as image:
        # `load()` forza la decodifica: un file troncato passa `open()` ma non `load()`.
        image.load()
        parts = [f"{image.format} {image.width}x{image.height}", f"mode={image.mode}"]
        if image.format == "PNG":
            parts.extend(_png_fields(raw))
        if "transparency" in image.info:
            parts.append("transparency=yes")
    return f"{path}: {' '.join(parts)} {len(raw)}B"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stampa formato, dimensione e struttura di un'immagine senza modificarla."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="file da ispezionare")
    args = parser.parse_args(argv)

    failed = False
    for path in args.paths:
        try:
            print(describe(path))
        except (OSError, struct.error) as exc:
            failed = True
            print(f"{path}: non leggibile ({exc})", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
