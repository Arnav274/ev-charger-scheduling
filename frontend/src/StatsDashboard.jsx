import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fetchExperimentSummary, fetchFindings } from "./api";
import { STRATEGIES, STRATEGY_LABELS } from "./strategies";

const VARIANT_LABELS = {
  baseline: "Baseline: 200 app drivers a day",
  high_demand: "High demand: 600 app drivers a day",
  distance_priority: "Cost strategy weighted towards distance",
  top3_choice: "Drivers pick any of the top three",
  "load_0.5x": "Background demand halved",
  "load_1.5x": "Background demand x1.5",
  load_2x: "Background demand doubled",
};
const SCENARIO_LABELS = {
  spread: "Spread across central London",
  corridor: "Along Euston and Marylebone Road",
  hotspot: "Everyone near King's Cross",
};

const minutes = (value) => (value >= 10 ? value.toFixed(0) : value.toFixed(1));
const unique = (values) => [...new Set(values)];

function Finding({ value, label, detail, tone }) {
  return (
    <div className={`finding-card${tone ? ` finding-card--${tone}` : ""}`}>
      <div className="finding-value">{value}</div>
      <div className="finding-label">{label}</div>
      {detail && <div className="finding-detail">{detail}</div>}
    </div>
  );
}

export function FindingsPanel({ findings }) {
  const best = findings.best_strategy;
  const baseline = findings.baseline;
  const { baseline: lookBase, high_demand: lookHigh } = findings.lookahead;
  const study = findings.study;
  const pValue = (p) => (p < 0.001 ? "p < 0.001" : `p = ${p.toFixed(3)}`);

  return (
    <div className="findings-panel">
      <div className="findings-title">What the simulation found</div>
      <div className="findings-sub">
        {study.stations} stations · {study.days_per_scenario} simulated days in each of{" "}
        {study.scenarios.length} scenarios · {study.app_drivers_simulated.toLocaleString()} app drivers per
        strategy
      </div>
      <div className="findings-grid">
        <Finding
          tone="highlight"
          value={`${minutes(baseline[best].journey_min)} min`}
          label={`average journey with ${STRATEGY_LABELS[best]}`}
          detail={`against ${minutes(baseline.nearest.journey_min)} min for Nearest, drive plus wait`}
        />
        <Finding
          tone="highlight"
          value={`${findings.vs_nearest.wait_reduction_pct.toFixed(1)}%`}
          label="less waiting than Nearest"
          detail={`for ${(findings.vs_nearest.extra_distance_km * 1000).toFixed(0)} m more driving`}
        />
        <Finding
          value={`${minutes(lookHigh.saving_min)} min`}
          label="saved by reservation lookahead at high demand"
          detail={`Queue aware vs Static queue, 95% CI ${minutes(lookHigh.saving_ci[0])} to ${minutes(
            lookHigh.saving_ci[1],
          )} min, d = ${lookHigh.cohens_dz.toFixed(2)}, ${pValue(lookHigh.p_holm)}`}
        />
        <Finding
          tone="modest"
          value={`${minutes(lookBase.saving_min)} min`}
          label="saved by the same lookahead at normal demand"
          detail={`Real but small (d = ${lookBase.cohens_dz.toFixed(2)}): it matters once app drivers crowd the same stations`}
        />
      </div>
    </div>
  );
}

export default function StatsDashboard() {
  const [rows, setRows] = useState([]);
  const [findings, setFindings] = useState(null);
  const [error, setError] = useState("");
  const [variant, setVariant] = useState("baseline");
  const [scenario, setScenario] = useState("spread");

  useEffect(() => {
    Promise.all([fetchExperimentSummary(), fetchFindings()])
      .then(([summary, found]) => {
        setRows(summary.rows || []);
        setFindings(found);
      })
      .catch((err) => setError(err.message));
  }, []);

  const cell = useMemo(() => {
    const byStrategy = new Map(
      rows.filter((r) => r.variant === variant && r.scenario === scenario).map((r) => [r.algorithm, r]),
    );
    return STRATEGIES.filter((s) => byStrategy.has(s.id)).map((s) => ({
      ...byStrategy.get(s.id),
      label: s.label,
    }));
  }, [rows, variant, scenario]);

  if (error) return <p className="status">Could not load the experiment results: {error}</p>;
  if (!findings) return <p className="status">Loading experiment results…</p>;

  return (
    <div className="stats-wrap">
      <FindingsPanel findings={findings} />

      <div className="field">
        <label htmlFor="stats-variant">Variant</label>
        <select id="stats-variant" value={variant} onChange={(e) => setVariant(e.target.value)}>
          {unique(rows.map((r) => r.variant)).map((v) => (
            <option key={v} value={v}>
              {VARIANT_LABELS[v] ?? v}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="stats-scenario">Where drivers start</label>
        <select id="stats-scenario" value={scenario} onChange={(e) => setScenario(e.target.value)}>
          {unique(rows.map((r) => r.scenario)).map((s) => (
            <option key={s} value={s}>
              {SCENARIO_LABELS[s] ?? s}
            </option>
          ))}
        </select>
      </div>

      <div className="chart-box">
        <h4>Mean journey time, drive plus wait (minutes, log scale)</h4>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={cell} layout="vertical" margin={{ left: 8, right: 24 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" scale="log" domain={[1, "auto"]} allowDataOverflow />
            <YAxis type="category" dataKey="label" width={96} />
            <Tooltip formatter={(value) => [`${minutes(value)} min`, "Journey"]} />
            <Bar dataKey="journey_min" fill="#2a78d6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <table className="stats-table">
        <thead>
          <tr>
            <th>Strategy</th>
            <th>Journey (min)</th>
            <th>Wait (min)</th>
            <th>Waited</th>
            <th>Drive (km)</th>
          </tr>
        </thead>
        <tbody>
          {cell.map((r) => (
            <tr key={r.algorithm}>
              <td>{r.label}</td>
              <td title={`95% CI ${minutes(r.journey_min_ci_low)} to ${minutes(r.journey_min_ci_high)}`}>
                {minutes(r.journey_min)}
              </td>
              <td>{minutes(r.wait_min)}</td>
              <td>{Math.round(r.share_waited * 100)}%</td>
              <td>{r.distance_km.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <details className="stats-details">
        <summary>How these numbers were produced</summary>
        <div className="stats-details-body">
          <p>
            Each simulated day, background drivers arrive at every station at random, and app drivers set off
            at random times and ask a strategy where to charge. They drive there, taking the real road travel
            time, and queue for a free charger. The waits are measured from that queue, not predicted.
          </p>
          <p>
            Every strategy faces exactly the same days, so differences between them come from the strategy
            alone. Drivers in the simulation never give up and leave, so where a queue grows through the day
            the averages show how overloaded that station is rather than how long anyone would really wait.
          </p>
        </div>
      </details>
    </div>
  );
}
