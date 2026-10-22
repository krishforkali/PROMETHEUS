import maplibregl, { type GeoJSONSource, type Map as MLMap, type Marker, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { BAND_COLOR, VEHICLE_COLOR, VEHICLE_ICON, priority, priorityBand, riskColor } from "../lib/format";
import type { RoadCollection, SimState, ZoneInfo } from "../types";

interface Props {
  state: SimState;
  zones: ZoneInfo[];
  roads: RoadCollection;
  osmTiles: boolean;
  blockMode: boolean;
  onRoadClick: (u: number, v: number) => void;
}

type FC = GeoJSON.FeatureCollection;
const empty: FC = { type: "FeatureCollection", features: [] };

// No glyphs, sprites or vector tiles: the map renders entirely from our own GeoJSON.
// Text labels are HTML markers. OSM raster tiles are an optional, hidden layer.
const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#0a0f1c" } },
    { id: "osm", type: "raster", source: "osm", layout: { visibility: "none" }, paint: { "raster-opacity": 0.35 } },
  ],
};

function zoneFeatures(zones: ZoneInfo[], state: SimState): FC {
  const live = new Map(state.zones.map((z) => [z.id, z]));
  return {
    type: "FeatureCollection",
    features: zones.map((z) => {
      const s = live.get(z.id);
      return {
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [z.polygon] },
        properties: {
          id: z.id,
          color: riskColor(s?.risk ?? 0),
          flooded: s?.flooded ?? false,
          cut_off: s?.cut_off ?? false,
        },
      };
    }),
  };
}

function blockedFeatures(roads: RoadCollection, blocked: [number, number][]): FC {
  const keys = new Set(blocked.map(([u, v]) => `${u}-${v}`));
  return {
    type: "FeatureCollection",
    features: roads.features.filter((f) => {
      const { u, v } = f.properties;
      return keys.has(`${Math.min(u, v)}-${Math.max(u, v)}`);
    }),
  };
}

function routeFeatures(state: SimState): FC {
  return {
    type: "FeatureCollection",
    features: state.vehicles
      .filter((v) => v.route.length >= 2)
      .map((v) => ({
        type: "Feature",
        geometry: { type: "LineString", coordinates: v.route.map(([lat, lon]) => [lon, lat]) },
        properties: { id: v.id, color: VEHICLE_COLOR[v.type] },
      })),
  };
}

function incidentFeatures(state: SimState): FC {
  return {
    type: "FeatureCollection",
    features: state.incidents.map((i) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [i.lon, i.lat] },
      properties: {
        id: i.id,
        served: i.status === "served",
        color: i.status === "served" ? "#475569" : BAND_COLOR[priorityBand(priority(i))],
        radius: i.status === "served" ? 4 : 6 + Math.min(10, Math.sqrt(priority(i))),
      },
    })),
  };
}

/** Create, move and remove HTML markers keyed by id. */
function syncMarkers<T>(
  map: MLMap,
  store: Map<string, Marker>,
  items: T[],
  key: (t: T) => string,
  lngLat: (t: T) => [number, number],
  render: (el: HTMLElement, t: T) => void,
): void {
  const seen = new Set<string>();
  for (const item of items) {
    const k = key(item);
    seen.add(k);
    let marker = store.get(k);
    if (!marker) {
      marker = new maplibregl.Marker({ element: document.createElement("div") }).setLngLat(lngLat(item)).addTo(map);
      store.set(k, marker);
    } else {
      marker.setLngLat(lngLat(item));
    }
    render(marker.getElement(), item);
  }
  for (const [k, marker] of store) {
    if (!seen.has(k)) {
      marker.remove();
      store.delete(k);
    }
  }
}

/** Render into an inner wrapper: the marker element itself carries maplibre's positioning classes. */
function setHtml(el: HTMLElement, className: string, html: string): void {
  const next = `<div class="${className}">${html}</div>`;
  if (el.dataset.html !== next) {
    el.dataset.html = next;
    el.innerHTML = next;
  }
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);

export function MapView({ state, zones, roads, osmTiles, blockMode, onRoadClick }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const markers = useRef({
    zones: new Map<string, Marker>(),
    hospitals: new Map<string, Marker>(),
    fps: new Map<string, Marker>(),
    vehicles: new Map<string, Marker>(),
  });
  const [loaded, setLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const roadClick = useRef(onRoadClick);
  roadClick.current = onRoadClick;
  const blockRef = useRef(blockMode);
  blockRef.current = blockMode;

  // One-time map setup.
  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({ container: container.current, style: STYLE, attributionControl: false });
    mapRef.current = map;
    map.on("error", (e) => {
      // Optional OSM tiles failing offline is expected; anything else is shown.
      if ((e as { sourceId?: string }).sourceId === "osm") return;
      setMapError(e.error?.message ?? "map error");
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");

    const lons = zones.flatMap((z) => z.polygon.map((p) => p[0]));
    const lats = zones.flatMap((z) => z.polygon.map((p) => p[1]));
    map.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: { top: 24, bottom: 24, right: 24, left: 310 }, duration: 0 }, // clear of the demo panel
    );

    map.on("load", () => {
      map.addSource("zones", { type: "geojson", data: empty });
      map.addSource("roads", { type: "geojson", data: roads as unknown as FC });
      map.addSource("blocked", { type: "geojson", data: empty });
      map.addSource("routes", { type: "geojson", data: empty });
      map.addSource("incidents", { type: "geojson", data: empty });

      map.addLayer({ id: "zones-fill", type: "fill", source: "zones", paint: { "fill-color": ["get", "color"], "fill-opacity": 0.22 } });
      map.addLayer({
        id: "zones-flood",
        type: "fill",
        source: "zones",
        filter: ["==", ["get", "flooded"], true],
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.28 },
      });
      map.addLayer({ id: "zones-line", type: "line", source: "zones", paint: { "line-color": "#1e293b", "line-width": 1 } });
      map.addLayer({
        id: "roads",
        type: "line",
        source: "roads",
        paint: {
          "line-color": "#64748b",
          "line-width": ["interpolate", ["linear"], ["zoom"], 12, 1, 16, 4],
          "line-opacity": 0.85,
        },
      });
      map.addLayer({ id: "roads-hit", type: "line", source: "roads", paint: { "line-color": "#000", "line-opacity": 0, "line-width": 12 } });
      map.addLayer({
        id: "zones-cutoff",
        type: "line",
        source: "zones",
        filter: ["==", ["get", "cut_off"], true],
        paint: { "line-color": "#ef4444", "line-width": 4, "line-dasharray": [2, 1.5] },
      });
      map.addLayer({ id: "blocked-casing", type: "line", source: "blocked", paint: { "line-color": "#000", "line-width": 9 } });
      map.addLayer({
        id: "blocked",
        type: "line",
        source: "blocked",
        paint: { "line-color": "#ef4444", "line-width": 5, "line-dasharray": [1, 0.6] },
      });
      map.addLayer({
        id: "routes",
        type: "line",
        source: "routes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": ["get", "color"], "line-width": 3, "line-opacity": 0.9, "line-dasharray": [2, 1] },
      });
      map.addLayer({
        id: "incidents",
        type: "circle",
        source: "incidents",
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": ["get", "radius"],
          "circle-stroke-color": "#0f172a",
          "circle-stroke-width": 2,
          "circle-opacity": ["case", ["get", "served"], 0.6, 0.95],
        },
      });

      map.on("click", "roads-hit", (e) => {
        if (!blockRef.current) return;
        const props = e.features?.[0]?.properties as { u?: number; v?: number } | undefined;
        if (props?.u != null && props.v != null) roadClick.current(props.u, props.v);
      });
      map.on("mousemove", "roads-hit", () => {
        map.getCanvas().style.cursor = blockRef.current ? "crosshair" : "";
      });
      map.on("mouseleave", "roads-hit", () => {
        map.getCanvas().style.cursor = "";
      });
      setLoaded(true);
    });

    return () => {
      setLoaded(false);
      for (const store of Object.values(markers.current)) store.clear();
      map.remove();
      mapRef.current = null;
    };
  }, [zones, roads]);

  useEffect(() => {
    const map = mapRef.current;
    if (map && loaded) map.setLayoutProperty("osm", "visibility", osmTiles ? "visible" : "none");
  }, [osmTiles, loaded]);

  // Per-tick updates.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    (map.getSource("zones") as GeoJSONSource).setData(zoneFeatures(zones, state));
    (map.getSource("blocked") as GeoJSONSource).setData(blockedFeatures(roads, state.blocked_edges));
    (map.getSource("routes") as GeoJSONSource).setData(routeFeatures(state));
    (map.getSource("incidents") as GeoJSONSource).setData(incidentFeatures(state));

    const m = markers.current;
    const live = new Map(state.zones.map((z) => [z.id, z]));
    syncMarkers(map, m.zones, zones, (z) => z.id, (z) => [z.centroid.lon, z.centroid.lat], (el, z) => {
      const s = live.get(z.id);
      const tag = s?.cut_off ? '<span class="zl-tag zl-cut">CUT OFF</span>' : s?.flooded ? '<span class="zl-tag zl-flood">FLOODED</span>' : "";
      setHtml(el, "zone-label", `${z.id}${tag}`);
    });
    syncMarkers(map, m.hospitals, state.hospitals, (h) => h.id, (h) => [h.lon, h.lat], (el, h) => {
      const low = h.beds_available / Math.max(1, h.capacity.beds_total) < 0.15;
      setHtml(
        el,
        `hosp-marker${low ? " hosp-low" : ""}`,
        `<span class="hosp-icon">H</span><span class="hosp-text">${esc(h.name)}<b>${h.beds_available} beds free</b></span>`,
      );
    });
    syncMarkers(map, m.fps, state.failure_points, (f) => f.id, (f) => [f.lon, f.lat], (el, f) => {
      setHtml(el, `fp-marker${f.failed ? " fp-failed" : ""}`, `<span class="fp-dot"></span><span>${esc(f.label)}</span>`);
    });
    syncMarkers(map, m.vehicles, state.vehicles, (v) => v.id, (v) => [v.lon, v.lat], (el, v) => {
      el.style.setProperty("--vc", VEHICLE_COLOR[v.type]);
      setHtml(el, `veh-marker veh-${v.status}`, `<span class="veh-icon">${VEHICLE_ICON[v.type]}</span><span class="veh-label">${esc(v.label)}</span>`);
    });
  }, [state, loaded, zones, roads]);

  return (
    <div className="relative h-full w-full">
      {/* inline style: maplibre-gl.css sets .maplibregl-map { position: relative } which would beat a class */}
      <div ref={container} style={{ position: "absolute", inset: 0 }} />
      <div className="pointer-events-none absolute right-3 top-3 rounded bg-amber-500/90 px-2 py-0.5 text-xs font-bold tracking-widest text-black">
        SIMULATED
      </div>
      {mapError && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded bg-red-800 px-3 py-1 text-sm">Map error: {mapError}</div>
      )}
      {blockMode && (
        <div className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded bg-red-600 px-3 py-1 text-sm font-semibold">
          Click a road to block it
        </div>
      )}
      <Legend />
    </div>
  );
}

function Legend() {
  return (
    <div className="pointer-events-none absolute bottom-8 left-3 space-y-1 rounded-md bg-slate-950/85 p-2 text-xs text-slate-300">
      <div className="flex items-center gap-2">
        <span className="h-3 w-5 rounded-sm" style={{ background: "linear-gradient(90deg,#22c55e,#eab308,#ef4444)" }} /> zone risk
      </div>
      <div className="flex items-center gap-2">
        <span className="h-3 w-5 rounded-sm bg-blue-600/60" /> flooded
      </div>
      <div className="flex items-center gap-2">
        <span className="h-0 w-5 border-t-2 border-dashed border-red-500" /> cut off / blocked
      </div>
      <div className="flex items-center gap-2">
        {Object.entries(BAND_COLOR).map(([k, c]) => (
          <span key={k} className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />
            {k}
          </span>
        ))}
      </div>
    </div>
  );
}
