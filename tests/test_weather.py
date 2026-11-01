"""Test del meteo: parsing del JSON reale di Open-Meteo, nessuna rete."""

from __future__ import annotations

from datetime import date

import pytest

from kindle_dashboard.exceptions import SourceError
from kindle_dashboard.sources import weather


def test_parse_current_and_daily(load_json):
    parsed = weather.parse(load_json("weather_openmeteo.json"), days=3)

    assert parsed.now.temperature == pytest.approx(17.5)
    assert parsed.now.apparent == pytest.approx(14.1)
    assert parsed.now.wind_kn == pytest.approx(6.1)
    assert parsed.now.wind_direction == 35
    assert weather.label(parsed.now.code) == "sereno"
    assert weather.icon_kind(parsed.now.code) == "sun"
    assert [day.day for day in parsed.days] == [
        date(2026, 11, 1),
        date(2026, 11, 2),
        date(2026, 11, 3),
    ]
    assert parsed.days[2].t_max == pytest.approx(17.7)
    assert parsed.days[2].t_min == pytest.approx(13.0)
    assert parsed.days[0].wind_kn == pytest.approx(11.1)
    assert parsed.days[0].wind_direction == 13


def test_parse_respects_requested_days(load_json):
    assert len(weather.parse(load_json("weather_openmeteo.json"), days=2).days) == 2


def test_daily_wind_is_optional_so_an_old_cached_payload_still_parses(load_json):
    """Una cache scritta prima dell'introduzione dei campi non deve rompere il fallback."""
    payload = load_json("weather_openmeteo.json")
    del payload["daily"]["wind_speed_10m_max"]
    del payload["daily"]["wind_direction_10m_dominant"]

    parsed = weather.parse(payload, days=3)

    assert parsed.days[0].wind_kn is None
    assert parsed.days[0].wind_direction is None


def test_fetch_payload_asks_for_knots_and_wind_direction(monkeypatch):
    captured: dict[str, object] = {}

    def fake_get_json(url, params, *, timeout):
        captured["url"] = url
        captured["params"] = dict(params)
        return {"current": {}, "daily": {}}

    monkeypatch.setattr(weather, "get_json", fake_get_json)
    weather.fetch_payload(42.0342, 11.8542, days=3, timezone="Europe/Rome")

    params = captured["params"]
    assert isinstance(params, dict)
    # Il pannello è nautico: se qualcuno rimette km/h, questo test lo ferma.
    assert params["wind_speed_unit"] == "kn"
    assert "wind_direction_10m" in params["current"]
    assert "wind_speed_10m_max" in params["daily"]
    # La direzione dominante serve alla striscia delle previsioni.
    assert "wind_direction_10m_dominant" in params["daily"]


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
