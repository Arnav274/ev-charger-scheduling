# Experiment design

This document describes how the strategy comparison in the README is produced: the question, the
model, the inputs, the variants and the statistics. The code is in `backend/experiments/`, and every
setting mentioned here lives in `backend/experiments/config.py`.

## Question

Given the same drivers on the same day, which station-selection strategy gets an app user charging
soonest, counting both the drive and the wait? And how do the answers change as the app gets more
users, or as the network gets busier?

## The model

One simulated day is a discrete-event simulation of every station in the study area.

**Stations.** Each station is a first-come, first-served queue with one server per charger. Any
driver can use any free charger at the station.

**Background drivers** stand for everyone who does not use the app. They arrive at every station as
a Poisson process at the station's arrival rate (0.75 an hour by default) and charge for an
exponentially distributed time with a mean of 40 minutes. Those are exactly the M/M/c assumptions
behind Erlang-C. Arrivals start four hours before midnight, so the queues have settled by the time
the first app driver leaves, and run two hours past the end of the day, so late app drivers still
meet a normal queue. Only background drivers arriving during the day are counted in their wait.

**App drivers** set off at uniformly random times through the day from a random origin in the
scenario's pool. Each has a 40 kWh battery at 8 to 30% charge, and a charging time drawn from the
same distribution as everyone else. At departure the driver's strategy ranks the candidate stations,
using the same `rank()` code as the API. The candidates follow the app's rule too: stations within
5 km, or the 25 nearest if there are none. The driver takes the top suggestion (or, in one variant,
any of the top three), drives there taking OSRM's travel time whatever the strategy estimated, and
joins the queue.

**What a strategy knows.** Only what the app would know: each station's charger count, price and
arrival rate, road travel from the origin, and, for `queue_aware`, the bookings made by earlier app
drivers. Each booking is recorded as the interval from arrival until the expected end of charging.
No strategy sees the actual queues.

**Exact waits.** Because no decision depends on anyone's realised wait, all of the day's choices can
be made first. The queues are then worked out exactly, merging app and background arrivals at each
station and serving them in arrival order with a min-heap of charger free times.

**Common random numbers.** A (scenario, day) pair has one seed. Every strategy, and every variant
that keeps the same number of app drivers, sees identical background arrivals and charging times
and identical app drivers. Differences between strategies therefore come from the strategies alone,
and they can be compared day by day.

## Inputs

`experiments/build_inputs.py` freezes everything taken from the live stack into
`experiments/data/`:

- **`stations.json`:** the 497 stations and 751 chargers ingested from OpenChargeMap, which is the
  500 records nearest (51.52, -0.13) with three test or non-operational entries removed. They reach
  about 2.6 km from that point.
- **`travel.npz`:** 200 seeded origins for each scenario and, from each origin to each of its
  candidate stations, the OSRM road distance and time plus the distance and time of our own Dijkstra
  route.
- **`manifest.json`:** what was built, and when.

With these committed, the experiment needs neither the database nor OSRM, and a re-run reproduces
`replicates.csv` and `drivers_baseline.csv.gz` byte for byte.

## Scenarios

All origins lie inside the area the station data covers, so no driver starts beyond its edge.

| Scenario | Origins |
|---|---|
| `spread` | Uniform over a disc of radius 2.2 km around the centre of the study area |
| `corridor` | A band along Euston Road and Marylebone Road |
| `hotspot` | Within 400 m of King's Cross, as after a large event |

## Variants

Each variant runs all three scenarios for 30 days (`REPLICATES`), with all six strategies.

| Variant | Change from baseline |
|---|---|
| `baseline` | 200 app drivers a day, background rate 0.75 an hour, equal cost weights, top suggestion taken |
| `high_demand` | 600 app drivers a day |
| `distance_priority` | `cost_optimized` weights distance 0.7, wait 0.2, price 0.1 |
| `top3_choice` | Drivers take any of the top three suggestions at random |
| `load_0.5x`, `load_1.5x`, `load_2x` | Background arrival rate scaled; strategies are told the true rate |

## Outcomes

Per app driver: road distance, drive time, simulated wait, journey time (drive plus wait), the wait
the strategy predicted, and whether the driver would arrive with the 2 kWh reserve. Per day: the
means of those, the 95th percentile and share of drivers who waited at all, the mean wait of
background drivers (the effect on people outside the app), and how concentrated the app's choices
were.

Journey time is the headline outcome because it is the one a driver feels. A strategy can always
cut the wait by driving further, or cut the drive by accepting a queue.

## Analysis

`experiments/analyse_results.py` treats the simulated day as the unit of analysis, since drivers
on the same day share queues and are not independent.

- **Intervals:** percentile bootstrap (2,000 resamples) of the mean over days.
- **Comparisons:** for the baseline and high-demand variants, every pair of strategies is compared
  on journey time over the 90 (scenario, day) pairs. Each comparison uses a paired t-test and a
  Wilcoxon signed-rank test, with the Wilcoxon p-values Holm-corrected across the 15 pairs.
- **Effect size:** Cohen's d<sub>z</sub>, the mean paired difference divided by its standard
  deviation.
- **Outputs:** `summary_ci.csv`, `comparison_table.md`, `paired_tests.csv`, two charts, and
  `findings.json`, which the app's Results tab renders.

## Validation

- `tests/test_simulation.py` feeds a single station only Poisson arrivals and exponential sessions
  and checks the long-run mean wait against Erlang-C for one, two and four chargers. That pins the
  queue engine and the formula to each other.
- The same tests check that a day is reproducible from its seed, that bookings change
  `queue_aware`'s choices, and that app and background drivers delay one another correctly.
- `docs/road_graph_validation.md` compares our Dijkstra routes with OSRM.

## What the model leaves out

- **Nobody gives up.** Drivers wait as long as it takes, so overloaded stations produce very large
  means. Real drivers would leave the queue.
- **Station differences.** Every station shares one arrival rate, and a session's length does not
  depend on the charger's power.
- **Time of day.** Demand is flat across the day, with no rush hours.
- **Traffic.** Travel times are free-flow.
- **App demand is extra.** App drivers are added on top of background demand rather than replacing
  part of it.
