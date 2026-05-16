const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function safeJson(res) {
  if (!res || typeof res.json !== "function") return {};
  try {
    return await res.json();
  } catch {
    return {};
  }
}

function parseErrorDetail(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (typeof first === "string") return first;
    if (first && typeof first === "object") {
      const field = Array.isArray(first.loc) ? first.loc.slice(1).join(".") : "field";
      return `${field}: ${first.msg || "invalid value"}`;
    }
  }
  if (typeof detail === "object" && detail.message) return String(detail.message);
  return fallback;
}

export async function registerUser(email, password) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(parseErrorDetail(body.detail, "Registration failed"));
  }
  return res.json();
}

export async function loginUser(email, password) {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) {
    const err = await safeJson(res);
    throw new Error(parseErrorDetail(err.detail, "Login failed"));
  }
  return res.json();
}

export async function fetchExperimentSummary() {
  const res = await fetch(`${API_BASE}/stats/experiment-summary`);
  if (!res.ok) throw new Error("Failed to load experiment summary");
  return res.json();
}

export async function fetchNearbyStations(lat, lon, radiusKm = 5) {
  const url = `${API_BASE}/stations/nearby?lat=${lat}&lon=${lon}&radius_km=${radiusKm}`;
  const res = await fetch(url);
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(parseErrorDetail(body.detail, "Failed to fetch nearby stations"));
  }
  return res.json();
}

export async function fetchStation(stationId) {
  const res = await fetch(`${API_BASE}/stations/${stationId}`);
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(parseErrorDetail(body.detail, "Failed to fetch station"));
  }
  return res.json();
}

export async function createReservation(payload, accessToken) {
  const res = await fetch(`${API_BASE}/reservations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(parseErrorDetail(body.detail, "Failed to create reservation"));
  }
  return res.json();
}

export async function suggestSlot(stationId, payload) {
  const res = await fetch(`${API_BASE}/stations/${stationId}/suggest-slot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(parseErrorDetail(body.detail, "Failed to suggest slot"));
  }
  return res.json();
}

export async function getRecommendations(payload) {
  const res = await fetch(`${API_BASE}/recommendations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(parseErrorDetail(body.detail, "Failed to get recommendations"));
  }
  return res.json();
}

export async function createVehicle(payload, accessToken) {
  const res = await fetch(`${API_BASE}/vehicles`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(parseErrorDetail(body.detail, "Failed to save vehicle"));
  }
  return res.json();
}

export async function fetchVehicles(accessToken) {
  const res = await fetch(`${API_BASE}/vehicles`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(parseErrorDetail(body.detail, "Failed to fetch vehicles"));
  }
  return res.json();
}

export async function getMyReservations(accessToken) {
  const res = await fetch(`${API_BASE}/reservations/mine`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) return [];
  return res.json();
}
