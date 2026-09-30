import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import * as api from "./api";

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  Marker: ({ children }) => <div>{children}</div>,
  Popup: ({ children }) => <div>{children}</div>,
  TileLayer: () => <div />,
  useMap: () => ({ fitBounds: vi.fn() }),
}));

const station = { id: "s1", name: "Kings Cross Car Park", lat: 51.53, lon: -0.12, borough: "London" };
const detail = { ...station, chargers: [{ id: "c1", name: "Charger 1", power_kw: 22 }] };
const recommendation = {
  station_id: "s1",
  station_name: "Kings Cross Car Park",
  lat: 51.53,
  lon: -0.12,
  travel_distance_km: 1.24,
  travel_time_min: 7.6,
  predicted_wait_min: 5.4,
  probability_of_delay: 0.15,
  current_occupancy: 1,
  score: 0.1,
  price_pence_per_kwh: 50,
};

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    vi.spyOn(api, "fetchNearbyStations").mockResolvedValue([station]);
    vi.spyOn(api, "fetchStation").mockResolvedValue(detail);
    vi.spyOn(api, "getRecommendations").mockResolvedValue([recommendation]);
    vi.spyOn(api, "fetchVehicles").mockResolvedValue([]);
    vi.spyOn(api, "getMyReservations").mockResolvedValue([]);
  });

  it("loads stations on start and shows ranked recommendations", async () => {
    render(<App />);
    expect(await screen.findByText("1 stations within 5 km.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Queue aware" }));

    expect(api.getRecommendations).toHaveBeenCalledWith(
      expect.objectContaining({ algorithm: "queue_aware", origin_lat: 51.5074, top_k: 5 }),
    );
    expect(await screen.findByText("Best stations: Queue aware")).toBeInTheDocument();
    expect(
      screen.getByText("1.2 km · 8 min drive · 5 min predicted wait · 15% chance of queueing · 1 in use now"),
    ).toBeInTheDocument();
  });

  it("sends battery details only when both are filled in", async () => {
    render(<App />);
    await userEvent.type(screen.getByLabelText("Charge left (%)"), "20");
    await userEvent.click(screen.getByRole("button", { name: "Range aware" }));
    expect(api.getRecommendations.mock.calls[0][0]).not.toHaveProperty("battery_level_percent");

    await userEvent.type(screen.getByLabelText("Battery capacity (kWh)"), "60");
    await userEvent.click(screen.getByRole("button", { name: "Range aware" }));
    expect(api.getRecommendations.mock.calls[1][0]).toMatchObject({
      battery_level_percent: 20,
      battery_capacity_kwh: 60,
    });
  });

  it("asks the user to sign in before booking", async () => {
    render(<App />);
    await userEvent.selectOptions(await screen.findByLabelText("Select station"), "s1");
    await userEvent.type(await screen.findByLabelText("Start"), "2031-01-15T10:00");
    await userEvent.type(screen.getByLabelText("End"), "2031-01-15T11:00");
    await userEvent.click(screen.getByRole("button", { name: "Reserve" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Sign in under My account");
  });

  it("books a charger when signed in and refreshes the booking list", async () => {
    localStorage.setItem("ev_access_token", "test-jwt");
    vi.spyOn(api, "createReservation").mockResolvedValue({ id: "r1" });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: "Queue aware" }));
    await userEvent.click(await screen.findByRole("button", { name: /Kings Cross Car Park/ }));
    const booking = (await screen.findByText("Book a charger")).closest("details");
    await userEvent.type(within(booking).getByLabelText("Start"), "2031-01-15T10:00");
    await userEvent.type(within(booking).getByLabelText("End"), "2031-01-15T11:00");
    await userEvent.click(within(booking).getByRole("button", { name: "Reserve" }));

    await waitFor(() => expect(api.createReservation).toHaveBeenCalled());
    const [payload, token] = api.createReservation.mock.calls[0];
    expect(token).toBe("test-jwt");
    expect(payload.charger_id).toBe("c1");
    expect(await within(booking).findByRole("status")).toHaveTextContent("Booked");
    expect(api.getMyReservations).toHaveBeenCalledTimes(2);
  });

  it("signs in and remembers the token", async () => {
    vi.spyOn(api, "loginUser").mockResolvedValue({ access_token: "new-token" });
    render(<App />);
    await userEvent.type(screen.getByLabelText("Email"), "driver@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "Password123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Signed in")).toBeInTheDocument();
    expect(localStorage.getItem("ev_access_token")).toBe("new-token");
  });

  it("keeps the latest strategy's results when an earlier request answers last", async () => {
    let answerSlowRequest;
    api.getRecommendations
      .mockImplementationOnce(() => new Promise((resolve) => (answerSlowRequest = resolve)))
      .mockResolvedValueOnce([{ ...recommendation, station_name: "Fast answer" }]);
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: "Dijkstra" }));
    await userEvent.click(screen.getByRole("button", { name: "Queue aware" }));
    expect(await screen.findByText("Fast answer")).toBeInTheDocument();

    answerSlowRequest([{ ...recommendation, station_name: "Slow answer" }]);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText("Slow answer")).not.toBeInTheDocument();
    expect(screen.getByText("Best stations: Queue aware")).toBeInTheDocument();
  });

  it("signs out when the saved token is no longer accepted", async () => {
    localStorage.setItem("ev_access_token", "expired");
    // Go through the real API client so its 401 handling runs.
    api.fetchVehicles.mockRestore();
    api.getMyReservations.mockRestore();
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Could not validate credentials" }),
    });
    render(<App />);

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(localStorage.getItem("ev_access_token")).toBeNull());
  });

  it("rejects a cleared latitude instead of searching at 0", async () => {
    render(<App />);
    await screen.findByText("1 stations within 5 km.");
    await userEvent.clear(screen.getByLabelText("Latitude"));
    await userEvent.click(screen.getByRole("button", { name: "Find nearby stations" }));

    expect(await screen.findByText("Enter a latitude between -90 and 90.")).toBeInTheDocument();
    expect(api.fetchNearbyStations).toHaveBeenCalledTimes(1);
  });

  it("searches with the typed centre and radius", async () => {
    render(<App />);
    await screen.findByText("1 stations within 5 km.");
    await userEvent.clear(screen.getByLabelText("Latitude"));
    await userEvent.type(screen.getByLabelText("Latitude"), "51.53");
    await userEvent.clear(screen.getByLabelText("Radius (km)"));
    await userEvent.type(screen.getByLabelText("Radius (km)"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Find nearby stations" }));

    expect(api.fetchNearbyStations).toHaveBeenLastCalledWith(51.53, -0.1278, 2);
  });

  it("lets an existing account with a short password sign in", async () => {
    vi.spyOn(api, "loginUser").mockResolvedValue({ access_token: "t" });
    render(<App />);
    await userEvent.type(screen.getByLabelText("Email"), "demo@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "demo");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(api.loginUser).toHaveBeenCalledWith("demo@example.com", "demo");
  });

  it("does not let a slow initial load overwrite the user's own search", async () => {
    let answerInitialLoad;
    api.fetchNearbyStations
      .mockImplementationOnce(() => new Promise((resolve) => (answerInitialLoad = resolve)))
      .mockResolvedValueOnce([station, { ...station, id: "s2", name: "Second" }]);
    render(<App />);

    await userEvent.clear(screen.getByLabelText("Radius (km)"));
    await userEvent.type(screen.getByLabelText("Radius (km)"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Find nearby stations" }));
    expect(await screen.findByText("2 stations within 2 km.")).toBeInTheDocument();

    answerInitialLoad([station]);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.getByText("2 stations within 2 km.")).toBeInTheDocument();
  });

  it("rejects a comma decimal rather than truncating it", async () => {
    render(<App />);
    await screen.findByText("1 stations within 5 km.");
    await userEvent.clear(screen.getByLabelText("Latitude"));
    await userEvent.type(screen.getByLabelText("Latitude"), "51,5074");
    await userEvent.click(screen.getByRole("button", { name: "Find nearby stations" }));
    expect(await screen.findByText("Enter a latitude between -90 and 90.")).toBeInTheDocument();
  });
});
