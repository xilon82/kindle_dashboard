"""Test delle partenze: parsing della risposta Transitous registrata."""

from __future__ import annotations

from datetime import datetime

import pytest

from kindle_dashboard.exceptions import SourceError
from kindle_dashboard.sources import trains
from kindle_dashboard.timezone_utils import zone

NOW = datetime(2026, 10, 31, 17, 0, tzinfo=zone("Europe/Rome"))


def parse(load_json, **overrides):
    options = {"now": NOW, "limit": 5, "timezone": "Europe/Rome"}
    options.update(overrides)
    return trains.parse(load_json("transitous_stoptimes.json"), **options)


def test_departures_already_gone_are_dropped(load_json):
    assert [item.line for item in parse(load_json)] == ["IC 673", "RV 2140", "REG 12138"]


def test_first_departure_has_realtime_delay_and_track(load_json):
    first = parse(load_json)[0]

    assert first.destination == "LIVORNO CENTRALE"
    assert first.track == "9"
    assert first.expected.strftime("%H:%M") == "18:10"
    assert first.scheduled.strftime("%H:%M") == "18:08"
    assert first.delay_minutes == 2
    assert first.realtime is True
    assert first.cancelled is False


def test_rows_without_realtime_and_cancelled_trains(load_json):
    second, third = parse(load_json)[1:3]

    assert second.realtime is False
    assert second.track == "11"
    assert second.delay_minutes == 0
    assert third.cancelled is True
    assert third.track == "1 TRONCO"


def test_limit_and_destination_filter(load_json):
    assert len(parse(load_json, limit=2)) == 2
    filtered = parse(load_json, destinations=("torino",))
    assert [item.destination for item in filtered] == ["TORINO PORTA NUOVA"]


def test_unreadable_rows_raise_source_error():
    with pytest.raises(SourceError, match="illeggibili"):
        trains.parse(
            {"stopTimes": [{"place": {}}, {"foo": "bar"}]},
            now=NOW,
            limit=3,
            timezone="Europe/Rome",
        )


def test_payload_without_stop_times_raises():
    with pytest.raises(SourceError, match="stopTimes"):
        trains.parse({}, now=NOW, limit=3, timezone="Europe/Rome")


def test_resolve_stations_maps_name_and_id(monkeypatch, load_json):
    payload = load_json("transitous_geocode.json")
    monkeypatch.setattr(trains, "get_json", lambda *args, **kwargs: payload)

    assert trains.resolve_stations("genova") == (
        ("GENOVA BRIGNOLE", "it-trenitalia_04702:station"),
        ("GENOVA PIAZZA PRINCIPE", "it-trenitalia_04700:station"),
    )


def test_fetch_trip_stops_reads_every_stop(monkeypatch, load_json):
    payload = load_json("transitous_trip.json")
    monkeypatch.setattr(trains, "get_json", lambda *args, **kwargs: payload)

    stops = trains.fetch_trip_stops(trains.DEFAULT_BASE_URL, "trip-esempio", timezone="Europe/Rome")

    assert [stop.name for stop in stops] == [
        "S.MARINELLA",
        "MARINA DI CERVETERI",
        "ROMA S.PIETRO",
        "ROMA TRASTEVERE",
        "ROMA OSTIENSE",
    ]
    assert stops[2].when.strftime("%H:%M") == "20:27"


def test_matching_stops_keeps_only_the_city_of_interest(monkeypatch, load_json):
    payload = load_json("transitous_trip.json")
    monkeypatch.setattr(trains, "get_json", lambda *args, **kwargs: payload)
    stops = trains.fetch_trip_stops(trains.DEFAULT_BASE_URL, "trip-esempio", timezone="Europe/Rome")

    roma = trains.matching_stops(stops, ("ROMA",))

    assert [stop.name for stop in roma] == ["ROMA S.PIETRO", "ROMA TRASTEVERE", "ROMA OSTIENSE"]
    assert trains.matching_stops(stops, ()) == stops


def test_trip_without_legs_raises(monkeypatch):
    monkeypatch.setattr(trains, "get_json", lambda *args, **kwargs: {"legs": []})

    with pytest.raises(SourceError, match="senza fermate"):
        trains.fetch_trip_stops(trains.DEFAULT_BASE_URL, "trip-vuoto", timezone="Europe/Rome")
