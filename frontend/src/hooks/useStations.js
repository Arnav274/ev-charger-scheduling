import { useCallback, useEffect, useState } from "react";

import { fetchNearbyStations } from "../api";

export const DEFAULT_CENTRE = { lat: 51.5074, lon: -0.1278 };
const STARTUP_RETRIES = 5;

export default function useStations() {
  const [centre, setCentre] = useState(DEFAULT_CENTRE);
  const [radiusKm, setRadiusKm] = useState(5);
  const [stations, setStations] = useState([]);
  const [status, setStatus] = useState("Loading stations…");

  const load = useCallback(async (lat, lon, radius) => {
    const data = await fetchNearbyStations(lat, lon, radius);
    setStations(data);
    setStatus(`${data.length} stations within ${radius} km.`);
  }, []);

  const search = useCallback(
    (at = centre) => load(at.lat, at.lon, radiusKm).catch((err) => setStatus(err.message)),
    [centre, radiusKm, load],
  );

  // On first load the backend may still be starting, so retry for a few seconds.
  useEffect(() => {
    let cancelled = false;
    let timer;
    const attempt = (remaining) =>
      load(DEFAULT_CENTRE.lat, DEFAULT_CENTRE.lon, 5).catch((err) => {
        if (cancelled) return;
        if (remaining === 0) {
          setStatus(err.message);
          return;
        }
        setStatus("Waiting for the backend to start…");
        timer = setTimeout(() => attempt(remaining - 1), 1000);
      });
    attempt(STARTUP_RETRIES);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [load]);

  return { centre, setCentre, radiusKm, setRadiusKm, stations, status, setStatus, search };
}
