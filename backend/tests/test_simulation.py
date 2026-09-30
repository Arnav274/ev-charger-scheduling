"""Tests for the discrete-event simulation and the analysis that summarises it."""

import json

import numpy as np
import pandas as pd
import pytest

import experiments.analyse_results as analyse
from app.algorithms import StationInfo
from app.queueing import erlang_c_wait_minutes
from experiments.simulation import (
    AppDriver,
    Day,
    Inputs,
    background_only,
    choose_stations,
    draw_day,
    fcfs_waits,
    simulate_queues,
)


class TestFcfsQueue:
    def test_single_server_queues_in_arrival_order(self) -> None:
        waits = fcfs_waits(np.array([0.0, 10.0, 20.0]), np.array([30.0, 30.0, 5.0]), servers=1)
        assert waits.tolist() == [0.0, 20.0, 40.0]

    def test_second_server_absorbs_an_overlap(self) -> None:
        waits = fcfs_waits(np.array([0.0, 10.0, 20.0]), np.array([30.0, 30.0, 5.0]), servers=2)
        assert waits.tolist() == [0.0, 0.0, 10.0]

    @pytest.mark.parametrize("servers,arrivals_per_hour", [(1, 0.75), (2, 1.5), (4, 4.5)])
    def test_long_run_average_matches_erlang_c(self, servers: int, arrivals_per_hour: float) -> None:
        # Poisson arrivals and exponential 40-minute sessions are exactly the
        # M/M/c assumptions, so the simulated mean wait must converge on Erlang-C.
        rng = np.random.default_rng(1)
        n = 400_000
        arrivals = np.cumsum(rng.exponential(60 / arrivals_per_hour, n))
        waits = fcfs_waits(arrivals, rng.exponential(40.0, n), servers)
        expected = erlang_c_wait_minutes(arrivals_per_hour, 40.0, servers)
        assert waits[n // 10 :].mean() == pytest.approx(expected, rel=0.06)


def station(sid: str, chargers: int, lat: float = 51.52, lon: float = -0.13) -> StationInfo:
    return StationInfo(sid, sid, lat, lon, chargers, 50.0, 0.75, 40.0)


@pytest.fixture
def inputs() -> Inputs:
    """Two origins and three stations: a close one-charger station, a hub, and one 30 km away."""
    km = np.array([[0.5, 2.0, 30.0], [1.0, 1.5, 30.0]], dtype=np.float32)
    minutes = km * 2
    return Inputs(
        stations=[station("close", 1), station("hub", 6), station("far", 1)],
        origins=np.array([[51.52, -0.13], [51.53, -0.12]]),
        scenario=np.array([0, 0]),
        osrm_km=km,
        osrm_min=minutes,
        dijkstra_km=km,
        dijkstra_min=minutes,
    )


def quiet_day(drivers: list[AppDriver], inputs: Inputs) -> Day:
    empty = (np.array([]), np.array([]))
    return Day(drivers=drivers, background=[empty for _ in inputs.stations])


def choose(inputs, day, algorithm, **kwargs):
    options = {"weights": (1 / 3, 1 / 3, 1 / 3), "top_k": 1, "load_multiplier": 1.0}
    options.update(kwargs)
    return choose_stations(inputs, day, algorithm, rng=np.random.default_rng(0), **options)


def test_draw_day_is_reproducible(inputs) -> None:
    a = draw_day(inputs, 0, 50, 1.0, np.random.default_rng(5))
    b = draw_day(inputs, 0, 50, 1.0, np.random.default_rng(5))
    assert a.drivers == b.drivers
    for (arr_a, svc_a), (arr_b, svc_b) in zip(a.background, b.background, strict=True):
        assert np.array_equal(arr_a, arr_b)
        assert np.array_equal(svc_a, svc_b)


def test_draw_day_departures_are_sorted_within_the_day(inputs) -> None:
    day = draw_day(inputs, 0, 100, 1.0, np.random.default_rng(3))
    departs = [d.depart_min for d in day.drivers]
    assert departs == sorted(departs)
    assert departs[0] >= 0 and departs[-1] < 24 * 60


def test_nearest_and_queue_strategies_disagree(inputs) -> None:
    day = quiet_day([AppDriver(60.0, 0, 90.0, 40.0)], inputs)
    assert choose(inputs, day, "nearest")[0].station == 0
    assert choose(inputs, day, "static_queue")[0].station == 1


def test_queue_aware_sees_earlier_bookings(inputs) -> None:
    # Six drivers from the same place a minute apart: static_queue sends them all
    # to the hub; queue_aware watches the hub fill up and moves later drivers on.
    drivers = [AppDriver(60.0 + i, 1, 90.0, 40.0) for i in range(6)]
    day = quiet_day(drivers, inputs)
    static = [c.station for c in choose(inputs, day, "static_queue")]
    aware = [c.station for c in choose(inputs, day, "queue_aware")]
    assert set(static) == {1}
    assert set(aware) != {1}


def test_range_aware_keeps_drivers_within_range(inputs) -> None:
    low_battery = quiet_day([AppDriver(0.0, 0, 8.0, 40.0)], inputs)
    choice = choose(inputs, low_battery, "range_aware")[0]
    assert choice.arrives_with_reserve
    assert choice.station != 2


def test_app_driver_queues_behind_background_driver(inputs) -> None:
    background = [
        (np.array([0.0]), np.array([60.0])),
        (np.array([]), np.array([])),
        (np.array([]), np.array([])),
    ]
    day = Day(drivers=[AppDriver(9.0, 0, 90.0, 20.0)], background=background)
    choices = choose(inputs, day, "nearest")  # the one-charger station, 1 minute away
    outcome = simulate_queues(inputs, day, choices, background_only(inputs, day))
    assert outcome.app_waits.tolist() == [50.0]


def test_app_driver_delays_the_background_driver_behind_them(inputs) -> None:
    background = [
        (np.array([5.0]), np.array([10.0])),
        (np.array([]), np.array([])),
        (np.array([]), np.array([])),
    ]
    day = Day(drivers=[AppDriver(0.0, 0, 90.0, 30.0)], background=background)
    baseline = background_only(inputs, day)
    outcome = simulate_queues(inputs, day, choose(inputs, day, "nearest"), baseline)
    assert baseline[0] == (0.0, 1)
    # The app driver arrives at minute 1 and charges until 31; the background driver arrives at 5.
    assert outcome.background_wait_sum == pytest.approx(26.0)
    assert outcome.background_count == 1


def test_holm_adjustment() -> None:
    assert analyse.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_analysis_runs_end_to_end(tmp_path, monkeypatch) -> None:
    rng = np.random.default_rng(0)
    algorithms = analyse.ALGORITHMS
    rows = [
        {
            "variant": variant,
            "scenario": scenario,
            "replicate": r,
            "algorithm": a,
            "drivers": 10,
            **{metric: float(rng.uniform(1, 5) + i) for metric in analyse.METRICS},
        }
        for variant in analyse.VARIANTS
        for scenario in ("spread", "hotspot")
        for r in range(4)
        for i, a in enumerate(algorithms)
    ]
    pd.DataFrame(rows).to_csv(tmp_path / "replicates.csv", index=False)
    pd.DataFrame([{"algorithm": a, "wait_min": 1.0, "predicted_wait_min": 0.5} for a in algorithms]).to_csv(
        tmp_path / "drivers_baseline.csv.gz", index=False
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"stations": 3, "chargers": 5, "scenarios": ["spread", "hotspot"]})
    )
    monkeypatch.setattr(analyse, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(analyse, "DATA_DIR", tmp_path)

    analyse.main()

    findings = json.loads((tmp_path / "findings.json").read_text())
    assert findings["best_strategy"] == "nearest"  # the synthetic data makes the first algorithm cheapest
    assert set(findings["baseline"]) == set(algorithms)
    assert (tmp_path / "journey_time_by_strategy.png").stat().st_size > 0
    assert (tmp_path / "load_sensitivity.png").stat().st_size > 0
    tests = pd.read_csv(tmp_path / "paired_tests.csv")
    assert len(tests) == 2 * 15
