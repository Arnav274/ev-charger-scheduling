# Analysis Notes

- Random seed for experiment generation is fixed at `42` in `run_experiments.py`.
- Scenarios use distinct geographic origin and session-duration ranges (urban/mixed/highway).
- Sensitivity variants include distance-priority weights, load stress multiplier, and top-k robustness sampling.
- Queue instability handling: when `rho >= 1`, `erlang_c_wait_minutes` returns a capped penalty (`1e6`) to represent infeasible congestion under M/M/c assumptions.
- ANOVA effect size is reported via eta-squared in `anova.txt` for the baseline variant.
- Pairwise post-hoc comparisons use Welch t-test with Bonferroni correction and include Cohen's d.
- Plot readability adjustments: boxplot values are capped at baseline p95; Pareto y-axis uses log10(wait).