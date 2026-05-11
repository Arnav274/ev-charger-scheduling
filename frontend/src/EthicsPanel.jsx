export default function EthicsPanel() {
  return (
    <div className="ethics-panel">
      <h3>Privacy, data sources, CMP ethics link</h3>
      <p>
        <strong>Location.</strong> Coordinates entered here are posted to your local FastAPI backend for PostGIS lookups and routing experiments. Treat this
        build as sandbox software: no telemetry or third‑party advertisers are wired in by default.
      </p>
      <p>
        <strong>OpenChargeMap.</strong> Charger positions and metadata are ingested from OpenChargeMap sample data (see repository README). Tariffs, socket
        availability, and operator maintenance status can diverge from ground truth—results are research artefacts, not live operator guidance.
      </p>
      <p>
        <strong>Algorithmic trade‑offs.</strong> Comparing <em>nearest</em>, <em>cost‑optimised</em>, and <em>queue‑aware</em> policies encodes value
        judgements (time vs money vs predicted congestion). CMP ethics sessions on <em>algorithmic bias</em> apply: different driver cohorts experience
        different burdens under each policy; interpret Jain fairness and queue metrics as partial indicators, not proof of social equity.
      </p>
      <p>
        <strong>Accounts.</strong> Passwords are stored as bcrypt hashes; JWTs sign with <code>JWT_SECRET_KEY</code>. Rotate secrets before any shared
        deployment and never reuse production passwords in coursework containers.
      </p>
      <p>
        Long-form notes for the dissertation appendix: <code>docs/threat_model_and_ethics_scope.md</code> and{" "}
        <code>docs/privacy_and_ethics_ui_copy.md</code>.
      </p>
    </div>
  );
}
