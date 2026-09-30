import { forwardRef, useState } from "react";

import { cancelReservation, createVehicle } from "../api";
import { formatDateTime } from "../lib/time";

function SignInForm({ auth }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  async function submit(action, { newAccount = false } = {}) {
    if (newAccount && password.length < 8) {
      setMessage("Choose a password of at least 8 characters.");
      return;
    }
    try {
      await action(email, password);
    } catch (err) {
      setMessage(err.message);
    }
  }

  return (
    <form
      className="auth-form"
      onSubmit={(e) => {
        e.preventDefault();
        submit(auth.login);
      }}
    >
      <p className="status small">Sign in to book chargers.</p>
      <div className="field">
        <label htmlFor="auth-email">Email</label>
        <input
          id="auth-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>
      <div className="field">
        <label htmlFor="auth-password">Password</label>
        <input
          id="auth-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      <div className="buttons">
        <button type="submit" className="btn-primary">
          Sign in
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => submit(auth.register, { newAccount: true })}
        >
          Register
        </button>
      </div>
      {message && (
        <p className="status" role="alert">
          {message}
        </p>
      )}
    </form>
  );
}

function Vehicles({ token, vehicles, onSaved, selectedId, onSelect }) {
  const [form, setForm] = useState({ make_model: "", battery_kwh: "" });
  const [error, setError] = useState("");

  async function save(event) {
    event.preventDefault();
    try {
      await createVehicle({ make_model: form.make_model, battery_kwh: Number(form.battery_kwh) }, token);
      setForm({ make_model: "", battery_kwh: "" });
      setError("");
      onSaved();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <h4 className="subsection-heading">My vehicles</h4>
      {vehicles.length > 0 && (
        <ul className="vehicle-list">
          {vehicles.map((v) => (
            <li key={v.id}>
              <button type="button" className="btn-link" onClick={() => onSelect(v)}>
                {v.make_model} ({v.battery_kwh} kWh){selectedId === v.id ? ", selected" : ""}
              </button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={save}>
        <div className="field">
          <label htmlFor="vehicle-model">Make and model</label>
          <input
            id="vehicle-model"
            maxLength={120}
            placeholder="e.g. Nissan Leaf"
            value={form.make_model}
            onChange={(e) => setForm({ ...form, make_model: e.target.value })}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="vehicle-battery">Battery (kWh)</label>
          <input
            id="vehicle-battery"
            type="number"
            min="1"
            step="0.1"
            placeholder="e.g. 40"
            value={form.battery_kwh}
            onChange={(e) => setForm({ ...form, battery_kwh: e.target.value })}
            required
          />
        </div>
        <button type="submit" className="btn-primary">
          Save vehicle
        </button>
      </form>
      {error && <p className="status">{error}</p>}
    </>
  );
}

const AccountPanel = forwardRef(function AccountPanel(
  { auth, vehicles, onVehiclesChanged, selectedVehicleId, onSelectVehicle, reservations, onCancelled },
  ref,
) {
  const [cancelError, setCancelError] = useState("");
  const [cancelling, setCancelling] = useState(null);

  async function cancel(reservation) {
    setCancelling(reservation.id);
    try {
      await cancelReservation(reservation.id, auth.token);
      setCancelError("");
      onCancelled();
    } catch (err) {
      setCancelError(err.message);
    } finally {
      setCancelling(null);
    }
  }

  return (
    <details className="sidebar-section auth-box" ref={ref}>
      <summary className="section-summary">My account</summary>
      <div className="section-body">
        {!auth.token ? (
          <SignInForm auth={auth} />
        ) : (
          <div className="auth-status">
            <p className="status signed-in">Signed in</p>
            <button type="button" className="btn-secondary" onClick={auth.logout}>
              Sign out
            </button>
            <Vehicles
              token={auth.token}
              vehicles={vehicles}
              onSaved={onVehiclesChanged}
              selectedId={selectedVehicleId}
              onSelect={onSelectVehicle}
            />
            {reservations.length > 0 && (
              <div className="my-reservations">
                <h4 className="subsection-heading">My bookings</h4>
                <ul>
                  {reservations.map((r) => (
                    <li key={r.id} className="reservation-item">
                      <strong>{r.station_name}</strong>, {r.charger_name}
                      <br />
                      {formatDateTime(r.start_time)} to {formatDateTime(r.end_time)}
                      {new Date(r.end_time) > new Date() && (
                        <button
                          type="button"
                          className="btn-link"
                          aria-label={`Cancel booking at ${r.station_name}`}
                          disabled={cancelling === r.id}
                          onClick={() => cancel(r)}
                        >
                          {cancelling === r.id ? "Cancelling…" : "Cancel"}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
                {cancelError && (
                  <p className="status" role="alert">
                    {cancelError}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </details>
  );
});

export default AccountPanel;
