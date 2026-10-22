import type { Clock, RoadCollection, SimEvent, ZoneInfo } from "./types";

export const API = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(typeof body.detail === "string" ? body.detail : `${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  zones: () => request<ZoneInfo[]>("/zones"),
  roads: () => request<RoadCollection>("/roads"),
  start: () => post<Clock>("/sim/start"),
  pause: () => post<Clock>("/sim/pause"),
  reset: () => post<Clock>("/sim/reset"),
  speed: (speed: number) => post<Clock>("/sim/speed", { speed }),
  event: (event: SimEvent) => post<{ plan_version: number }>("/sim/event", event),
  approve: () => post<{ plan_version: number }>("/sim/approve"),
  autoApprove: (enabled: boolean) => post<{ auto_approve: boolean }>("/sim/auto-approve", { enabled }),
};

export function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${API}/ws`;
}
