import { describe, expect, it } from "vitest";
import { applyRunEvent, liveBadgeFor, pruneLiveRuns, type LiveRunState } from "./runlive";
import type { AEvent } from "./api";

const ev = (event_type: string, agg_id: string, payload: Record<string, unknown> = {}): AEvent => ({
  id: 1, ts: "2026-09-29T00:00:00", actor_type: "human", actor_id: "u1", project_id: "p1",
  agg_type: "run", agg_id, event_type, payload,
});

describe("applyRunEvent", () => {
  it("requested binds run→item and lights running; terminal states resolve by agg_id lookup", () => {
    let s: LiveRunState = { runs: {} };
    s = applyRunEvent(s, ev("run.requested", "r1", { item_id: "i1", agent_role: "dev-agent" }), 1000);
    expect(liveBadgeFor(s, "i1")).toMatchObject({ status: "running", role: "dev-agent" });

    s = applyRunEvent(s, ev("run.succeeded", "r1", { outcome: "ok" }), 2000);
    expect(liveBadgeFor(s, "i1")?.status).toBe("succeeded");
  });

  it("terminal events for unknown run ids are ignored (no requested history)", () => {
    const s = applyRunEvent({ runs: {} }, ev("run.succeeded", "rX"), 1000);
    expect(s.runs).toEqual({});
    expect(liveBadgeFor(s, "i1")).toBeNull();
  });

  it("requested without item_id never enters the overlay; resumed returns to running", () => {
    let s = applyRunEvent({ runs: {} }, ev("run.requested", "r2", { agent_role: "qa-agent" }), 1000);
    expect(s.runs).toEqual({}); // 无工件关联——徽标面不关心

    s = applyRunEvent({ runs: {} }, ev("run.requested", "r3", { item_id: "i3", agent_role: "dev-agent" }), 1000);
    s = applyRunEvent(s, ev("run.interrupted", "r3", { reason: "awaiting_approval" }), 2000);
    expect(liveBadgeFor(s, "i3")?.status).toBe("interrupted");
    s = applyRunEvent(s, ev("run.resumed", "r3"), 3000);
    expect(liveBadgeFor(s, "i3")?.status).toBe("running");
  });
});

describe("pruneLiveRuns", () => {
  it("expired result badges are dropped; running/interrupted persist", () => {
    let s: LiveRunState = { runs: {} };
    s = applyRunEvent(s, ev("run.requested", "r1", { item_id: "i1", agent_role: "dev-agent" }), 0);
    s = applyRunEvent(s, ev("run.succeeded", "r1"), 1000);
    s = applyRunEvent(s, ev("run.requested", "r2", { item_id: "i2", agent_role: "qa-agent" }), 1000);
    s = applyRunEvent(s, ev("run.interrupted", "r2"), 2000);

    const pruned = pruneLiveRuns(s, 1000 + 8001);
    expect(pruned.runs.r1).toBeUndefined(); // 终态超 TTL 清除
    expect(pruned.runs.r2?.status).toBe("interrupted"); // 挂起无 TTL
    // 未到期原样返回（引用相等——避免无谓重渲染）
    expect(pruneLiveRuns(s, 5000)).toBe(s);
  });
});
