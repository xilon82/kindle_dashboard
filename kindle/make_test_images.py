"""Genera la scheda di prova e le varianti di formato per il test su e-ink.

`deploy.ps1 -TestImages` copia `cache/testimages` sul Kindle, ma quella cartella non nasce da sola:
questo script la produce, così il test dei formati è ripetibile invece di dipendere da file rimasti
in cache da una sessione precedente. La scheda sintetica contiene **data e ora**, l'unico modo per
distinguere un contenuto nuovo da un'immagine vecchia rimasta sullo schermo.

    python kindle/make_test_images.py                      # scheda sintetica 600x800
    python kindle/make_test_images.py --source panel.png   # varianti del PNG vero del server

Le varianti sono le stesse attese da `deploy.ps1`: `test_l.png` (grigi 8 bit), `test_1.png` (1 bit),
`test_rgb.png` (RGB), `test_p.png` (palette indicizzata) e `test.jpg`.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from kindle_dashboard.render import fonts

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "cache" / "testimages"
DEFAULT_SIZE = "600x800"
# Valori fissi: cambia solo la data, perché la scheda serve a misurare il decoder, non a essere bella.
GRAY_STEPS = 16


def test_card(size: tuple[int, int]) -> Image.Image:
    """Scheda sintetica: scala di grigi, scacchiera, righe da 1 px e caratteri accentati."""
    width, height = size
    scale = height / 800
    image = Image.new("L", size, "white")
    draw = ImageDraw.Draw(image)
    margin = round(width * 0.05)
    body = fonts.load(max(8, round(24 * scale)))
    small = fonts.load(max(8, round(20 * scale)))

    draw.rectangle((0, 0, width - 1, height - 1), outline=0, width=max(2, round(3 * scale)))
    draw.text(
        (margin, round(50 * scale)),
        "KINDLE 4 - TEST",
        font=fonts.load(max(8, round(52 * scale)), bold=True),
        fill=0,
    )
    draw.text(
        (margin, round(120 * scale)),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        font=body,
        fill=0,
    )
    draw.text((margin, round(170 * scale)), "scala di grigi, 16 livelli", font=small, fill=0)

    # Rampa: se il device mostra meno livelli, o li inverte, si vede qui e non sul pannello vero.
    ramp_top = round(200 * scale)
    ramp_height = round(90 * scale)
    cell = max(1, (width - 2 * margin) // GRAY_STEPS)
    for index in range(GRAY_STEPS):
        left = margin + index * cell
        shade = round(index * 255 / (GRAY_STEPS - 1))
        draw.rectangle((left, ramp_top, left + cell - 1, ramp_top + ramp_height), fill=shade)
    labels_top = ramp_top + ramp_height + round(4 * scale)
    for index, label in ((0, "0"), (GRAY_STEPS // 2, "128"), (GRAY_STEPS - 1, "255")):
        draw.text((margin + index * cell, labels_top), label, font=small, fill=0)

    # Scacchiera: un decoder che sbaglia il passo della riga produce bande diagonali.
    checker_top = round(330 * scale)
    checker_cell = round(20 * scale)
    for row in range(8):
        for column in range(8):
            if (row + column) % 2 == 0:
                left = margin + column * checker_cell
                top = checker_top + row * checker_cell
                draw.rectangle((left, top, left + checker_cell - 1, top + checker_cell - 1), fill=0)

    # Righe da 1 px: un renderer che scala per adattare l'immagine le fonde in un grigio uniforme.
    lines_top = round(520 * scale)
    for offset in range(0, width - 2 * margin, 3):
        left = margin + offset
        draw.line((left, lines_top, left, lines_top + round(40 * scale)), fill=0, width=1)

    draw.text((margin, round(590 * scale)), "à è é ì ò ù ° · … \u00d7 8cm", font=body, fill=0)

    # Etichette di orientamento: dicono subito se il PNG è ruotato o tagliato ai bordi.
    draw.text((margin, height - margin - small.size), "BASSO", font=small, fill=0)
    top_width = draw.textlength("ALTO", font=small)
    draw.text((width - margin - top_width, margin), "ALTO", font=small, fill=0)
    return image


def flatten_alpha(image: Image.Image) -> Image.Image:
    """Fonde l'eventuale trasparenza su bianco: `eips` non ha un canale alpha da mostrare."""
    if "A" in image.getbands() or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image


def variants(image: Image.Image) -> dict[str, Image.Image]:
    """Le codifiche che `eips` può accettare o rifiutare, con lo stesso contenuto."""
    gray = image.convert("L")
    return {
        "test_l.png": gray,
        "test_1.png": gray.convert("1"),
        "test_rgb.png": gray.convert("RGB"),
        "test_p.png": gray.convert("P", palette=Image.ADAPTIVE, colors=GRAY_STEPS),
    }


def _parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x", 1))
    except ValueError as exc:
        raise SystemExit(f"dimensione non valida: {value} (atteso LARGHEZZAxALTEZZA)") from exc
    if width <= 0 or height <= 0:
        raise SystemExit(f"dimensione non valida: {value}")
    return width, height


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Genera la scheda di test e le varianti di formato per il Kindle."
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="immagine da convertire (il PNG del server); se assente si usa la scheda sintetica",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help=f"cartella di uscita ({DEFAULT_OUT})"
    )
    parser.add_argument(
        "--size", default=DEFAULT_SIZE, help=f"dimensione della scheda sintetica ({DEFAULT_SIZE})"
    )
    args = parser.parse_args(argv)

    if args.source:
        with Image.open(args.source) as opened:
            opened.load()
            # Copia prima di chiudere il file: le varianti si salvano dopo il `with`.
            base = flatten_alpha(opened).copy()
    else:
        base = test_card(_parse_size(args.size))

    args.out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, image in variants(base).items():
        path = args.out / name
        image.save(path, format="PNG", optimize=True)
        written.append(path)
    jpeg = args.out / "test.jpg"
    base.convert("L").save(jpeg, format="JPEG", quality=85)
    written.append(jpeg)

    for path in written:
        print(f"{path} ({path.stat().st_size}B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
