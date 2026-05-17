# Model Parameter Justification

This document justifies the three numeric constants defined in `backend/app/config.py`
that parameterise the queuing model and range-aware strategy. Each entry records the
empirical source, the value adopted, and the sensitivity range exercised in experiments.

---

## 1. `ARRIVAL_RATE_PER_HOUR_DEFAULT = 0.75`

**Meaning:** Expected number of EV arrivals per charging point per hour under baseline
conditions. Used to initialise `Station.arrival_rate_per_hour` during database seeding
and as the λ input to Erlang-C wait-time calculations.

**Stability rationale:**

With `MEAN_SERVICE_MINUTES_DEFAULT = 40`, the per-charger service rate is
μ = 60 / 40 = **1.5 sessions/hr**. The M/M/c stability condition requires
λ < c · μ. The following derivation assumes a representative single-charger
station (c = 1); stations with multiple chargers have proportionally lower
utilisation, ρ = λ/(c·μ). For c = 1, λ must be strictly below 1.5/hr.
Setting λ = 0.75 gives a utilisation ratio of:

> ρ = λ / (c · μ) = 0.75 / 1.5 = **0.50**

A value of ρ = 0.5 represents a moderately loaded system — chargers are busy half the
time on average — and yields finite, meaningful Erlang-C wait times rather than the
saturation penalty returned when ρ ≥ 1.

**Empirical source:**

> Hecht, C., Figgener, J., & Sauer, D.U. (2022). Analysis of electric vehicle charging
> station usage and profitability in Germany based on empirical data. *iScience*, *25*(12),
> 105634. https://doi.org/10.1016/j.isci.2022.105634

This study analysed 22,200 public charging stations across Germany and reported that most
AC charging stations operate well below full capacity, with many stations seeing fewer than
1 session per hour during off-peak periods. The figure of 0.75 arrivals/hour is consistent
with a typical urban AC charge point under moderate demand — below the empirical peak but
above the near-idle off-peak rate, making it a representative baseline for algorithm
comparison. UK public EVSE utilisation data compiled by Zapmap for the Department for Transport
confirms that average sessions per point per day remain well below saturation for most
of the network (Department for Transport, 2026; Zapmap, 2026), confirming that 0.75/hr
is a realistic busy-hour figure rather than an unreachable extreme.

> Department for Transport. (2026). *Electric vehicle public charging infrastructure
> statistics*. GOV.UK.
> https://www.gov.uk/government/collections/electric-vehicle-charging-infrastructure-statistics

> Zapmap. (2026). *EV charging statistics 2026*.
> https://www.zapmap.com/ev-stats/how-many-charging-points [Accessed: May 2026]
**Sensitivity tested in experiments (`run_experiments.py`):**

| Variant | `load_multiplier` | Effective λ (arrivals/hr) | ρ (c = 1) | Queue state |
|---|---|---|---|---|
| `baseline_equal`, `distance_priority`, `topk_robustness` | 1.0 | 0.75 | 0.50 | Stable — baseline |
| `queue_stress` | 1.6 | 1.20 | 0.80 | Stable — peak demand |
| `erlang_sensitivity` × 0.5 | 0.5 | 0.375 | 0.25 | Stable — light load |
| `erlang_sensitivity` × 1.0 | 1.0 | 0.75 | 0.50 | Stable — baseline |
| `erlang_sensitivity` × 1.5 | 1.5 | 1.125 | 0.75 | Stable — moderate load |
| `erlang_sensitivity` × 2.0 | 2.0 | 1.50 | 1.00 | Boundary — saturation onset |
| `erlang_sensitivity` × 3.0 | 3.0 | 2.25 | 1.50 | Unstable — penalty region |

The `queue_stress` variant (λ = 1.2/hr, ρ = 0.8) models congested peak demand while
remaining stable, allowing the Erlang-C model to produce finite wait predictions.
Erlang-C wait times increase non-linearly as ρ → 1; results in the analysis show that
`queue_aware` reduces mean wait by the largest margin precisely under the `queue_stress`
condition, validating the strategy's reservation-lookahead mechanism. The
`erlang_sensitivity` sweep spans sub-baseline through saturation (ρ = 0.25 to 1.50) to
characterise Erlang-C behaviour across the full stability range; only the ×2.0 and ×3.0
variants push into or beyond the saturation boundary and are excluded from the main
algorithm comparison table.

**Caveats:** Arrival rates vary substantially by charger type (AC vs DC), location
(motorway services vs urban street), time of day, and national fleet penetration rate.
The chosen value is an urban AC default; production deployments should calibrate per-station
λ from operator telemetry.

---

## 2. `MEAN_SERVICE_MINUTES_DEFAULT = 40.0`

**Meaning:** Mean duration of a single charging session (μ⁻¹ in Erlang-C notation).
Used in `erlang_c_wait_minutes` and `erlang_c_probability_of_delay`.

**Source:**

> U.S. Department of Energy, Office of Energy Efficiency and Renewable Energy (EERE).
> (2023, December 4). *FOTW #1319: EV Charging at Paid DC Fast Charging Stations Average
> 42 Minutes per Session*. Energetics / EVWATTS Dashboard, 2.4 million charging sessions,
> June 2020 – June 2023.
> https://www.energy.gov/eere/vehicles/articles/fotw-1319-december-4-2023-ev-charging-paid-dc-fast-charging-stations-average
> [Accessed: January 2026]
The DoE dataset of 2.4 million sessions found a mean of **42 minutes** for paid DC fast
charging. Level 2 AC sessions have longer *connection* times (drivers leave vehicles
plugged in after charging completes), but empirical *active charging* durations for 7–22 kW
AC chargers in European urban settings are broadly consistent with the 40-minute figure
adopted here. Wolbertus et al. (2018) (*Energy Policy*, 104, 61–68) report median
connection times of 1–3 hours for Dutch workplace chargers but note median *charging*
durations closer to 40–60 minutes for public street chargers. The value of 40 minutes is
therefore a conservative lower bound on session duration, which makes the Erlang-C model
slightly optimistic about capacity (shorter sessions free chargers faster), providing a
safety margin in wait predictions.

**Sensitivity tested in experiments:**

Background reservations are seeded with uniformly distributed session durations:

| Reservation type | Duration range (min) |
|---|---|
| Normal stations | U(20, 60) |
| Hotspot stations | U(35, 65) |
| Simulated EV requests — urban scenario | U(30, 50) |
| Simulated EV requests — mixed scenario | U(25, 55) |
| Simulated EV requests — highway scenario | U(20, 45) |

The Erlang-C model is evaluated at the fixed default μ = 1/40 min⁻¹ for scoring; the
random session draws affect only the reservation-slot blocking logic used to test
rejection rates and Jain fairness.

**Caveats:** Session duration distributions are right-skewed in practice (a small proportion
of sessions are very long). A single-server exponential service assumption (Erlang-C) does
not capture this tail. For stations with mixed fast/slow charger fleets the effective mean
should be computed as a weighted harmonic mean of per-charger service rates.

---

## 3. `ENERGY_CONSUMPTION_KWH_PER_KM = 0.2`

**Meaning:** Standard per-kilometre energy consumption estimate for a battery electric
vehicle. Used in `RangeAwareStrategy` to compute estimated consumption along the route and
determine whether a station is safely reachable from the EV's current state of charge.

**Source:**

> Weiss, M., Winbush, T., Newman, A., & Helmers, E. (2024). Energy Consumption of Electric
> Vehicles in Europe. *Sustainability*, *16*(17), 7529.
> https://doi.org/10.3390/su16177529

Analysis of 342 fully electric car models sold in the Netherlands, Germany, and the UK
(autumn 2023 – summer 2024) found:

- **Certified consumption (WLTP):** 19 ± 4 kWh/100 km
- **Real-world consumption:** 21 ± 4 kWh/100 km

The value 0.20 kWh/km (= 20 kWh/100 km) falls between the certified and real-world
averages and rounds cleanly, making it an appropriate conservative estimate for a
scheduling system. Each additional 100 kg of vehicle mass adds approximately 0.2 kWh/100 km;
each additional 0.1 m² of frontal area adds approximately 0.9 kWh/100 km, so heavier SUVs
and vans will exceed this figure.

**Sensitivity tested in experiments:**

`ENERGY_CONSUMPTION_KWH_PER_KM` is used only in `RangeAwareStrategy`, which was added
after the main experiment batch. The constant has **not yet been varied** in a systematic
sensitivity sweep. A planned extension would repeat the recommendation experiment with
consumption values of 0.15, 0.20, and 0.25 kWh/km to quantify how the penalty threshold
(2 kWh safety buffer) interacts with range anxiety at different vehicle efficiency levels.

**Caveats:** Real-world consumption varies substantially with driving speed (motorway vs
urban), ambient temperature (battery efficiency drops ~20 % at 0 °C), and auxiliary load
(heating, air-conditioning). The 0.20 kWh/km figure is appropriate for mixed urban/suburban
driving in temperate conditions; applications in cold climates or for highway routing should
use a higher value (0.25–0.30 kWh/km).

---

## Summary table

| Constant | Value | Primary source | Sensitivity range exercised |
|---|---|---|---|
| `ARRIVAL_RATE_PER_HOUR_DEFAULT` | 0.75 arr/hr | Hecht et al. (2022) iScience | 0.375–2.25 (×0.5 to ×3.0 load multipliers; ρ 0.25→1.5) |
| `MEAN_SERVICE_MINUTES_DEFAULT` | 40 min | DoE EERE FOTW #1319 (2023) | 20–65 min (uniform draw in seeding) |
| `ENERGY_CONSUMPTION_KWH_PER_KM` | 0.2 kWh/km | Weiss et al. (2024) Sustainability | Not yet varied — planned future work |
