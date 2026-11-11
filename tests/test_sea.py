"""Test del mare: parsing del JSON reale di Open-Meteo Marine, nessuna rete."""

from __future__ import annotations

from datetime import date

import pytest

from kindle_dashboard.exceptions import SourceError
from kindle_dashboard.sources import marine


def test_parse_current_and_daily(load_json):
    parsed = marine.parse(load_json("marine_openmeteo.json"), days=3)

    assert parsed.now.wave_height == pytest.approx(0.46)
    assert parsed.now.water_temperature == pytest.approx(20.6)
    assert [day.day for day in parsed.days] == [
        date(2026, 11, 1),
        date(2026, 11, 2),
        date(2026, 11, 3),
    ]
    assert parsed.days[0].wave_height_max == pytest.approx(0.54)
    assert parsed.days[2].wave_height_max == pytest.approx(0.40)


def test_parse_respects_requested_days(load_json):
    assert len(marine.parse(load_json("marine_openmeteo.json"), days=2).days) == 2


def test_parse_reports_missing_fields(load_json):
    payload = load_json("marine_openmeteo.json")
    del payload["current"]["wave_height"]

    with pytest.raises(SourceError, match="incompleta"):
        marine.parse(payload, days=3)


def test_parse_reports_an_empty_daily_block(load_json):
    payload = load_json("marine_openmeteo.json")
    payload["daily"]["time"] = []

    with pytest.raises(SourceError, match="nessuna previsione"):
        marine.parse(payload, days=3)


@pytest.mark.parametrize(
    ("height", "force", "label", "kind"),
    [
        # Grado 0: 0-2 cm inclusi. Il modello non scende sotto 0.02 m, quindi il suo fondo scala
        # coincide con il "calmo" del bollettino.
        (0.0, 0, "calmo", "sea_calm"),
        (0.01, 0, "calmo", "sea_calm"),
        (0.02, 0, "calmo", "sea_calm"),
        (0.04, 1, "quasi calmo", "sea_calm"),
        (0.08, 1, "quasi calmo", "sea_calm"),
        # Ogni fascia è verificata sui due lati del confine.
        (0.10, 2, "poco mosso", "sea_slight"),
        (0.49, 2, "poco mosso", "sea_slight"),
        (0.50, 3, "mosso", "sea_moderate"),
        (1.24, 3, "mosso", "sea_moderate"),
        (1.25, 4, "molto mosso", "sea_rough"),
        (2.49, 4, "molto mosso", "sea_rough"),
        (2.50, 5, "agitato", "sea_rough"),
        (3.99, 5, "agitato", "sea_rough"),
        (4.00, 6, "molto agitato", "sea_rough"),
        (5.99, 6, "molto agitato", "sea_rough"),
        (6.00, 7, "grosso", "sea_rough"),
        (8.99, 7, "grosso", "sea_rough"),
        (9.00, 8, "molto grosso", "sea_rough"),
        # Il bollettino scrive "9 - 14 m" per il grado 8 e "> 14 m" per il 9: 14.00 chiude l'8.
        (14.00, 8, "molto grosso", "sea_rough"),
        (14.01, 9, "tempestoso", "sea_rough"),
        (20.0, 9, "tempestoso", "sea_rough"),
    ],
)
def test_douglas_scale(height, force, label, kind):
    assert marine.state_force(height) == force
    assert marine.state_label(height) == label
    assert marine.state_kind(height) == kind


def test_scale_matches_the_official_table():
    """Soglie e parole della scala ufficiale: un grado sfasato deve fare rosso il gate."""
    assert [lower for lower, _, _, _ in marine._STATES] == [
        0.10, 0.50, 1.25, 2.50, 4.00, 6.00, 9.00,
    ]
    assert [force for _, force, _, _ in marine._STATES] == list(range(2, 9))
    assert [label for _, _, label, _ in marine._STATES] == [
        "poco mosso",
        "mosso",
        "molto mosso",
        "agitato",
        "molto agitato",
        "grosso",
        "molto grosso",
    ]
    assert marine._QUASI_CALM[0] == 1
    assert marine._CALM_TO_M == 0.02
    assert marine._TEMPESTUOUS[0] == 9
    assert marine._TEMPESTUOUS_FROM_M == 14.0


def test_height_label_is_compact():
    assert marine.height_label(0.48) == "0.5m"
    assert marine.height_label(2.0) == "2.0m"
    # Sotto i 10 cm si passa ai centimetri: il numero resta esatto e non esce dalla fascia.
    assert marine.height_label(0.02) == "2cm"
    assert marine.height_label(0.08) == "8cm"
    assert marine.height_label(0.10) == "0.1m"


def test_fetch_payload_uses_the_location_coordinates(monkeypatch):
    captured: dict[str, object] = {}

    def fake_get_json(url, params, *, timeout):
        captured["url"] = url
        captured["params"] = dict(params)
        return {"current": {}, "daily": {}}

    monkeypatch.setattr(marine, "get_json", fake_get_json)
    marine.fetch_payload(42.0342, 11.8542, days=3, timezone="Europe/Rome")

    params = captured["params"]
    assert captured["url"] == marine.API_URL
    assert isinstance(params, dict)
    assert params["latitude"] == "42.0342"
    assert params["forecast_days"] == 3
    assert params["timezone"] == "Europe/Rome"
