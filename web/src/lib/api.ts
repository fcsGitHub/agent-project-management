/** Typed REST client for the AgentPM API (page and NL commands share it). */
export type Project = {
  id: string; name: string; description?: string; ontology: string; template: string;
  status: string; charter?: string; created_at: string; updated_at: string;
  features?: Feature[]; item_counts?: Record<string, number>; bootstrap?: Record<string, string>;
};
export type Feature = {
  id: string; project_id: string; title: string; brief?: string; status: string;
  sort_order: number; created_at: string; updated_at: string;
};
export type Conversation = {
  id: string; project_id: string; feature_id?: string; kind: string; title?: string;
  status: string; item_id?: string; run_id?: string; instruction?: string;
  created_at: string; updated_at: string; messages?: Message[];
};
export type Message = {
  id: string; conversation_id: string; parent_id?: string; role: string;
  actor_type?: string; actor_id?: string; content: string; span_id?: string; created_at: string;
};
export type Item = {
  id: string; project_id: string; feature_id?: string; concept_id: string; title: string;
  status: string; status_group: string; priority?: string; assignee_type?: string;
  assignee_id?: string; estimate_hours?: number; created_at: string; updated_at: string;
  relations?: { id: string; from_item: string; to_item: string; relation_type: string }[];
};
export type Run = {
  id: string; project_id?: string; conversation_id: string; agent_role?: string;
  item_id?: string; status: string; started_at?: string; ended_at?: string;
  error?: string; input?: string; conversation_title?: string; item_title?: string;
  total_input_tokens?: number; total_output_tokens?: number;
};
export type Span = {
  id: string; run_id: string; parent_id?: string; span_kind: string; name: string;
  ts_start?: string; ts_end?: string; status?: string;
  attributes: Record<string, unknown>; io?: Record<string, unknown> | null;
};
export type Approval = {
  id: string; project_id?: string; run_id?: string; conversation_id?: string; kind: string;
  status: string; requested_at?: string; decided_at?: string; reviewer_id?: string;
  comment?: string; payload_snapshot: {
    gate?: string; gate_label?: string; role?: string; tool?: string; summary?: string;
    artifact?: { path?: string; commit?: string }; edit_note?: string; revise_notes?: string[];
  };
};
export type AEvent = {
  id: number; ts: string; actor_type: string; actor_id: string; project_id: string;
  agg_type: string; agg_id: string; event_type: string; payload: Record<string, unknown>;
};
export type BoardData = {
  project_id: string; feature_id?: string; group_by: string;
  buckets: { id: string; name: string; items: Item[] }[];
  columns: { id: string; concept_id: string; concept_name: string; status: string; name: string; group: string }[];
};
export type Ontology = {
  name: string; display_name: string; version: number; errors: string[];
  competency_questions: string[];
  concepts: {
    id: string; name: string; icon: string; default_phase?: string; agent_roles: string[];
    states: { id: string; name: string; group: string }[]; artifact_kinds: { id: string; deposits_to?: string }[];
  }[];
  phases: { id: string; name: string; gate?: string }[];
  relations: { id: string; name: string }[];
  asset_kinds: { id: string; name: string; library: string }[];
  libraries: { id: string; name: string; accepts: string[] }[];
};
export type Artifact = {
  path: string; kind: string; commit: string; updated_at?: string; versions: number; deposits_to?: string;
};
export type Asset = {
  id: string; library_id: string; kind: string; title: string; status: string;
  tags?: string; version: number; citation_count: number; updated_at: string;
};
export type Context = {
  L1: { content?: string; version?: number; editable: boolean };
  L2: { content?: string };
  L3: { content?: string; version?: number; editable: boolean };
  merged_preview: string;
};

const BASE = import.meta.env.VITE_API_BASE || "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const body = await r.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch { /* keep status */ }
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<{ status: string; version: string; provider_mode: string }>("/health"),

  listProjects: () => req<{ projects: Project[] }>("/projects"),
  createProject: (body: { name: string; ontology: string; requirement?: string; description?: string }) =>
    req<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id: string) => req<Project>(`/projects/${id}`),
  patchProject: (id: string, body: Partial<Pick<Project, "name" | "description" | "charter">>) =>
    req<Project>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  getPhases: (id: string) =>
    req<{ phases: { id: string; name: string; gate?: string; gate_label?: string; status: string }[] }>(`/projects/${id}/phases`),
  getGraph: (id: string) =>
    req<{ nodes: { id: string; kind: string; label: string; [k: string]: unknown }[]; edges: { source: string; target: string; kind: string }[] }>(`/projects/${id}/graph`),
  deliver: (id: string) => req<{ conversation_id: string; run_id: string }>(`/projects/${id}/deliver`, { method: "POST" }),

  listFeatures: (pid: string) => req<{ features: Feature[] }>(`/projects/${pid}/features`),
  createFeature: (pid: string, body: { title: string; brief?: string }) =>
    req<Feature>(`/projects/${pid}/features`, { method: "POST", body: JSON.stringify(body) }),
  getFeature: (fid: string) => req<Feature & { items?: Item[]; conversations?: Conversation[]; artifacts?: Artifact[] }>(`/features/${fid}`),
  patchFeature: (fid: string, body: Partial<Pick<Feature, "title" | "brief">>) =>
    req<Feature>(`/features/${fid}`, { method: "PATCH", body: JSON.stringify(body) }),

  listConversations: (pid: string, params?: { feature_id?: string }) =>
    req<{ conversations: Conversation[] }>(`/conversations?project_id=${pid}${params?.feature_id ? `&feature_id=${params.feature_id}` : ""}`),
  getConversation: (cid: string) => req<Conversation>(`/conversations/${cid}`),
  createConversation: (body: { project_id: string; feature_id?: string; kind: string; title?: string; instruction?: string; item_id?: string }) =>
    req<Conversation>("/conversations", { method: "POST", body: JSON.stringify(body) }),
  sendMessage: (cid: string, content: string) =>
    req<{ message: Message; interrupted: boolean }>(`/conversations/${cid}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
  interruptConversation: (cid: string) => req<Conversation>(`/conversations/${cid}/interrupt`, { method: "POST" }),
  resumeConversation: (cid: string, instruction?: string) =>
    req<Conversation>(`/conversations/${cid}/resume`, { method: "POST", body: JSON.stringify({ instruction }) }),
  getContext: (cid: string) => req<Context>(`/conversations/${cid}/context`),
  putContext: (cid: string, level: "L1" | "L3", content: string) =>
    req<Context>(`/conversations/${cid}/context/${level}`, { method: "PUT", body: JSON.stringify({ content }) }),

  listItems: (pid: string, params?: { feature_id?: string }) =>
    req<{ items: Item[] }>(`/projects/${pid}/items${params?.feature_id ? `?feature_id=${params.feature_id}` : ""}`),
  patchItem: (iid: string, body: Record<string, unknown>) =>
    req<Item>(`/items/${iid}`, { method: "PATCH", body: JSON.stringify(body) }),
  getBoard: (pid: string, featureId?: string) =>
    req<BoardData>(`/projects/${pid}/board${featureId ? `?feature_id=${featureId}` : ""}`),
  batchStart: (ids: string[]) =>
    req<{ started: { item_id: string; run_id?: string; conversation_id: string }[]; skipped: { item_id: string; reason: string }[] }>("/orchestrator/batch-start", { method: "POST", body: JSON.stringify({ item_ids: ids }) }),

  listRuns: (pid: string) => req<{ runs: Run[] }>(`/runs?project_id=${pid}`),
  getRun: (rid: string) => req<Run>(`/runs/${rid}`),
  getSpans: (rid: string) => req<{ spans: Span[] }>(`/runs/${rid}/spans`),
  getTimeline: (rid: string) =>
    req<{ entries: { ts: string; actor_type: string; kind: string; name?: string; event_type?: string; summary?: string; span_kind?: string; status?: string }[] }>(`/runs/${rid}/timeline`),

  listApprovals: (params?: { status?: string; project_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.project_id) q.set("project_id", params.project_id);
    return req<{ approvals: Approval[] }>(`/approvals?${q.toString()}`);
  },
  decide: (aid: string, decision: "approved" | "rejected" | "edit_and_resume", comment?: string) =>
    req<Approval>(`/approvals/${aid}/decision`, { method: "POST", body: JSON.stringify({ decision, comment }) }),
  bulkDecide: (ids: string[], decision = "approved") =>
    req<{ results: unknown[] }>("/approvals/bulk-decision", { method: "POST", body: JSON.stringify({ ids, decision }) }),

  listArtifacts: (pid: string) => req<{ artifacts: Artifact[] }>(`/projects/${pid}/artifacts`),
  getArtifact: (pid: string, path: string) =>
    req<{ path: string; content: string; history: { commit: string; date: string; message: string }[]; diff_vs_previous: string }>(
      `/projects/${pid}/artifacts/${path}`),

  listEvents: (params: { project_id?: string; event_type?: string; actor_type?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && q.set(k, String(v)));
    return req<{ events: AEvent[]; total: number }>(`/events?${q.toString()}`);
  },

  getOntology: (nameOrPid: string, isProject = false) =>
    req<Ontology>(isProject ? `/projects/${nameOrPid}/ontology` : `/ontologies/${nameOrPid}`),
  listOntologies: () => req<{ ontologies: { name: string; display_name: string; valid: boolean; errors: string[] }[] }>("/ontologies"),

  // Assets (I12)
  listAssets: (params?: { library?: string; kind?: string; q?: string }) => {
    const q = new URLSearchParams();
    Object.entries(params ?? {}).forEach(([k, v]) => v && q.set(k, v));
    return req<{ assets: Asset[] }>(`/assets?${q.toString()}`);
  },

  // NL commands (I10)
  uiCommand: (utterance: string, page_state: Record<string, unknown>) =>
    req<{
      id: string; actions: { action: string; params: Record<string, unknown>; read_only: boolean; status?: string }[];
      requires_confirmation: boolean; reply?: string;
    }>("/ui_commands", { method: "POST", body: JSON.stringify({ utterance, page_state }) }),
  confirmUiCommand: (id: string) => req<{ status: string }>(`/ui_commands/${id}/confirm`, { method: "POST" }),
};
