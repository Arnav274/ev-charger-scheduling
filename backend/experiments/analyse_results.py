from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

OUT_DIR = Path(__file__).parent / "outputs"

ALL_ALGORITHMS = ["nearest", "cost_optimized", "queue_aware", "static_queue", "dijkstra", "range_aware"]


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
        if "probability_of_delay" in group.columns:
            p_ci = bootstrap_ci(group["probability_of_delay"])
        else:
            p_ci = (0.0, 0.0)
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
                "pdelay_mean": group["probability_of_delay"].mean() if "probability_of_delay" in group.columns else 0.0,
                "pdelay_ci_low": p_ci[0],
                "pdelay_ci_high": p_ci[1],
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
    n_comparisons = max(1, len(names) * (len(names) - 1) // 2)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            t_stat, p_raw = stats.ttest_ind(alg_groups[a], alg_groups[b], equal_var=False)
            p_adj = min(1.0, p_raw * n_comparisons)  # Bonferroni correction
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

    # Optional: ANOVA for probability of delay (risk metric).
    if "probability_of_delay" in baseline_df.columns:
        pdelay_groups = [g["probability_of_delay"].values for _, g in baseline_df.groupby("algorithm")]
        f2, p2 = stats.f_oneway(*pdelay_groups)
        grand_mean2 = baseline_df["probability_of_delay"].mean()
        ss_between2 = sum(
            len(group) * ((group.mean() - grand_mean2) ** 2)
            for _, group in baseline_df.groupby("algorithm")["probability_of_delay"]
        )
        ss_total2 = ((baseline_df["probability_of_delay"] - grand_mean2) ** 2).sum()
        eta2 = float(ss_between2 / ss_total2) if ss_total2 else 0.0
        (OUT_DIR / "anova_pdelay.txt").write_text(
            f"One-way ANOVA probability_of_delay (baseline_equal)\nF={f2:.4f}\np={p2:.8f}\neta_squared={eta2:.6f}\n",
            encoding="utf-8",
        )
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
    label_offsets = {
        "nearest": (6, 6),
        "cost_optimized": (8, 10),
        "queue_aware": (8, -12),
        "static_queue": (8, -20),
        "dijkstra": (6, 14),
        "range_aware": (6, -6),
    }
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

    generate_comparison_table(df)
    plot_algorithm_comparison_bar(baseline_df)
    plot_erlang_sensitivity(df)


def generate_comparison_table(df: pd.DataFrame) -> None:
    """Aggregate per-algorithm stats for the baseline_equal variant and write outputs/comparison_table.md."""
    df = df[df["variant"] == "baseline_equal"]
    rows = []
    for algorithm, grp in df.groupby("algorithm"):
        d_ci = bootstrap_ci(grp["distance_km"])
        w_ci = bootstrap_ci(grp["wait_min"])
        pdelay_mean = grp["probability_of_delay"].mean() if "probability_of_delay" in grp.columns else 0.0
        rows.append(
            {
                "algorithm": algorithm,
                "mean_distance_km": round(grp["distance_km"].mean(), 4),
                "ci_low_dist": round(d_ci[0], 4),
                "ci_high_dist": round(d_ci[1], 4),
                "mean_wait_min": round(grp["wait_min"].mean(), 4),
                "ci_low_wait": round(w_ci[0], 4),
                "ci_high_wait": round(w_ci[1], 4),
                "mean_pdelay": round(float(pdelay_mean), 4),
                "acceptance_rate": round(float(grp["reservation_accepted"].mean()), 4),
            }
        )
    tbl = pd.DataFrame(rows)
    # Sort by mean_wait_min ascending so best performers appear first.
    tbl = tbl.sort_values("mean_wait_min").reset_index(drop=True)

    header = "| " + " | ".join(tbl.columns) + " |"
    sep = "| " + " | ".join("---" for _ in tbl.columns) + " |"
    body_lines = [
        "| " + " | ".join(str(v) for v in row) + " |"
        for row in tbl.itertuples(index=False, name=None)
    ]
    md = "\n".join(["# Algorithm Comparison Table", "", header, sep] + body_lines + [""])
    (OUT_DIR / "comparison_table.md").write_text(md, encoding="utf-8")


def plot_algorithm_comparison_bar(baseline_df: pd.DataFrame) -> None:
    """Grouped bar chart of mean wait_min per algorithm for the baseline_equal variant."""
    if baseline_df.empty:
        return
    algorithms = sorted(baseline_df["algorithm"].unique())
    scenarios = sorted(baseline_df["scenario"].unique())

    x = np.arange(len(algorithms))
    width = 0.8 / max(len(scenarios), 1)
    fig, ax = plt.subplots(figsize=(10, 6))

    for i, scenario in enumerate(scenarios):
        means = []
        for alg in algorithms:
            sub = baseline_df[(baseline_df["algorithm"] == alg) & (baseline_df["scenario"] == scenario)]
            means.append(sub["wait_min"].mean() if not sub.empty else 0.0)
        ax.bar(x + i * width - (len(scenarios) - 1) * width / 2, means, width=width, label=scenario)

    ax.set_xticks(x)
    ax.set_xticklabels(algorithms, rotation=15, ha="right")
    ax.set_ylabel("Mean wait time (min)")
    ax.set_title("Algorithm Wait Time Comparison — baseline_equal variant")
    ax.legend(title="Scenario")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "algorithm_comparison_bar.png", dpi=180)
    plt.close()


def plot_erlang_sensitivity(df: pd.DataFrame) -> None:
    sens_df = df[df["variant"] == "erlang_sensitivity"].copy()
    if sens_df.empty:
        return
    grouped = (
        sens_df.groupby(["lambda_multiplier", "algorithm"])["wait_min"]
        .mean()
        .reset_index()
        .rename(columns={"wait_min": "mean_wait_min"})
    )
    plt.figure(figsize=(9, 5))
    for algorithm, alg_df in grouped.groupby("algorithm"):
        alg_df = alg_df.sort_values("lambda_multiplier")
        plt.plot(alg_df["lambda_multiplier"], alg_df["mean_wait_min"], marker="o", label=algorithm)
    plt.xlabel("Arrival-rate multiplier (λ scale factor)")
    plt.ylabel("Mean wait time (min)")
    plt.title("Erlang-C Sensitivity: mean wait vs arrival-rate multiplier")
    plt.legend(title="Algorithm")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "erlang_sensitivity_plot.png", dpi=180)
    plt.close()


if __name__ == "__main__":
    main()
    print("Analysis complete.")
