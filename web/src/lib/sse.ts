/** SSE → TanStack Query bridge: one global stream invalidates queries per event.
 * I138: `run.token_delta` 是瞬态流式增量（不落库），经订阅口直达对话视图逐字
 * 渲染，绝不触发 query 失效。 */
import { QueryClient } from "@tanstack/react-query";
import type { AEvent } from "./api";

const BASE = (import.meta.env.VITE_API_BASE || "/api").replace("/api", "");

type StreamHandler = (e: AEvent) => void;
const handlers = new Set<StreamHandler>();

/** 订阅原始流事件（如 token 逐字渲染）；返回注销函数。 */
export function onStreamEvent(h: StreamHandler): () => void {
  handlers.add(h);
  return () => handlers.delete(h);
}

export function connectStream(queryClient: QueryClient, projectId?: string) {
  const es = new EventSource(`${BASE}/api/stream${projectId ? `?project_id=${projectId}` : ""}`);
  es.addEventListener("apm", (ev) => {
    try {
      const event = JSON.parse((ev as MessageEvent).data) as AEvent;
      handlers.forEach((h) => {
        try { h(event); } catch { /* handler isolation */ }
      });
      invalidateFor(queryClient, event);
    } catch { /* malformed frame */ }
  });
  return es;
}

function invalidateFor(qc: QueryClient, e: AEvent) {
  const t = e.event_type;
  if (t === "run.token_delta") return; // 高频瞬态增量——渲染走订阅口，失效归零
  const keys: string[] = [];
  if (t.startsWith("project") || t.startsWith("ontology")) keys.push("projects", "phases", "graph", "ontology");
  if (t.startsWith("feature")) keys.push("features", "project");
  if (t.startsWith("conversation") || t === "message.created" || t === "prompt.updated")
    keys.push("conversations", "conversation");
  if (t.startsWith("item")) keys.push("items", "board", "project", "graph");
  if (t.startsWith("run") || t.startsWith("approval")) keys.push("runs", "run", "approvals", "conversation", "items", "board", "events", "phases");
  if (t.startsWith("artifact")) keys.push("artifacts", "artifact", "feature");
  if (t.startsWith("asset") || t === "asset.linked") keys.push("assets", "asset");
  if (t.startsWith("ui_command")) keys.push("events");
  keys.push("events", "timeline");
  qc.invalidateQueries({ queryKey: ["health"] });
  keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}
