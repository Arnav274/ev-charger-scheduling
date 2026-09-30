"""Unit tests for the selection strategies, independent of the database and OSRM."""

import pytest

from app.algorithms import (
    STRATEGIES,
    CostOptimizedStrategy,
    DijkstraStrategy,
    NearestStrategy,
    QueueAwareStrategy,
    RangeAwareStrategy,
    RecommendationContext,
    StaticQueueStrategy,
    StationInfo,
    Travel,
)


def station(sid: str, *, chargers: int = 2, price: float = 50.0, arrival_rate: float = 0.75) -> StationInfo:
    return StationInfo(
        id=sid,
        name=sid,
        lat=51.5,
        lon=-0.1,
        chargers=chargers,
        price_pence_per_kwh=price,
        arrival_rate_per_hour=arrival_rate,
        mean_service_minutes=40.0,
    )


def ctx(distances: dict[str, float], **kwargs) -> RecommendationContext:
    return RecommendationContext(
        origin_lat=51.5,
        origin_lon=-0.1,
        travel={sid: Travel(km, km * 2) for sid, km in distances.items()},
        **kwargs,
    )


def order(strategy, stations, context) -> list[str]:
    return [r.station.id for r in strategy.rank(stations, context)]


def test_registry_exposes_all_six_strategies() -> None:
    assert set(STRATEGIES) == {
        "nearest",
        "dijkstra",
        "cost_optimized",
        "static_queue",
        "queue_aware",
        "range_aware",
    }


def test_rank_of_nothing_is_empty() -> None:
    for strategy in STRATEGIES.values():
        assert strategy.rank([], ctx({})) == []


def test_nearest_orders_by_road_distance() -> None:
    stations = [station("far"), station("near"), station("mid")]
    assert order(NearestStrategy(), stations, ctx({"far": 9, "near": 1, "mid": 4})) == ["near", "mid", "far"]


def test_ties_are_broken_deterministically_by_id() -> None:
    stations = [station("b"), station("a")]
    assert order(NearestStrategy(), stations, ctx({"a": 2, "b": 2})) == ["a", "b"]


def test_static_queue_trades_a_little_distance_for_a_much_shorter_queue() -> None:
    stations = [station("single", chargers=1), station("hub", chargers=4)]
    context = ctx({"single": 1.0, "hub": 1.5})
    assert order(NearestStrategy(), stations, context)[0] == "single"
    assert order(StaticQueueStrategy(), stations, context)[0] == "hub"


def test_static_queue_ignores_reservations_but_queue_aware_does_not() -> None:
    busy, quiet = station("busy", chargers=3), station("quiet", chargers=3)
    context = ctx({"busy": 1.0, "quiet": 1.2}, reserved_by_station={"busy": 3})

    assert order(StaticQueueStrategy(), [busy, quiet], context)[0] == "busy"
    assert order(QueueAwareStrategy(), [busy, quiet], context)[0] == "quiet"


def test_queue_aware_never_models_fewer_than_one_charger() -> None:
    s = station("s", chargers=2)
    context = ctx({"s": 1.0}, reserved_by_station={"s": 5})
    assert QueueAwareStrategy().free_chargers(s, context) == 1


def test_prediction_matches_what_the_strategy_scored() -> None:
    s = station("s", chargers=2)
    context = ctx({"s": 1.0}, reserved_by_station={"s": 1})
    static, aware = StaticQueueStrategy().rank([s], context)[0], QueueAwareStrategy().rank([s], context)[0]
    assert aware.prediction.wait_min > static.prediction.wait_min


def test_cost_optimized_follows_the_weights() -> None:
    cheap_far = station("cheap_far", price=30.0)
    dear_near = station("dear_near", price=80.0)
    distances = {"cheap_far": 8.0, "dear_near": 1.0}

    price_first = ctx(distances, weights=(0.0, 0.0, 1.0))
    distance_first = ctx(distances, weights=(1.0, 0.0, 0.0))
    stations = [cheap_far, dear_near]

    assert order(CostOptimizedStrategy(), stations, price_first)[0] == "cheap_far"
    assert order(CostOptimizedStrategy(), stations, distance_first)[0] == "dear_near"


def test_range_aware_puts_unreachable_stations_last() -> None:
    near_busy = station("near_busy", chargers=1)
    far_quiet = station("far_quiet", chargers=6)
    context = ctx({"near_busy": 2.0, "far_quiet": 30.0}, battery_level_percent=10, battery_capacity_kwh=40)

    # 4 kWh left minus a 2 kWh reserve is about 10 km at 0.2 kWh/km.
    assert order(RangeAwareStrategy(), [far_quiet, near_busy], context) == ["near_busy", "far_quiet"]


def test_range_aware_with_enough_charge_picks_the_shortest_queue() -> None:
    near_busy = station("near_busy", chargers=1)
    far_quiet = station("far_quiet", chargers=6)
    context = ctx({"near_busy": 2.0, "far_quiet": 30.0}, battery_level_percent=90, battery_capacity_kwh=60)
    assert order(RangeAwareStrategy(), [near_busy, far_quiet], context)[0] == "far_quiet"


def test_range_aware_without_battery_info_treats_everything_as_reachable() -> None:
    s = station("s")
    assert RangeAwareStrategy().reachable(s, ctx({"s": 500.0}))


def test_arrival_rate_scale_raises_predicted_waits() -> None:
    s = station("s", chargers=2)
    base = StaticQueueStrategy().predict(s, ctx({"s": 1.0}))
    stressed = StaticQueueStrategy().predict(s, ctx({"s": 1.0}, arrival_rate_scale=2.0))
    assert stressed.wait_min > base.wait_min


def test_dijkstra_ranks_by_drive_time_from_its_router() -> None:
    stations = [station("a"), station("b"), station("c"), station("island")]
    routes = {"a": Travel(2.0, 7.0), "b": Travel(4.0, 3.0), "c": Travel(1.0, 5.0), "island": None}
    strategy = DijkstraStrategy(router=lambda lat, lon, candidates: routes)

    ranked = strategy.rank(stations, ctx({"a": 1, "b": 1, "c": 1, "island": 1}))

    # Fastest first, even though "c" is the shortest; the unreachable station is dropped.
    assert [r.station.id for r in ranked] == ["b", "c", "a"]
    assert [r.score for r in ranked] == pytest.approx([3.0, 5.0, 7.0])
    assert ranked[0].travel == Travel(4.0, 3.0)
