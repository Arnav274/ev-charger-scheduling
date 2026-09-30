"""Endpoint tests against a real PostGIS database (see conftest.py)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Reservation


def test_healthcheck(client) -> None:
    assert client.get("/health").json() == {"status": "ok"}


PASSWORD = "Password123"


class TestAuth:
    def test_register_then_login(self, client) -> None:
        body = {"email": "new.driver@example.com", "password": "Password123"}
        assert client.post("/auth/register", json=body).status_code == 201

        response = client.post("/auth/login", data={"username": body["email"], "password": body["password"]})
        assert response.status_code == 200
        assert response.json()["token_type"] == "bearer"

    def test_register_rejects_duplicate_email_regardless_of_case(self, client) -> None:
        client.post("/auth/register", json={"email": "driver@example.com", "password": PASSWORD})
        response = client.post("/auth/register", json={"email": "Driver@Example.com", "password": PASSWORD})
        assert response.status_code == 409

    def test_login_is_case_insensitive(self, client) -> None:
        client.post("/auth/register", json={"email": "mixed@example.com", "password": PASSWORD})
        response = client.post("/auth/login", data={"username": "MIXED@example.com", "password": PASSWORD})
        assert response.status_code == 200

    def test_login_rejects_wrong_password(self, client, user) -> None:
        response = client.post("/auth/login", data={"username": user.email, "password": "not-it"})
        assert response.status_code == 401

    def test_protected_route_requires_token(self, client) -> None:
        assert client.get("/reservations/mine").status_code == 401

    def test_protected_route_rejects_garbage_token(self, client) -> None:
        response = client.get("/reservations/mine", headers={"Authorization": "Bearer not-a-jwt"})
        assert response.status_code == 401


class TestStations:
    def test_nearby_returns_stations_in_radius_sorted_by_distance(self, client, make_station) -> None:
        far = make_station(lat=51.5300, lon=-0.1278, name="Far")  # ~2.5 km north
        near = make_station(lat=51.5080, lon=-0.1278, name="Near")  # ~70 m north
        make_station(lat=52.2053, lon=0.1218, name="Cambridge")  # outside the radius

        response = client.get("/stations/nearby", params={"lat": 51.5074, "lon": -0.1278, "radius_km": 5})

        assert response.status_code == 200
        rows = response.json()
        assert [r["id"] for r in rows] == [str(near.id), str(far.id)]
        assert rows[0]["distance_m"] == pytest.approx(67, abs=5)

    def test_nearby_validates_coordinates(self, client) -> None:
        assert client.get("/stations/nearby", params={"lat": 123, "lon": 0}).status_code == 422

    def test_detail_lists_chargers(self, client, make_station) -> None:
        station = make_station(chargers=3)
        response = client.get(f"/stations/{station.id}")
        assert response.status_code == 200
        assert len(response.json()["chargers"]) == 3

    def test_detail_404_for_unknown_station(self, client) -> None:
        assert client.get(f"/stations/{uuid.uuid4()}").status_code == 404

    def test_detail_422_for_malformed_id(self, client) -> None:
        assert client.get("/stations/not-a-uuid").status_code == 422


class TestSuggestSlot:
    desired = datetime(2030, 6, 1, 10, 0, tzinfo=UTC)

    def test_free_station_offers_the_desired_time(self, client, make_station) -> None:
        station = make_station(chargers=2)
        response = client.post(
            f"/stations/{station.id}/suggest-slot",
            json={"desired_arrival": self.desired.isoformat(), "duration_minutes": 60},
        )
        slots = response.json()
        assert len(slots) == 2
        assert all(s["wait_from_desired_minutes"] == 0 for s in slots)

    def test_rounds_up_to_the_next_half_hour(self, client, make_station) -> None:
        station = make_station(chargers=1)
        response = client.post(
            f"/stations/{station.id}/suggest-slot",
            json={"desired_arrival": "2030-06-01T10:05:00Z", "duration_minutes": 30},
        )
        assert response.json()[0]["suggested_start"].startswith("2030-06-01T10:30:00")

    def test_skips_past_an_existing_booking(self, client, db, make_station, user) -> None:
        station = make_station(chargers=1)
        db.add(
            Reservation(
                charger_id=station.chargers[0].id,
                user_id=user.id,
                start_time=self.desired,
                end_time=self.desired + timedelta(minutes=45),
            )
        )
        db.flush()
        response = client.post(
            f"/stations/{station.id}/suggest-slot",
            json={"desired_arrival": self.desired.isoformat(), "duration_minutes": 60},
        )
        assert response.json()[0]["wait_from_desired_minutes"] == 60

    def test_never_offers_a_slot_that_has_already_started(self, client, make_station) -> None:
        station = make_station(chargers=1)
        an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
        response = client.post(
            f"/stations/{station.id}/suggest-slot",
            json={"desired_arrival": an_hour_ago.isoformat(), "duration_minutes": 30},
        )
        slot = response.json()[0]
        assert datetime.fromisoformat(slot["suggested_start"]) >= datetime.now(UTC) - timedelta(seconds=1)
        # The wait counts from now, not from the hour-old request.
        assert slot["wait_from_desired_minutes"] <= 30

    def test_fully_booked_station_offers_nothing(self, client, db, make_station, user) -> None:
        station = make_station(chargers=1)
        db.add(
            Reservation(
                charger_id=station.chargers[0].id,
                user_id=user.id,
                start_time=self.desired,
                end_time=self.desired + timedelta(hours=4),
            )
        )
        db.flush()
        response = client.post(
            f"/stations/{station.id}/suggest-slot",
            json={"desired_arrival": self.desired.isoformat(), "duration_minutes": 60},
        )
        assert response.json() == []


class TestReservations:
    def _book(self, client, headers, charger_id, start: datetime, minutes: int = 60):
        return client.post(
            "/reservations",
            headers=headers,
            json={
                "charger_id": str(charger_id),
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(minutes=minutes)).isoformat(),
            },
        )

    def test_book_and_list(self, client, auth_headers, make_station, now) -> None:
        station = make_station(chargers=1, name="Kings Cross")
        assert self._book(client, auth_headers, station.chargers[0].id, now).status_code == 201

        mine = client.get("/reservations/mine", headers=auth_headers).json()
        assert len(mine) == 1
        assert mine[0]["station_name"] == "Kings Cross"
        assert mine[0]["charger_name"] == "C1"

    def test_overlapping_booking_is_rejected_by_the_database(
        self, client, auth_headers, make_station, now
    ) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        assert self._book(client, auth_headers, charger_id, now).status_code == 201

        response = self._book(client, auth_headers, charger_id, now + timedelta(minutes=30))
        assert response.status_code == 409
        # The session is still usable after the rolled-back insert.
        assert len(client.get("/reservations/mine", headers=auth_headers).json()) == 1

    def test_back_to_back_bookings_are_allowed(self, client, auth_headers, make_station, now) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        assert self._book(client, auth_headers, charger_id, now).status_code == 201
        assert self._book(client, auth_headers, charger_id, now + timedelta(minutes=60)).status_code == 201

    def test_same_time_on_another_charger_is_allowed(self, client, auth_headers, make_station, now) -> None:
        station = make_station(chargers=2)
        assert self._book(client, auth_headers, station.chargers[0].id, now).status_code == 201
        assert self._book(client, auth_headers, station.chargers[1].id, now).status_code == 201

    def test_end_before_start_is_rejected(self, client, auth_headers, make_station, now) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        assert self._book(client, auth_headers, charger_id, now, minutes=-15).status_code == 400

    def test_bookings_in_the_past_are_rejected(self, client, auth_headers, make_station, now) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        response = self._book(client, auth_headers, charger_id, now - timedelta(hours=2))
        assert response.status_code == 400
        assert "future" in response.json()["detail"]

    def test_bookings_longer_than_twelve_hours_are_rejected(
        self, client, auth_headers, make_station, now
    ) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        assert self._book(client, auth_headers, charger_id, now, minutes=13 * 60).status_code == 400
        assert self._book(client, auth_headers, charger_id, now, minutes=12 * 60).status_code == 201

    def test_upcoming_bookings_per_user_are_capped(self, client, auth_headers, make_station, now) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        for i in range(10):
            assert self._book(client, auth_headers, charger_id, now + timedelta(hours=i)).status_code == 201
        response = self._book(client, auth_headers, charger_id, now + timedelta(hours=10))
        assert response.status_code == 409
        assert "10 upcoming" in response.json()["detail"]

    def test_bookings_that_have_already_ended_are_rejected(
        self, client, auth_headers, make_station, now
    ) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        response = self._book(client, auth_headers, charger_id, now - timedelta(minutes=4), minutes=3)
        assert response.status_code == 400

    def test_bookings_more_than_thirty_days_ahead_are_rejected(
        self, client, auth_headers, make_station, now
    ) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        assert self._book(client, auth_headers, charger_id, now + timedelta(days=31)).status_code == 400
        assert self._book(client, auth_headers, charger_id, now + timedelta(days=29)).status_code == 201

    def test_cancel_frees_the_slot(self, client, auth_headers, make_station, now) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        booking = self._book(client, auth_headers, charger_id, now).json()

        assert client.delete(f"/reservations/{booking['id']}", headers=auth_headers).status_code == 204
        assert client.get("/reservations/mine", headers=auth_headers).json() == []
        assert self._book(client, auth_headers, charger_id, now).status_code == 201

    def test_cannot_cancel_someone_elses_booking(self, client, auth_headers, make_station, now) -> None:
        charger_id = make_station(chargers=1).chargers[0].id
        booking = self._book(client, auth_headers, charger_id, now).json()
        client.post("/auth/register", json={"email": "other@example.com", "password": PASSWORD})
        token = client.post(
            "/auth/login", data={"username": "other@example.com", "password": PASSWORD}
        ).json()["access_token"]

        response = client.delete(
            f"/reservations/{booking['id']}", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404
        assert len(client.get("/reservations/mine", headers=auth_headers).json()) == 1

    def test_unknown_charger_is_404(self, client, auth_headers, now) -> None:
        assert self._book(client, auth_headers, uuid.uuid4(), now).status_code == 404

    def test_only_own_reservations_are_listed(self, client, auth_headers, db, make_station, now) -> None:
        other = make_station(chargers=1)
        client.post("/auth/register", json={"email": "other@example.com", "password": "Password123"})
        token = client.post(
            "/auth/login", data={"username": "other@example.com", "password": "Password123"}
        ).json()["access_token"]
        self._book(client, {"Authorization": f"Bearer {token}"}, other.chargers[0].id, now)

        assert client.get("/reservations/mine", headers=auth_headers).json() == []


class TestVehicles:
    def test_create_and_list(self, client, auth_headers) -> None:
        response = client.post(
            "/vehicles", headers=auth_headers, json={"make_model": "Nissan Leaf", "battery_kwh": 40}
        )
        assert response.status_code == 201

        vehicles = client.get("/vehicles", headers=auth_headers).json()
        assert [v["make_model"] for v in vehicles] == ["Nissan Leaf"]

    def test_rejects_non_positive_battery(self, client, auth_headers) -> None:
        response = client.post("/vehicles", headers=auth_headers, json={"make_model": "X", "battery_kwh": 0})
        assert response.status_code == 422


def test_experiment_summary_serves_committed_results(client) -> None:
    rows = client.get("/stats/experiment-summary").json()["rows"]
    assert rows
    assert {"variant", "scenario", "algorithm"} <= rows[0].keys()


def test_findings_are_served(client) -> None:
    findings = client.get("/stats/findings").json()
    assert findings["best_strategy"] in findings["baseline"]
    assert {"baseline", "high_demand"} <= findings["lookahead"].keys()
