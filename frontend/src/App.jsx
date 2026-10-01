import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";

import { fetchStation, fetchVehicles, getMyReservations, getRecommendations } from "./api";
import AccountPanel from "./components/AccountPanel";
import BookingPanel from "./components/BookingPanel";
import RecommendationList from "./components/RecommendationList";
import StationFinder from "./components/StationFinder";
import StationMap from "./components/StationMap";
import StrategyPicker from "./components/StrategyPicker";
import EthicsPanel from "./EthicsPanel";
import useAuth from "./hooks/useAuth";
import useLatestRequest from "./hooks/useLatestRequest";
import useStations, { parseSearch } from "./hooks/useStations";

// The charts library is only needed on the Results tab, so it loads on demand.
const StatsDashboard = lazy(() => import("./StatsDashboard"));

const TABS = [
  { id: "map", label: "Map" },
  { id: "stats", label: "Results" },
  { id: "privacy", label: "Privacy & ethics" },
];

function scrollTo(ref) {
  requestAnimationFrame(() => ref.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }));
}

export default function App() {
  const [tab, setTab] = useState("map");
  const auth = useAuth();
  const finder = useStations();

  const [strategy, setStrategy] = useState(null);
  // Kept with the strategy that produced them, so the heading never labels stale results.
  const [results, setResults] = useState({ strategy: null, items: [], error: "" });
  const [battery, setBattery] = useState({ level: "", capacity: "" });
  const [selectedStation, setSelectedStation] = useState(null);
  const [showHotspots, setShowHotspots] = useState(false);
  const [vehicles, setVehicles] = useState([]);
  const [selectedVehicleId, setSelectedVehicleId] = useState(null);
  const [reservations, setReservations] = useState([]);

  // Only the most recent recommendation request may update the results.
  const recommendations = useLatestRequest();
  const resultsRef = useRef(null);
  const bookingRef = useRef(null);
  const accountRef = useRef(null);

  const { token } = auth;
  const refreshVehicles = useCallback(() => {
    fetchVehicles(token)
      .then(setVehicles)
      .catch(() => setVehicles([]));
  }, [token]);
  const refreshReservations = useCallback(() => {
    getMyReservations(token)
      .then(setReservations)
      .catch(() => setReservations([]));
  }, [token]);

  useEffect(() => {
    if (!token) {
      setVehicles([]);
      setReservations([]);
      setSelectedVehicleId(null);
      return;
    }
    refreshVehicles();
    refreshReservations();
  }, [token, refreshVehicles, refreshReservations]);

  // A search for somewhere else makes the current recommendations, and any on
  // their way, out of date.
  function clearResults() {
    recommendations.cancel();
    setResults({ strategy: null, items: [], error: "" });
  }

  async function recommend(algorithm) {
    // Recommend from what is typed in the search fields, the same place a search would use.
    const where = parseSearch(finder.draft);
    if (where.error) {
      recommendations.cancel(); // an earlier request must not land after this error
      finder.setStatus(where.error);
      return;
    }
    setStrategy(algorithm);
    const request = recommendations.claim();
    // Keep the station list and map in step with where the recommendations are for.
    finder.showStationsAround(where);
    const payload = {
      origin_lat: where.centre.lat,
      origin_lon: where.centre.lon,
      radius_km: where.radius,
      algorithm,
      top_k: 5,
    };
    if (battery.level !== "" && battery.capacity !== "") {
      payload.battery_level_percent = Number(battery.level);
      payload.battery_capacity_kwh = Number(battery.capacity);
    }
    try {
      const items = await getRecommendations(payload);
      if (!recommendations.isLatest(request)) return; // a newer request superseded this one
      setResults({ strategy: algorithm, items, error: "" });
      scrollTo(resultsRef);
    } catch (err) {
      if (!recommendations.isLatest(request)) return;
      // Shown with the results rather than in the search status line, which the
      // station reload running alongside this request may also update.
      setResults({ strategy: algorithm, items: [], error: err.message });
    }
  }

  async function selectStation(stationId) {
    try {
      setSelectedStation(await fetchStation(stationId));
      scrollTo(bookingRef);
    } catch (err) {
      finder.setStatus(err.message);
    }
  }

  return (
    <div className="layout">
      <div className="sidebar">
        <h1 className="sidebar-title">EV Charger Scheduling</h1>

        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              className={tab === t.id ? "active" : ""}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "privacy" && <EthicsPanel />}
        {tab === "stats" && (
          <Suspense fallback={<p className="status">Loading results…</p>}>
            <StatsDashboard />
          </Suspense>
        )}
        {tab === "map" && (
          <>
            <p className="status global-status" role="status">
              {finder.status}
            </p>
            <StationFinder stations={finder} onSelectStation={selectStation} onSearch={clearResults} />
            <StrategyPicker
              active={strategy}
              onPick={recommend}
              battery={battery}
              onBatteryChange={setBattery}
            />
            <RecommendationList
              ref={resultsRef}
              strategy={results.strategy}
              recommendations={results.items}
              error={results.error}
              onSelectStation={selectStation}
            />
            {selectedStation && (
              <BookingPanel
                key={selectedStation.id}
                ref={bookingRef}
                station={selectedStation}
                token={token}
                onBooked={() => {
                  refreshReservations();
                  if (accountRef.current) accountRef.current.open = true;
                }}
              />
            )}
            <AccountPanel
              ref={accountRef}
              auth={auth}
              vehicles={vehicles}
              onVehiclesChanged={refreshVehicles}
              selectedVehicleId={selectedVehicleId}
              onSelectVehicle={(v) => {
                setSelectedVehicleId(v.id);
                setBattery((b) => ({ ...b, capacity: String(v.battery_kwh) }));
              }}
              reservations={reservations}
              onCancelled={refreshReservations}
            />
            <label className="checkbox sidebar-section">
              <input
                type="checkbox"
                checked={showHotspots}
                onChange={(e) => setShowHotspots(e.target.checked)}
              />
              Shade recommended stations by chance of queueing
            </label>
          </>
        )}
      </div>

      <StationMap
        stations={finder.stations}
        recommendations={results.items}
        showHotspots={showHotspots}
        onSelectStation={selectStation}
      />
    </div>
  );
}
