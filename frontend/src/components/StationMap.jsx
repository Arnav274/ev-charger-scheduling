import { useEffect, useMemo } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

import HeatmapLayer from "./HeatmapLayer";

function FitToStations({ stations }) {
  const map = useMap();
  useEffect(() => {
    if (!stations.length) return;
    map.fitBounds(L.latLngBounds(stations.map((s) => [s.lat, s.lon])), { padding: [40, 40], maxZoom: 15 });
  }, [stations, map]);
  return null;
}

export default function StationMap({ centre, stations, recommendations, showHotspots, onSelectStation }) {
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
    <MapContainer center={[centre.lat, centre.lon]} zoom={12} className="map-container">
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
