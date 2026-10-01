import { beforeEach, describe, expect, it, vi } from "vitest";

import { createReservation, fetchNearbyStations, fetchStation, getRecommendations } from "./api";

describe("api helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });



  it("fetchNearbyStations builds URL and returns parsed payload", async () => {
    const payload = [{ id: "1", name: "Station A" }];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    });



    const data = await fetchNearbyStations(51.5, -0.12, 7);

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/stations/nearby?lat=51.5&lon=-0.12&radius_km=7",
    );
    expect(data).toEqual(payload);
  });

  it("fetchStation throws for non-2xx responses", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false });
    await expect(fetchStation("abc")).rejects.toThrow("Failed to fetch station");
  });


  it("createReservation surfaces backend detail message", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "Overlapping reservation" }),
    });

    await expect(createReservation({}, "tok")).rejects.toThrow("Overlapping reservation");
  });





  it("createReservation sends bearer token", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "x" }) });
    await createReservation({ charger_id: "c1" }, "secret");
    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/reservations",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer secret",
        }),
      }),
    );
  });



  
  it("getRecommendations posts payload and returns JSON", async () => {
    const payload = [{ station_id: "x" }];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    });
    const body = { origin_lat: 51.5, origin_lon: -0.12, algorithm: "nearest" };
    const result = await getRecommendations(body);
    expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/recommendations", expect.any(Object));
    expect(result).toEqual(payload);
  });
});
