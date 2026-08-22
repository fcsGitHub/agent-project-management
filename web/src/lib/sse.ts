/** SSE → TanStack Query bridge: one global stream invalidates queries per event. */
import { QueryClient } from "@tanstack/react-query";
import type { AEvent } from "./api";

const BASE = (import.meta.env.VITE_API_BASE || "/api").replace("/api", "");

export function connectStream(queryClient: QueryClient, projectId?: string) {
  const es = new EventSource(`${BASE}/api/stream${projectId ? `?project_id=${projectId}` : ""}`);
  es.addEventListener("apm", (ev) => {
    try {
      const event = JSON.parse((ev as MessageEvent).data) as AEvent;
      invalidateFor(queryClient, event);
    } catch { /* malformed frame */ }
  });
  return es;
}

function invalidateFor(qc: QueryClient, e: AEvent) {
  const t = e.event_type;
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
