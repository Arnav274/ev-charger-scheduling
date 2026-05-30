import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";




const VARIANT_OPTIONS = ["baseline_equal", "distance_priority", "queue_stress", "topk_robustness"];
const SCENARIO_OPTIONS = ["urban", "mixed", "highway"];

export default function StatsDashboard({ rows, loadError }) {
  const [variant, setVariant] = useState("baseline_equal");
  const [scenario, setScenario] = useState("urban");

  const chartRows = useMemo(() => {
    const subset = rows.filter((r) => r.variant === variant && r.scenario === scenario);
    return subset.map((r) => ({
      algorithm: r.algorithm,
      distance_km: Number(r.distance_mean ?? 0),
      wait_min: Number(r.wait_mean ?? 0),
      accept_pct: Number(r.reservation_accept_rate ?? 0) * 100,
    }));
  }, [rows, variant, scenario]);

  if (loadError) {
    return <p className="status">Could not load experiment summary: {loadError}</p>;
  }

  if (!rows.length) {
    return (
      <p className="status">
        No experiment summaries found. Run <code>docker compose exec backend python -m experiments.run_experiments</code> then{" "}
        <code>analyse_results</code>.
      </p>
    );
  }



  
  return (
    <div className="stats-wrap">
      <div className="field">
        <label>Variant</label>
        <select value={variant} onChange={(e) => setVariant(e.target.value)}>
          {VARIANT_OPTIONS.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>Scenario</label>
        <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
          {SCENARIO_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <p className="stats-note">
        Values come from frozen <code>summary_ci.csv</code> (<code>/stats/experiment-summary</code>). Large wait predictions indicate unstable Erlang‑C
        regimes (ρ ≥ 1) for that synthetic profile—explain in writing, do not hide the anomaly.
      </p>
      <p className="stats-summary">
        These charts show simulation results across multiple configurations. Each bar represents one routing algorithm. Lower wait time and higher
        acceptance rate are better. Queue-aware achieves near-zero predicted wait by avoiding congested stations, at the cost of slightly longer
        travel distance.
      </p>
      <details className="stats-details">
        <summary>What am I looking at?</summary>
        <div className="stats-details-body">
          <p><strong>Variant options:</strong></p>
          <ul>
            <li><strong>baseline_equal</strong> — equal weights across all routing criteria</li>
            <li><strong>distance_priority</strong> — users prefer shorter drives</li>
            <li><strong>queue_stress</strong> — artificially high load to stress-test queuing behaviour</li>
            <li><strong>topk_robustness</strong> — only top-k stations sampled per request</li>
          </ul>
          <p><strong>Scenario options:</strong></p>
          <ul>
            <li><strong>urban</strong> — high-density city demand profile</li>
            <li><strong>mixed</strong> — blend of urban and highway demand</li>
            <li><strong>highway</strong> — long-distance motorway demand profile</li>
          </ul>
          <p><em>Note: Very large wait values (e.g. 40 min) indicate the Erlang-C queueing model became unstable at high load (ρ ≥ 1). This is expected and discussed in the dissertation.</em></p>
        </div>
      </details>
      <div className="chart-box">
        <h4>Mean travel distance (km)</h4>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartRows}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="algorithm" angle={-20} height={70} interval={0} textAnchor="end" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="distance_km" fill="#2563eb" name="Distance (km)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-box">
        <h4>Model-predicted wait (minutes)</h4>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartRows}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="algorithm" angle={-20} height={70} interval={0} textAnchor="end" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="wait_min" fill="#059669" name="Wait (min)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-box">
        <h4>Simulated reservation acceptance rate (%)</h4>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartRows}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="algorithm" angle={-20} height={70} interval={0} textAnchor="end" />
            <YAxis domain={[0, 100]} />
            <Tooltip />
            <Legend />
            <Bar dataKey="accept_pct" fill="#d97706" name="Accepted (%)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
