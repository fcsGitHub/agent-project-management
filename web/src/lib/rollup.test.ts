import { describe, expect, it } from "vitest";
import { subtaskProgress } from "./rollup";

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
