"""Test del meteo: parsing del JSON reale di Open-Meteo, nessuna rete."""

from __future__ import annotations

from datetime import date

import pytest

from kindle_dashboard.exceptions import SourceError
from kindle_dashboard.sources import weather


def test_parse_current_and_daily(load_json):
    parsed = weather.parse(load_json("weather_openmeteo.json"), days=3)

    assert parsed.now.temperature == pytest.approx(16.6)
    assert parsed.now.apparent == pytest.approx(15.9)
    assert parsed.now.wind_kmh == pytest.approx(8.4)
    assert weather.label(parsed.now.code) == "sereno"
    assert weather.icon_kind(parsed.now.code) == "sun"
    assert [day.day for day in parsed.days] == [
        date(2026, 10, 31),
        date(2026, 11, 1),
        date(2026, 11, 2),
    ]
    assert parsed.days[2].t_max == pytest.approx(15.0)
    assert parsed.days[2].t_min == pytest.approx(9.5)


def test_parse_respects_requested_days(load_json):
    assert len(weather.parse(load_json("weather_openmeteo.json"), days=2).days) == 2


def test_parse_reports_missing_fields(load_json):
    payload = load_json("weather_openmeteo.json")
    del payload["current"]["temperature_2m"]

    with pytest.raises(SourceError, match="incompleta"):
        weather.parse(payload, days=3)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "sun"),
        (2, "partly"),
        (3, "cloud"),
        (45, "fog"),
        (51, "drizzle"),
        (61, "rain"),
        (80, "rain"),
        (73, "snow"),
        (95, "storm"),
    ],
)
def test_icon_kind(code, expected):
    assert weather.icon_kind(code) == expected


def test_unknown_code_has_readable_label():
    assert weather.label(1234) == "non disponibile"
    assert weather.icon_kind(1234) == "cloud"
