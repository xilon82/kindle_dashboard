"""Test dei font: ricerca multipiattaforma e copertura dei caratteri del pannello."""

from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

from kindle_dashboard.render import fonts


def test_the_embedded_pillow_font_lacks_the_accented_glyphs():
    """È il difetto visto nel container: senza TTF le accentate diventano quadratini."""
    missing = fonts.missing_glyphs(ImageFont.load_default(size=20), "à\u00d7°")

    assert missing == "à\u00d7"


def test_the_loaded_font_covers_every_glyph_the_panel_uses():
    """Gradi, separatori, ellissi, segno di moltiplicazione e accenti: se mancano, si vedono quadrati."""
    assert fonts.missing_glyphs(fonts.load(20), fonts.REQUIRED_GLYPHS) == ""


def test_font_directories_are_not_windows_only(monkeypatch):
    """Su Linux (container) la ricerca deve guardare /usr/share/fonts, non C:/Windows/Fonts."""
    monkeypatch.setattr(fonts.sys, "platform", "linux")

    assert Path("/usr/share/fonts/truetype/dejavu") in fonts.font_directories()


def test_the_panel_ships_its_font():
    """Il TTF viaggia con il pacchetto: senza, anteprima e device ricadono su due font di sistema diversi."""
    regular = fonts.shipped_font()
    bold = fonts.shipped_font(bold=True)

    assert regular.is_file()
    assert bold.is_file()
    # Un file troncato si aprirebbe lo stesso: sotto i 100 KB non è un TTF completo.
    assert regular.stat().st_size > 100_000
    assert bold.stat().st_size > 100_000


def test_the_license_ships_next_to_the_font():
    """SIL OFL 1.1 richiede la licenza insieme ai binari: senza, il font non si può ridistribuire."""
    assert (fonts.shipped_font().parent / "OFL.txt").is_file()


def test_the_loaded_font_is_the_shipped_one():
    """`load()` deve prendere il TTF del repo, non quello installato nel sistema."""
    assert Path(fonts.load(23).path).resolve() == fonts.shipped_font().resolve()
    assert Path(fonts.load(23, bold=True).path).resolve() == fonts.shipped_font(bold=True).resolve()


def test_the_container_font_is_both_shipped_and_the_first_candidate():
    """Il TTF incluso ha lo stesso nome del primo candidato di sistema.

    Così, se il file spedito mancasse (installazione senza package data), il ripiego prenderebbe
    comunque lo stesso font quando è installato nel sistema: il nome è la cerniera fra le due strade.
    """
    assert fonts.shipped_font().name == fonts._REGULAR_CANDIDATES[0]
    assert fonts.shipped_font(bold=True).name == fonts._BOLD_CANDIDATES[0]


def test_a_compact_family_comes_before_the_wide_fallback():
    """Liberation deve restare davanti a DejaVu.

    Il pannello misura i font: un font più largo non toglie pixel a nessuno, diventa ellissi. Il
    bold di DejaVu Sans è ~1,30x il Segoe UI Semibold e nel container tagliava ``REG 12519`` a
    ``REG 12…``; quello di Liberation sta in 1,15x. Se qualcuno riordina i candidati tornando a
    DejaVu, il pannello perde informazioni senza che nessun test sui pixel lo noti: questo test
    tiene fermo l'ordine.
    """
    regular = fonts._REGULAR_CANDIDATES
    bold = fonts._BOLD_CANDIDATES

    assert regular.index("LiberationSans-Regular.ttf") < regular.index("DejaVuSans.ttf")
    assert bold.index("LiberationSans-Bold.ttf") < bold.index("DejaVuSans-Bold.ttf")