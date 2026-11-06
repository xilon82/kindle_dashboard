"""Test dell'orchestrazione: sezioni indipendenti e fallback sulla cache."""

from __future__ import annotations

from datetime import datetime

from kindle_dashboard.cache import Cache
from kindle_dashboard.collect import collect
from kindle_dashboard.config import Config, LocationConfig, SeaConfig, WasteConfig
from kindle_dashboard.exceptions import SourceError
from kindle_dashboard.sources import marine as marine_source
from kindle_dashboard.sources import waste as waste_source
from kindle_dashboard.sources import weather as weather_source
from kindle_dashboard.timezone_utils import zone

NOW = datetime(2026, 10, 31, 18, 0, tzinfo=zone("Europe/Rome"))


def test_unconfigured_sections_explain_themselves(tmp_path):
    data = collect(Config(cache_dir=tmp_path), Cache(tmp_path), NOW)

    assert data.weather is None
    assert data.weather_sync.error == "posizione non configurata"
    assert data.events_sync.error == "calendario non configurato"
    assert data.departures_sync.error == "treni non configurati"
    # None e non (): il renderer usa questa differenza per spegnere la colonna destra.
    assert data.waste is None
    assert data.waste_sync.error == "differenziata non configurata"


def test_collect_marks_the_night_band_like_the_server_does(tmp_path):
    """L'anteprima di `render` deve mostrare `NOTTE` come il Kindle, non l'orologio.

    La fascia viene da `schedule.is_night`, che è l'unico posto in cui la regola vive: prima il
    calcolo stava solo in `server.py` e `python -m kindle_dashboard render` mostrava l'ora anche
    alle 23:30, quindi l'anteprima non era confrontabile con il PNG servito.
    """
    config = Config(cache_dir=tmp_path)
    evening = datetime(2026, 11, 6, 23, 30, tzinfo=zone("Europe/Rome"))
    morning = datetime(2026, 11, 6, 12, 0, tzinfo=zone("Europe/Rome"))

    assert collect(config, Cache(tmp_path), evening).night is True
    assert collect(config, Cache(tmp_path), morning).night is False


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


def test_waste_falls_back_to_cache_when_the_source_fails(tmp_path, monkeypatch, read_fixture):
    config = Config(
        waste=WasteConfig(ics_url="https://calendar.example/public/basic.ics"),
        cache_dir=tmp_path,
    )
    cache = Cache(tmp_path)
    monkeypatch.setattr(waste_source, "fetch_payload", lambda *args, **kwargs: read_fixture("waste.ics"))

    fresh = collect(config, cache, NOW)
    assert fresh.waste is not None
    assert fresh.waste_sync.stale is False
    assert fresh.waste_sync.updated_at == NOW
    assert fresh.waste[0].kinds == ("Umido",)

    def failing(*args, **kwargs):
        raise SourceError("calendar.google.com: HTTP 503")

    monkeypatch.setattr(waste_source, "fetch_payload", failing)
    cached = collect(config, cache, NOW)

    assert cached.waste == fresh.waste
    assert cached.waste_sync.stale is True
    assert cached.waste_sync.error == "calendar.google.com: HTTP 503"
    assert cached.waste_sync.updated_at == NOW


def test_waste_without_cache_reports_the_error_and_stays_empty(tmp_path, monkeypatch):
    config = Config(waste=WasteConfig(ics_url="https://calendar.example/x"), cache_dir=tmp_path)

    def failing(*args, **kwargs):
        raise SourceError("calendar.example: HTTP 500")

    monkeypatch.setattr(waste_source, "fetch_payload", failing)

    data = collect(config, Cache(tmp_path), NOW)

    assert data.waste == ()
    assert data.waste_sync.error == "calendar.example: HTTP 500"
    assert data.waste_sync.stale is False


def test_sea_is_off_until_configured(tmp_path):
    data = collect(Config(cache_dir=tmp_path), Cache(tmp_path), NOW)

    assert data.sea is None
    # Sezione spenta: nessun errore, così il renderer non annuncia un guasto che non esiste.
    assert data.sea_sync.error is None


def test_sea_without_location_explains_itself(tmp_path):
    config = Config(sea=SeaConfig(enabled=True), cache_dir=tmp_path)

    data = collect(config, Cache(tmp_path), NOW)

    assert data.sea is None
    assert data.sea_sync.error is not None
    assert "posizione" in data.sea_sync.error


def test_sea_falls_back_to_cache_when_the_source_fails(tmp_path, monkeypatch, load_json):
    payload = load_json("marine_openmeteo.json")
    config = Config(
        location=LocationConfig(name="Santa Marinella", latitude=42.0342, longitude=11.8542),
        sea=SeaConfig(enabled=True),
        cache_dir=tmp_path,
    )
    cache = Cache(tmp_path)
    monkeypatch.setattr(marine_source, "fetch_payload", lambda *args, **kwargs: payload)

    fresh = collect(config, cache, NOW)
    assert fresh.sea is not None
    assert fresh.sea_sync.stale is False
    assert fresh.sea_sync.updated_at == NOW
    assert fresh.sea.now.wave_height == 0.46

    def failing(*args, **kwargs):
        raise SourceError("marine-api.open-meteo.com: HTTP 503")

    monkeypatch.setattr(marine_source, "fetch_payload", failing)
    cached = collect(config, cache, NOW)

    assert cached.sea == fresh.sea
    assert cached.sea_sync.stale is True
    assert cached.sea_sync.error == "marine-api.open-meteo.com: HTTP 503"
    assert cached.sea_sync.updated_at == NOW
