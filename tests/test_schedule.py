"""Test della finestra giorno/notte: confini, mezzanotte e clamp dell'intervallo."""

from __future__ import annotations

from datetime import datetime, time

import pytest

from kindle_dashboard.schedule import Schedule, is_night, next_boundary, refresh_seconds
from kindle_dashboard.timezone_utils import zone

TZ = zone("Europe/Rome")
SCHEDULE = Schedule(
    night_start=time(23, 0), night_end=time(6, 30), day_seconds=90, night_seconds=3600
)


def moment(hours: int, minutes: int, seconds: int = 0) -> datetime:
    return datetime(2026, 11, 1, hours, minutes, seconds, tzinfo=TZ)


@pytest.mark.parametrize(
    ("hours", "minutes", "expected"),
    [
        (22, 59, False),
        (23, 0, True),
        (23, 59, True),
        (0, 0, True),
        (0, 30, True),
        (6, 29, True),
        (6, 30, False),
        (12, 0, False),
    ],
)
def test_is_night_handles_the_window_across_midnight(hours, minutes, expected):
    assert is_night(moment(hours, minutes), SCHEDULE) is expected


@pytest.mark.parametrize(
    ("hours", "minutes", "seconds", "expected"),
    [
        (22, 59, 0, 60),  # tagliato al confine delle 23:00
        (23, 0, 0, 3600),
        (0, 30, 0, 3600),
        (6, 29, 0, 60),  # tagliato al confine delle 06:30, non un'ora
        (6, 29, 50, 10),
        (6, 30, 0, 90),
        (12, 0, 0, 90),
    ],
)
def test_refresh_seconds_never_crosses_a_boundary(hours, minutes, seconds, expected):
    assert refresh_seconds(moment(hours, minutes, seconds), SCHEDULE) == expected


def test_next_boundary_is_the_first_future_transition():
    assert next_boundary(moment(12, 0), SCHEDULE) == moment(23, 0)
    assert next_boundary(moment(23, 30), SCHEDULE) == datetime(2026, 11, 2, 6, 30, tzinfo=TZ)
    assert next_boundary(moment(6, 0), SCHEDULE) == moment(6, 30)


def test_daytime_boundary_keeps_the_night_interval_out_of_the_way():
    schedule = Schedule(
        night_start=time(23, 0), night_end=time(6, 30), day_seconds=600, night_seconds=7200
    )

    assert refresh_seconds(moment(22, 50), schedule) == 600
