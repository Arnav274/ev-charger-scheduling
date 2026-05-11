import csv
import random
import time
from pathlib import Path

from sqlalchemy.orm import joinedload

from app.algorithms import RecommendationContext, STRATEGIES, haversine_km
from app.database import SessionLocal
from app.models import Station
from app.queueing import erlang_c_wait_minutes

OUT_DIR = Path(__file__).parent / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)


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
            {"name": "baseline_equal", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 1.0, "top_k": 1},
            {"name": "distance_priority", "weights": (0.7, 0.2, 0.1), "load_multiplier": 1.0, "top_k": 1},
            {"name": "queue_stress", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 1.6, "top_k": 1},
            {"name": "topk_robustness", "weights": (1 / 3, 1 / 3, 1 / 3), "load_multiplier": 1.0, "top_k": 3},
        ]

        for variant in variants:
            for scenario, cfg in scenario_configs.items():
                per_alg_loads = {
                    algorithm: {str(s.id): 0 for s in stations}
                    for algorithm in STRATEGIES
                }
                per_alg_attempts = {algorithm: 0 for algorithm in STRATEGIES}
                per_alg_rejections = {algorithm: 0 for algorithm in STRATEGIES}
                per_alg_schedules = {
                    algorithm: {
                        str(s.id): {str(c.id): [] for c in s.chargers}
                        for s in stations
                    }
                    for algorithm in STRATEGIES
                }

                for _ in range(n_trials):
                    origin_lat = random.uniform(*cfg["lat_range"])
                    origin_lon = random.uniform(*cfg["lon_range"])
                    context = RecommendationContext(
                        origin_lat=origin_lat,
                        origin_lon=origin_lon,
                        weights=variant["weights"],
                    )
                    max_distance = max(haversine_km(origin_lat, origin_lon, s.lat, s.lon) for s in stations) or 1.0
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
                        t0 = time.perf_counter()
                        ranked = sorted(stations, key=lambda s: strategy.score(s, context, max_vals))
                        candidate_pool = ranked[: variant["top_k"]]
                        best = random.choice(candidate_pool)
                        runtime_ms = (time.perf_counter() - t0) * 1000
                        request_start = random.uniform(0, 24 * 60)
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
                        rows.append(
                            {
                                "variant": variant["name"],
                                "scenario": scenario,
                                "algorithm": algorithm,
                                "distance_km": haversine_km(origin_lat, origin_lon, best.lat, best.lon),
                                "wait_min": erlang_c_wait_minutes(
                                    best.arrival_rate_per_hour * variant["load_multiplier"],
                                    best.mean_service_minutes,
                                    max(1, len(best.chargers)),
                                ),
                                "price_pence_per_kwh": best.price_pence_per_kwh,
                                "runtime_ms": runtime_ms,
                                "reservation_accepted": int(accepted),
                                "load_multiplier": variant["load_multiplier"],
                                "top_k_sampled": variant["top_k"],
                                "weights_distance": variant["weights"][0],
                                "weights_wait": variant["weights"][1],
                                "weights_cost": variant["weights"][2],
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
