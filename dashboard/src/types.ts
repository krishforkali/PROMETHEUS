// Mirrors the backend state from GET /state and /ws (backend/app/engine.py `Simulation.state`).

export type LatLon = [number, number];
export type VehicleType = "ambulance" | "boat" | "drone" | "truck";
export type VehicleStatus = "idle" | "en_route" | "transporting" | "lost";
export type IncidentStatus = "open" | "assigned" | "served";
export type IncidentSource = "app" | "ivr" | "sms" | "dashboard";

export interface Casualties {
  low: number;
  expected: number;
  high: number;
}

export interface ZoneState {
  id: string;
  population: number;
  risk: number;
  casualties: Casualties;
  flooded: boolean;
  cut_off: boolean;
  simulated: boolean;
}

export interface FailurePoint {
  id: string;
  label: string;
  name: string;
  lat: number;
  lon: number;
  zone: string;
  edges: [number, number][];
  risk: number;
  failed: boolean;
}

export interface HospitalState {
  id: string;
  name: string;
  lat: number;
  lon: number;
  node: number;
  emergency: boolean;
  capacity: { beds_total: number; beds_available: number; simulated: boolean };
  beds_available: number;
  provisional?: boolean;
}

export interface Target {
  kind: "incident" | "hospital";
  id: string;
  patients?: number;
}

export interface VehicleState {
  id: string;
  label: string;
  type: VehicleType;
  status: VehicleStatus;
  lat: number;
  lon: number;
  capacity: number;
  target: Target | null;
  route: LatLon[];
}

export interface Incident {
  id: string;
  lat: number;
  lon: number;
  zone: string;
  severity: number;
  people: number;
  kind: "medical" | "supplies";
  source: IncidentSource;
  created_s: number;
  status: IncidentStatus;
  assigned_to?: string;
  eta_s?: number;
  served_s?: number;
  served_by?: string;
}

export interface Leg {
  to: Target;
  depart_s: number;
  arrive_s: number;
  path: LatLon[];
}

export interface Score {
  served: number;
  dropped: number;
  people_reached: number;
  avg_response_s: number | null;
  cost: number;
}

/** Backend reasons for one assignment (dispatch.explain). */
export interface Why {
  priority: number;
  rank: number;
  of: number;
  rule: string;
  mode: "road" | "water" | "air";
  stop: number;
  travel_s: number;
  distance_m: number;
  nearest: { vehicle: string; travel_s: number; busy_with: string[] };
  baseline: { vehicle: string; eta_s: number } | null;
  hospital?: { id: string; name: string; beds_free: number };
}

export interface Assignment {
  vehicle: string;
  incident: string;
  eta_s: number;
  why: Why;
}

export interface PlanChanges {
  added: string[];
  reassigned: { incident: string; from: string; to: string }[];
  unassigned: string[];
  unchanged: number;
}

export interface Plan {
  t0: number;
  version: number;
  reason: string;
  solver: "or-tools" | "baseline";
  assignments: Assignment[];
  routes: { vehicle: string; type: VehicleType; legs: Leg[] }[];
  dropped: string[];
  metrics: Score;
  baseline: Score & { method: string };
  improvement_pct: { cost: number | null; avg_response: number | null; people_reached: number | null };
  changes: PlanChanges;
}

export interface Metrics {
  people_at_risk: number;
  incidents: number;
  served: number;
  open: number;
  people_reached: number;
  avg_response_s: number | null;
  /** Cumulative priority-weighted gain of the optimiser over nearest-first, across re-plans. */
  plan_gain_pct: number | null;
  plans_compared: number;
}

export interface LogEntry {
  t: number;
  type: string;
  source: "timeline" | "manual" | "sim";
  message: string;
}

export interface Clock {
  running: boolean;
  speed: number;
  time_s: number;
}

export interface SimState {
  simulated: true;
  time_s: number;
  rain_mm_hr: number;
  zones: ZoneState[];
  failure_points: FailurePoint[];
  blocked_edges: [number, number][];
  hospitals: HospitalState[];
  vehicles: VehicleState[];
  incidents: Incident[];
  plan: Plan | null;
  /** Re-plan awaiting operator approval; the sim clock holds while set. */
  proposal: Plan | null;
  auto_approve: boolean;
  metrics: Metrics;
  log: LogEntry[];
  next_event_s: number | null;
  clock: Clock;
}

// Static data from GET /zones and GET /roads.
export interface ZoneInfo {
  id: string;
  row: number;
  col: number;
  polygon: [number, number][];
  centroid: { lat: number; lon: number };
  population: number;
  elevation_m: number;
  river_distance_m: number;
}

export interface RoadFeature {
  type: "Feature";
  geometry: { type: "LineString"; coordinates: [number, number][] };
  properties: { u: number; v: number; key: number; length_m: number; highway: string | null; name: string | null; bridge: boolean };
}

export interface RoadCollection {
  type: "FeatureCollection";
  features: RoadFeature[];
}

export type SimEvent =
  | { type: "block_road"; failure_point: string }
  | { type: "block_road"; u: number; v: number }
  | { type: "add_sos_wave"; count: number; zone?: string }
  | { type: "remove_vehicle"; vehicle: string };
