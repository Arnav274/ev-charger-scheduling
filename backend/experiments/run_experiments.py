import csv
import copy
import random
import time
from pathlib import Path

from sqlalchemy.orm import joinedload

from app.algorithms import DijkstraStrategy, RecommendationContext, STRATEGIES, haversine_km
from app.database import SessionLocal
from app.models import Station
from app.queueing import erlang_c_probability_of_delay, erlang_c_wait_minutes
from app.routing_osrm import route_one_to_many

OUT_DIR = Path(__file__).parent / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ARRIVAL_WINDOW_MIN = 15.0


def jain_fairness(loads: list[int]) -> float:
    if not loads:
        return 0.0
    total = sum(loads)
    if total == 0:
        return 0.0
    denom = len(loads) * sum(v * v for v in loads)
    if denom == 0:
        return 0.0
    return (total * total) / denom


def overlaps(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


def max_overlapping_in_window(
    intervals: list[tuple[float, float]], *, window_start: float, window_end: float
) -> int:
    """
    Maximum number of overlapping intervals during [window_start, window_end).
    """
    if window_end <= window_start:
        return 0
    events: list[tuple[float, int]] = []
    for s, e in intervals:
        if e <= s:
            continue
        if e <= window_start or s >= window_end:
            continue
        s2 = max(s, window_start)
        e2 = min(e, window_end)
        if e2 <= s2:
            continue
        events.append((s2, +1))
        events.append((e2, -1))
    if not events:
        return 0
    # End before start when tied.
    events.sort(key=lambda x: (x[0], x[1]))
    cur = 0
    best = 0
    for _t, d in events:
        cur += d
        if cur > best:
            best = cur
    return best


def count_starts_in_window(intervals: list[tuple[float, float]], *, window_start: float, window_end: float) -> int:
    if window_end <= window_start:
        return 0
    return sum(1 for s, _e in intervals if window_start <= s < window_end)


def flatten_station_intervals(charger_schedules: dict[str, list[tuple[float, float]]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for slots in charger_schedules.values():
        out.extend(slots)
    return out


def seed_background_schedules(
    *,
    stations: list[Station],
    background_reservations_per_station: int = 12,
) -> dict[str, dict[str, list[tuple[float, float]]]]:
    """
    Deterministic background reservations used as shared 'ground truth' so predictive queueing diverges from static.
    Stored as minutes-from-midnight floats in [0, 1440).
    """
    rnd = random.Random(12345)
    schedules: dict[str, dict[str, list[tuple[float, float]]]] = {
        str(s.id): {str(c.id): [] for c in s.chargers} for s in stations
    }
    if not stations:
        return schedules

    # Create a deliberate hotspot on a small subset of stations (higher parallel overlap).
    hotspot_station_ids = [str(s.id) for s in stations[: max(1, min(5, len(stations) // 10))]]

    for s in stations:
        sid = str(s.id)
        is_hotspot = sid in hotspot_station_ids
        n = background_reservations_per_station * (3 if is_hotspot else 1)
        for _ in range(n):
            # Bias hotspot into a narrow time band to increase overlap.
            if is_hotspot:
                start = rnd.uniform(8 * 60, 10 * 60)  # 08:00-10:00
                duration = rnd.uniform(35, 65)
            else:
                start = rnd.uniform(0, 24 * 60)
                duration = rnd.uniform(20, 60)

            # Try to place on any charger (no per-charger overlap).
            try_reserve(
                schedules[sid],
                request_start_min=start,
                duration_min=duration,
            )
    return schedules


def try_reserve(
    charger_schedules: dict[str, list[tuple[float, float]]],
    request_start_min: float,
    duration_min: float,
) -> bool:
    request_end = request_start_min + duration_min
    for charger_id, slots in charger_schedules.items():
        if all(not overlaps(request_start_min, request_end, s0, s1) for s0, s1 in slots):
            slots.append((request_start_min, request_end))
            charger_schedules[charger_id] = slots
            return True
    return False


def run(n_trials: int = 100) -> Path:
    random.seed(42)
    db = SessionLocal()
    try:
        stations = db.query(Station).options(joinedload(Station.chargers)).all()
        if not stations:
            raise RuntimeError("No stations found. Run ingestion first.")

        rows: list[dict] = []
        scenario_configs = {
            "urban": {
                "lat_range": (51.49, 51.53),
                "lon_range": (-0.16, -0.10),
                "duration_range": (30, 50),
            },
            "mixed": {
                "lat_range": (51.48, 51.56),
                "lon_range": (-0.22, -0.05),
                "duration_range": (25, 55),
            },
            "highway": {
                "lat_range": (51.50, 51.53),
                "lon_range": (-0.35, 0.08),
                "duration_range": (20, 45),
            },
        }
        summary_metrics: list[dict] = []
        variants = [
            {"name": "baseline_equal", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 1.0, "top_k": 1, "lambda_multiplier": 1.0},
            {"name": "distance_priority", "weights": (0.7, 0.2, 0.1), "load_multiplier": 1.0, "top_k": 1, "lambda_multiplier": 1.0},
            {"name": "queue_stress", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 1.6, "top_k": 1, "lambda_multiplier": 1.6},
            {"name": "topk_robustness", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 1.0, "top_k": 3, "lambda_multiplier": 1.0},
            # Erlang sensitivity sweep — fixed equal weights, varies arrival-rate multiplier only.
            {"name": "erlang_sensitivity", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 0.5, "top_k": 1, "lambda_multiplier": 0.5},
            {"name": "erlang_sensitivity", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 1.0, "top_k": 1, "lambda_multiplier": 1.0},
            {"name": "erlang_sensitivity", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 1.5, "top_k": 1, "lambda_multiplier": 1.5},
            {"name": "erlang_sensitivity", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 2.0, "top_k": 1, "lambda_multiplier": 2.0},
            {"name": "erlang_sensitivity", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 3.0, "top_k": 1, "lambda_multiplier": 3.0},
        ]

        for variant in variants:
            for scenario, cfg in scenario_configs.items():
                background = seed_background_schedules(stations=stations)
                per_alg_loads = {
                    algorithm: {str(s.id): 0 for s in stations}
                    for algorithm in STRATEGIES
                }
                per_alg_attempts = {algorithm: 0 for algorithm in STRATEGIES}
                per_alg_rejections = {algorithm: 0 for algorithm in STRATEGIES}
                per_alg_schedules = {
                    algorithm: {
                        str(s.id): copy.deepcopy(background[str(s.id)])
                        for s in stations
                    }
                    for algorithm in STRATEGIES
                }

                for _ in range(n_trials):
                    origin_lat = random.uniform(*cfg["lat_range"])
                    origin_lon = random.uniform(*cfg["lon_range"])
                    # Simulate range-stressed EVs: 8–30 % SOC on a 40 kWh battery
                    # gives a safe reach of 6–50 km (at 0.2 kWh/km, 2 kWh buffer).
                    # This ensures RangeAwareStrategy's penalty actually fires for
                    # distant stations in mixed/highway scenarios.
                    battery_capacity_kwh = 40.0
                    battery_level_percent = random.uniform(8.0, 30.0)
                    context = RecommendationContext(
                        origin_lat=origin_lat,
                        origin_lon=origin_lon,
                        weights=variant["weights"],
                        arrival_window_minutes=int(ARRIVAL_WINDOW_MIN),
                        battery_level_percent=battery_level_percent,
                        battery_capacity_kwh=battery_capacity_kwh,
                    )
                    travel_metrics = route_one_to_many(
                        origin_lat=origin_lat,
                        origin_lon=origin_lon,
                        destinations=[(s.lat, s.lon) for s in stations],
                    )
                    if travel_metrics is None:
                        travel_by_station = {
                            str(s.id): (haversine_km(origin_lat, origin_lon, s.lat, s.lon), (haversine_km(origin_lat, origin_lon, s.lat, s.lon) / 25.0) * 60.0)
                            for s in stations
                        }
                    else:
                        travel_by_station = {
                            str(s.id): (m.distance_km, m.duration_min)
                            for s, m in zip(stations, travel_metrics, strict=False)
                        }
                    # attach travel metrics for strategy scoring (road-network distance via OSRM when available)
                    context.travel_by_station = travel_by_station  # type: ignore[attr-defined]

                    max_distance = max(travel_by_station[str(s.id)][0] for s in stations) or 1.0
                    max_wait = max(
                        erlang_c_wait_minutes(
                            s.arrival_rate_per_hour * variant["load_multiplier"],
                            s.mean_service_minutes,
                            max(1, len(s.chargers)),
                        )
                        for s in stations
                    ) or 1.0
                    max_cost = max(s.price_pence_per_kwh for s in stations) or 1.0
                    max_vals = {"distance": max_distance, "wait": max_wait, "cost": max_cost}

                    for algorithm, strategy in STRATEGIES.items():
                        # Build predictive context from the algorithm's current reservation schedule:
                        # a) reserved_parallel in the arrival window (capacity reduction)
                        # b) starts in window (arrival-rate uplift)
                        request_start = random.uniform(0, 24 * 60)
                        future_reserved_parallel_by_station: dict[str, int] = {}
                        future_reservation_starts_by_station: dict[str, int] = {}
                        for s in stations:
                            sid = str(s.id)
                            distance_km, travel_time_min = travel_by_station[sid]
                            arrival_start = request_start + float(travel_time_min)
                            window_start = arrival_start
                            window_end = arrival_start + ARRIVAL_WINDOW_MIN
                            all_intervals = flatten_station_intervals(per_alg_schedules[algorithm][sid])
                            future_reserved_parallel_by_station[sid] = max_overlapping_in_window(
                                all_intervals, window_start=window_start, window_end=window_end
                            )
                            future_reservation_starts_by_station[sid] = count_starts_in_window(
                                all_intervals, window_start=window_start, window_end=window_end
                            )
                        context.future_reserved_parallel_by_station = future_reserved_parallel_by_station  # type: ignore[attr-defined]
                        context.future_reservation_starts_by_station = future_reservation_starts_by_station  # type: ignore[attr-defined]

                        t0 = time.perf_counter()
                        pre_computed_dijkstra: dict[str, float] | None = None
                        if isinstance(strategy, DijkstraStrategy):
                            pre_computed_dijkstra = strategy.rank_all(stations, context)

                        def _score(s: Station, _strategy=strategy, _ctx=context, _mv=max_vals, _pd=pre_computed_dijkstra) -> float:
                            if _pd is not None:
                                return _strategy.score(s, _ctx, _mv, _pd[str(s.id)])
                            return _strategy.score(s, _ctx, _mv)

                        ranked = sorted(stations, key=_score)
                        candidate_pool = ranked[: variant["top_k"]]
                        best = random.choice(candidate_pool)
                        runtime_ms = (time.perf_counter() - t0) * 1000
                        duration = random.uniform(*cfg["duration_range"])
                        accepted = try_reserve(
                            per_alg_schedules[algorithm][str(best.id)],
                            request_start_min=request_start,
                            duration_min=duration,
                        )
                        per_alg_attempts[algorithm] += 1
                        if not accepted:
                            per_alg_rejections[algorithm] += 1
                        per_alg_loads[algorithm][str(best.id)] += 1

                        # Use the same predictive computation that powers `queue_aware` (reservation-aware),
                        # so offline evaluation matches online behavior.
                        sid = str(best.id)
                        reserved_parallel = int(future_reserved_parallel_by_station.get(sid, 0))
                        reservation_starts = int(future_reservation_starts_by_station.get(sid, 0))
                        c = max(1, len(best.chargers))
                        c_eff = max(1, c - reserved_parallel) if algorithm == "queue_aware" else c
                        window_hours = max(1.0, ARRIVAL_WINDOW_MIN) / 60.0
                        lambda_base = best.arrival_rate_per_hour * float(variant["load_multiplier"])
                        lambda_future = (
                            lambda_base + (reservation_starts / window_hours) if algorithm == "queue_aware" else lambda_base
                        )
                        wait_min = erlang_c_wait_minutes(lambda_future, best.mean_service_minutes, c_eff)
                        p_delay = erlang_c_probability_of_delay(
                            arrival_rate_per_hour=lambda_future,
                            service_rate_per_hour=60.0 / best.mean_service_minutes,
                            c=c_eff,
                        )

                        rows.append(
                            {
                                "variant": variant["name"],
                                "scenario": scenario,
                                "algorithm": algorithm,
                                "distance_km": travel_by_station[str(best.id)][0],
                                "wait_min": wait_min,
                                "probability_of_delay": p_delay,
                                "reserved_parallel": reserved_parallel if algorithm == "queue_aware" else 0,
                                "reservation_starts": reservation_starts if algorithm == "queue_aware" else 0,
                                "price_pence_per_kwh": best.price_pence_per_kwh,
                                "runtime_ms": runtime_ms,
                                "reservation_accepted": int(accepted),
                                "load_multiplier": variant["load_multiplier"],
                                "lambda_multiplier": variant["lambda_multiplier"],
                                "top_k_sampled": variant["top_k"],
                                "weights_distance": variant["weights"][0],
                                "weights_wait": variant["weights"][1],
                                "weights_cost": variant["weights"][2],
                                "battery_level_percent": battery_level_percent,
                                "battery_capacity_kwh": battery_capacity_kwh,
                            }
                        )
                for algorithm in STRATEGIES:
                    loads = list(per_alg_loads[algorithm].values())
                    attempts = per_alg_attempts[algorithm]
                    rejection_rate = (per_alg_rejections[algorithm] / attempts) if attempts else 0.0
                    summary_metrics.append(
                        {
                            "variant": variant["name"],
                            "scenario": scenario,
                            "algorithm": algorithm,
                            "fairness_jain": jain_fairness(loads),
                            "reservation_rejection_rate": rejection_rate,
                            "load_multiplier": variant["load_multiplier"],
                            "top_k_sampled": variant["top_k"],
                            "weights_distance": variant["weights"][0],
                            "weights_wait": variant["weights"][1],
                            "weights_cost": variant["weights"][2],
                        }
                    )
    finally:
        db.close()

    out_csv = OUT_DIR / "experiment_results.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary_csv = OUT_DIR / "experiment_summary_metrics.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(summary_metrics[0].keys()))
        writer.writeheader()
        writer.writerows(summary_metrics)
    return out_csv


if __name__ == "__main__":
    path = run(100)
    print(f"Saved: {path}")
