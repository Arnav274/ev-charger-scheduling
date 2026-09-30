import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "./api";
import StatsDashboard from "./StatsDashboard";

vi.mock("recharts", () => {
  const Stub = ({ children }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Stub,
    BarChart: Stub,
    Bar: () => null,
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
  };
});

const strategyStats = (journey, wait) => ({ journey_min: journey, wait_min: wait, distance_km: 1 });

const findings = {
  study: {
    stations: 497,
    days_per_scenario: 30,
    scenarios: ["spread", "hotspot"],
    app_drivers_simulated: 18000,
  },
  best_strategy: "queue_aware",
  vs_nearest: { journey_reduction_pct: 98.7, wait_reduction_pct: 99.9, extra_distance_km: 0.66 },
  lookahead: {
    baseline: { saving_min: 0.56, saving_ci: [0.4, 0.72], cohens_dz: 0.72, p_holm: 1e-9 },
    high_demand: { saving_min: 100.1, saving_ci: [80.4, 119.2], cohens_dz: 1.04, p_holm: 2e-15 },
  },
  baseline: { queue_aware: strategyStats(3.08, 0.2), nearest: strategyStats(241.3, 240.3) },
};

const row = (variant, scenario, algorithm, journey) => ({
  variant,
  scenario,
  algorithm,
  journey_min: journey,
  journey_min_ci_low: journey - 1,
  journey_min_ci_high: journey + 1,
  wait_min: journey - 2,
  share_waited: 0.5,
  distance_km: 1.25,
});

describe("StatsDashboard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "fetchFindings").mockResolvedValue(findings);
    vi.spyOn(api, "fetchExperimentSummary").mockResolvedValue({
      rows: [
        row("baseline", "spread", "nearest", 35),
        row("baseline", "spread", "queue_aware", 2.5),
        row("high_demand", "spread", "nearest", 67),
        row("high_demand", "spread", "queue_aware", 2.7),
        row("baseline", "hotspot", "nearest", 616),
        row("baseline", "hotspot", "queue_aware", 4),
      ],
    });
  });

  it("shows the headline findings from the analysis output", async () => {
    render(<StatsDashboard />);

    expect(await screen.findByText("3.1 min")).toBeInTheDocument();
    expect(screen.getByText(/average journey with Queue aware/)).toBeInTheDocument();
    expect(screen.getByText("99.9%")).toBeInTheDocument();
    expect(screen.getByText("100 min")).toBeInTheDocument();
    expect(screen.getByText(/497 stations/)).toBeInTheDocument();
  });

  it("filters the table by variant and scenario", async () => {
    render(<StatsDashboard />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("35")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Variant"), "high_demand");
    expect(within(table).getByText("67")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Where drivers start"), "hotspot");
    expect(within(table).queryAllByRole("row")).toHaveLength(1); // no high-demand hotspot rows in the fixture
  });

  it("reports a load failure", async () => {
    api.fetchFindings.mockRejectedValue(new Error("Failed to load experiment findings"));
    render(<StatsDashboard />);
    expect(await screen.findByText(/Could not load the experiment results/)).toBeInTheDocument();
  });
});
