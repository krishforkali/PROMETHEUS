import { describe, expect, it } from "vitest";
import type { Incident } from "../types";
import { clock, duration, priorityBand, queueOrder, riskColor } from "./format";

const inc = (id: string, severity: number, people: number, extra: Partial<Incident> = {}): Incident => ({
  id,
  lat: 0,
  lon: 0,
  zone: "Z01",
  severity,
  people,
  kind: "medical",
  source: "app",
  created_s: 0,
  status: "open",
  ...extra,
});

describe("format", () => {
  it("formats clocks and durations", () => {
    expect(clock(3725)).toBe("01:02:05");
    expect(duration(45)).toBe("45s");
    expect(duration(405.1)).toBe("6m 45s");
    expect(duration(null)).toBe("—");
  });

  it("bands priority", () => {
    expect(priorityBand(150)).toBe("critical");
    expect(priorityBand(40)).toBe("high");
    expect(priorityBand(15)).toBe("medium");
    expect(priorityBand(2)).toBe("low");
  });

  it("orders the queue: open by priority, served last", () => {
    const order = queueOrder([
      inc("a", 1, 5),
      inc("b", 5, 30, { status: "served", served_s: 10 }),
      inc("c", 4, 20),
      inc("d", 2, 10, { status: "assigned" }),
    ]).map((i) => i.id);
    expect(order).toEqual(["c", "d", "a", "b"]);
  });

  it("ramps risk colours", () => {
    expect(riskColor(0)).toBe("rgb(34,197,94)");
    expect(riskColor(2)).toBe("rgb(153,27,27)");
  });
});
