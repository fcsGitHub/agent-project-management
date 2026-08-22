import { describe, expect, it } from "vitest";
import { timeAgo } from "./fmt";

describe("timeAgo", () => {
  it("renders recent timestamps as 刚刚", () => {
    expect(timeAgo(new Date().toISOString())).toBe("刚刚");
  });
  it("renders minutes ago", () => {
    const d = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(timeAgo(d)).toBe("5 分钟前");
  });
});
