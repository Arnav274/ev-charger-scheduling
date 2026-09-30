import { forwardRef, useState } from "react";

import { createReservation, suggestSlot } from "../api";
import { formatDateTime, nearestHalfHour, toDatetimeInput } from "../lib/time";

const chargerLabel = (charger) => `${charger.name} (${charger.power_kw} kW)`;

function SlotFinder({ station, onUseSlot }) {
  const [arrival, setArrival] = useState(() => toDatetimeInput(nearestHalfHour()));
  const [duration, setDuration] = useState("60");
  const [slots, setSlots] = useState([]);
  const [message, setMessage] = useState("");

  async function search() {
    setSlots([]);
    setMessage("Searching…");
    try {
      const found = await suggestSlot(station.id, {
        desired_arrival: new Date(arrival).toISOString(),
        duration_minutes: Number(duration),
      });
      setSlots(found);
      setMessage(found.length ? "" : "No free slot within four hours of that time.");
    } catch (err) {
      setMessage(err.message);
    }
  }

  return (
    <>
      <h4 className="subsection-heading">Find a free slot</h4>
      <div className="field">
        <label htmlFor="slot-arrival">Arriving at</label>
        <input
          id="slot-arrival"
          type="datetime-local"
          value={arrival}
          min={toDatetimeInput(new Date())}
          onChange={(e) => setArrival(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="slot-duration">Charging for (minutes)</label>
        <input
          id="slot-duration"
          type="number"
          min="30"
          max="480"
          step="30"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
        />
      </div>
      <button type="button" className="btn-primary btn-block" onClick={search} disabled={!arrival}>
        Find available slot
      </button>
      {message && <p className="status">{message}</p>}
      {slots.length > 0 && (
        <ul className="slot-list">
          {slots.map((slot) => {
            const charger = station.chargers.find((c) => c.id === slot.charger_id);
            return (
              <li key={slot.charger_id} className="slot-item">
                <strong>{charger ? chargerLabel(charger) : "Charger"}</strong>:{" "}
                {formatDateTime(slot.suggested_start)} to {formatDateTime(slot.suggested_end)}{" "}
                {slot.wait_from_desired_minutes > 0
                  ? `(${Math.round(slot.wait_from_desired_minutes)} min later)`
                  : "(right away)"}
                <button
                  type="button"
                  className="btn-use-slot"
                  onClick={() => {
                    onUseSlot(slot);
                    setSlots([]);
                  }}
                >
                  Use this slot
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

const BookingPanel = forwardRef(function BookingPanel({ station, token, onBooked }, ref) {
  const [form, setForm] = useState({ charger_id: station.chargers[0]?.id ?? "", start: "", end: "" });
  const [error, setError] = useState("");
  const [booked, setBooked] = useState(null);

  async function reserve(event) {
    event.preventDefault();
    setBooked(null);
    if (!token) {
      setError("Sign in under My account before booking.");
      return;
    }
    const start = new Date(form.start);
    const end = new Date(form.end);
    if (start < new Date()) {
      setError("The start time has already passed.");
      return;
    }
    if (end <= start) {
      setError("The end time must be after the start time.");
      return;
    }
    try {
      await createReservation(
        { charger_id: form.charger_id, start_time: start.toISOString(), end_time: end.toISOString() },
        token,
      );
      const charger = station.chargers.find((c) => c.id === form.charger_id);
      setBooked({ charger: charger ? chargerLabel(charger) : "", start, end });
      setError("");
      setForm((f) => ({ ...f, start: "", end: "" }));
      onBooked();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <details open className="sidebar-section" ref={ref}>
      <summary className="section-summary">Book a charger</summary>
      <div className="section-body">
        <p className="selected-station-name">{station.name}</p>
        <form onSubmit={reserve}>
          <div className="field">
            <label htmlFor="book-charger">Charger</label>
            <select
              id="book-charger"
              value={form.charger_id}
              onChange={(e) => setForm({ ...form, charger_id: e.target.value })}
              required
            >
              {station.chargers.map((c) => (
                <option key={c.id} value={c.id}>
                  {chargerLabel(c)}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="book-start">Start</label>
            <input
              id="book-start"
              type="datetime-local"
              value={form.start}
              min={toDatetimeInput(new Date())}
              onChange={(e) => setForm({ ...form, start: e.target.value })}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="book-end">End</label>
            <input
              id="book-end"
              type="datetime-local"
              value={form.end}
              min={form.start || toDatetimeInput(new Date())}
              onChange={(e) => setForm({ ...form, end: e.target.value })}
              required
            />
          </div>
          <button type="submit" className="btn-primary btn-block">
            Reserve
          </button>
        </form>
        {booked && (
          <div className="reservation-banner" role="status">
            <strong>Booked</strong> {station.name}, {booked.charger}
            <br />
            {formatDateTime(booked.start)} to {formatDateTime(booked.end)}
          </div>
        )}
        {error && (
          <p className="status reservation-error" role="alert">
            {error}
          </p>
        )}

        <SlotFinder
          station={station}
          onUseSlot={(slot) =>
            setForm({
              charger_id: slot.charger_id,
              start: toDatetimeInput(new Date(slot.suggested_start)),
              end: toDatetimeInput(new Date(slot.suggested_end)),
            })
          }
        />
      </div>
    </details>
  );
});

export default BookingPanel;
