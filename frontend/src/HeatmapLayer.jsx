import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";

// Minimal Leaflet heatmap implementation without extra dependencies.
// Uses circle markers with intensity-driven radius/opacity so it renders in vanilla Leaflet.
export default function HeatmapLayer({ points, enabled }) {
  const map = useMap();

  useEffect(() => {
    if (!enabled) return;
    if (!points || !points.length) return;

    const group = L.layerGroup();
    points.forEach((p) => {
      const intensity = Math.max(0, Math.min(1, Number(p.intensity || 0)));
      const radius = 10 + intensity * 35;
      const color = intensity > 0.66 ? "#d7301f" : intensity > 0.33 ? "#fc8d59" : "#fee08b";
      const marker = L.circleMarker([p.lat, p.lon], {
        radius,
        color,
        weight: 1,
        opacity: 0.65,
        fillOpacity: 0.35 + intensity * 0.35,
      });
      marker.bindPopup(`${p.label || "Hotspot"} (intensity ${intensity.toFixed(2)})`);
      group.addLayer(marker);
    });

    group.addTo(map);
    return () => {
      group.remove();
    };
  }, [map, points, enabled]);

  return null;
}

