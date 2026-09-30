import { useEffect, useMemo } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

import { DEFAULT_CENTRE } from "../hooks/useStations";
import HeatmapLayer from "./HeatmapLayer";

function FitToStations({ stations }) {
  const map = useMap();
  useEffect(() => {
    if (!stations.length) return;
    map.fitBounds(L.latLngBounds(stations.map((s) => [s.lat, s.lon])), { padding: [40, 40], maxZoom: 15 });
  }, [stations, map]);
  return null;
}

export default function StationMap({ stations, recommendations, showHotspots, onSelectStation }) {
  const hotspots = useMemo(
    () =>
      recommendations.map((r) => ({
        lat: r.lat,
        lon: r.lon,
        intensity: r.probability_of_delay,
        label: r.station_name,
      })),
    [recommendations],
  );

  return (
    // The starting view only; FitToStations follows each search after that.
    <MapContainer center={[DEFAULT_CENTRE.lat, DEFAULT_CENTRE.lon]} zoom={12} className="map-container">
      <FitToStations stations={stations} />
      <HeatmapLayer enabled={showHotspots} points={hotspots} />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {stations.map((s) => (
        <Marker key={s.id} position={[s.lat, s.lon]} eventHandlers={{ click: () => onSelectStation(s.id) }}>
          <Popup>{s.name}</Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
