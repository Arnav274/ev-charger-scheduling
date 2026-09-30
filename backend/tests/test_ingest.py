import pytest

from scripts.ingest_openchargemap import is_usable, max_power_kw, parse_price_pence_per_kwh


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
