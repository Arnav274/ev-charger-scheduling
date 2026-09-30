"""The six station-selection strategies compared by the app and the experiments.

Every strategy ranks the same candidate list and differs only in what it
optimises. Strategies work on plain `StationInfo` records rather than ORM rows,
so the experiment runner can drive them from a snapshot file with no database.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.config import ENERGY_CONSUMPTION_KWH_PER_KM
from app.dijkstra import Station as GraphStation
from app.dijkstra import shortest_paths_to_stations
from app.queueing import WaitPrediction, predict_wait


@dataclass(frozen=True)
class StationInfo:
    id: str
    name: str
    lat: float
    lon: float
    chargers: int
    price_pence_per_kwh: float
    arrival_rate_per_hour: float
    mean_service_minutes: float

    @classmethod
    def from_model(cls, station) -> StationInfo:
        return cls(
            id=str(station.id),
            name=station.name,
            lat=station.lat,
            lon=station.lon,
            chargers=len(station.chargers),
            price_pence_per_kwh=station.price_pence_per_kwh,
            arrival_rate_per_hour=station.arrival_rate_per_hour,
            mean_service_minutes=station.mean_service_minutes,
        )


@dataclass(frozen=True)
class Travel:
    distance_km: float
    duration_min: float


@dataclass
class RecommendationContext:
    origin_lat: float
    origin_lon: float
    # Road distance and drive time from the origin to each candidate, keyed by station id.
    travel: dict[str, Travel]
    # Peak number of chargers already booked at each station during the driver's
    # expected arrival window. Only QueueAwareStrategy looks at it.
    reserved_by_station: dict[str, int] = field(default_factory=dict)
    weights: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)  # distance, wait, price
    battery_level_percent: float | None = None
    battery_capacity_kwh: float | None = None
    # Lets the experiments stress-test every strategy with a higher arrival rate.
    arrival_rate_scale: float = 1.0


@dataclass(frozen=True)
class Ranked:
    station: StationInfo
    score: float
    prediction: WaitPrediction


@dataclass(frozen=True)
class Normaliser:
    """Largest value of each objective across the candidate set, so each term scales to [0, 1]."""

    distance: float
    wait: float
    price: float

    @classmethod
    def over(
        cls,
        stations: Sequence[StationInfo],
        ctx: RecommendationContext,
        predictions: dict[str, WaitPrediction],
    ) -> Normaliser:
        return cls(
            distance=max(ctx.travel[s.id].distance_km for s in stations) or 1.0,
            wait=max(p.wait_min for p in predictions.values()) or 1.0,
            price=max(s.price_pence_per_kwh for s in stations) or 1.0,
        )


class SelectionStrategy:
    """Base class: predict each station's wait, normalise, score, and sort (lower score is better)."""

    uses_reservations = False

    def free_chargers(self, station: StationInfo, ctx: RecommendationContext) -> int:
        if not self.uses_reservations:
            return station.chargers
        # At least one charger is assumed to free up eventually, so a fully booked
        # station is treated as a single-server queue rather than an infinite wait.
        return max(1, station.chargers - ctx.reserved_by_station.get(station.id, 0))

    def predict(self, station: StationInfo, ctx: RecommendationContext) -> WaitPrediction:
        return predict_wait(
            station.arrival_rate_per_hour * ctx.arrival_rate_scale,
            station.mean_service_minutes,
            self.free_chargers(station, ctx),
        )

    def rank(self, stations: Sequence[StationInfo], ctx: RecommendationContext) -> list[Ranked]:
        if not stations:
            return []
        predictions = {s.id: self.predict(s, ctx) for s in stations}
        norm = Normaliser.over(stations, ctx, predictions)
        ranked = [Ranked(s, self.score(s, ctx, predictions[s.id], norm), predictions[s.id]) for s in stations]
        ranked.sort(key=lambda r: (r.score, r.station.id))
        return ranked

    def score(
        self, station: StationInfo, ctx: RecommendationContext, prediction: WaitPrediction, norm: Normaliser
    ) -> float:
        raise NotImplementedError


class NearestStrategy(SelectionStrategy):
    """Shortest road distance, ignoring the queue entirely."""

    def score(self, station, ctx, prediction, norm):
        return ctx.travel[station.id].distance_km


class CostOptimizedStrategy(SelectionStrategy):
    """Weighted sum of normalised distance, predicted wait and price."""

    def score(self, station, ctx, prediction, norm):
        w_distance, w_wait, w_price = ctx.weights
        return (
            w_distance * ctx.travel[station.id].distance_km / norm.distance
            + w_wait * prediction.wait_min / norm.wait
            + w_price * station.price_pence_per_kwh / norm.price
        )


# The queue strategies weight wait heavily; the small distance term stops them
# sending a driver across London to shave a few seconds off an already short queue.
QUEUE_WEIGHT = 0.85


class StaticQueueStrategy(SelectionStrategy):
    """Erlang-C wait from station parameters alone, plus a little distance."""

    def score(self, station, ctx, prediction, norm):
        return (
            QUEUE_WEIGHT * prediction.wait_min / norm.wait
            + (1 - QUEUE_WEIGHT) * ctx.travel[station.id].distance_km / norm.distance
        )


class QueueAwareStrategy(StaticQueueStrategy):
    """As StaticQueue, but chargers already booked for the arrival window are taken out of service."""

    uses_reservations = True


class RangeAwareStrategy(SelectionStrategy):
    """Lowest predicted wait among the stations the car can reach on its current charge."""

    SAFETY_BUFFER_KWH = 2.0  # charge the driver should still have on arrival
    # Normalised wait lies in [0, 1], so adding 2 puts every unreachable station
    # behind every reachable one while keeping their relative order.
    UNREACHABLE_PENALTY = 2.0

    def reachable(self, station: StationInfo, ctx: RecommendationContext) -> bool:
        if ctx.battery_level_percent is None or ctx.battery_capacity_kwh is None:
            return True
        remaining_kwh = ctx.battery_level_percent / 100.0 * ctx.battery_capacity_kwh
        needed_kwh = ctx.travel[station.id].distance_km * ENERGY_CONSUMPTION_KWH_PER_KM
        return remaining_kwh - needed_kwh >= self.SAFETY_BUFFER_KWH

    def score(self, station, ctx, prediction, norm):
        penalty = 0.0 if self.reachable(station, ctx) else self.UNREACHABLE_PENALTY
        return prediction.wait_min / norm.wait + penalty


Router = Callable[[float, float, Sequence[StationInfo]], dict[str, float]]


def straight_line_router(
    origin_lat: float, origin_lon: float, stations: Sequence[StationInfo]
) -> dict[str, float]:
    results = shortest_paths_to_stations(
        origin_lat, origin_lon, [GraphStation(s.id, s.lat, s.lon) for s in stations]
    )
    return {sid: r.distance_km for sid, r in results.items()}


class DijkstraStrategy(SelectionStrategy):
    """Shortest path computed by our own Dijkstra implementation."""

    def __init__(self, router: Router = straight_line_router) -> None:
        self.router = router

    def rank(self, stations, ctx):
        if not stations:
            return []
        path_costs = self.router(ctx.origin_lat, ctx.origin_lon, stations)
        ranked = [Ranked(s, path_costs[s.id], self.predict(s, ctx)) for s in stations]
        ranked.sort(key=lambda r: (r.score, r.station.id))
        return ranked


STRATEGIES: dict[str, SelectionStrategy] = {
    "nearest": NearestStrategy(),
    "dijkstra": DijkstraStrategy(),
    "cost_optimized": CostOptimizedStrategy(),
    "static_queue": StaticQueueStrategy(),
    "queue_aware": QueueAwareStrategy(),
    "range_aware": RangeAwareStrategy(),
}
