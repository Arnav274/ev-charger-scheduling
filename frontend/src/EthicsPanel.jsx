export default function EthicsPanel() {
  return (
    <div className="ethics-panel">
      <h3>Privacy &amp; Ethics</h3>

      <p>
        <strong>Your location data.</strong> When you search for nearby charging stations, your entered coordinates are
        sent to the local research server to find nearby stations. No location data is stored after the request
        completes, and no third-party analytics or advertising services are used.
      </p>

      <p>
        <strong>Charging station data.</strong> Station locations and information come from the OpenChargeMap open
        dataset. Prices, availability, and operator details may not reflect real-time ground truth — this is a research
        prototype, not a live booking service.
      </p>

      <p>
        <strong>Algorithmic fairness.</strong> This system compares six routing algorithms. Each one encodes different
        trade-offs between travel distance, waiting time, and cost. Research has shown that different routing policies
        can affect different groups of drivers unevenly — for example, penalising drivers who live further from city
        centres. The Jain fairness index shown in the Stats tab measures how evenly recommendations are spread across
        stations.
      </p>

      <p>
        <strong>Accounts and passwords.</strong> Passwords are stored using bcrypt hashing (a standard security
        practice). This is a sandboxed research build — do not reuse real passwords. Accounts and reservations are
        stored locally in Docker and are not shared with any third party.
      </p>

      <p>
        <strong>Research ethics.</strong> This project was developed following the University of East Anglia CMP ethics
        guidelines. The comparison of algorithmic policies is a research artefact. Results should not be used to make
        real-world charging decisions.
      </p>
    </div>
  );
}
