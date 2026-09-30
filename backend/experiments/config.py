"""Everything that defines the experiment, in one place."""

from pathlib import Path

EXPERIMENTS_DIR = Path(__file__).resolve().parent
DATA_DIR = EXPERIMENTS_DIR / "data"
OUTPUT_DIR = EXPERIMENTS_DIR / "outputs"

SEED = 42

# The station data is the 497 stations nearest (51.52, -0.13), which reach
# about 2.6 km from that point. Every origin is drawn inside that area so no
# driver starts beyond the edge of the data. The scenarios vary the shape of
# demand: spread evenly, strung along a main road, or packed around one place.
STUDY_CENTRE = (51.52, -0.13)
SCENARIOS = {
    "spread": {"centre": STUDY_CENTRE, "radius_km": 2.2},
    # Euston Road and Marylebone Road, a busy east-west corridor.
    "corridor": {"lat_range": (51.522, 51.530), "lon_range": (-0.160, -0.100)},
    # Everyone within 400 m of King's Cross, as after a large event.
    "hotspot": {"centre": (51.5308, -0.1238), "radius_km": 0.4},
}
ORIGINS_PER_SCENARIO = 200

REPLICATES = 30  # simulated days per variant and scenario
DAY_MINUTES = 24 * 60
# Background arrivals start this long before midnight so the stations are
# already at steady state when the first app driver sets off.
WARM_UP_MINUTES = 4 * 60
ARRIVAL_WINDOW_MINUTES = 15  # the app's default lookahead window
BATTERY_CAPACITY_KWH = 40.0
BATTERY_PERCENT_RANGE = (8.0, 30.0)  # drivers looking for a charger are running low

BASELINE = {"drivers_per_day": 200, "load_multiplier": 1.0, "weights": (1 / 3, 1 / 3, 1 / 3), "top_k": 1}
VARIANTS = {
    "baseline": BASELINE,
    # Three times as many app users, so their own choices start to crowd stations.
    "high_demand": {**BASELINE, "drivers_per_day": 600},
    # cost_optimized cares mostly about distance.
    "distance_priority": {**BASELINE, "weights": (0.7, 0.2, 0.1)},
    # Drivers take one of the top three suggestions at random rather than the first.
    "top3_choice": {**BASELINE, "top_k": 3},
    # Background arrival rate scaled against the 0.75 per hour default.
    "load_0.5x": {**BASELINE, "load_multiplier": 0.5},
    "load_1.5x": {**BASELINE, "load_multiplier": 1.5},
    "load_2x": {**BASELINE, "load_multiplier": 2.0},
}

ALGORITHMS = ["nearest", "dijkstra", "cost_optimized", "static_queue", "queue_aware", "range_aware"]
