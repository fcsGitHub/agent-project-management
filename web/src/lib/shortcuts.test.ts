import { describe, expect, it } from "vitest";
import { SHORTCUTS, isTypingTarget } from "./shortcuts";

describe("shortcuts registry", () => {
  it("has no duplicate key bindings", () => {
    const seen = new Set<string>();
    for (const s of SHORTCUTS) {
      const k = s.keys.join("+");
      expect(seen.has(k), `duplicate binding: ${k}`).toBe(false);
      seen.add(k);
    }
  });
  it("documents the I95 surface (? overlay, j/k cursor, Enter, C create)", () => {
    const flat = SHORTCUTS.map((s) => s.keys.join("+")).join("|");
    expect(flat).toContain("?");
    expect(flat).toContain("J");
    expect(flat).toContain("K");
    expect(flat).toContain("Enter");
    expect(flat).toContain("C");
  });
});

describe("isTypingTarget", () => {
  const fake = (t: object) => t as unknown as EventTarget;
  it("yields to text entry surfaces", () => {
    for (const tag of ["INPUT", "TEXTAREA", "SELECT"]) {
      expect(isTypingTarget(fake({ tagName: tag }))).toBe(true);
    }
    expect(isTypingTarget(fake({ tagName: "DIV", isContentEditable: true }))).toBe(true);
  });
  it("lets single-key shortcuts run elsewhere", () => {
    expect(isTypingTarget(fake({ tagName: "DIV" }))).toBe(false);
    expect(isTypingTarget(fake({ tagName: "BODY" }))).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});
