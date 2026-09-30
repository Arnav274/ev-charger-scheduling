import { useState } from "react";

export default function StationFinder({ stations: finder, onSelectStation }) {
  const { centre, setCentre, radiusKm, setRadiusKm, stations, search, setStatus } = finder;
  const [filter, setFilter] = useState("");
  const [locating, setLocating] = useState(false);

  function locateMe() {
    setLocating(true);
    setStatus("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const here = { lat: coords.latitude, lon: coords.longitude };
        setCentre(here);
        setLocating(false);
        search(here);
      },
      () => {
        setLocating(false);
        setStatus("Location access was denied, so the search stays centred on London.");
      },
    );
  }

  const matching = stations.filter((s) => s.name.toLowerCase().includes(filter.toLowerCase()));

  return (
    <details open className="sidebar-section">
      <summary className="section-summary">Find stations</summary>
      <div className="section-body">
        <div className="field">
          <label htmlFor="centre-lat">Latitude</label>
          <input
            id="centre-lat"
            type="number"
            step="0.001"
            value={centre.lat}
            onChange={(e) => setCentre((c) => ({ ...c, lat: Number(e.target.value) }))}
          />
        </div>
        <div className="field">
          <label htmlFor="centre-lon">Longitude</label>
          <input
            id="centre-lon"
            type="number"
            step="0.001"
            value={centre.lon}
            onChange={(e) => setCentre((c) => ({ ...c, lon: Number(e.target.value) }))}
          />
        </div>
        <div className="field">
          <label htmlFor="radius">Radius (km)</label>
          <input
            id="radius"
            type="number"
            min="0.5"
            max="50"
            step="0.5"
            value={radiusKm}
            onChange={(e) => setRadiusKm(Number(e.target.value))}
          />
        </div>
        <div className="find-buttons">
          <button type="button" className="btn-primary btn-block" onClick={() => search()}>
            Find nearby stations
          </button>
          {"geolocation" in navigator && (
            <button type="button" className="btn-secondary btn-block" onClick={locateMe} disabled={locating}>
              {locating ? "Finding you…" : "Use my location"}
            </button>
          )}
        </div>

        {stations.length > 0 && (
          <>
            <div className="field">
              <label htmlFor="station-filter">Filter stations</label>
              <input
                id="station-filter"
                type="text"
                placeholder="Type to search…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="station-select">Select station</label>
              <select
                id="station-select"
                value=""
                onChange={(e) => e.target.value && onSelectStation(e.target.value)}
              >
                <option value="" disabled>
                  {matching.length} stations
                </option>
                {matching.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.borough ? ` (${s.borough})` : ""}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}
      </div>
    </details>
  );
}
