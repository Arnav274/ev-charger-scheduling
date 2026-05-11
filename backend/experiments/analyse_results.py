from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

OUT_DIR = Path(__file__).parent / "outputs"


def bootstrap_ci(series: pd.Series, n_boot: int = 1000, alpha: float = 0.05) -> tuple[float, float]:
    samples = [series.sample(frac=1.0, replace=True).mean() for _ in range(n_boot)]
    lower = pd.Series(samples).quantile(alpha / 2)
    upper = pd.Series(samples).quantile(1 - alpha / 2)
    return float(lower), float(upper)


def main() -> None:
    df = pd.read_csv(OUT_DIR / "experiment_results.csv")
    metrics_path = OUT_DIR / "experiment_summary_metrics.csv"
    metrics_df = pd.read_csv(metrics_path) if metrics_path.exists() else None

    summary_rows = []
    for (variant, scenario, algorithm), group in df.groupby(["variant", "scenario", "algorithm"]):
        d_ci = bootstrap_ci(group["distance_km"])
        w_ci = bootstrap_ci(group["wait_min"])
        summary_rows.append(
            {
                "variant": variant,
                "scenario": scenario,
                "algorithm": algorithm,
                "distance_mean": group["distance_km"].mean(),
                "distance_ci_low": d_ci[0],
                "distance_ci_high": d_ci[1],
                "wait_mean": group["wait_min"].mean(),
                "wait_ci_low": w_ci[0],
                "wait_ci_high": w_ci[1],
                "runtime_ms_mean": group["runtime_ms"].mean(),
                "reservation_accept_rate": group["reservation_accepted"].mean(),
            }
        )
    summary_df = pd.DataFrame(summary_rows)
    if metrics_df is not None:
        summary_df = summary_df.merge(metrics_df, on=["variant", "scenario", "algorithm"], how="left")
    summary_df.to_csv(OUT_DIR / "summary_ci.csv", index=False)

    baseline_df = df[df["variant"] == "baseline_equal"]
    wait_groups = [g["wait_min"].values for _, g in baseline_df.groupby("algorithm")]
    f_stat, p_value = stats.f_oneway(*wait_groups)
    grand_mean = baseline_df["wait_min"].mean()
    ss_between = sum(
        len(group) * ((group.mean() - grand_mean) ** 2)
        for _, group in baseline_df.groupby("algorithm")["wait_min"]
    )
    ss_total = ((baseline_df["wait_min"] - grand_mean) ** 2).sum()
    eta_squared = float(ss_between / ss_total) if ss_total else 0.0
    (OUT_DIR / "anova.txt").write_text(
        f"One-way ANOVA wait times (baseline_equal)\nF={f_stat:.4f}\np={p_value:.8f}\neta_squared={eta_squared:.6f}\n",
        encoding="utf-8",
    )
    posthoc_rows = []
    alg_groups = {name: grp["wait_min"].values for name, grp in baseline_df.groupby("algorithm")}
    names = list(alg_groups.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            t_stat, p_raw = stats.ttest_ind(alg_groups[a], alg_groups[b], equal_var=False)
            p_adj = min(1.0, p_raw * 3)  # Bonferroni for 3 pairwise comparisons
            posthoc_rows.append(
                {
                    "group_a": a,
                    "group_b": b,
                    "t_stat": t_stat,
                    "p_raw": p_raw,
                    "p_bonferroni": p_adj,
                    "cohen_d": (
                        (alg_groups[a].mean() - alg_groups[b].mean())
                        / (
                            (
                                ((alg_groups[a].std(ddof=1) ** 2) + (alg_groups[b].std(ddof=1) ** 2))
                                / 2
                            )
                            ** 0.5
                        )
                        if (alg_groups[a].std(ddof=1) > 0 or alg_groups[b].std(ddof=1) > 0)
                        else 0.0
                    ),
                }
            )
    pd.DataFrame(posthoc_rows).to_csv(OUT_DIR / "posthoc_wait.csv", index=False)
    sensitivity_rows = []
    for (variant, algorithm), group in df.groupby(["variant", "algorithm"]):
        sensitivity_rows.append(
            {
                "variant": variant,
                "algorithm": algorithm,
                "mean_wait_min": group["wait_min"].mean(),
                "mean_distance_km": group["distance_km"].mean(),
                "acceptance_rate": group["reservation_accepted"].mean(),
            }
        )
    pd.DataFrame(sensitivity_rows).to_csv(OUT_DIR / "sensitivity_summary.csv", index=False)
    (OUT_DIR / "analysis_notes.md").write_text(
        "\n".join(
            [
                "# Analysis Notes",
                "",
                "- Random seed for experiment generation is fixed at `42` in `run_experiments.py`.",
                "- Scenarios use distinct geographic origin and session-duration ranges (urban/mixed/highway).",
                "- Sensitivity variants include distance-priority weights, load stress multiplier, and top-k robustness sampling.",
                "- Queue instability handling: when `rho >= 1`, `erlang_c_wait_minutes` returns a capped penalty (`1e6`) to represent infeasible congestion under M/M/c assumptions.",
                "- ANOVA effect size is reported via eta-squared in `anova.txt` for the baseline variant.",
                "- Pairwise post-hoc comparisons use Welch t-test with Bonferroni correction and include Cohen's d.",
                "- Plot readability adjustments: boxplot values are capped at baseline p95; Pareto y-axis uses log10(wait).",
            ]
        ),
        encoding="utf-8",
    )

    sns.set_theme(style="whitegrid")
    plot_df = baseline_df.copy()
    # Keep figures readable when unstable-queue penalties (1e6) dominate the axis.
    cap_value = float(plot_df["wait_min"].quantile(0.95))
    plot_df["wait_min_capped"] = plot_df["wait_min"].clip(upper=cap_value)
    plt.figure(figsize=(8, 5))
    sns.boxplot(data=plot_df, x="algorithm", y="wait_min_capped")
    plt.title("Wait Time by Algorithm (baseline_equal, capped at p95)")
    plt.ylabel("wait_min (capped)")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "boxplot_wait_time.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8, 5))
    grouped = baseline_df.groupby("algorithm")[["distance_km", "wait_min"]].mean().reset_index()
    grouped["wait_min_log10"] = grouped["wait_min"].apply(lambda x: 0.0 if x <= 0 else float(np.log10(x)))
    sns.scatterplot(data=grouped, x="distance_km", y="wait_min_log10", hue="algorithm", s=120)
    label_offsets = {"nearest": (6, 6), "cost_optimized": (8, 10), "queue_aware": (8, -12)}
    for _, row in grouped.iterrows():
        dx, dy = label_offsets.get(row["algorithm"], (6, 6))
        plt.annotate(
            row["algorithm"],
            (row["distance_km"], row["wait_min_log10"]),
            textcoords="offset points",
            xytext=(dx, dy),
        )
    plt.title("Pareto-style Tradeoff (distance vs log10(wait))")
    plt.ylabel("log10(wait_min)")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "pareto_distance_wait.png", dpi=180)
    plt.close()


if __name__ == "__main__":
    main()
    print("Analysis complete.")
