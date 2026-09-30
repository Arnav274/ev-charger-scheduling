import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createReservation,
  errorMessage,
  fetchNearbyStations,
  fetchStation,
  getRecommendations,
  loginUser,
} from "./api";

const ok = (payload) => ({ ok: true, json: async () => payload });

describe("api", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("builds the nearby-stations URL", async () => {
    global.fetch = vi.fn().mockResolvedValue(ok([{ id: "1" }]));
    expect(await fetchNearbyStations(51.5, -0.12, 7)).toEqual([{ id: "1" }]);
    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/stations/nearby?lat=51.5&lon=-0.12&radius_km=7",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("posts JSON bodies", async () => {
    global.fetch = vi.fn().mockResolvedValue(ok([]));
    await getRecommendations({ algorithm: "nearest" });
    const [, options] = global.fetch.mock.calls[0];
    expect(options.method).toBe("POST");
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(options.body)).toEqual({ algorithm: "nearest" });
  });

  it("signs in with a form-encoded body, as OAuth2 password flow expects", async () => {
    global.fetch = vi.fn().mockResolvedValue(ok({ access_token: "t" }));
    await loginUser("a@b.com", "pw pw");
    const [, options] = global.fetch.mock.calls[0];
    expect(options.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
    expect(options.body).toBe("username=a%40b.com&password=pw+pw");
  });

  it("sends the bearer token", async () => {
    global.fetch = vi.fn().mockResolvedValue(ok({ id: "x" }));
    await createReservation({ charger_id: "c1" }, "secret");
    expect(global.fetch.mock.calls[0][1].headers.Authorization).toBe("Bearer secret");
  });

  it("surfaces the backend's error detail", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "Overlapping reservation" }),
    });
    await expect(createReservation({}, "tok")).rejects.toThrow("Overlapping reservation");
  });

  it("falls back to a generic message when the error body is not JSON", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false });
    await expect(fetchStation("abc")).rejects.toThrow("Could not load the station");
  });

  it("explains when the backend cannot be reached", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(fetchStation("abc")).rejects.toThrow(/Cannot reach the backend/);
  });

  it("formats validation errors", () => {
    const detail = [{ loc: ["body", "radius_km"], msg: "Input should be less than or equal to 50" }];
    expect(errorMessage(detail, "x")).toBe("radius_km: Input should be less than or equal to 50");
    expect(errorMessage(undefined, "fallback")).toBe("fallback");
  });
});
