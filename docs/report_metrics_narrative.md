## Recommendation metrics narrative (for report)

### What the system optimises
The recommendation endpoint returns, per station:
- `travel_time_min`, `travel_distance_km` (road-network via OSRM)
- `predicted_wait_min` (Erlang‑C expected queueing delay)
- `probability_of_delay` = \(P(W_q>0)\) (Erlang‑C probability of waiting at all)

This enables a user-facing decision that is not purely “shortest drive”.

### Why `probability_of_delay` is useful (not just academic)
`predicted_wait_min` is a mean; it can be dominated by rare long waits, and two stations can have similar means but different risk profiles.

`probability_of_delay` answers a simpler question: **will I likely have to wait at all?**

In the EV-charging context, many users are risk-averse (range anxiety / time constraints). A station with:
- slightly longer travel time, but
- near-zero \(P(W_q>0)\)

can be preferable to a closer station with a non-trivial chance of waiting, even if mean waits are similar.

### How predictive queueing changes the inputs
Baselines:
- **Nearest**: choose minimal road-network distance/time.
- **Static queue baseline (`static_queue`)**: Erlang‑C uses only station-level parameters:
  - arrival rate \(\lambda\) (arrivals/hour)
  - mean service time \(S\) (minutes)
  - number of chargers \(c\)

Predictive algorithm:
- **Reservation-aware (`queue_aware`)**: for the user’s estimated arrival window \([t_a, t_a+\Delta]\), query reservations overlapping that window and derive:
  - **effective capacity** \(c_{eff}=\max(1, c - r_{parallel})\)
  - **future arrival uplift** \(\lambda_{future}=\lambda + \frac{r_{starts}}{\Delta_{hours}}\)

Then compute:
- \(P(W_q>0)\) and \(E[W_q]\) using Erlang‑C with \((\lambda_{future}, c_{eff}, S)\).

### Evaluation interpretation (what you can claim safely)
The project’s evaluation is **simulation-based** and “model-driven”:
- OSRM provides realistic travel times/distances.
- Erlang‑C provides a queueing-theoretic estimate of waiting under M/M/c assumptions.
- Reservations provide “known future load” during the arrival window.

Therefore, the correct claim is that the predictive algorithm **reduces predicted waiting and hotspot intensity under the model**, not that it perfectly predicts real-world queues.

### What to report in results/discussion
For each algorithm (nearest vs static vs predictive), report:
- Mean/CI of `wait_min` (from experiments output)
- ANOVA + effect sizes (eta-squared) and pairwise Cohen’s d
- Mean/CI of `probability_of_delay` (risk metric) and (optionally) ANOVA on it

Then interpret with a concrete trade-off example:
- “A 5-minute longer drive reduced \(P(W_q>0)\) from 0.10 to ~0.00 in the hotspot scenario, demonstrating hotspot avoidance.”

