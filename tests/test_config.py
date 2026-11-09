"""Test di configurazione: valori reali, errori comprensibili, override da ambiente."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from kindle_dashboard.config import (
    _SECTION_KEYS,
    ICS_URL_ENV,
    CalendarConfig,
    ConfigError,
    LocationConfig,
    PanelConfig,
    RenderConfig,
    SeaConfig,
    ServerConfig,
    TrainsConfig,
    WasteConfig,
    WeatherConfig,
    load_config,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "config.example.toml"

MINIMAL = """
[location]
name = "Genova"
latitude = 44.4072
longitude = 8.9476

[trains]
station = "Genova Brignole"
stop_id = "it-trenitalia_04702"
destinations = ["Torino"]
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_values_and_resolves_cache_dir(tmp_path):
    config = load_config(write(tmp_path, MINIMAL))

    assert config.location is not None
    assert config.location.name == "Genova"
    assert config.trains.stop_id == "it-trenitalia_04702"
    assert config.trains.destinations == ("Torino",)
    assert config.panel.width == 600
    assert config.panel.height == 720
    assert config.cache_dir == tmp_path / "cache"


def test_missing_file_points_to_the_example(tmp_path):
    with pytest.raises(ConfigError, match=r"config\.example\.toml"):
        load_config(tmp_path / "assente.toml")


def test_invalid_port_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="port"):
        load_config(write(tmp_path, MINIMAL + "\n[server]\nport = 99999\n"))


def test_ics_url_can_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(ICS_URL_ENV, "https://calendar.example/private/basic.ics")

    config = load_config(write(tmp_path, MINIMAL))

    assert config.calendar.ics_url == "https://calendar.example/private/basic.ics"
    assert config.calendar.enabled is True


def test_explicit_ics_url_wins_over_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(ICS_URL_ENV, "https://env.example/x")
    text = MINIMAL + '\n[calendar]\nics_url = "https://file.example/y"\n'

    config = load_config(write(tmp_path, text))

    assert config.calendar.ics_url == "https://file.example/y"


def test_unknown_key_in_a_section_is_rejected(tmp_path):
    text = MINIMAL + '\n[[trains.board]]\nstop_id = "ignorato"\n'

    with pytest.raises(ConfigError, match=r"\[trains\]"):
        load_config(write(tmp_path, text))


def test_key_in_the_wrong_section_names_the_right_one(tmp_path):
    # La trappola vera: le chiavi di `[schedule]` scritte dentro `[server]` non le leggeva nessuno
    # e il pannello usava i default senza dirlo.
    text = MINIMAL + '\n[server]\nnight_start = "22:00"\n'

    with pytest.raises(ConfigError, match=r"night_start sta in \[schedule\]"):
        load_config(write(tmp_path, text))


def test_unknown_section_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match=r"sezione sconosciuta: \[meteo\]"):
        load_config(write(tmp_path, MINIMAL + "\n[meteo]\ndays = 3\n"))


def test_stop_details_defaults_to_false(tmp_path):
    assert load_config(write(tmp_path, MINIMAL)).trains.stop_details is False


def test_stop_details_can_be_enabled(tmp_path):
    text = MINIMAL.replace(
        'destinations = ["Torino"]', 'destinations = ["Torino"]\nstop_details = true'
    )

    assert load_config(write(tmp_path, text)).trains.stop_details is True


def test_stop_details_must_be_boolean(tmp_path):
    text = MINIMAL.replace('destinations = ["Torino"]', 'stop_details = "si"')

    with pytest.raises(ConfigError, match="stop_details"):
        load_config(write(tmp_path, text))


def test_waste_is_disabled_by_default(tmp_path):
    config = load_config(write(tmp_path, MINIMAL))

    assert config.waste.enabled is False
    assert config.waste.days == 3


def test_waste_calendar_is_read_from_its_section(tmp_path):
    text = MINIMAL + (
        "\n[waste]\n"
        'ics_url = "https://calendar.example/public/basic.ics"\n'
        "days = 2\n"
    )

    config = load_config(write(tmp_path, text))

    assert config.waste.enabled is True
    assert config.waste.ics_url == "https://calendar.example/public/basic.ics"
    assert config.waste.days == 2


def test_waste_days_out_of_range_is_rejected(tmp_path):
    text = MINIMAL + '\n[waste]\nics_url = "https://calendar.example/x"\ndays = 0\n'

    with pytest.raises(ConfigError, match=r"\[waste\] days"):
        load_config(write(tmp_path, text))


def test_sea_is_disabled_by_default(tmp_path):
    config = load_config(write(tmp_path, MINIMAL))

    assert config.sea.enabled is False
    assert config.sea.days == 3


def test_sea_section_can_be_enabled(tmp_path):
    config = load_config(write(tmp_path, MINIMAL + "\n[sea]\nenabled = true\ndays = 2\n"))

    assert config.sea.enabled is True
    assert config.sea.days == 2


def test_sea_days_out_of_range_is_rejected(tmp_path):
    text = MINIMAL + "\n[sea]\nenabled = true\ndays = 9\n"

    with pytest.raises(ConfigError, match=r"\[sea\] days"):
        load_config(write(tmp_path, text))


def test_sea_enabled_must_be_boolean(tmp_path):
    text = MINIMAL + '\n[sea]\nenabled = "si"\n'

    with pytest.raises(ConfigError, match=r"\[sea\] enabled"):
        load_config(write(tmp_path, text))


def test_location_section_is_optional(tmp_path):
    # Senza `[location]` il pannello non ha meteo né mare, e la configurazione resta valida: è la
    # regola delle altre sezioni. Prima non valeva, perché `name` era obbligatorio anche quando la
    # sezione non c'era.
    config = load_config(write(tmp_path, "[panel]\nwidth = 600\n"))

    assert config.location is None
    assert config.weather.days == 3


def test_example_config_is_valid_and_shows_every_feature(monkeypatch):
    """L'esempio è la vetrina del progetto: se non si carica, il README mente."""
    # Un `KDASH_ICS_URL` nella shell di chi lancia i test accenderebbe il calendario e falserebbe
    # le asserzioni qui sotto.
    monkeypatch.delenv(ICS_URL_ENV, raising=False)

    config = load_config(EXAMPLE)

    assert config.location is not None  # meteo (e mare, dalle stesse coordinate)
    assert config.sea.enabled is True  # il mare si vede al primo avvio
    assert config.trains.stop_id  # tabellone configurato
    assert config.trains.stop_details is True  # seconda riga con le fermate
    assert config.calendar.enabled is False  # nessun URL segreto nel repo
    assert config.waste.enabled is False
    assert config.cache_dir == EXAMPLE.parent / "cache"


def test_allowed_keys_match_the_dataclasses():
    """`_SECTION_KEYS` duplica le dataclass: l'allineamento si verifica qui, non a memoria."""
    pairs = (
        ("panel", PanelConfig),
        ("location", LocationConfig),
        ("weather", WeatherConfig),
        ("sea", SeaConfig),
        ("calendar", CalendarConfig),
        ("waste", WasteConfig),
        ("trains", TrainsConfig),
        ("render", RenderConfig),
        ("server", ServerConfig),
    )

    for name, model in pairs:
        # `[schedule]` e `[cache]` restano fuori: la prima non rispecchia `Schedule` (`day_seconds`
        # arriva da `panel.refresh_seconds`), la seconda non ha una dataclass.
        assert set(_SECTION_KEYS[name]) == {item.name for item in fields(model)}, name

