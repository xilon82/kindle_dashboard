"""Test del parser ICS: ricorrenze, eccezioni, fusi e limiti dichiarati."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from kindle_dashboard.exceptions import SourceError
from kindle_dashboard.sources import calendar


def window(read_fixture, tz, start: datetime, days: int = 7, limit: int = 10):
    return calendar.parse_events(
        read_fixture("calendar.ics"),
        start=start,
        end=start + timedelta(days=days),
        tz=tz,
        limit=limit,
    )


def test_events_inside_window_are_sorted(read_fixture, rome):
    start = datetime(2026, 10, 31, 17, 0, tzinfo=rome)

    events = window(read_fixture, rome, start)

    assert [event.summary for event in events] == [
        "Palestra",
        "Ponte di Ognissanti",
        "Standup UTC",
        "Cena settimanale con gli amici",
        "Cena spostata",
    ]
    assert events[0].start.strftime("%d/%m %H:%M") == "31/10 18:00"
    assert events[1].all_day is True
    assert events[1].start.hour == 0
    assert events[2].start.strftime("%H:%M") == "09:30"


def test_weekly_recurrence_honours_count_and_exdate(read_fixture, rome):
    start = datetime(2026, 10, 26, 0, 0, tzinfo=rome)

    events = window(read_fixture, rome, start, days=4)

    # 26/10 incluso, 28/10 escluso da EXDATE, 02/11 fuori finestra.
    assert [event.summary for event in events] == ["Cena settimanale con gli amici"]


def test_moved_occurrence_replaces_original_and_cancelled_is_dropped(read_fixture, rome):
    start = datetime(2026, 11, 2, 0, 0, tzinfo=rome)

    events = window(read_fixture, rome, start, days=1)

    # L'occorrenza del 02/11 è stata spostata al 04/11, l'evento annullato non compare.
    assert [event.summary for event in events] == ["Standup UTC"]


def test_limit_is_respected(read_fixture, rome):
    start = datetime(2026, 10, 31, 17, 0, tzinfo=rome)

    assert len(window(read_fixture, rome, start, limit=2)) == 2


def test_google_embed_url_gives_a_readable_error():
    embed = "https://calendar.google.com/calendar/embed?src=abc%40group.calendar.google.com"

    with pytest.raises(SourceError, match=r"pagina embed"):
        calendar.fetch_payload(embed)


def test_unknown_tzid_falls_back_to_panel_timezone(rome):
    text = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "DTSTART;TZID=Not/AZone:20261102T101500",
            "SUMMARY:Fuso sconosciuto",
            "UID:evt-x",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
    )
    start = datetime(2026, 11, 2, 0, 0, tzinfo=rome)

    events = calendar.parse_events(text, start=start, end=start + timedelta(days=1), tz=rome, limit=5)

    assert events[0].start.strftime("%H:%M") == "10:15"
