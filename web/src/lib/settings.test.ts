import { describe, expect, it } from "vitest";
import { SETTINGS_SECTIONS, budgetOk } from "./settings";

describe("budgetOk", () => {
  it("empty means budget disabled (legal); otherwise non-negative finite only", () => {
    expect(budgetOk("")).toBe(true);
    expect(budgetOk("  ")).toBe(true);
    expect(budgetOk("120")).toBe(true);
    expect(budgetOk("0")).toBe(true);
    expect(budgetOk("-5")).toBe(false);
    expect(budgetOk("abc")).toBe(false);
    expect(budgetOk("Infinity")).toBe(false);
  });
});

describe("SETTINGS_SECTIONS", () => {
  it("declares the four hub sections with stable ids for deep links", () => {
    expect(SETTINGS_SECTIONS.map((s) => s.id)).toEqual(["project", "access", "notify", "board"]);
  });
});
