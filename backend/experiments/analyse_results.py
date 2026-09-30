"""Summarise the simulation: tables, paired significance tests, charts and findings.json.

    docker compose exec backend python -m experiments.analyse_results

The unit of analysis is a simulated day. Every algorithm faced the same days,
so algorithms are compared with paired tests over (scenario, day) pairs rather
than by treating thousands of drivers from the same day as independent.
"""

from __future__ import annotations

import json
from itertools import combinations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from experiments.config import ALGORITHMS, DATA_DIR, OUTPUT_DIR, REPLICATES, SEED, VARIANTS  # noqa: E402

BOOTSTRAP_RESAMPLES = 2000
METRICS = [
    "journey_min",
    "wait_min",
    "p95_wait_min",
    "share_waited",
    "distance_km",
    "drive_min",
    "predicted_wait_min",
    "background_wait_min",
    "busiest_station_share",
]
LABELS = {
    "nearest": "Nearest",
    "dijkstra": "Dijkstra (fastest)",
    "cost_optimized": "Cost optimised",
    "static_queue": "Static queue",
    "queue_aware": "Queue aware",
    "range_aware": "Range aware",
}
# One colour per algorithm on every chart (validated categorical order, light surface).
COLOURS = dict(
    zip(ALGORITHMS, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"], strict=True)
)
INK, INK_MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def bootstrap_ci(values: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    """Percentile bootstrap 95% interval for the mean."""
    means = rng.choice(values, size=(BOOTSTRAP_RESAMPLES, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def holm(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values (step-down, monotone)."""
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values))
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted.tolist()


def summarise(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for (variant, scenario, algorithm), group in df.groupby(["variant", "scenario", "algorithm"], sort=False):
        row = {"variant": variant, "scenario": scenario, "algorithm": algorithm, "days": len(group)}
        for metric in METRICS:
            row[metric] = group[metric].mean()
        for metric in ("journey_min", "wait_min"):
            row[f"{metric}_ci_low"], row[f"{metric}_ci_high"] = bootstrap_ci(group[metric].to_numpy(), rng)
        rows.append(row)
    return pd.DataFrame(rows)


def pooled(df: pd.DataFrame, variant: str, rng: np.random.Generator) -> dict[str, dict]:
    """Per-algorithm means over every scenario and day of one variant."""
    out = {}
    subset = df[df["variant"] == variant]
    for algorithm in ALGORITHMS:
        group = subset[subset["algorithm"] == algorithm]
        entry = {metric: float(group[metric].mean()) for metric in METRICS}
        entry["journey_ci"] = bootstrap_ci(group["journey_min"].to_numpy(), rng)
        entry["wait_ci"] = bootstrap_ci(group["wait_min"].to_numpy(), rng)
        out[algorithm] = entry
    return out


def paired_tests(df: pd.DataFrame, variant: str, metric: str, rng: np.random.Generator) -> pd.DataFrame:
    wide = df[df["variant"] == variant].pivot_table(
        index=["scenario", "replicate"], columns="algorithm", values=metric
    )
    rows = []
    for a, b in combinations(ALGORITHMS, 2):
        diff = (wide[a] - wide[b]).to_numpy()
        sd = diff.std(ddof=1)
        ci_low, ci_high = bootstrap_ci(diff, rng)
        rows.append(
            {
                "variant": variant,
                "metric": metric,
                "a": a,
                "b": b,
                "mean_a": wide[a].mean(),
                "mean_b": wide[b].mean(),
                "mean_diff": diff.mean(),
                "diff_ci_low": ci_low,
                "diff_ci_high": ci_high,
                # Cohen's d_z: the mean paired difference in units of its own spread.
                "cohens_dz": diff.mean() / sd if sd > 0 else 0.0,
                "p_ttest": stats.ttest_rel(wide[a], wide[b]).pvalue if sd > 0 else 1.0,
                "p_wilcoxon": stats.wilcoxon(diff).pvalue if np.any(diff != 0) else 1.0,
                "pairs": len(diff),
            }
        )
    table = pd.DataFrame(rows)
    table["p_holm"] = holm(table["p_wilcoxon"].tolist())
    return table


def calibration(drivers: pd.DataFrame) -> dict[str, dict]:
    """Mean Erlang-C prediction shown to drivers against the wait they then had."""
    return {
        algorithm: {
            "predicted_wait_min": float(group["predicted_wait_min"].mean()),
            "simulated_wait_min": float(group["wait_min"].mean()),
        }
        for algorithm, group in drivers.groupby("algorithm")
    }


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_journeys(summary: pd.DataFrame, path) -> None:
    """Dot plot of mean journey time with 95% intervals, one panel per scenario and demand level."""
    scenarios = list(dict.fromkeys(summary["scenario"]))
    variants = [("baseline", "200 app drivers a day"), ("high_demand", "600 app drivers a day")]
    fig, axes = plt.subplots(
        len(variants), len(scenarios), figsize=(12, 6.2), sharex=True, sharey=True, facecolor=SURFACE
    )
    y = np.arange(len(ALGORITHMS))[::-1]
    for r, (variant, variant_label) in enumerate(variants):
        for c, scenario in enumerate(scenarios):
            ax = axes[r, c]
            _style(ax)
            cell = summary[(summary["variant"] == variant) & (summary["scenario"] == scenario)].set_index(
                "algorithm"
            )
            for yi, algorithm in zip(y, ALGORITHMS, strict=True):
                row = cell.loc[algorithm]
                ax.plot(
                    [row["journey_min_ci_low"], row["journey_min_ci_high"]],
                    [yi, yi],
                    color=COLOURS[algorithm],
                    linewidth=2,
                    solid_capstyle="round",
                )
                ax.scatter(
                    row["journey_min"],
                    yi,
                    s=64,
                    color=COLOURS[algorithm],
                    edgecolor=SURFACE,
                    linewidth=2,
                    zorder=3,
                )
                ax.annotate(
                    f"{row['journey_min']:.0f}" if row["journey_min"] >= 10 else f"{row['journey_min']:.1f}",
                    (row["journey_min"], yi),
                    xytext=(8, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize=8,
                    color=INK_MUTED,
                )
            ax.set_xscale("log")
            ax.set_yticks(y, [LABELS[a] for a in ALGORITHMS], color=INK)
            if r == 0:
                ax.set_title(scenario.capitalize(), color=INK, fontsize=11, loc="left")
            if c == 0:
                ax.set_ylabel(variant_label, color=INK_MUTED, fontsize=9)
    fig.supxlabel("Mean journey time, drive plus wait (minutes, log scale)", color=INK_MUTED, fontsize=9)
    fig.suptitle(
        "Journey time by strategy: mean over 30 simulated days, with 95% intervals",
        x=0.01,
        ha="left",
        color=INK,
        fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_load_sensitivity(summary: pd.DataFrame, path) -> None:
    """Mean wait against background load, one line per algorithm, directly labelled."""
    order = [("load_0.5x", 0.5), ("baseline", 1.0), ("load_1.5x", 1.5), ("load_2x", 2.0)]
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ends = []
    for algorithm in ALGORITHMS:
        waits = [
            summary[(summary["variant"] == v) & (summary["algorithm"] == algorithm)]["wait_min"].mean()
            for v, _ in order
        ]
        xs = [m for _, m in order]
        ax.plot(xs, waits, color=COLOURS[algorithm], linewidth=2, marker="o", markersize=6)
        ends.append((waits[-1], algorithm))
    ax.set_yscale("symlog", linthresh=1)
    ax.set_xticks([m for _, m in order], ["0.5x", "1x", "1.5x", "2x"])
    ax.set_xlim(0.4, 2.55)
    fig.canvas.draw()
    # Direct labels at the line ends, nudged apart where lines finish close together.
    px_per_pt = fig.dpi / 72
    min_gap = 13 * px_per_pt
    placed: list[float] = []
    for value, algorithm in sorted(ends):
        y_px = ax.transData.transform((order[-1][1], value))[1]
        offset = max([0.0] + [p + min_gap - y_px for p in placed])
        placed.append(y_px + offset)
        ax.annotate(
            LABELS[algorithm],
            (order[-1][1], value),
            xytext=(8, offset / px_per_pt),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=INK,
        )
    ax.set_xlabel(
        "Background arrival rate, relative to 0.75 per station per hour", color=INK_MUTED, fontsize=9
    )
    ax.set_ylabel("Mean wait of app drivers (minutes)", color=INK_MUTED, fontsize=9)
    ax.set_title("Wait as the network gets busier", color=INK, fontsize=12, loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def comparison_table(stats_by_algorithm: dict[str, dict], title: str) -> str:
    lines = [
        f"### {title}",
        "",
        "| Strategy | Journey (min) | 95% CI | Wait (min) | 95th pct wait | Waited at all | Drive (km) | "
        "Others' wait (min) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for algorithm in sorted(ALGORITHMS, key=lambda a: stats_by_algorithm[a]["journey_min"]):
        s = stats_by_algorithm[algorithm]
        lo, hi = s["journey_ci"]
        lines.append(
            f"| `{algorithm}` | {s['journey_min']:.1f} | {lo:.1f} to {hi:.1f} | {s['wait_min']:.1f} | "
            f"{s['p95_wait_min']:.0f} | {s['share_waited']:.0%} | {s['distance_km']:.2f} | "
            f"{s['background_wait_min']:.1f} |"
        )
    return "\n".join(lines)


def main() -> None:
    rng = np.random.default_rng(SEED)
    df = pd.read_csv(OUTPUT_DIR / "replicates.csv")
    drivers = pd.read_csv(OUTPUT_DIR / "drivers_baseline.csv.gz")
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))

    summary = summarise(df, rng)
    summary.to_csv(OUTPUT_DIR / "summary_ci.csv", index=False, float_format="%.6g")

    tests = pd.concat(
        [paired_tests(df, variant, "journey_min", rng) for variant in ("baseline", "high_demand")],
        ignore_index=True,
    )
    tests.to_csv(OUTPUT_DIR / "paired_tests.csv", index=False, float_format="%.6g")

    baseline = pooled(df, "baseline", rng)
    high = pooled(df, "high_demand", rng)
    (OUTPUT_DIR / "comparison_table.md").write_text(
        "\n\n".join(
            [
                "# Strategy comparison",
                f"Means over every scenario and simulated day ({REPLICATES} days x 3 scenarios each). "
                "Journey is drive plus wait. 'Others' wait' is the mean wait of the background drivers "
                "who do not use the app.",
                comparison_table(baseline, "Baseline: 200 app drivers a day"),
                comparison_table(high, "High demand: 600 app drivers a day"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    plot_journeys(summary, OUTPUT_DIR / "journey_time_by_strategy.png")
    plot_load_sensitivity(summary, OUTPUT_DIR / "load_sensitivity.png")

    def lookahead(variant: str) -> dict:
        row = tests[
            (tests["variant"] == variant) & (tests["a"] == "static_queue") & (tests["b"] == "queue_aware")
        ]
        row = row.iloc[0]
        return {
            "static_queue_journey_min": row["mean_a"],
            "queue_aware_journey_min": row["mean_b"],
            "saving_min": row["mean_diff"],
            "saving_ci": [row["diff_ci_low"], row["diff_ci_high"]],
            "cohens_dz": row["cohens_dz"],
            "p_holm": row["p_holm"],
        }

    best = min(ALGORITHMS, key=lambda a: baseline[a]["journey_min"])
    findings = {
        "study": {
            "stations": manifest["stations"],
            "chargers": manifest["chargers"],
            "scenarios": manifest["scenarios"],
            "days_per_scenario": REPLICATES,
            "variants": list(VARIANTS),
            # App drivers each strategy routed in the baseline variant.
            "baseline_app_drivers": int(df[df["variant"] == "baseline"]["drivers"].sum()) // len(ALGORITHMS),
        },
        "best_strategy": best,
        "vs_nearest": {
            "journey_reduction_pct": 100
            * (1 - baseline[best]["journey_min"] / baseline["nearest"]["journey_min"]),
            "wait_reduction_pct": 100 * (1 - baseline[best]["wait_min"] / baseline["nearest"]["wait_min"]),
            "extra_distance_km": baseline[best]["distance_km"] - baseline["nearest"]["distance_km"],
        },
        "lookahead": {"baseline": lookahead("baseline"), "high_demand": lookahead("high_demand")},
        "baseline": baseline,
        "high_demand": high,
        "calibration": calibration(drivers),
    }
    (OUTPUT_DIR / "findings.json").write_text(
        json.dumps(findings, indent=2, default=float) + "\n", encoding="utf-8"
    )
    print((OUTPUT_DIR / "comparison_table.md").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {k: findings[k] for k in ("best_strategy", "vs_nearest", "lookahead")}, indent=2, default=float
        )
    )


if __name__ == "__main__":
    main()
