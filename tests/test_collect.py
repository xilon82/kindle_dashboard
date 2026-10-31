"""Test dell'orchestrazione: sezioni indipendenti e fallback sulla cache."""

from __future__ import annotations

from datetime import datetime

from kindle_dashboard.cache import Cache
from kindle_dashboard.collect import collect
from kindle_dashboard.config import Config, LocationConfig
from kindle_dashboard.exceptions import SourceError
from kindle_dashboard.sources import weather as weather_source
from kindle_dashboard.timezone_utils import zone

NOW = datetime(2026, 10, 31, 18, 0, tzinfo=zone("Europe/Rome"))


def test_unconfigured_sections_explain_themselves(tmp_path):
    data = collect(Config(cache_dir=tmp_path), Cache(tmp_path), NOW)

    assert data.weather is None
    assert data.weather_sync.error == "posizione non configurata"
    assert data.events_sync.error == "calendario non configurato"
    assert data.departures_sync.error == "treni non configurati"


def test_weather_falls_back_to_cache_when_the_source_fails(tmp_path, monkeypatch, load_json):
    payload = load_json("weather_openmeteo.json")
    config = Config(
        location=LocationConfig(name="Genova", latitude=44.4072, longitude=8.9476),
        cache_dir=tmp_path,
    )
    cache = Cache(tmp_path)
    monkeypatch.setattr(weather_source, "fetch_payload", lambda *args, **kwargs: payload)

    fresh = collect(config, cache, NOW)
    assert fresh.weather is not None
    assert fresh.weather_sync.stale is False
    assert fresh.weather_sync.updated_at == NOW

    def failing(*args, **kwargs):
        raise SourceError("api.open-meteo.com: HTTP 503")

    monkeypatch.setattr(weather_source, "fetch_payload", failing)
    cached = collect(config, cache, NOW)

    assert cached.weather is not None
    assert cached.weather_sync.stale is True
    assert cached.weather_sync.error == "api.open-meteo.com: HTTP 503"
    assert cached.weather_sync.updated_at == NOW
    assert cached.weather.days == fresh.weather.days
