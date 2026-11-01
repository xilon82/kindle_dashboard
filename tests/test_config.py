"""Test di configurazione: valori reali, errori comprensibili, override da ambiente."""

from __future__ import annotations

from pathlib import Path

import pytest

from kindle_dashboard.config import ICS_URL_ENV, ConfigError, load_config

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


def test_unknown_keys_in_trains_do_not_break_loading(tmp_path):
    text = MINIMAL + '\n[[trains.board]]\nstop_id = "ignorato"\n'

    config = load_config(write(tmp_path, text))

    assert config.trains.stop_id == "it-trenitalia_04702"


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
