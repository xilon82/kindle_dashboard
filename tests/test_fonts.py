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