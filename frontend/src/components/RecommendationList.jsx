import { forwardRef } from "react";

import { STRATEGY_LABELS } from "../strategies";

const RecommendationList = forwardRef(function RecommendationList(
  { strategy, recommendations, error, onSelectStation },
  ref,
) {
  if (!recommendations.length && !error) return null;
  return (
    <section ref={ref} className="sidebar-section recommendations-section">
      <h3 className="recommendations-label">Best stations: {STRATEGY_LABELS[strategy]}</h3>
      {error && (
        <p className="status" role="alert">
          {error}
        </p>
      )}
      <ol className="recommendations-list">
        {recommendations.map((r) => (
          <li key={r.station_id}>
            <button type="button" className="recommendation" onClick={() => onSelectStation(r.station_id)}>
              <span className="recommendation-name">{r.station_name}</span>
              <span className="recommendation-facts">
                {r.travel_distance_km.toFixed(1)} km · {Math.round(r.travel_time_min)} min drive ·{" "}
                {r.predicted_wait_min < 1 ? "under a minute" : `${Math.round(r.predicted_wait_min)} min`}{" "}
                predicted wait · {Math.round(r.probability_of_delay * 100)}% chance of queueing
                {r.current_occupancy > 0 && ` · ${r.current_occupancy} in use now`}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
});

export default RecommendationList;
