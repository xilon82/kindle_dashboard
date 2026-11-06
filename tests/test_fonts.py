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


def test_the_container_font_comes_first_on_every_platform():
    """Il primo candidato deve essere il font che il container installa.

    L'anteprima sul PC vale solo se misura lo stesso font del device: le colonne usano
    `font.getlength`, quindi con Segoe UI Semibold davanti (più stretto di ~1,09-1,15x) il PC
    mostrava righe integre che sul Kindle finivano in ellissi. Se qualcuno rimette i font di Windows
    in testa, l'anteprima torna a mentire e nessun test sui pixel lo nota: questo test tiene fermo
    l'accordo fra `fonts.py` e il `Dockerfile`.
    """
    assert fonts._REGULAR_CANDIDATES[0] == "LiberationSans-Regular.ttf"
    assert fonts._BOLD_CANDIDATES[0] == "LiberationSans-Bold.ttf"


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