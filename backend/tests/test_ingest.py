from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import Charger, Reservation
from scripts.ingest_openchargemap import (
    ingest,
    is_usable,
    max_power_kw,
    parse_price_pence_per_kwh,
    sync_chargers,
)


def record(**overrides) -> dict:
    base = {
        "ID": 1,
        "AddressInfo": {
            "Title": "Kings Cross Car Park",
            "AddressLine1": "1 York Way",
            "Latitude": 51.53,
            "Longitude": -0.12,
        },
        "StatusType": {"IsOperational": True},
        "SubmissionStatus": {"IsLive": True},
    }
    return {**base, **overrides}


def test_a_normal_station_is_usable() -> None:
    assert is_usable(record())


def test_unknown_status_is_kept() -> None:
    assert is_usable(record(StatusType=None))
    assert is_usable(record(StatusType={"IsOperational": None, "Title": "Unknown"}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"AddressInfo": {"Title": "QA Test Station", "Latitude": 51.5, "Longitude": -0.12}},
        {
            "AddressInfo": {
                "Title": "Car park",
                "AddressLine1": "1 QA Street",
                "Latitude": 51.5,
                "Longitude": 0,
            }
        },
        {"StatusType": {"IsOperational": False, "Title": "Not Operational"}},
        {"SubmissionStatus": {"IsLive": False}},
        {"AddressInfo": {"Title": "No location"}},
        {"ID": None},
    ],
)
def test_test_entries_and_broken_stations_are_skipped(overrides) -> None:
    assert not is_usable(record(**overrides))


def test_words_containing_test_are_not_mistaken_for_test_entries() -> None:
    assert is_usable(record(AddressInfo={"Title": "Contest Road", "Latitude": 51.5, "Longitude": -0.1}))


@pytest.mark.parametrize(
    "tariff,expected",
    [
        ("£0.59/kWh; other tariffs available", 59.0),
        ("Day (07:00-00:00): £0.65/kWh Night (00:00-0700): £0.29/kWh", 65.0),
        ("£0.35 + £0.45/kWh", 45.0),
        ("75p per kWh", 75.0),
        ("ESB: PAYG 29p per kWh, or 25p per kWh with membership", 29.0),
        ("Free. Parking fees apply.", 0.0),
        ("£0.073/minute; min £1.38", None),
        ("Inclusive; for subscription members only", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_price(tariff, expected) -> None:
    assert parse_price_pence_per_kwh(tariff) == pytest.approx(expected)


def test_max_power_takes_the_fastest_connection() -> None:
    assert max_power_kw({"Connections": [{"PowerKW": 7}, {"PowerKW": 50}, {"PowerKW": None}]}) == 50
    assert max_power_kw({"Connections": []}) == 7.0
    assert max_power_kw({}) == 7.0


def test_duplicate_records_count_once_towards_the_minimum(monkeypatch) -> None:
    import scripts.ingest_openchargemap as module

    monkeypatch.setattr(module, "SessionLocal", lambda: pytest.fail("ingest opened a database session"))
    with pytest.raises(SystemExit, match="Only 2 usable stations"):
        ingest([record(ID=1)] * 30 + [record(ID=2)] * 30, prune=True, min_stations=50)


def test_a_short_response_is_refused_before_anything_is_written(monkeypatch) -> None:
    import scripts.ingest_openchargemap as module

    def no_database():
        raise AssertionError("ingest opened a database session")

    monkeypatch.setattr(module, "SessionLocal", no_database)
    with pytest.raises(SystemExit, match="Only 1 usable stations"):
        ingest([record()], prune=True, min_stations=50)


def charger_names(db, station) -> list[str]:
    return list(
        db.scalars(select(Charger.name).where(Charger.station_id == station.id).order_by(Charger.name))
    )


def test_re_ingesting_keeps_bookings_and_updates_power(db, make_station, user, now) -> None:
    station = make_station(chargers=2)
    booked = Reservation(
        charger_id=station.chargers[0].id, user_id=user.id, start_time=now, end_time=now + timedelta(hours=1)
    )
    db.add(booked)
    db.flush()

    sync_chargers(db, station.id, wanted=2, power_kw=50.0)
    db.expire_all()

    assert db.get(Reservation, booked.id) is not None
    assert {c.power_kw for c in db.scalars(select(Charger).where(Charger.station_id == station.id))} == {50.0}


def test_re_ingesting_adds_and_removes_chargers(db, make_station) -> None:
    station = make_station(chargers=2)  # named C1 and C2
    sync_chargers(db, station.id, wanted=4, power_kw=7.0)
    assert charger_names(db, station) == ["C1", "C2", "Charger 1", "Charger 2"]

    sync_chargers(db, station.id, wanted=1, power_kw=7.0)
    assert charger_names(db, station) == ["C1"]


def test_unbooked_chargers_are_removed_before_booked_ones(db, make_station, user, now) -> None:
    station = make_station(chargers=2)  # C1 unbooked, C2 booked
    c2 = station.chargers[1]
    db.add(Reservation(charger_id=c2.id, user_id=user.id, start_time=now, end_time=now + timedelta(hours=1)))
    db.flush()

    assert sync_chargers(db, station.id, wanted=1, power_kw=7.0) == 0  # no upcoming booking lost

    assert charger_names(db, station) == ["C2"]
    sync_chargers(db, station.id, wanted=2, power_kw=7.0)
    assert charger_names(db, station) == ["C2", "Charger 1"]


def test_bookings_lost_to_a_shrinking_station_are_counted(db, make_station, user, now) -> None:
    station = make_station(chargers=2)
    for charger in station.chargers:
        db.add(
            Reservation(
                charger_id=charger.id, user_id=user.id, start_time=now, end_time=now + timedelta(hours=1)
            )
        )
    db.flush()
    assert sync_chargers(db, station.id, wanted=1, power_kw=7.0) == 1
