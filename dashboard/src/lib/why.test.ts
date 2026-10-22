import { describe, expect, it } from "vitest";
import type { Assignment } from "../types";
import { changeLines, whyLines } from "./why";

const label = (id: string) => ({ "DRO-01": "Drone 1", "DRO-02": "Drone 2", "AMB-01": "Ambulance 1" })[id] ?? id;

const base: Assignment = {
  vehicle: "DRO-02",
  incident: "SOS-011",
  eta_s: 3300,
  why: {
    priority: 120,
    rank: 1,
    of: 4,
    rule: "Z11 is cut off from every hospital by road, so only drones can reach it",
    mode: "air",
    stop: 1,
    travel_s: 290,
    distance_m: 4830,
    nearest: { vehicle: "DRO-02", travel_s: 290, busy_with: [] },
    baseline: { vehicle: "DRO-02", eta_s: 3300 },
  },
};

describe("whyLines", () => {
  it("explains a nearest-vehicle choice", () => {
    const lines = whyLines(base, 3000, label);
    expect(lines[0]).toBe("Priority 120 (severity × people): #1 of 4 calls in this plan.");
    expect(lines[1]).toContain("cut off");
    expect(lines[2]).toBe("4.8 km straight-line flight, about 4m 50s.");
    expect(lines).toContain("It is the nearest suitable vehicle.");
    expect(lines).toContain("Nearest-first would make the same choice.");
  });

  it("explains why the nearest vehicle was not used", () => {
    const a: Assignment = {
      ...base,
      why: {
        ...base.why,
        stop: 2,
        nearest: { vehicle: "DRO-01", travel_s: 60, busy_with: ["SOS-012"] },
        baseline: { vehicle: "DRO-01", eta_s: 3060 },
      },
    };
    const lines = whyLines(a, 3000, label);
    expect(lines[2]).toContain("as stop 2 on its route");
    expect(lines).toContain("Nearest suitable was Drone 1 (1m 00s away), but the plan needs it for SOS-012.");
    expect(lines).toContain("Nearest-first would send Drone 1 (ETA 1m 00s).");
  });
});

describe("changeLines", () => {
  it("summarises plan changes", () => {
    expect(
      changeLines({ added: ["SOS-020"], reassigned: [{ incident: "SOS-011", from: "DRO-01", to: "DRO-02" }], unassigned: [], unchanged: 3 }, label),
    ).toEqual(["1 newly assigned: SOS-020", "SOS-011: Drone 1 → Drone 2"]);
    expect(changeLines({ added: [], reassigned: [], unassigned: [], unchanged: 2 }, label)).toEqual([
      "No changes to 2 existing assignments",
    ]);
  });
});
