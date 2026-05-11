from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from app.models import Station
from app.queueing import erlang_c_wait_minutes


@dataclass
class RecommendationContext:
    origin_lat: float
    origin_lon: float
    weights: tuple[float, float, float]


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
        return haversine_km(context.origin_lat, context.origin_lon, station.lat, station.lon)


class CostOptimizedStrategy(SelectionStrategy):
    def score(self, station: Station, context: RecommendationContext, max_vals: dict[str, float]) -> float:
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
        distance = haversine_km(context.origin_lat, context.origin_lon, station.lat, station.lon)
        wait = erlang_c_wait_minutes(
            arrival_rate_per_hour=station.arrival_rate_per_hour,
            mean_service_minutes=station.mean_service_minutes,
            c=max(1, len(station.chargers)),
        )
        return 0.85 * (wait / max_vals["wait"]) + 0.15 * (distance / max_vals["distance"])


STRATEGIES: dict[str, SelectionStrategy] = {
    "nearest": NearestStrategy(),
    "cost_optimized": CostOptimizedStrategy(),
    "queue_aware": QueueAwareStrategy(),
}
