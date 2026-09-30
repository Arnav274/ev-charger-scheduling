"""Run every strategy through the simulated days and save the results.

    docker compose exec backend python -m experiments.run_experiments

Needs only experiments/data (committed), not the database or OSRM. Output is
deterministic: the same inputs and seed give byte-identical files.

Writes to experiments/outputs:
    replicates.csv          one row per variant, scenario, simulated day and algorithm
    drivers_baseline.csv.gz one row per app driver in the baseline variant
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import product

import numpy as np

from experiments.config import (
    ALGORITHMS,
    DATA_DIR,
    OUTPUT_DIR,
    REPLICATES,
    SCENARIOS,
    SEED,
    VARIANTS,
)
from experiments.simulation import Inputs, background_only, choose_stations, draw_day, simulate_queues

_inputs: Inputs | None = None


def _worker_init() -> None:
    global _inputs
    _inputs = Inputs.load(DATA_DIR)


def day_seed(scenario_index: int, replicate: int, stream: int = 0) -> np.random.Generator:
    # The same (scenario, day) seed is used under every variant and every
    # algorithm, so comparisons between them are paired.
    return np.random.default_rng(np.random.SeedSequence([SEED, scenario_index, replicate, stream]))


def run_cell(variant_name: str, scenario_index: int, replicates: int) -> tuple[list[dict], list[dict]]:
    inputs = _inputs
    variant = VARIANTS[variant_name]
    scenario = list(SCENARIOS)[scenario_index]
    summaries, drivers = [], []

    for replicate in range(replicates):
        day = draw_day(
            inputs,
            scenario_index,
            variant["drivers_per_day"],
            variant["load_multiplier"],
            day_seed(scenario_index, replicate),
        )
        baseline = background_only(inputs, day)
        for a, algorithm in enumerate(ALGORITHMS):
            choices = choose_stations(
                inputs,
                day,
                algorithm,
                weights=variant["weights"],
                top_k=variant["top_k"],
                load_multiplier=variant["load_multiplier"],
                rng=day_seed(scenario_index, replicate, stream=1 + a),
            )
            outcome = simulate_queues(inputs, day, choices, baseline)
            waits = outcome.app_waits
            drive = np.array([c.drive_min for c in choices])
            stations_used = np.bincount([c.station for c in choices])
            summaries.append(
                {
                    "variant": variant_name,
                    "scenario": scenario,
                    "replicate": replicate,
                    "algorithm": algorithm,
                    "drivers": len(choices),
                    "journey_min": float(np.mean(drive + waits)),
                    "wait_min": float(np.mean(waits)),
                    "p95_wait_min": float(np.percentile(waits, 95)),
                    "share_waited": float(np.mean(waits > 0)),
                    "distance_km": float(np.mean([c.distance_km for c in choices])),
                    "drive_min": float(np.mean(drive)),
                    "predicted_wait_min": float(np.mean([c.predicted_wait_min for c in choices])),
                    "share_with_reserve": float(np.mean([c.arrives_with_reserve for c in choices])),
                    "background_wait_min": outcome.background_wait_sum / outcome.background_count,
                    "stations_used": int(np.count_nonzero(stations_used)),
                    "busiest_station_share": float(stations_used.max() / len(choices)),
                }
            )
            if variant_name == "baseline":
                drivers += [
                    {
                        "scenario": scenario,
                        "replicate": replicate,
                        "algorithm": algorithm,
                        "driver": d,
                        "chargers": inputs.stations[c.station].chargers,
                        "distance_km": c.distance_km,
                        "drive_min": c.drive_min,
                        "wait_min": float(waits[d]),
                        "predicted_wait_min": c.predicted_wait_min,
                    }
                    for d, c in enumerate(choices)
                ]
    return summaries, drivers


def _csv_text(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: round(v, 6) if isinstance(v, float) else v for k, v in row.items()})
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the scheduling experiment.")
    parser.add_argument("--replicates", type=int, default=REPLICATES, help="simulated days per cell")
    args = parser.parse_args()

    started = time.perf_counter()
    cells = list(product(VARIANTS, range(len(SCENARIOS)), [args.replicates]))
    with ProcessPoolExecutor(initializer=_worker_init) as pool:
        results = list(pool.map(run_cell, *zip(*cells, strict=True)))

    summaries = [row for cell_rows, _ in results for row in cell_rows]
    drivers = [row for _, cell_drivers in results for row in cell_drivers]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "replicates.csv").write_text(_csv_text(summaries), encoding="utf-8")
    # mtime=0 keeps the gzip header, and so the file, identical between runs.
    with (
        open(OUTPUT_DIR / "drivers_baseline.csv.gz", "wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz,
    ):
        gz.write(_csv_text(drivers).encode("utf-8"))

    print(
        f"{len(summaries)} simulated days x algorithms across {len(VARIANTS)} variants and "
        f"{len(SCENARIOS)} scenarios in {time.perf_counter() - started:.0f}s."
    )


if __name__ == "__main__":
    main()
