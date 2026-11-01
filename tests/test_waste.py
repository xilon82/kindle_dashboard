"""Test del calendario della raccolta differenziata: giorni allineati, buchi, raggruppamento."""

from __future__ import annotations

from datetime import date

import pytest

from kindle_dashboard.exceptions import SourceError
from kindle_dashboard.model import WasteDay
from kindle_dashboard.sources import waste


def test_window_is_aligned_to_days_and_keeps_the_sunday_gap(read_fixture, rome):
    days = waste.parse(read_fixture("waste.ics"), today=date(2026, 10, 31), days=3, tz=rome)

    assert [(item.day, item.kinds) for item in days] == [
        (date(2026, 10, 31), ("Umido",)),
        (date(2026, 11, 1), ()),
        (date(2026, 11, 2), ("Secco",)),
    ]


def test_more_materials_on_the_same_day_stay_together(read_fixture, rome):
    days = waste.parse(read_fixture("waste.ics"), today=date(2026, 11, 5), days=1, tz=rome)

    assert days == (WasteDay(day=date(2026, 11, 5), kinds=("Carta", "Vetro")),)


def test_cancelled_days_are_empty(read_fixture, rome):
    days = waste.parse(read_fixture("waste.ics"), today=date(2026, 11, 6), days=1, tz=rome)

    assert days[0].kinds == ()


def test_days_limit_is_respected(read_fixture, rome):
    days = waste.parse(read_fixture("waste.ics"), today=date(2026, 10, 31), days=5, tz=rome)

    assert [item.day for item in days] == [
        date(2026, 10, 31),
        date(2026, 11, 1),
        date(2026, 11, 2),
        date(2026, 11, 3),
        date(2026, 11, 4),
    ]


def test_events_before_today_are_ignored(read_fixture, rome):
    days = waste.parse(read_fixture("waste.ics"), today=date(2026, 11, 1), days=2, tz=rome)

    assert days == (
        WasteDay(day=date(2026, 11, 1)),
        WasteDay(day=date(2026, 11, 2), kinds=("Secco",)),
    )


def test_google_embed_url_is_rejected_like_the_events_calendar():
    embed = "https://calendar.google.com/calendar/embed?src=abc%40group.calendar.google.com"

    with pytest.raises(SourceError, match=r"pagina embed"):
        waste.fetch_payload(embed)
