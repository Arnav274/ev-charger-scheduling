import { STRATEGIES } from "../strategies";

export default function StrategyPicker({ active, onPick, battery, onBatteryChange }) {
  return (
    <details open className="sidebar-section">
      <summary className="section-summary">Strategy</summary>
      <div className="section-body">
        <div className="algo-buttons">
          {STRATEGIES.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`btn-algo${active === s.id ? " active" : ""}`}
              title={s.description}
              aria-pressed={active === s.id}
              onClick={() => onPick(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
        {active && <p className="algo-tip">{STRATEGIES.find((s) => s.id === active).description}</p>}

        <details className="range-inputs" open={active === "range_aware"}>
          <summary>Battery, for Range aware</summary>
          <div className="field">
            <label htmlFor="battery-level">Charge left (%)</label>
            <input
              id="battery-level"
              type="number"
              min="0"
              max="100"
              placeholder="e.g. 20"
              value={battery.level}
              onChange={(e) => onBatteryChange({ ...battery, level: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="battery-capacity">Battery capacity (kWh)</label>
            <input
              id="battery-capacity"
              type="number"
              min="1"
              placeholder="e.g. 60"
              value={battery.capacity}
              onChange={(e) => onBatteryChange({ ...battery, capacity: e.target.value })}
            />
          </div>
        </details>
      </div>
    </details>
  );
}
