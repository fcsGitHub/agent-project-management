import { describe, expect, it } from "vitest";
import { bundleWatch } from "./notify";
import type { BundleInput } from "./notify";

const note = (id: string, kind: string, project_id: string): BundleInput => ({
  id, kind, project_id, summary: `s-${id}`, read: 0, created_at: "2026-09-21T00:00:00",
});

describe("bundleWatch", () => {
  it("collapses consecutive same-project watch notes into one bundle", () => {
    const rows = bundleWatch([
      note("1", "assigned", "p1"),
      note("2", "watch", "p1"),
      note("3", "watch", "p1"),
      note("4", "watch", "p1"),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[0].kind).toBe("single");
    const bundle = rows[1];
    expect(bundle.kind).toBe("bundle");
    if (bundle.kind === "bundle") {
      expect(bundle.notes.map((n) => n.id)).toEqual(["2", "3", "4"]);
    }
  });

  it("a different project or kind breaks the bundle", () => {
    const rows = bundleWatch([
      note("1", "watch", "p1"),
      note("2", "watch", "p2"), // project change breaks
      note("3", "watch", "p2"),
      note("4", "assigned", "p2"), // kind change breaks
      note("5", "watch", "p2"), // starts a NEW bundle after the break
    ]);
    expect(rows.filter((r) => r.kind === "bundle")).toHaveLength(3);
  });

  it("a single watch note still renders as a (1-item) bundle row", () => {
    const rows = bundleWatch([note("1", "watch", "p1"), note("2", "approval", "p1")]);
    expect(rows).toHaveLength(2);
    expect(rows[0].kind).toBe("bundle");
  });

  it("non-watch kinds pass through untouched and keep order", () => {
    const rows = bundleWatch([note("1", "assigned", "p1"), note("2", "approval", "p1")]);
    expect(rows.map((r) => (r.kind === "single" ? r.note.id : "bundle")))
      .toEqual(["1", "2"]);
  });
});
