/** I207: board card live-run badges — SSE-driven overlay on top of the
 * polled `runs` query. run.requested carries item_id + agent_role (the only
 * chance to bind run→item: terminal events carry just the run id as agg_id),
 * so the map is built there and terminal states are resolved by lookup.
 * Result badges expire after a short TTL; running/interrupted persist until
 * a follow-up event (resumed/succeeded/failed) or a page reload (overlay is
 * ephemeral by design — the stale `runByItem` link remains the fallback). */
import type { AEvent } from "./api";

export type LiveRunStatus = "running" | "interrupted" | "succeeded" | "failed";
export type LiveRun = { runId: string; itemId: string; role: string; status: LiveRunStatus; at: number };
export type LiveRunState = { runs: Record<string, LiveRun> };

/** 终态徽标的展示时长——之后回落到 runs query 的既有文本链接。 */
export const RESULT_TTL_MS = 8000;

export function applyRunEvent(state: LiveRunState, e: AEvent, now = Date.now()): LiveRunState {
  const t = e.event_type;
  const prev = state.runs[e.agg_id];
  if (t === "run.requested") {
    const itemId = typeof e.payload.item_id === "string" ? e.payload.item_id : "";
    if (!itemId) return state; // 无工件关联的 run 不上看板徽标
    const role = typeof e.payload.agent_role === "string" ? e.payload.agent_role : "";
    return { runs: { ...state.runs, [e.agg_id]: { runId: e.agg_id, itemId, role, status: "running", at: now } } };
  }
  if (!prev) return state; // requested 前科是 run→item 映射的唯一来源
  if (t === "run.started" || t === "run.resumed") {
    if (prev.status === "running") return state;
    return { runs: { ...state.runs, [e.agg_id]: { ...prev, status: "running", at: now } } };
  }
  if (t === "run.interrupted") {
    if (prev.status === "interrupted") return state;
    return { runs: { ...state.runs, [e.agg_id]: { ...prev, status: "interrupted", at: now } } };
  }
  if (t === "run.succeeded" || t === "run.failed") {
    const status = t === "run.succeeded" ? "succeeded" : "failed";
    return { runs: { ...state.runs, [e.agg_id]: { ...prev, status, at: now } } };
  }
  return state; // forked/span_*/token_delta/tokens_recorded 与徽标无关
}

/** 结果态徽标到期清除（interrupted 是待人行动态，无 TTL）。 */
export function pruneLiveRuns(state: LiveRunState, now = Date.now(), ttl = RESULT_TTL_MS): LiveRunState {
  const runs: Record<string, LiveRun> = {};
  let changed = false;
  for (const [id, r] of Object.entries(state.runs)) {
    const expired = (r.status === "succeeded" || r.status === "failed") && now - r.at > ttl;
    if (expired) changed = true;
    else runs[id] = r;
  }
  return changed ? { runs } : state;
}

/** 卡片徽标查询：该工件最新一条 live run（无则 null——回落 runs query）。 */
export function liveBadgeFor(state: LiveRunState, itemId: string): LiveRun | null {
  let best: LiveRun | null = null;
  for (const r of Object.values(state.runs)) {
    if (r.itemId !== itemId) continue;
    if (!best || r.at > best.at) best = r;
  }
  return best;
}
