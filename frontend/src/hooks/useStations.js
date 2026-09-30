import { useCallback, useEffect, useRef, useState } from "react";

import { fetchNearbyStations } from "../api";

export const DEFAULT_CENTRE = { lat: 51.5074, lon: -0.1278 };
export const DEFAULT_RADIUS_KM = 5;
const STARTUP_RETRIES = 5;

// Plain decimals only: Number() alone would also accept "0x32", "5e1" and "".
const DECIMAL = /^\s*-?\d+(\.\d+)?\s*$/;

// Turns the text in the search fields into numbers. Range checks are left to
// the API, whose validation messages the client already displays.
export function parseSearch(draft) {
  const fields = { lat: "Latitude", lon: "Longitude", radius: "Radius" };
  for (const [key, label] of Object.entries(fields)) {
    if (!DECIMAL.test(draft[key])) return { error: `${label} must be a number, like 51.5074.` };
  }
  return { centre: { lat: Number(draft.lat), lon: Number(draft.lon) }, radius: Number(draft.radius) };
}

export default function useStations() {
  // What the user has typed. Searching and recommending both read it, so they
  // always use the same place.
  const [draft, setDraft] = useState({
    lat: String(DEFAULT_CENTRE.lat),
    lon: String(DEFAULT_CENTRE.lon),
    radius: String(DEFAULT_RADIUS_KM),
  });
  // Where the stations on the map were found; only changes when a search succeeds.
  const [centre, setCentre] = useState(DEFAULT_CENTRE);
  const [stations, setStations] = useState([]);
  const [status, setStatus] = useState("Loading stations…");
  // Only the most recent search may update the list, however the responses arrive.
  const latestRequest = useRef(0);

  const load = useCallback(async (at, radius) => {
    const request = ++latestRequest.current;
    try {
      const data = await fetchNearbyStations(at.lat, at.lon, radius);
      if (request !== latestRequest.current) return;
      setCentre(at);
      setStations(data);
      setStatus(`${data.length} stations within ${radius} km.`);
    } catch (err) {
      if (request === latestRequest.current) setStatus(err.message);
      throw err;
    }
  }, []);

  // Searches wherever `nextDraft` (by default, what is typed) points.
  const search = useCallback(
    (nextDraft = draft) => {
      const parsed = parseSearch(nextDraft);
      if (parsed.error) {
        setStatus(parsed.error);
        return;
      }
      load(parsed.centre, parsed.radius).catch(() => {});
    },
    [draft, load],
  );

  // On first load the backend may still be starting, so retry for a few seconds,
  // giving up as soon as the user runs a search of their own.
  useEffect(() => {
    let timer;
    const attempt = (remaining) => {
      const pending = load(DEFAULT_CENTRE, DEFAULT_RADIUS_KM);
      const request = latestRequest.current; // load() claims its number synchronously
      pending.catch(() => {
        if (remaining === 0 || latestRequest.current !== request) return;
        setStatus("Waiting for the backend to start…");
        timer = setTimeout(() => {
          if (latestRequest.current === request) attempt(remaining - 1);
        }, 1000);
      });
    };
    attempt(STARTUP_RETRIES);
    return () => {
      clearTimeout(timer);
      latestRequest.current += 1; // drop any response still in flight
    };
  }, [load]);

  return { draft, setDraft, centre, stations, status, setStatus, search };
}
