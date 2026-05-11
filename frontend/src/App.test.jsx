import { render, screen, waitFor } from "@testing-library/react";
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

vi.mock("recharts", () => {
  const Stub = ({ children }) => <div data-testid="chart-stub">{children}</div>;
  return {
    ResponsiveContainer: Stub,
    BarChart: Stub,
    Bar: () => null,
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    Legend: () => null,
  };
});

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("loads nearby stations and renders recommendation results", async () => {
    vi.spyOn(api, "fetchNearbyStations").mockResolvedValue([
      { id: "s1", name: "Station 1", lat: 51.5, lon: -0.1 },
    ]);
    vi.spyOn(api, "fetchStation").mockResolvedValue({
      id: "s1",
      name: "Station 1",
      chargers: [{ id: "c1", name: "C1", power_kw: 22 }],
    });
    vi.spyOn(api, "getRecommendations").mockResolvedValue([
      {
        station_id: "s1",
        station_name: "Station 1",
        distance_km: 1.2,
        predicted_wait_min: 5.4,
        score: 0.1,
        price_pence_per_kwh: 50,
      },
    ]);
    vi.spyOn(api, "createReservation").mockResolvedValue({ id: "r1" });

    render(<App />);

    await waitFor(() => expect(api.fetchNearbyStations).toHaveBeenCalled());
    await userEvent.click(await screen.findByRole("button", { name: "Nearest" }));

    expect(await screen.findByText(/Station 1 \| 1.20 km \| 5.40 min wait/)).toBeInTheDocument();
  });

  it("submits reservation form and shows success status", async () => {
    localStorage.setItem("ev_portfolio_access_token", "test-jwt");
    vi.spyOn(api, "fetchNearbyStations").mockResolvedValue([
      { id: "s1", name: "Station 1", lat: 51.5, lon: -0.1 },
    ]);
    vi.spyOn(api, "fetchStation").mockResolvedValue({
      id: "s1",
      name: "Station 1",
      chargers: [{ id: "c1", name: "C1", power_kw: 22 }],
    });
    vi.spyOn(api, "getRecommendations").mockResolvedValue([]);
    vi.spyOn(api, "createReservation").mockResolvedValue({ id: "r1" });

    render(<App />);
    await waitFor(() => expect(api.fetchNearbyStations).toHaveBeenCalled());

    await userEvent.click(await screen.findByRole("button", { name: "Station 1" }));
    const datetimeInputs = document.querySelectorAll('input[type="datetime-local"]');
    await userEvent.type(datetimeInputs[0], "2026-05-10T10:00");
    await userEvent.type(datetimeInputs[1], "2026-05-10T11:00");
    await userEvent.click(screen.getByRole("button", { name: "Reserve" }));

    await waitFor(() => expect(api.createReservation).toHaveBeenCalled());
    const [payload, token] = api.createReservation.mock.calls[0];
    expect(token).toBe("test-jwt");
    expect(payload.charger_id).toBe("c1");
    expect(await screen.findByText("Reservation created.")).toBeInTheDocument();
  });
});
