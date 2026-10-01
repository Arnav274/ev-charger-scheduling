import { useCallback, useEffect, useRef, useState } from "react";

import { fetchNearbyStations } from "../api";
import useLatestRequest from "./useLatestRequest";

export const DEFAULT_CENTRE = { lat: 51.5074, lon: -0.1278 };
export const DEFAULT_RADIUS_KM = 5;
const STARTUP_RETRIES = 5;

// Plain decimals such as 51.5, -0.12, .5 or 5. Number() alone would also accept "0x32" and "5e1".
const DECIMAL = /^\s*[+-]?(\d+\.?\d*|\.\d+)\s*$/;
const FIELDS = [
  ["lat", "Latitude", "51.5074"],
  ["lon", "Longitude", "-0.1278"],
  ["radius", "Radius", "5"],
];

// Turns the text in the search fields into numbers. Range checks are left to
// the API, whose validation messages the client already displays.
export function parseSearch(draft) {
  for (const [key, label, example] of FIELDS) {
    if (!DECIMAL.test(draft[key])) return { error: `${label} must be a number, like ${example}.` };
  }
  return { centre: { lat: Number(draft.lat), lon: Number(draft.lon) }, radius: Number(draft.radius) };
}

const sameSearch = (a, b) =>
  a && b && a.centre.lat === b.centre.lat && a.centre.lon === b.centre.lon && a.radius === b.radius;

export default function useStations() {
  // What the user has typed. Searching and recommending both read it, so they
  // always use the same place.
  const [draft, setDraft] = useState({
    lat: String(DEFAULT_CENTRE.lat),
    lon: String(DEFAULT_CENTRE.lon),
    radius: String(DEFAULT_RADIUS_KM),
  });
  const [stations, setStations] = useState([]);
  const [status, setStatus] = useState("Loading stations…");
  const requests = useLatestRequest();
  // The search the listed stations came from, and the one in flight, if any.
  // A repeat of either needs no new request.
  const shown = useRef(null);
  const pending = useRef(null);

  const load = useCallback(
    async (where, request = requests.claim()) => {
      pending.current = where;
      try {
        const data = await fetchNearbyStations(where.centre.lat, where.centre.lon, where.radius);
        if (!requests.isLatest(request)) return;
        pending.current = null;
        shown.current = where;
        setStations(data);
        setStatus(`${data.length} stations within ${where.radius} km.`);
      } catch (err) {
        if (requests.isLatest(request)) {
          pending.current = null;
          setStatus(err.message);
        }
        throw err;
      }
    },
    [requests],
  );

  // Searches wherever `nextDraft` (by default, what is typed) points. Returns the
  // parsed location, or null if the input is invalid.
  const search = useCallback(
    (nextDraft = draft) => {
      const where = parseSearch(nextDraft);
      if (where.error) {
        requests.cancel(); // an earlier search must not land after this error
        pending.current = null;
        setStatus(where.error);
        return null;
      }
      load(where).catch(() => {});
      return where;
    },
    [draft, load, requests],
  );

  // Makes sure the listed stations match `where`, searching again only if they do not.
  const showStationsAround = useCallback(
    (where) => {
      if (!sameSearch(where, shown.current) && !sameSearch(where, pending.current)) {
        load(where).catch(() => {});
      }
    },
    [load],
  );

  // On first load the backend may still be starting, so retry for a few seconds,
  // giving up as soon as the user runs a search of their own.
  useEffect(() => {
    let timer;
    const initial = { centre: DEFAULT_CENTRE, radius: DEFAULT_RADIUS_KM };
    const attempt = (remaining) => {
      const request = requests.claim();
      load(initial, request).catch(() => {
        if (remaining === 0 || !requests.isLatest(request)) return;
        setStatus("Waiting for the backend to start…");
        timer = setTimeout(() => {
          if (requests.isLatest(request)) attempt(remaining - 1);
        }, 1000);
      });
    };
    attempt(STARTUP_RETRIES);
    return () => {
      clearTimeout(timer);
      requests.cancel(); // drop any response still in flight
    };
  }, [load, requests]);

  return { draft, setDraft, stations, status, setStatus, search, showStationsAround };
}
