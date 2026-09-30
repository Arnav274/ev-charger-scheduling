import { useCallback, useEffect, useRef, useState } from "react";

import { fetchNearbyStations } from "../api";

export const DEFAULT_CENTRE = { lat: 51.5074, lon: -0.1278 };
export const DEFAULT_RADIUS_KM = 5;
const STARTUP_RETRIES = 5;

export default function useStations() {
  const [centre, setCentre] = useState(DEFAULT_CENTRE);
  const [radiusKm, setRadiusKm] = useState(DEFAULT_RADIUS_KM);
  const [stations, setStations] = useState([]);
  const [status, setStatus] = useState("Loading stations…");
  // Only the most recent search may update the list, however the responses arrive.
  const latestRequest = useRef(0);

  const search = useCallback(async (at, radius) => {
    const request = ++latestRequest.current;
    try {
      const data = await fetchNearbyStations(at.lat, at.lon, radius);
      if (request !== latestRequest.current) return;
      setStations(data);
      setStatus(`${data.length} stations within ${radius} km.`);
    } catch (err) {
      if (request === latestRequest.current) setStatus(err.message);
      throw err;
    }
  }, []);

  // On first load the backend may still be starting, so retry for a few seconds,
  // giving up as soon as the user runs a search of their own.
  useEffect(() => {
    let timer;
    const attempt = (remaining) => {
      const pending = search(DEFAULT_CENTRE, DEFAULT_RADIUS_KM);
      const request = latestRequest.current; // search() claims its number synchronously
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
  }, [search]);

  const searchSafely = useCallback((at, radius) => search(at, radius).catch(() => {}), [search]);

  return { centre, setCentre, radiusKm, setRadiusKm, stations, status, setStatus, search: searchSafely };
}
