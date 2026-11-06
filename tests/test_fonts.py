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


def test_a_compact_family_comes_before_the_wide_fallback():
    """Su Linux deve vincere Liberation, non DejaVu.

    Il pannello misura i font: un font più largo non toglie pixel a nessuno, diventa ellissi. Il
    bold di DejaVu Sans è ~1,3x il Segoe UI Semibold di sviluppo e nel container tagliava
    ``REG 12519`` a ``REG 12…``; quello di Liberation sta in 1,08x. Se qualcuno riordina i
    candidati tornando a DejaVu, il pannello perde informazioni senza che nessun test sui pixel lo
    noti: questo test tiene fermo l'ordine.
    """
    regular = fonts._REGULAR_CANDIDATES
    bold = fonts._BOLD_CANDIDATES

    assert regular.index("LiberationSans-Regular.ttf") < regular.index("DejaVuSans.ttf")
    assert bold.index("LiberationSans-Bold.ttf") < bold.index("DejaVuSans-Bold.ttf")