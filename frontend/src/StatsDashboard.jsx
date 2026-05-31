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
      <div className="findings-panel">
        <div className="findings-title">Experiment results</div>
        <div className="findings-sub">162 conditions &nbsp;·&nbsp; 9 variants × 3 scenarios × 6 algorithms &nbsp;·&nbsp; 100 trials each</div>
        <div className="findings-grid">
          <div className="finding-card finding-card--highlight">
            <div className="finding-value">~99%</div>
            <div className="finding-label">predicted wait reduction</div>
            <div className="finding-detail">queue-aware vs nearest / dijkstra</div>
          </div>
          <div className="finding-card finding-card--highlight">
            <div className="finding-value">d = 1.17</div>
            <div className="finding-label">Cohen's d</div>
            <div className="finding-detail">effect size — large (&gt; 0.8)</div>
          </div>
          <div className="finding-card">
            <div className="finding-value">F = 228.67</div>
            <div className="finding-label">ANOVA, p ≈ 0</div>
            <div className="finding-detail">algorithm choice is statistically significant</div>
          </div>
          <div className="finding-card">
            <div className="finding-value">η² = 0.39</div>
            <div className="finding-label">eta-squared</div>
            <div className="finding-detail">39% of wait variance explained by algorithm</div>
          </div>
          <div className="finding-card finding-card--nonresult">
            <div className="finding-value">d = 0.03 &nbsp;·&nbsp; p = 1.0</div>
            <div className="finding-label">queue_aware vs static_queue</div>
            <div className="finding-detail">reservation lookahead shows no significant benefit at baseline load</div>
          </div>
        </div>
      </div>
      <p className="stats-summary">
        The charts below show one configuration at a time. Use the dropdowns to explore different variants and scenarios. The headline numbers above are from the full ANOVA across all 162 conditions.
      </p>
      <details className="stats-details">
        <summary>What am I looking at?</summary>
        <div className="stats-details-body">
          <p><strong>Variant options:</strong></p>
          <ul>
            <li><strong>baseline_equal:</strong> equal weights across all routing criteria</li>
            <li><strong>distance_priority:</strong> users prefer shorter drives</li>
            <li><strong>queue_stress:</strong> artificially high arrival rate to stress-test queuing behaviour</li>
            <li><strong>topk_robustness:</strong> only the top-k nearest stations are considered per request</li>
          </ul>
          <p><strong>Scenario options:</strong></p>
          <ul>
            <li><strong>urban:</strong> high-density city demand profile</li>
            <li><strong>mixed:</strong> blend of urban and highway demand</li>
            <li><strong>highway:</strong> long-distance motorway demand profile</li>
          </ul>
          <p><em>Note: Very large wait values (e.g. 40 min) indicate the Erlang-C model reached high utilisation for that synthetic profile. This is expected behaviour and is discussed in the dissertation.</em></p>
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
