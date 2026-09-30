const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// FastAPI reports errors as {detail: string} or, for validation, {detail: [{loc, msg}]}.
export function errorMessage(detail, fallback) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]) {
    const first = detail[0];
    if (typeof first === "string") return first;
    const field = Array.isArray(first.loc) ? first.loc.slice(1).join(".") : "field";
    return `${field}: ${first.msg || "invalid value"}`;
  }
  return fallback;
}

async function request(path, { method = "GET", json, form, token, failure }) {
  const headers = {};
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form !== undefined) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    body = new URLSearchParams(form).toString();
  }
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, headers, body });
  } catch {
    throw new Error("Cannot reach the backend. Is `docker compose up` running?");
  }
  if (!res.ok) {
    // Error bodies are not always JSON (a proxy's HTML page, an empty 502).
    const payload = await Promise.resolve()
      .then(() => res.json())
      .catch(() => ({}));
    const error = new Error(errorMessage(payload.detail, failure));
    error.status = res.status;
    throw error;
  }
  return res.json();
}

export const registerUser = (email, password) =>
  request("/auth/register", { method: "POST", json: { email, password }, failure: "Registration failed" });

export const loginUser = (email, password) =>
  request("/auth/login", {
    method: "POST",
    form: { username: email, password },
    failure: "Sign-in failed",
  });

export const fetchNearbyStations = (lat, lon, radiusKm) =>
  request(`/stations/nearby?lat=${lat}&lon=${lon}&radius_km=${radiusKm}`, {
    failure: "Could not load nearby stations",
  });

export const fetchStation = (stationId) =>
  request(`/stations/${stationId}`, { failure: "Could not load the station" });

export const suggestSlot = (stationId, payload) =>
  request(`/stations/${stationId}/suggest-slot`, {
    method: "POST",
    json: payload,
    failure: "Could not search for a slot",
  });

export const getRecommendations = (payload) =>
  request("/recommendations", { method: "POST", json: payload, failure: "Could not get recommendations" });

export const createReservation = (payload, token) =>
  request("/reservations", { method: "POST", json: payload, token, failure: "Could not make the booking" });

export const getMyReservations = (token) =>
  request("/reservations/mine", { token, failure: "Could not load your bookings" });

export const createVehicle = (payload, token) =>
  request("/vehicles", { method: "POST", json: payload, token, failure: "Could not save the vehicle" });

export const fetchVehicles = (token) => request("/vehicles", { token, failure: "Could not load vehicles" });

export const fetchExperimentSummary = () =>
  request("/stats/experiment-summary", { failure: "Could not load the experiment summary" });

export const fetchFindings = () =>
  request("/stats/findings", { failure: "Could not load the experiment findings" });
