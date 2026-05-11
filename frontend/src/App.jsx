import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import {
  createReservation,
  fetchNearbyStations,
  fetchExperimentSummary,
  fetchStation,
  getRecommendations,
  loginUser,
  registerUser,
} from "./api";
import EthicsPanel from "./EthicsPanel";
import StatsDashboard from "./StatsDashboard";

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
  const reserveSectionRef = useRef(null);

  useEffect(() => {
    if (accessToken) localStorage.setItem(TOKEN_KEY, accessToken);
    else localStorage.removeItem(TOKEN_KEY);
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

  async function onSelectStation(stationId) {
    try {
      const data = await fetchStation(stationId);
      setSelectedStation(data);
      setForm((prev) => ({ ...prev, charger_id: data.chargers[0]?.id || "" }));
      setReservationStatus("");
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
      const data = await getRecommendations({
        origin_lat: center.lat,
        origin_lon: center.lon,
        radius_km: radiusKm,
        algorithm,
        top_k: 5,
      });
      setRecommendations(data);
      setStatus(`Recommendations computed with ${algorithm}.`);
    } catch (err) {
      setStatus(err.message);
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
    } catch (err) {
      setReservationStatus(err.message);
    }
  }

  const position = useMemo(() => [center.lat, center.lon], [center]);

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
                </div>
              )}
              {authStatus ? <p className="status">{authStatus}</p> : null}
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
            </div>
            <p className="status">{status}</p>

            <h3>Stations</h3>
            <p className="stats-note">
              Using local cached OpenChargeMap sample (2 stations). Live ingestion requires `OPENCHARGEMAP_API_KEY`.
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
                  {r.station_name} | {r.distance_km.toFixed(2)} km | {r.predicted_wait_min.toFixed(2)} min wait
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
              </section>
            )}
          </>
        )}
      </div>

      <MapContainer center={position} zoom={12} style={{ height: "100vh", width: "100%" }}>
        <FitBoundsToStations stations={stations} />
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
