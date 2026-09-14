import { describe, expect, it } from "vitest";
import { subtaskProgress, weightedProgress } from "./rollup";
import type { RollupItem } from "./rollup";

describe("subtaskProgress", () => {
  const items = [
    { id: "p", status_group: "open" },
    { id: "s1", parent_id: "p", status_group: "done", spent_minutes: 30 },
    { id: "s2", parent_id: "p", status_group: "open", spent_minutes: 15 },
    { id: "s3", parent_id: "p", status_group: "cancelled" },
    { id: "g1", parent_id: "s1", status_group: "done" }, // grandchild → rolls to s1, not p
    { id: "loner", status_group: "open" },
  ];

  it("counts done/total over direct children only", () => {
    const m = subtaskProgress(items);
    expect(m.get("p")).toEqual({ done: 1, total: 3, spent: 45 });
    expect(m.get("s1")).toEqual({ done: 1, total: 1, spent: 0 });
    expect(m.has("loner")).toBe(false);
    expect(m.has("s2")).toBe(false);
  });

  it("full completion and empty input", () => {
    const all = subtaskProgress([
      { id: "x", parent_id: "p", status_group: "done" },
      { id: "y", parent_id: "p", status_group: "done" },
    ]);
    expect(all.get("p")).toEqual({ done: 2, total: 2, spent: 0 });
    expect(subtaskProgress([]).size).toBe(0);
  });
});

describe("weightedProgress", () => {
  it("rolls a three-level chain up by estimate weight", () => {
    const items = [
      { id: "p", status_group: "open" },
      { id: "c1", parent_id: "p", estimate_hours: 4, status_group: "open" },
      { id: "g1", parent_id: "c1", status_group: "done", spent_minutes: 60 },
      { id: "c2", parent_id: "p", status_group: "open", spent_minutes: 10 },
    ];
    const m = weightedProgress(items);
    // c1 (w=4, grandchild done → fraction 1) vs c2 (no estimate → w=1, 0) → 80%
    expect(m.get("p")).toEqual({ percent: 80, done: 1, total: 3, spent: 70 });
    expect(m.get("c1")).toEqual({ percent: 100, done: 1, total: 1, spent: 60 });
    expect(m.has("c2")).toBe(false); // leaf → parents only
    expect(m.has("g1")).toBe(false);
  });

  it("weights by estimate_hours", () => {
    const m = weightedProgress([
      { id: "p", status_group: "open" },
      { id: "a", parent_id: "p", estimate_hours: 4, status_group: "done" },
      { id: "b", parent_id: "p", estimate_hours: 2, status_group: "open" },
    ]);
    expect(m.get("p")).toEqual({ percent: 67, done: 1, total: 2, spent: 0 });
  });

  it("falls back to weight 1.0 without estimates", () => {
    const m = weightedProgress([
      { id: "p", status_group: "open" },
      { id: "a", parent_id: "p", estimate_hours: 0, status_group: "done" },
      { id: "b", parent_id: "p", status_group: "open" },
    ]);
    expect(m.get("p")!.percent).toBe(50);
  });

  it("caps runaway depth and cycles defensively", () => {
    const chain: RollupItem[] = [{ id: "p", status_group: "open" }];
    for (let i = 1; i <= 14; i++)
      chain.push({ id: `c${i}`, parent_id: i === 1 ? "p" : `c${i - 1}`, status_group: i === 14 ? "done" : "open" });
    const m = weightedProgress(chain);
    expect(m.get("p")!.percent).toBe(0); // depth cap treats deep levels as leaf own-status
    expect(m.get("p")!.done).toBe(1);
    expect(m.get("p")!.total).toBe(14);
    const cyc = weightedProgress([
      { id: "a", parent_id: "b", status_group: "open" },
      { id: "b", parent_id: "a", status_group: "open" },
    ]);
    expect(cyc.get("a")!.percent).toBe(0); // real cycle: can't hang or NaN
  });

  it("parents only, full completion", () => {
    const all = weightedProgress([
      { id: "p", status_group: "open" },
      { id: "x", parent_id: "p", status_group: "done" },
      { id: "y", parent_id: "p", status_group: "done" },
    ]);
    expect(all.get("p")).toEqual({ percent: 100, done: 2, total: 2, spent: 0 });
    expect(weightedProgress([]).size).toBe(0);
  });
});
