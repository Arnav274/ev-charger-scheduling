import { useRef, useState } from "react";

// The inputs hold text while the user types; they are only parsed and applied on
// search, so a cleared or half-typed field never becomes 0 (the Gulf of Guinea).
// Strict: Number("51,5") and Number("51.5abc") are NaN, where parseFloat would
// quietly read them as 51 and 51.5.
const toNumber = (text) => (String(text).trim() === "" ? NaN : Number(text));

function parseSearch(draft) {
  const lat = toNumber(draft.lat);
  const lon = toNumber(draft.lon);
  const radius = toNumber(draft.radius);
  if (!Number.isFinite(lat) || lat < -90 || lat > 90)
    return { error: "Enter a latitude between -90 and 90." };
  if (!Number.isFinite(lon) || lon < -180 || lon > 180)
    return { error: "Enter a longitude between -180 and 180." };
  if (!Number.isFinite(radius) || radius < 0.5 || radius > 50)
    return { error: "Enter a radius between 0.5 and 50 km." };
  return { centre: { lat, lon }, radius };
}

export default function StationFinder({ stations: finder, onSelectStation }) {
  const { centre, setCentre, radiusKm, setRadiusKm, stations, search, setStatus } = finder;
  const [draft, setDraft] = useState({
    lat: String(centre.lat),
    lon: String(centre.lon),
    radius: String(radiusKm),
  });
  // The geolocation callback runs later, so it reads the draft through a ref to
  // pick up anything typed while the browser was asking for permission.
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const [filter, setFilter] = useState("");
  const [locating, setLocating] = useState(false);

  function apply(parsed) {
    setCentre(parsed.centre);
    setRadiusKm(parsed.radius);
    search(parsed.centre, parsed.radius);
  }

  function findNearby() {
    const parsed = parseSearch(draft);
    if (parsed.error) setStatus(parsed.error);
    else apply(parsed);
  }

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
        const parsed = parseSearch(located);
        if (parsed.error) setStatus(parsed.error);
        else apply(parsed);
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
          <button type="button" className="btn-primary btn-block" onClick={findNearby}>
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
