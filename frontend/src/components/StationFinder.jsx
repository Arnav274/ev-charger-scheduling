import { useRef, useState } from "react";

export default function StationFinder({ stations: finder, onSelectStation, onSearch }) {
  const { draft, setDraft, stations, search, setStatus } = finder;
  const [filter, setFilter] = useState("");
  const [locating, setLocating] = useState(false);
  // The geolocation callback runs after the permission prompt, so it reads the
  // draft through a ref to keep anything typed in the meantime (the radius, say).
  const draftRef = useRef(draft);
  draftRef.current = draft;

  function locateMe() {
    setLocating(true);
    setStatus("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocating(false);
        const located = {
          ...draftRef.current,
          lat: coords.latitude.toFixed(5),
          lon: coords.longitude.toFixed(5),
        };
        setDraft(located);
        onSearch();
        search(located);
      },
      () => {
        setLocating(false);
        setStatus("Location access was denied, so the search stays where it was.");
      },
    );
  }

  const field = (key) => ({
    value: draft[key],
    onChange: (e) => setDraft({ ...draft, [key]: e.target.value }),
  });
  const matching = stations.filter((s) => s.name.toLowerCase().includes(filter.toLowerCase()));

  return (
    <details open className="sidebar-section">
      <summary className="section-summary">Find stations</summary>
      <div className="section-body">
        <div className="field">
          <label htmlFor="centre-lat">Latitude</label>
          <input id="centre-lat" type="text" inputMode="decimal" {...field("lat")} />
        </div>
        <div className="field">
          <label htmlFor="centre-lon">Longitude</label>
          <input id="centre-lon" type="text" inputMode="decimal" {...field("lon")} />
        </div>
        <div className="field">
          <label htmlFor="radius">Radius (km)</label>
          <input id="radius" type="text" inputMode="decimal" {...field("radius")} />
        </div>
        <div className="find-buttons">
          <button
            type="button"
            className="btn-primary btn-block"
            onClick={() => {
              onSearch();
              search();
            }}
          >
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
