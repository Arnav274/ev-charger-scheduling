import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import {
  createReservation,
  createVehicle,
  fetchNearbyStations,
  fetchExperimentSummary,
  fetchStation,
  fetchVehicles,
  getMyReservations,
  getRecommendations,
  loginUser,
  registerUser,
  suggestSlot,
} from "./api";
import EthicsPanel from "./EthicsPanel";
import StatsDashboard from "./StatsDashboard";
import HeatmapLayer from "./HeatmapLayer";

const defaultCenter = { lat: 51.5074, lon: -0.1278 };
const TOKEN_KEY = "ev_portfolio_access_token";
const toLocalDatetimeInput = (d) => {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

function FitBoundsToStations({ stations }) {
  const map = useMap();

  useEffect(() => {
    if (!stations.length) return;
    const bounds = L.latLngBounds(stations.map((s) => [s.lat, s.lon]));
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
  }, [stations, map]);

  return null;
}

function App() {
  const [tab, setTab] = useState("map");
  const [center, setCenter] = useState(defaultCenter);
  const [radiusKm, setRadiusKm] = useState(5);
  const [stations, setStations] = useState([]);
  const [selectedStation, setSelectedStation] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [status, setStatus] = useState("Ready.");
  const [form, setForm] = useState({ charger_id: "", start_time: "", end_time: "" });
  const [accessToken, setAccessToken] = useState(() => localStorage.getItem(TOKEN_KEY) || "");
  const [regs, setRegs] = useState({ email: "", password: "" });
  const [statsRows, setStatsRows] = useState([]);
  const [statsLoadError, setStatsLoadError] = useState("");
  const [authStatus, setAuthStatus] = useState("");
  const [reservationStatus, setReservationStatus] = useState("");
  const [showHotspots, setShowHotspots] = useState(false);
  const [slotArrival, setSlotArrival] = useState("");
  const [slotDuration, setSlotDuration] = useState("60");
  const [suggestedSlots, setSuggestedSlots] = useState([]);
  const [slotStatus, setSlotStatus] = useState("");
  const [batteryLevel, setBatteryLevel] = useState("");
  const [batteryCapacity, setBatteryCapacity] = useState("");
  const [supplementaryStations, setSupplementaryStations] = useState(new Map());
  const [fetchingHotspots, setFetchingHotspots] = useState(false);
  const [vehicles, setVehicles] = useState([]);
  const [vehicleForm, setVehicleForm] = useState({ make_model: "", battery_kwh: "" });
  const [myReservations, setMyReservations] = useState([]);
  const [selectedVehicleId, setSelectedVehicleId] = useState(null);
  const reserveSectionRef = useRef(null);

  useEffect(() => {
    if (accessToken) localStorage.setItem(TOKEN_KEY, accessToken);
    else localStorage.removeItem(TOKEN_KEY);
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) { setVehicles([]); setSelectedVehicleId(null); return; }
    fetchVehicles(accessToken).then(setVehicles).catch(() => {});
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) { setMyReservations([]); return; }
    getMyReservations(accessToken).then(setMyReservations).catch(() => {});
  }, [accessToken]);

  async function loadNearby() {
    try {
      const data = await fetchNearbyStations(center.lat, center.lon, radiusKm);
      setStations(data);
      setStatus(`Loaded ${data.length} stations.`);
    } catch (err) {
      setStatus(err.message);
    }
  }

  useEffect(() => {
    loadNearby();
  }, []);

  useEffect(() => {
    if (tab !== "stats") return;
    fetchExperimentSummary()
      .then((data) => {
        setStatsRows(data.rows || []);
        setStatsLoadError("");
      })
      .catch((err) => setStatsLoadError(err.message || "fetch failed"));
  }, [tab]);

  useEffect(() => {
    if (!recommendations.length) return;
    const stationById = new Map(stations.map((s) => [String(s.id), s]));
    const missing = recommendations
      .map((r) => String(r.station_id))
      .filter((id) => !stationById.has(id) && !supplementaryStations.has(id));
    if (!missing.length) return;

    setFetchingHotspots(true);
    Promise.all(missing.map((id) => fetchStation(id).then((st) => [id, st]).catch(() => null)))
      .then((results) => {
        setSupplementaryStations((prev) => {
          const next = new Map(prev);
          results.forEach((entry) => { if (entry) next.set(entry[0], entry[1]); });
          return next;
        });
      })
      .finally(() => setFetchingHotspots(false));
  }, [recommendations, stations, supplementaryStations]);

  async function onSuggestSlot() {
    if (!selectedStation || !slotArrival) {
      setSlotStatus("Choose a desired arrival time.");
      return;
    }
    const dur = parseInt(slotDuration, 10);
    if (!dur || dur <= 0) {
      setSlotStatus("Enter a positive duration.");
      return;
    }
    try {
      setSlotStatus("Searching…");
      setSuggestedSlots([]);
      const data = await suggestSlot(selectedStation.id, {
        desired_arrival: new Date(slotArrival).toISOString(),
        duration_minutes: dur,
      });
      if (data.length === 0) {
        setSlotStatus("No slot found within 4 hours of the desired arrival.");
      } else {
        setSuggestedSlots(data);
        setSlotStatus("");
      }
    } catch (err) {
      setSlotStatus(err.message);
    }
  }

  async function onSelectStation(stationId) {
    try {
      const data = await fetchStation(stationId);
      setSelectedStation(data);
      setForm((prev) => ({ ...prev, charger_id: data.chargers[0]?.id || "" }));
      setReservationStatus("");
      setSuggestedSlots([]);
      setSlotStatus("");
      requestAnimationFrame(() => {
        if (typeof reserveSectionRef.current?.scrollIntoView === "function") {
          reserveSectionRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    } catch (err) {
      setStatus(err.message);
    }
  }

  async function onRecommend(algorithm) {
    try {
      const payload = {
        origin_lat: center.lat,
        origin_lon: center.lon,
        radius_km: radiusKm,
        algorithm,
        top_k: 5,
        arrival_window_minutes: 15,
      };
      if (batteryLevel !== "" && batteryCapacity !== "") {
        payload.battery_level_percent = Number(batteryLevel);
        payload.battery_capacity_kwh = Number(batteryCapacity);
      }
      const data = await getRecommendations(payload);
      setRecommendations(data);
      setStatus(`Recommendations computed with ${algorithm}.`);
    } catch (err) {
      setStatus(err.message);
    }
  }

  async function onSaveVehicle(e) {
    e.preventDefault();
    try {
      await createVehicle({ make_model: vehicleForm.make_model, battery_kwh: Number(vehicleForm.battery_kwh) }, accessToken);
      setVehicleForm({ make_model: "", battery_kwh: "" });
      const updated = await fetchVehicles(accessToken);
      setVehicles(updated);
    } catch (err) {
      setAuthStatus(err.message || "Failed to save vehicle. Please try again.");
    }
  }

  async function onRegister(e) {
    e.preventDefault();
    if (!regs.password || regs.password.length < 8) {
      setAuthStatus("Password must be at least 8 characters.");
      return;
    }
    try {
      const tok = await registerUser(regs.email, regs.password);
      setAccessToken(tok.access_token);
      setAuthStatus("Registered and signed in.");
    } catch (err) {
      setAuthStatus(err.message);
    }
  }

  async function onLogin(e) {
    e.preventDefault();
    try {
      const tok = await loginUser(regs.email, regs.password);
      setAccessToken(tok.access_token);
      setAuthStatus("Signed in.");
    } catch (err) {
      setAuthStatus(err.message);
    }
  }

  async function onReserve(e) {
    e.preventDefault();
    if (!accessToken) {
      setReservationStatus("Sign in before reserving.");
      return;
    }
    if (!form.start_time || !form.end_time) {
      setReservationStatus("Please choose both start and end date/time.");
      return;
    }
    const start = new Date(form.start_time);
    const end = new Date(form.end_time);
    const now = new Date();
    if (start < now) {
      setReservationStatus("Start time must be in the future.");
      return;
    }
    if (end <= start) {
      setReservationStatus("End time must be after start time.");
      return;
    }
    try {
      await createReservation(
        {
          charger_id: form.charger_id,
          start_time: start.toISOString(),
          end_time: end.toISOString(),
        },
        accessToken,
      );
      setReservationStatus("Reservation created.");
      setForm((prev) => ({ ...prev, start_time: "", end_time: "" }));
      getMyReservations(accessToken).then(setMyReservations).catch(() => {});
    } catch (err) {
      setReservationStatus(err.message);
    }
  }

  const position = useMemo(() => [center.lat, center.lon], [center]);
  const hotspotPoints = useMemo(() => {
    if (!recommendations.length) return [];
    const stationById = new Map(stations.map((s) => [String(s.id), s]));
    const byId = new Map();
    recommendations.forEach((r) => {
      const st = stationById.get(String(r.station_id)) ?? supplementaryStations.get(String(r.station_id));
      if (!st) return;
      const intensity = Math.max(0, Math.min(1, Number(r.probability_of_delay || 0)));
      byId.set(String(r.station_id), {
        lat: st.lat,
        lon: st.lon,
        intensity,
        label: r.station_name,
      });
    });
    return Array.from(byId.values());
  }, [recommendations, stations, supplementaryStations]);

  return (
    <div className="layout">
      <div className="sidebar">
        <h2>EV Reservation Platform</h2>
        <div className="tabs">
          <button type="button" className={tab === "map" ? "active" : ""} onClick={() => setTab("map")}>
            Map
          </button>
          <button type="button" className={tab === "privacy" ? "active" : ""} onClick={() => setTab("privacy")}>
            Privacy & ethics
          </button>
          <button type="button" className={tab === "stats" ? "active" : ""} onClick={() => setTab("stats")}>
            Stats
          </button>
        </div>

        {tab === "privacy" && <EthicsPanel />}

        {tab === "stats" && <StatsDashboard rows={statsRows} loadError={statsLoadError} />}

        {tab === "map" && (
          <>
            <section className="auth-box">
              <h3>Account</h3>
              {!accessToken ? (
                <>
                  <p className="status small">JWT required for reservations. Try demo credential from README seed script.</p>
                  <form className="auth-form" onSubmit={onRegister}>
                    <div className="field">
                      <label>Email</label>
                      <input value={regs.email} onChange={(e) => setRegs({ ...regs, email: e.target.value })} type="email" required />
                    </div>
                    <div className="field">
                      <label>Password (min 8)</label>
                      <input value={regs.password} onChange={(e) => setRegs({ ...regs, password: e.target.value })} type="password" required />
                    </div>
                    <div className="buttons">
                      <button type="submit">Register</button>
                      <button type="button" onClick={onLogin}>
                        Sign in
                      </button>
                    </div>
                  </form>
                </>
              ) : (
                <div className="auth-status">
                  <p className="status">Authenticated (JWT in localStorage).</p>
                  <button type="button" onClick={() => setAccessToken("")}>
                    Sign out
                  </button>
                  <h4>My Vehicle</h4>
                  <form onSubmit={onSaveVehicle}>
                    <div className="field">
                      <label>Make / Model</label>
                      <input
                        type="text"
                        maxLength={120}
                        placeholder="e.g. Tesla Model 3"
                        value={vehicleForm.make_model}
                        onChange={(e) => setVehicleForm((f) => ({ ...f, make_model: e.target.value }))}
                        required
                      />
                    </div>
                    <div className="field">
                      <label>Battery (kWh)</label>
                      <input
                        type="number"
                        min="0.1"
                        step="0.1"
                        placeholder="e.g. 75"
                        value={vehicleForm.battery_kwh}
                        onChange={(e) => setVehicleForm((f) => ({ ...f, battery_kwh: e.target.value }))}
                        required
                      />
                    </div>
                    <button type="submit">Save vehicle</button>
                  </form>
                  {vehicles.length > 0 && (
                    <ul>
                      {vehicles.map((v) => (
                        <li key={v.id}>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedVehicleId(v.id);
                              setBatteryCapacity(String(v.battery_kwh));
                            }}
                          >
                            {v.make_model} ({v.battery_kwh} kWh){selectedVehicleId === v.id ? " (selected)" : ""}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {authStatus ? <p className="status">{authStatus}</p> : null}
              {myReservations.length > 0 && (
                <div className="my-reservations">
                  <h4>My Reservations</h4>
                  <ul>
                    {myReservations.map((r) => {
                      const fmt = (iso) => {
                        const d = new Date(iso);
                        const dd = String(d.getDate()).padStart(2, "0");
                        const mm = String(d.getMonth() + 1).padStart(2, "0");
                        const yyyy = d.getFullYear();
                        const hh = String(d.getHours()).padStart(2, "0");
                        const min = String(d.getMinutes()).padStart(2, "0");
                        return `${dd}/${mm}/${yyyy} ${hh}:${min}`;
                      };
                      return (
                        <li key={r.id}>
                          <strong>{r.station_name}</strong> — {r.charger_name}<br />
                          {fmt(r.start_time)} → {fmt(r.end_time)}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </section>

            <div className="field">
              <label>Latitude</label>
              <input
                type="number"
                value={center.lat}
                onChange={(e) => setCenter((c) => ({ ...c, lat: Number(e.target.value) }))}
              />
            </div>
            <div className="field">
              <label>Longitude</label>
              <input
                type="number"
                value={center.lon}
                onChange={(e) => setCenter((c) => ({ ...c, lon: Number(e.target.value) }))}
              />
            </div>
            <div className="field">
              <label>Radius (km)</label>
              <input type="number" value={radiusKm} onChange={(e) => setRadiusKm(Number(e.target.value))} />
            </div>
            <button onClick={loadNearby}>Find nearby stations</button>
            <div className="buttons">
              <button onClick={() => onRecommend("nearest")}>Nearest</button>
              <button onClick={() => onRecommend("cost_optimized")}>Cost</button>
              <button onClick={() => onRecommend("queue_aware")}>Queue-aware</button>
              <button onClick={() => onRecommend("static_queue")}>Static queue (baseline)</button>
              <button onClick={() => onRecommend("dijkstra")}>Dijkstra</button>
            </div>
            <p style={{fontSize: '0.8em', color: '#666', margin: '8px 0 2px'}}>
              For range-aware routing:
            </p>
            <div style={{border: '1px solid #ddd', borderRadius: '6px', padding: '8px 12px'}}>
              <div className="field">
                <label>Battery level (%)</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  placeholder="e.g. 40"
                  value={batteryLevel}
                  onChange={(e) => setBatteryLevel(e.target.value)}
                />
              </div>
              <div className="field">
                <label>Battery capacity (kWh)</label>
                <input
                  type="number"
                  min="1"
                  placeholder="e.g. 60"
                  value={batteryCapacity}
                  onChange={(e) => setBatteryCapacity(e.target.value)}
                />
              </div>
              <button onClick={() => onRecommend("range_aware")}>Range-aware</button>
            </div>
            <label className="checkbox">
              <input type="checkbox" checked={showHotspots} onChange={(e) => setShowHotspots(e.target.checked)} />
              Show hotspots (predictive delay)
            </label>
            <p className="status">{status}</p>
            {fetchingHotspots && <p className="status">Fetching hotspot locations…</p>}

            <h3>Stations</h3>
            <p className="stats-note">
              Station count depends on ingestion. For realistic experiments, ingest 50+ live stations with `OPENCHARGEMAP_API_KEY`.
            </p>
            <ul>
              {stations.map((s) => (
                <li key={s.id}>
                  <button onClick={() => onSelectStation(s.id)}>
                    {s.name}
                    {s.borough ? ` (${s.borough})` : ""}
                  </button>
                </li>
              ))}
            </ul>

            <h3>Recommendations</h3>
            <ol>
              {recommendations.map((r) => (
                <li key={r.station_id}>
                  {r.station_name} | {Number(r.travel_distance_km).toFixed(2)} km | {Number(r.travel_time_min).toFixed(1)} min travel |{" "}
                  {Number(r.predicted_wait_min).toFixed(2)} min wait | P(delay) {Number(r.probability_of_delay).toFixed(2)} |{" "}
                  occupancy {r.current_occupancy}
                </li>
              ))}
            </ol>

            {selectedStation && (
              <section ref={reserveSectionRef}>
                <h3>Reserve charger</h3>
                <p>{selectedStation.name}</p>
                <form onSubmit={onReserve}>
                  <div className="field">
                    <label>Charger</label>
                    <select
                      value={form.charger_id}
                      onChange={(e) => setForm({ ...form, charger_id: e.target.value })}
                      required
                    >
                      {selectedStation.chargers.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name} ({c.power_kw}kW)
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label>Start</label>
                    <input
                      type="datetime-local"
                      value={form.start_time}
                      onChange={(e) => setForm({ ...form, start_time: e.target.value })}
                      min={toLocalDatetimeInput(new Date())}
                      required
                    />
                  </div>
                  <div className="field">
                    <label>End</label>
                    <input
                      type="datetime-local"
                      value={form.end_time}
                      onChange={(e) => setForm({ ...form, end_time: e.target.value })}
                      min={form.start_time || toLocalDatetimeInput(new Date())}
                      required
                    />
                  </div>
                  <button type="submit">Reserve</button>
                </form>
                {reservationStatus ? <p className="status">{reservationStatus}</p> : null}

                <h3>Suggest charging slot</h3>
                <div className="field">
                  <label>Desired arrival</label>
                  <input
                    type="datetime-local"
                    value={slotArrival}
                    min={toLocalDatetimeInput(new Date())}
                    onChange={(e) => setSlotArrival(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label>Duration (minutes)</label>
                  <input
                    type="number"
                    min="30"
                    step="30"
                    value={slotDuration}
                    onChange={(e) => setSlotDuration(e.target.value)}
                  />
                </div>
                <button type="button" onClick={onSuggestSlot}>Find available slot</button>
                {slotStatus ? <p className="status">{slotStatus}</p> : null}
                {suggestedSlots.length > 0 && (
                  <ul>
                    {suggestedSlots.map((s) => {
                      const charger = selectedStation.chargers.find((c) => c.id === s.charger_id);
                      const chargerLabel = charger ? `${charger.name} (${charger.power_kw}kW)` : s.charger_id.slice(0, 8);
                      const start = new Date(s.suggested_start);
                      const end = new Date(s.suggested_end);
                      return (
                        <li key={s.charger_id} style={{ marginBottom: "0.5rem" }}>
                          <strong>{chargerLabel}</strong>:{" "}
                          {start.toLocaleString()} – {end.toLocaleString()}{" "}
                          {s.wait_from_desired_minutes > 0
                            ? `(wait ${Math.round(s.wait_from_desired_minutes)} min)`
                            : "(no wait)"}
                          <button
                            type="button"
                            style={{ marginLeft: "0.5rem" }}
                            onClick={() =>
                              setForm({
                                charger_id: s.charger_id,
                                start_time: toLocalDatetimeInput(start),
                                end_time: toLocalDatetimeInput(end),
                              })
                            }
                          >
                            Use this slot
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            )}
          </>
        )}
      </div>

      <MapContainer center={position} zoom={12} style={{ height: "100vh", width: "100%" }}>
        <FitBoundsToStations stations={stations} />
        <HeatmapLayer enabled={showHotspots} points={hotspotPoints} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {stations.map((s) => (
          <Marker key={s.id} position={[s.lat, s.lon]} eventHandlers={{ click: () => onSelectStation(s.id) }}>
            <Popup>{s.name}</Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}

export default App;
