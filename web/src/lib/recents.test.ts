/** M64-I193: palette recents helper — localStorage-backed, newest-first,
 * dedup, cap 5. Personal UI state: never the event stream. */
import { describe, expect, beforeEach, it } from "vitest";

const RECENTS_KEY = "apm-search-recents";
function loadRecents(): string[] {
  try { return JSON.parse(localStorage.getItem(RECENTS_KEY) || "[]"); } catch { return []; }
}
function pushRecent(term: string): string[] {
  const next = [term, ...loadRecents().filter((t) => t !== term)].slice(0, 5);
  localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  return next;
}

describe("search recents", () => {
  beforeEach(() => localStorage.removeItem(RECENTS_KEY));

  it("pushes newest first and dedupes", () => {
    pushRecent("部署");
    pushRecent("清单");
    pushRecent("部署"); // re-push moves it to front, no dup
    expect(loadRecents()).toEqual(["部署", "清单"]);
  });

  it("caps at 5", () => {
    for (const t of ["a", "b", "c", "d", "e", "f", "g"]) pushRecent(t);
    const got = loadRecents();
    expect(got.length).toBe(5);
    expect(got).toEqual(["g", "f", "e", "d", "c"]);
  });

  it("tolerates a corrupt stored value", () => {
    localStorage.setItem(RECENTS_KEY, "{not json");
    expect(loadRecents()).toEqual([]);
    pushRecent("ok");
    expect(loadRecents()).toEqual(["ok"]);
  });
});
