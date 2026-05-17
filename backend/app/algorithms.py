from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from app.config import ENERGY_CONSUMPTION_KWH_PER_KM
from app.dijkstra import Station as DijkstraStation
from app.dijkstra import shortest_paths_to_stations
from app.models import Station
from app.queueing import erlang_c_wait_minutes


@dataclass
class RecommendationContext:
    origin_lat: float
    origin_lon: float
    weights: tuple[float, float, float]
    arrival_window_minutes: int = 15
    future_reserved_parallel_by_station: dict[str, int] | None = None
    future_reservation_starts_by_station: dict[str, int] | None = None
    travel_by_station: dict[str, tuple[float, float]] | None = None  # station_id -> (distance_km, duration_min)
    current_occupancy_by_station: dict[str, int] | None = None
    battery_level_percent: float | None = None  # 0–100
    battery_capacity_kwh: float | None = None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


class SelectionStrategy:
    def score(self, station: Station, context: RecommendationContext, max_vals: dict[str, float]) -> float:
        raise NotImplementedError


class NearestStrategy(SelectionStrategy):
    def score(self, station: Station, context: RecommendationContext, max_vals: dict[str, float]) -> float:
        if context.travel_by_station is not None and str(station.id) in context.travel_by_station:
            return float(context.travel_by_station[str(station.id)][0])
        return haversine_km(context.origin_lat, context.origin_lon, station.lat, station.lon)


class CostOptimizedStrategy(SelectionStrategy):
    def score(self, station: Station, context: RecommendationContext, max_vals: dict[str, float]) -> float:
        if context.travel_by_station is not None and str(station.id) in context.travel_by_station:
            distance = float(context.travel_by_station[str(station.id)][0])
        else:
            distance = haversine_km(context.origin_lat, context.origin_lon, station.lat, station.lon)
        wait = erlang_c_wait_minutes(
            arrival_rate_per_hour=station.arrival_rate_per_hour,
            mean_service_minutes=station.mean_service_minutes,
            c=max(1, len(station.chargers)),
        )
        cost = station.price_pence_per_kwh
        w_d, w_q, w_c = context.weights
        return (
            w_d * (distance / max_vals["distance"])
            + w_q * (wait / max_vals["wait"])
            + w_c * (cost / max_vals["cost"])
        )


class QueueAwareStrategy(SelectionStrategy):
    def score(self, station: Station, context: RecommendationContext, max_vals: dict[str, float]) -> float:
        if context.travel_by_station is not None and str(station.id) in context.travel_by_station:
            distance = float(context.travel_by_station[str(station.id)][0])
        else:
            distance = haversine_km(context.origin_lat, context.origin_lon, station.lat, station.lon)
        reserved_parallel = 0
        reservation_starts = 0
        if context.future_reserved_parallel_by_station is not None:
            reserved_parallel = int(context.future_reserved_parallel_by_station.get(str(station.id), 0))
        if context.future_reservation_starts_by_station is not None:
            reservation_starts = int(context.future_reservation_starts_by_station.get(str(station.id), 0))

        current_occupancy = 0
        if context.current_occupancy_by_station is not None:
            current_occupancy = int(context.current_occupancy_by_station.get(str(station.id), 0))

        c = max(1, len(station.chargers))
        c_eff = max(1, c - reserved_parallel)
        window_hours = max(1, int(getattr(context, "arrival_window_minutes", 15))) / 60.0
        lambda_future = station.arrival_rate_per_hour + (reservation_starts / window_hours)
        wait = erlang_c_wait_minutes(
            arrival_rate_per_hour=lambda_future,
            mean_service_minutes=station.mean_service_minutes,
            c=c_eff,
        )
        # 0.85 wait / 0.15 distance: supervisor spec prioritises minimising wait (Zhang, project brief 2024).
        # Non-zero distance weight prevents recommending unreachable zero-queue stations.
        return 0.85 * (wait / max_vals["wait"]) + 0.15 * (distance / max_vals["distance"])


class StaticQueueStrategy(SelectionStrategy):
    """
    Baseline: Erlang-C using only station parameters (no reservation lookahead).
    """

    def score(self, station: Station, context: RecommendationContext, max_vals: dict[str, float]) -> float:
        if context.travel_by_station is not None and str(station.id) in context.travel_by_station:
            distance = float(context.travel_by_station[str(station.id)][0])
        else:
            distance = haversine_km(context.origin_lat, context.origin_lon, station.lat, station.lon)
        wait = erlang_c_wait_minutes(
            arrival_rate_per_hour=station.arrival_rate_per_hour,
            mean_service_minutes=station.mean_service_minutes,
            c=max(1, len(station.chargers)),
        )
        return 0.85 * (wait / max_vals["wait"]) + 0.15 * (distance / max_vals["distance"])


class DijkstraStrategy(SelectionStrategy):
    """Distance-based selection using Dijkstra's algorithm on a complete graph.

    Intended to be driven via rank_all(), which passes ALL candidate stations
    to shortest_paths_to_stations() in a single call so that each station can
    act as an intermediate waypoint — the correct, academically meaningful use
    of the algorithm. See dijkstra.py module docstring for the full rationale.

    score() is retained for per-station calls and accepts an optional
    pre_computed_distance; when not supplied it falls back to direct haversine
    (useful for unit testing individual stations in isolation).
    """

    def rank_all(
        self,
        stations: list,
        context: RecommendationContext,
    ) -> dict[str, float]:
        """Run Dijkstra once over the full candidate graph.

        Args:
            stations: All candidate ORM Station objects.
            context: Supplies the EV origin coordinates.

        Returns:
            Mapping of station_id (str) -> shortest-path distance in km.
        """
        dijkstra_stations = [
            DijkstraStation(station_id=str(s.id), lat=s.lat, lon=s.lon)
            for s in stations
        ]
        results = shortest_paths_to_stations(
            origin_lat=context.origin_lat,
            origin_lon=context.origin_lon,
            stations=dijkstra_stations,
        )
        return {sid: r.distance_km for sid, r in results.items()}

    def score(
        self,
        station: Station,
        context: RecommendationContext,
        max_vals: dict[str, float],
        pre_computed_distance: float | None = None,
    ) -> float:
        if pre_computed_distance is not None:
            return pre_computed_distance
        return haversine_km(context.origin_lat, context.origin_lon, station.lat, station.lon)


class RangeAwareStrategy(SelectionStrategy):
    """Wait-minimising strategy restricted to stations the EV can safely reach.

    Among reachable stations the score is normalised Erlang-C wait time, so the
    algorithm selects the fastest charger the EV can actually get to.  Stations
    that would drain the battery below the 2 kWh safety buffer receive a large
    additive penalty, pushing them behind all reachable alternatives.

    Behaviour by battery state:
      - High SOC (all stations reachable): equivalent to StaticQueueStrategy.
      - Low SOC (some stations unreachable): picks lowest-wait among reachable
        stations, which may be farther than the globally nearest charger.
      - No battery context supplied: falls back to StaticQueueStrategy.

    Consumption estimate: 0.2 kWh/km (IEA/ACEA fleet average, config.py).
    """

    _CONSUMPTION_KWH_PER_KM = ENERGY_CONSUMPTION_KWH_PER_KM
    _SAFETY_BUFFER_KWH = 2.0
    _RANGE_PENALTY = 1e6

    def score(self, station: Station, context: RecommendationContext, max_vals: dict[str, float]) -> float:
        if context.travel_by_station is not None and str(station.id) in context.travel_by_station:
            distance_km = float(context.travel_by_station[str(station.id)][0])
        else:
            distance_km = haversine_km(context.origin_lat, context.origin_lon, station.lat, station.lon)

        wait = erlang_c_wait_minutes(
            arrival_rate_per_hour=station.arrival_rate_per_hour,
            mean_service_minutes=station.mean_service_minutes,
            c=max(1, len(station.chargers)),
        )
        # Normalise wait so the penalty dominates clearly.
        base_score = wait / max(max_vals["wait"], 1e-9)

        penalty = 0.0
        if context.battery_level_percent is not None and context.battery_capacity_kwh is not None:
            remaining_kwh = (context.battery_level_percent / 100.0) * context.battery_capacity_kwh
            if remaining_kwh - distance_km * self._CONSUMPTION_KWH_PER_KM < self._SAFETY_BUFFER_KWH:
                penalty = self._RANGE_PENALTY

        return base_score + penalty


STRATEGIES: dict[str, SelectionStrategy] = {
    "nearest": NearestStrategy(),
    "cost_optimized": CostOptimizedStrategy(),
    "queue_aware": QueueAwareStrategy(),
    "static_queue": StaticQueueStrategy(),
    "dijkstra": DijkstraStrategy(),
    "range_aware": RangeAwareStrategy(),
}
