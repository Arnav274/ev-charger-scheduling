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
    weights: tuple[float, float, float]           # (w_distance, w_wait, w_cost) for CostOptimized
    arrival_window_minutes: int = 15
    # Counts how many chargers at each station are reserved in parallel during
    # the user's estimated arrival window — used by QueueAwareStrategy to
    # reduce the effective server count (c_eff) fed into Erlang-C.
    future_reserved_parallel_by_station: dict[str, int] | None = None
    future_reservation_starts_by_station: dict[str, int] | None = None
    travel_by_station: dict[str, tuple[float, float]] | None = None  # station_id -> (distance_km, duration_min)
    current_occupancy_by_station: dict[str, int] | None = None
    battery_level_percent: float | None = None  # 0–100
    battery_capacity_kwh: float | None = None




def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points (km). Used as fallback when OSRM is unavailable."""
    r = 6371.0  # Earth's mean radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))




class SelectionStrategy:
    def score(self, station: Station, context: RecommendationContext, max_vals: dict[str, float]) -> float:
        """Return a score for this station (lower = better). max_vals normalises each dimension to [0, 1]."""
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
        # Weighted linear sum of three normalised objectives: distance, queue
        # wait, and price. Each term is 0–1 relative to the worst candidate in
        # the set. Weights allow the user to express a preference (e.g. cheaper
        # vs faster). Default weights are set in config.py.
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
        if context.future_reserved_parallel_by_station is not None:
            reserved_parallel = int(context.future_reserved_parallel_by_station.get(str(station.id), 0))





        c = max(1, len(station.chargers))
        # c_eff: effective available chargers after subtracting those already
        # reserved by other users during this driver's expected arrival window.
        # Feeding c_eff into Erlang-C gives a more realistic wait estimate than
        # using total charger count (c), which StaticQueueStrategy does.
        c_eff = max(1, c - reserved_parallel)
        wait = erlang_c_wait_minutes(
            arrival_rate_per_hour=station.arrival_rate_per_hour,
            mean_service_minutes=station.mean_service_minutes,
            c=c_eff,
        )
        # 0.85/0.15 split: strongly prioritises wait time (supervisor aim) while
        # keeping a small distance component to avoid routing to distant zero-queue stations.
        return 0.85 * (wait / max_vals["wait"]) + 0.15 * (distance / max_vals["distance"])





class StaticQueueStrategy(SelectionStrategy):
    """Baseline: Erlang-C using only station parameters, no reservation lookahead."""

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
    """Distance-based selection using Dijkstra on a complete Haversine graph."""

    def rank_all(
        self,
        stations: list,
        context: RecommendationContext,
    ) -> dict[str, float]:
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
    """Erlang-C wait scoring with a large penalty for stations outside battery range."""

    _CONSUMPTION_KWH_PER_KM = ENERGY_CONSUMPTION_KWH_PER_KM  # ~0.2 kWh/km (see config.py)
    _SAFETY_BUFFER_KWH = 2.0     # Minimum reserve after arriving — prevents routing to a station the car can barely reach
    _RANGE_PENALTY = 1e6         # Score penalty large enough to push unreachable stations to last place

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
