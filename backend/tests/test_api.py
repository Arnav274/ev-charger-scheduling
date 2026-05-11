from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.auth_deps import get_current_user_id
from app.database import get_db
from app.main import app
from app.models import Charger, Reservation, Station


class FakeResult:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self._rows


class FakeQuery:
    def __init__(self, station_rows: list[Station]) -> None:
        self._station_rows = station_rows
        self._filtered_station_id: str | None = None

    def options(self, *_args, **_kwargs) -> "FakeQuery":
        return self

    def filter(self, expression) -> "FakeQuery":
        try:
            self._filtered_station_id = str(expression.right.value)
        except Exception:
            self._filtered_station_id = None
        return self

    def all(self) -> list[Station]:
        return self._station_rows

    def first(self) -> Station | None:
        if self._filtered_station_id is None:
            return self._station_rows[0] if self._station_rows else None
        for station in self._station_rows:
            if str(station.id) == self._filtered_station_id:
                return station
        return None


class FakeDb:
    def __init__(
        self,
        *,
        nearby_rows: list[SimpleNamespace] | None = None,
        station_rows: list[Station] | None = None,
        fail_overlap: bool = False,
        fail_generic_commit: bool = False,
    ) -> None:
        self._nearby_rows = nearby_rows or []
        self._station_rows = station_rows or []
        self._fail_overlap = fail_overlap
        self._fail_generic_commit = fail_generic_commit
        self.added: list[Reservation] = []
        self.refreshed: list[Reservation] = []
        self.rollback_called = False

    def execute(self, *_args, **_kwargs) -> FakeResult:
        return FakeResult(self._nearby_rows)

    def query(self, _model):
        return FakeQuery(self._station_rows)

    def add(self, instance: Reservation) -> None:
        self.added.append(instance)

    def commit(self) -> None:
        if self._fail_overlap:
            raise IntegrityError("stmt", "params", Exception("exclude_overlapping_reservations"))
        if self._fail_generic_commit:
            raise IntegrityError("stmt", "params", Exception("other_integrity_issue"))

    def refresh(self, instance: Reservation) -> None:
        if instance.id is None:
            instance.id = uuid4()
        self.refreshed.append(instance)

    def close(self) -> None:
        return None

    def rollback(self) -> None:
        self.rollback_called = True


def make_station(*, station_id: str | None = None, n_chargers: int = 2) -> Station:
    sid = station_id or str(uuid4())
    station = Station(
        id=sid,
        source="test",
        source_id=f"src-{sid}",
        name=f"Station-{sid[:8]}",
        borough="Westminster",
        address="Somewhere",
        lat=51.5074,
        lon=-0.1278,
        price_pence_per_kwh=52.0,
        arrival_rate_per_hour=4.0,
        mean_service_minutes=40.0,
        raw_json={},
    )
    station.chargers = [
        Charger(id=str(uuid4()), station_id=sid, name=f"C{i+1}", power_kw=22.0, connector_type="Type2")
        for i in range(n_chargers)
    ]
    return station


def with_override(fake_db: FakeDb) -> TestClient:
    def _get_db_override():
        yield fake_db

    app.dependency_overrides[get_db] = _get_db_override
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_healthcheck() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_stations_nearby_returns_rows() -> None:
    rows = [
        SimpleNamespace(
            id=str(uuid4()),
            name="A",
            borough="Camden",
            lat=51.51,
            lon=-0.12,
            price_pence_per_kwh=48.0,
            distance_m=123.4,
        )
    ]
    client = with_override(FakeDb(nearby_rows=rows))
    response = client.get("/stations/nearby?lat=51.5074&lon=-0.1278&radius_km=5")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "A"
    assert payload[0]["distance_m"] == pytest.approx(123.4)


def test_station_detail_404_for_missing_station() -> None:
    client = with_override(FakeDb(station_rows=[]))
    response = client.get(f"/stations/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Station not found"


def test_station_detail_returns_chargers() -> None:
    station = make_station(n_chargers=1)
    client = with_override(FakeDb(station_rows=[station]))
    response = client.get(f"/stations/{station.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(station.id)
    assert len(payload["chargers"]) == 1


def test_create_reservation_rejects_invalid_window() -> None:
    station = make_station(n_chargers=1)
    client = with_override(FakeDb(station_rows=[station]))
    uid = uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: uid
    start = datetime.now(timezone.utc)
    end = start - timedelta(minutes=15)
    response = client.post(
        "/reservations",
        json={
            "charger_id": str(station.chargers[0].id),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        },
    )
    assert response.status_code == 400
    assert "after start_time" in response.json()["detail"]


def test_create_reservation_returns_201() -> None:
    station = make_station(n_chargers=1)
    fake_db = FakeDb(station_rows=[station])
    client = with_override(fake_db)
    uid = uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: uid
    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=45)
    response = client.post(
        "/reservations",
        json={
            "charger_id": str(station.chargers[0].id),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        },
    )
    assert response.status_code == 201
    assert len(fake_db.added) == 1
    assert len(fake_db.refreshed) == 1


def test_create_reservation_returns_409_on_overlap() -> None:
    station = make_station(n_chargers=1)
    fake_db = FakeDb(station_rows=[station], fail_overlap=True)
    client = with_override(fake_db)
    uid = uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: uid
    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=30)
    response = client.post(
        "/reservations",
        json={
            "charger_id": str(station.chargers[0].id),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Overlapping reservation"
    assert fake_db.rollback_called


def test_create_reservation_returns_400_on_generic_integrity_error() -> None:
    station = make_station(n_chargers=1)
    client = with_override(FakeDb(station_rows=[station], fail_generic_commit=True))
    uid = uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: uid
    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=30)
    response = client.post(
        "/reservations",
        json={
            "charger_id": str(station.chargers[0].id),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation creation failed"


def test_recommendations_rejects_unknown_algorithm() -> None:
    client = TestClient(app)
    response = client.post(
        "/recommendations",
        json={
            "origin_lat": 51.5074,
            "origin_lon": -0.1278,
            "radius_km": 5,
            "algorithm": "not_a_real_algorithm",
            "top_k": 3,
        },
    )
    assert response.status_code == 400
    assert "Unknown algorithm" in response.json()["detail"]


@pytest.mark.parametrize("algorithm", ["nearest", "cost_optimized", "queue_aware"])
def test_recommendations_support_all_algorithms(algorithm: str) -> None:
    station_a = make_station(n_chargers=2)
    station_b = make_station(n_chargers=3)
    client = with_override(FakeDb(station_rows=[station_a, station_b]))
    response = client.post(
        "/recommendations",
        json={
            "origin_lat": 51.5074,
            "origin_lon": -0.1278,
            "radius_km": 5,
            "algorithm": algorithm,
            "top_k": 2,
            "weights": [0.33, 0.33, 0.34],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert all("station_name" in row for row in payload)


def test_recommendations_fallback_to_all_when_radius_empty() -> None:
    far_station = make_station(n_chargers=1)
    far_station.lat = 55.9533
    far_station.lon = -3.1883
    client = with_override(FakeDb(station_rows=[far_station]))
    response = client.post(
        "/recommendations",
        json={
            "origin_lat": 51.5074,
            "origin_lon": -0.1278,
            "radius_km": 0.1,
            "algorithm": "nearest",
            "top_k": 1,
        },
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
