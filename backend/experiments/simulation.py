"""Discrete-event simulation of one day of charging demand.

Each station is a first-come-first-served queue with one server per charger.
Two kinds of driver arrive:

* background drivers, who turn up at every station as a Poisson process at the
  station's arrival rate and never use the app;
* app drivers, who set off from a scenario origin at a random time of day,
  ask a strategy where to charge, drive there (taking OSRM's travel time),
  and join the queue.

The strategy sees what the app would really know: station parameters, road
travel from the origin, and, for queue_aware, the bookings made by earlier app
drivers. It never sees the queues themselves. Because no decision depends on
how long anyone actually waited, every choice can be made first and the queues
worked out afterwards, which gives the exact FCFS waits.

Every strategy is run against the same day: the same background arrivals and
charging times, and the same app drivers with the same origins, departure times
and batteries (common random numbers), so strategies can be compared pairwise.
"""

from __future__ import annotations

import heapq
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from app.algorithms import (
    STRATEGIES,
    DijkstraStrategy,
    RangeAwareStrategy,
    RecommendationContext,
    StationInfo,
    Travel,
)
from app.predictive_queueing import ReservationInterval, booked_during_arrival
from experiments.config import (
    ARRIVAL_WINDOW_MINUTES,
    BATTERY_CAPACITY_KWH,
    BATTERY_PERCENT_RANGE,
    DAY_MINUTES,
    WARM_UP_MINUTES,
)

# Background drivers keep arriving after midnight so late app drivers still meet a normal queue.
COOL_DOWN_MINUTES = 2 * 60
# Minute offsets are turned into timestamps so the production lookahead code can be reused.
EPOCH = datetime(2030, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Inputs:
    stations: list[StationInfo]
    origins: np.ndarray  # (n_origins, 2) lat, lon
    scenario: np.ndarray  # scenario index of each origin
    osrm_km: np.ndarray  # (n_origins, n_stations); NaN where a station is not a candidate
    osrm_min: np.ndarray
    dijkstra_km: np.ndarray
    dijkstra_min: np.ndarray

    @classmethod
    def load(cls, data_dir: Path) -> Inputs:
        raw = json.loads((data_dir / "stations.json").read_text(encoding="utf-8"))
        stations = [StationInfo(**s) for s in raw]
        with np.load(data_dir / "travel.npz") as travel:
            return cls(stations=stations, **{key: travel[key] for key in travel.files})

    def origins_in(self, scenario_index: int) -> np.ndarray:
        return np.flatnonzero(self.scenario == scenario_index)

    def candidates(self, origin: int) -> np.ndarray:
        return np.flatnonzero(np.isfinite(self.osrm_km[origin]))


@dataclass(frozen=True)
class AppDriver:
    depart_min: float
    origin: int
    battery_percent: float
    service_min: float


@dataclass(frozen=True)
class Day:
    drivers: list[AppDriver]
    # Per station: background arrival times and charging durations, in minutes from midnight.
    background: list[tuple[np.ndarray, np.ndarray]]


def draw_day(
    inputs: Inputs,
    scenario_index: int,
    drivers_per_day: int,
    load_multiplier: float,
    rng: np.random.Generator,
) -> Day:
    start, end = -WARM_UP_MINUTES, DAY_MINUTES + COOL_DOWN_MINUTES
    background = []
    for s in inputs.stations:
        rate_per_min = s.arrival_rate_per_hour * load_multiplier / 60
        count = rng.poisson(rate_per_min * (end - start))
        arrivals = np.sort(rng.uniform(start, end, count))
        background.append((arrivals, rng.exponential(s.mean_service_minutes, count)))

    pool = inputs.origins_in(scenario_index)
    mean_service = float(np.mean([s.mean_service_minutes for s in inputs.stations]))
    departs = np.sort(rng.uniform(0, DAY_MINUTES, drivers_per_day))
    drivers = [
        AppDriver(
            depart_min=float(depart),
            origin=int(rng.choice(pool)),
            battery_percent=float(rng.uniform(*BATTERY_PERCENT_RANGE)),
            service_min=float(rng.exponential(mean_service)),
        )
        for depart in departs
    ]
    return Day(drivers=drivers, background=background)


@dataclass(frozen=True)
class Choice:
    station: int
    distance_km: float
    drive_min: float
    predicted_wait_min: float
    arrives_with_reserve: bool


def _timestamp(minutes: float) -> datetime:
    return EPOCH + timedelta(minutes=minutes)


def choose_stations(
    inputs: Inputs,
    day: Day,
    algorithm: str,
    *,
    weights: tuple[float, float, float],
    top_k: int,
    load_multiplier: float,
    rng: np.random.Generator,
) -> list[Choice]:
    """Run every app driver of the day through one strategy, in departure order."""
    index_of = {s.id: i for i, s in enumerate(inputs.stations)}
    # Bookings made through the app so far, per station, as (arrival, expected departure).
    bookings: dict[int, list[ReservationInterval]] = {}
    range_check = RangeAwareStrategy()
    window = timedelta(minutes=ARRIVAL_WINDOW_MINUTES)
    shared_strategy = STRATEGIES[algorithm]
    choices = []

    for driver in day.drivers:
        o = driver.origin
        candidates = inputs.candidates(o)
        stations = [inputs.stations[i] for i in candidates]
        travel = {
            inputs.stations[i].id: Travel(float(inputs.osrm_km[o, i]), float(inputs.osrm_min[o, i]))
            for i in candidates
        }

        reserved = {}
        if shared_strategy.uses_reservations:
            for i in candidates:
                if i in bookings:
                    arrive_at = _timestamp(driver.depart_min + float(inputs.osrm_min[o, i]))
                    reserved[inputs.stations[i].id] = booked_during_arrival(bookings[i], arrive_at, window)

        ctx = RecommendationContext(
            origin_lat=float(inputs.origins[o, 0]),
            origin_lon=float(inputs.origins[o, 1]),
            travel=travel,
            reserved_by_station=reserved,
            weights=weights,
            battery_level_percent=driver.battery_percent,
            battery_capacity_kwh=BATTERY_CAPACITY_KWH,
            arrival_rate_scale=load_multiplier,
        )
        if algorithm == "dijkstra":
            routes = {
                inputs.stations[i].id: Travel(
                    float(inputs.dijkstra_km[o, i]), float(inputs.dijkstra_min[o, i])
                )
                if np.isfinite(inputs.dijkstra_min[o, i])
                else None
                for i in candidates
            }
            strategy = DijkstraStrategy(router=lambda _lat, _lon, _stations, routes=routes: routes)
        else:
            strategy = shared_strategy

        # Dijkstra can, very rarely, fail to reach any candidate; that driver falls back to the nearest.
        ranked = strategy.rank(stations, ctx) or STRATEGIES["nearest"].rank(stations, ctx)
        pick = ranked[int(rng.integers(min(top_k, len(ranked))))] if top_k > 1 else ranked[0]
        station = index_of[pick.station.id]
        # Everyone drives the real (OSRM) route, whatever the strategy estimated.
        drive_min = float(inputs.osrm_min[o, station])
        arrive = driver.depart_min + drive_min
        bookings.setdefault(station, []).append(
            ReservationInterval(_timestamp(arrive), _timestamp(arrive + pick.station.mean_service_minutes))
        )
        choices.append(
            Choice(
                station=station,
                distance_km=float(inputs.osrm_km[o, station]),
                drive_min=drive_min,
                predicted_wait_min=pick.prediction.wait_min,
                arrives_with_reserve=range_check.reachable(pick.station, ctx),
            )
        )
    return choices


def fcfs_waits(arrivals: np.ndarray, services: np.ndarray, servers: int) -> np.ndarray:
    """Exact waits in a first-come-first-served queue with `servers` identical servers.

    A min-heap holds the time each server next becomes free; each arrival takes
    the earliest free server. `arrivals` must be sorted.
    """
    free_at = [-np.inf] * servers
    waits = np.empty(len(arrivals))
    for k, (arrive, service) in enumerate(zip(arrivals.tolist(), services.tolist(), strict=True)):
        start = max(arrive, heapq.heappop(free_at))
        waits[k] = start - arrive
        heapq.heappush(free_at, start + service)
    return waits


@dataclass(frozen=True)
class QueueOutcome:
    app_waits: np.ndarray  # wait of each app driver, in the order of day.drivers
    background_wait_sum: float  # over background drivers arriving between midnight and midnight
    background_count: int


def background_only(inputs: Inputs, day: Day) -> list[tuple[float, int]]:
    """Per station, (sum of waits, number of drivers) for background drivers arriving during the day."""
    totals = []
    for s, (arrivals, services) in zip(inputs.stations, day.background, strict=True):
        waits = fcfs_waits(arrivals, services, s.chargers)
        in_day = (arrivals >= 0) & (arrivals < DAY_MINUTES)
        totals.append((float(waits[in_day].sum()), int(in_day.sum())))
    return totals


def simulate_queues(
    inputs: Inputs, day: Day, choices: list[Choice], baseline: list[tuple[float, int]]
) -> QueueOutcome:
    """Merge app drivers into the background queues and measure everyone's wait.

    Stations no app driver visited are unchanged, so their background totals
    are reused from `baseline` rather than simulated again.
    """
    visitors: dict[int, list[int]] = {}
    for d, choice in enumerate(choices):
        visitors.setdefault(choice.station, []).append(d)

    app_waits = np.zeros(len(choices))
    bg_sum = sum(total for total, _ in baseline)
    bg_count = sum(count for _, count in baseline)
    for station, drivers in visitors.items():
        bg_arrivals, bg_services = day.background[station]
        app_arrivals = np.array([day.drivers[d].depart_min + choices[d].drive_min for d in drivers])
        app_services = np.array([day.drivers[d].service_min for d in drivers])

        arrivals = np.concatenate([bg_arrivals, app_arrivals])
        services = np.concatenate([bg_services, app_services])
        # -1 marks a background driver; otherwise the index of the app driver.
        who = np.concatenate([np.full(len(bg_arrivals), -1), np.array(drivers)])
        order = np.argsort(arrivals, kind="stable")
        waits = fcfs_waits(arrivals[order], services[order], inputs.stations[station].chargers)

        who, arrivals = who[order], arrivals[order]
        app = who >= 0
        app_waits[who[app]] = waits[app]
        in_day = ~app & (arrivals >= 0) & (arrivals < DAY_MINUTES)
        bg_sum += float(waits[in_day].sum()) - baseline[station][0]

    return QueueOutcome(app_waits=app_waits, background_wait_sum=bg_sum, background_count=bg_count)
