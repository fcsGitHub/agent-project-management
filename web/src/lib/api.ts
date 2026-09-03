/** Typed REST client for the AgentPM API (page and NL commands share it). */
export type Project = {
  id: string; name: string; description?: string; ontology: string; template: string;
  status: string; charter?: string; created_at: string; updated_at: string;
  features?: Feature[]; item_counts?: Record<string, number>; bootstrap?: Record<string, string>;
  disabled_fields?: string[]; gates_pending?: number;
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
  assignee_id?: string; estimate_hours?: number; start_date?: string | null; due_date?: string | null;
  milestone_id?: string | null; auto_scheduled?: number | boolean;
  custom_fields?: Record<string, unknown> | null;
  created_at: string; updated_at: string;
  relations?: { id: string; from_item: string; to_item: string; relation_type: string }[];
};
export type Milestone = {
  id: string; project_id: string; title: string; description?: string | null;
  due_date: string; status: string; created_at: string; updated_at: string;
  progress?: { items_total: number; items_done: number; done_ratio: number | null; overdue_items: number };
  items?: Pick<Item, "id" | "title" | "concept_id" | "status" | "status_group" | "assignee_id">[];
};
export type SavedView = {
  id: string; project_id: string; name: string; owner_id: string | null;
  is_public: number; definition: Record<string, string>;
  created_at: string; updated_at: string;
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
  id: string; project_id?: string; run_id?: string; conversation_id?: string; item_id?: string; kind: string;
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
export type ProjectReport = {
  project_id: string;
  funnel: Record<string, number>;
  concepts: Record<string, number>;
  gates_pending: (Pick<Approval, "id" | "kind" | "run_id" | "item_id" | "conversation_id" | "requested_at" | "payload_snapshot">)[];
  overdue: (Pick<Item, "id" | "title" | "status" | "project_id" | "created_at"> & {
    project_name?: string; status_group: string; reason: string;
  })[];
  throughput: {
    days: number;
    series: { date: string; created: number; done: number }[];
    created_total: number; done_total: number;
  };
};
export type MyWork = {
  user_id: string;
  items: (Item & { project_name?: string })[];
  approvals: (Pick<Approval, "id" | "project_id" | "kind" | "run_id" | "item_id" | "requested_at"> & { project_name?: string })[];
  projects: { id: string; name: string }[];
};
export type BoardData = {
  project_id: string; feature_id?: string; group_by: string;
  buckets: { id: string; name: string; items: Item[] }[];
  columns: { id: string; concept_id: string; concept_name: string; status: string; name: string; group: string }[];
  field?: { id: string; name: string; type: string } | null;
  groups?: { id: string; name: string; items: Item[] }[] | null;
  disabled_fields?: string[];
};
export type Ontology = {
  name: string; display_name: string; version: number; errors: string[];
  competency_questions: string[];
  concepts: {
    id: string; name: string; icon: string; default_phase?: string; agent_roles: string[];
    states: { id: string; name: string; group: string }[]; artifact_kinds: { id: string; deposits_to?: string }[];
    fields?: { id: string; name: string; type: string; values?: (string | number)[] }[];
  }[];
  phases: { id: string; name: string; gate?: string }[];
  relations: { id: string; name: string }[];
  asset_kinds: { id: string; name: string; library: string }[];
  libraries: { id: string; name: string; accepts: string[] }[];
};
export type OntologyCandidate = {
  id: string; kind: string; summary: string;
  patch: Record<string, unknown>;
  provenance: { rule: string; support: number; channels?: string[]; confidence?: number;
                llm_rationale?: string;
                sample_item_ids?: string[]; sample_run_ids?: string[]; sample_asset_ids?: string[] };
};
export type OntologyLearnResult = {
  ontology: string; version: number;
  scanned: { projects: number; items: number; relations: number; artifact_links: number };
  candidates: OntologyCandidate[];
  observations: { unused_concepts: string[] };
  llm?: { provider_mode: string; raw: number; accepted: number; merged: number;
          dropped_low_confidence: number; error?: string | null };
};
export type OntologyVersionEvent = {
  event_id: number; ts: string; actor_id: string;
  previous_version: number; version: number; applied_count: number;
  applied: { id: string; kind: string; summary: string; provenance_rule: string }[];
  summary: string;
};
export type OntologyHistory = {
  name: string; current_version: number; snapshots: number[];
  history: OntologyVersionEvent[];
};
export type OntologyDiff = {
  name: string; from_version: number; to_version: number;
  diff: {
    concepts: {
      added: { id: string; name?: string }[]; removed: { id: string; name?: string }[];
      modified: { id: string; name: string; changes: { type: string; detail: string }[] }[];
    };
    relations: { added: { id: string; name?: string }[]; removed: { id: string; name?: string }[] };
    phases: { added: { id: string; name?: string }[]; removed: { id: string; name?: string }[] };
    asset_kinds: { added: { id: string; name?: string }[]; removed: { id: string; name?: string }[] };
  };
  impact: {
    blocking: { kind: string; concept?: string; relation?: string; detail: string;
                item_count?: number; reference_count?: number;
                sample_items?: { id: string; title: string }[] }[];
    warnings: { kind: string; concept?: string; relation?: string; phase?: string;
                asset_kind?: string; detail: string }[];
  };
  summary: string;
  to_validation_errors: string[];
};
export type CqEvidence = { source: string; count: number; summary: string };
export type CqCheck = {
  name: string; checked: number; summary: string;
  questions: { question: string; status: "answerable" | "no_data" | "unmapped"; evidence: CqEvidence[] }[];
};
export type Artifact = {
  path: string; kind: string; commit: string; updated_at?: string; versions: number; deposits_to?: string;
};
export type Asset = {
  id: string; library_id: string; kind: string; title: string; status: string;
  tags?: string; version: number; citation_count: number; updated_at: string;
};
export type TemplatePack = {
  name: string; display_name: string; version: number; source: string; valid: boolean;
  concepts: number; states: number; fields: number; phases: number; relations: number;
  competency_questions: number; registered_at?: string; imported_at?: string;
  imported_by?: string; origin_ontology?: string;
};
export type AutomationRule = {
  id: string; project_id: string; name: string; trigger_event: string;
  condition: { concept_id?: string; fields?: Record<string, string | number | boolean> };
  action: { type: string; user_id?: string; value?: string | number | boolean | (string | number)[]; field_id?: string; status?: string };
  enabled: boolean; created_at: string; updated_at: string;
};
export type AutomationRuleIn = {
  name: string; trigger_event: string;
  condition: { concept_id?: string; fields?: Record<string, string | number | boolean> };
  action: { type: string; user_id?: string; value?: string | number | boolean | (string | number)[]; field_id?: string; status?: string };
  enabled?: boolean;
};
export type AutomationTestRun = {
  matched: boolean; reason?: string; item_id?: string; item_title?: string;
  action?: AutomationRule["action"];
};
export type AutomationRun = {
  event_id: number; ts: string; rule_name: string; trigger_event: string;
  trigger_event_id: number; item_id: string; item_title: string;
  result: { type: string; ok: boolean; detail: string };
};
export type Webhook = {
  id: string; project_id: string; url: string; events: string[];
  enabled: boolean; has_secret: boolean; secret?: string;
  created_at: string; updated_at: string;
};
export type DeliveryRecord = {
  delivery_id: string; event_type: string; event_id: number;
  attempts: number; status_code?: number; duration_ms?: number; error?: string;
};
export type TemplatePackPreview = {
  name: string; display_name: string; version: number; source: string;
  summary: { concepts: number; states: number; fields: number; phases: number; relations: number; competency_questions: number };
  competency_questions: string[];
  concepts: {
    id: string; name: string; icon: string;
    states: { id: string; name: string; group: string }[];
    fields: { id: string; name: string; type: string; values?: (string | number)[] }[];
    agent_roles: string[];
  }[];
  phases: { id: string; name: string; gate?: string }[];
  relations: { id: string; name: string }[];
  errors: string[];
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
  if (r.status === 401 && !path.startsWith("/auth/") && location.hash !== "#/login") {
    location.hash = "#/login"; // network 模式会话失效 → 登录页（M8-I28）
  }
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
  getProjectReport: (id: string) => req<ProjectReport>(`/projects/${id}/report`),
  getMyWork: () => req<MyWork>("/my/work"),

  listMilestones: (pid: string) => req<{ milestones: Milestone[] }>(`/projects/${pid}/milestones`),
  createMilestone: (pid: string, body: { title: string; due_date: string; description?: string }) =>
    req<Milestone>(`/projects/${pid}/milestones`, { method: "POST", body: JSON.stringify(body) }),
  patchMilestone: (id: string, body: Partial<Pick<Milestone, "title" | "description" | "due_date" | "status">>) =>
    req<Milestone>(`/milestones/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteMilestone: (id: string) => req<{ deleted: string }>(`/milestones/${id}`, { method: "DELETE" }),

  listViews: (pid: string) => req<{ views: SavedView[] }>(`/projects/${pid}/views`),
  createView: (pid: string, body: { name: string; definition: Record<string, string>; is_public: boolean }) =>
    req<SavedView>(`/projects/${pid}/views`, { method: "POST", body: JSON.stringify(body) }),
  patchView: (id: string, body: { name?: string; definition?: Record<string, string>; is_public?: boolean }) =>
    req<SavedView>(`/views/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteView: (id: string) => req<{ deleted: string }>(`/views/${id}`, { method: "DELETE" }),
  patchProjectFields: (id: string, body: { field_id: string; active: boolean }) =>
    req<Project>(`/projects/${id}/fields`, { method: "PATCH", body: JSON.stringify(body) }),
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
  getItem: (iid: string) => req<Item>(`/items/${iid}`),
  patchItem: (iid: string, body: Record<string, unknown>) =>
    req<Item>(`/items/${iid}`, { method: "PATCH", body: JSON.stringify(body) }),
  getBoard: (pid: string, featureId?: string, groupBy?: string) => {
    const q = new URLSearchParams();
    if (featureId) q.set("feature_id", featureId);
    if (groupBy) q.set("group_by", groupBy);
    const qs = q.toString();
    return req<BoardData>(`/projects/${pid}/board${qs ? `?${qs}` : ""}`);
  },
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

  listEvents: (params: { project_id?: string; event_type?: string; actor_type?: string; agg_type?: string; agg_id?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && q.set(k, String(v)));
    return req<{ events: AEvent[]; total: number }>(`/events?${q.toString()}`);
  },

  getOntology: (nameOrPid: string, isProject = false) =>
    req<Ontology>(isProject ? `/projects/${nameOrPid}/ontology` : `/ontologies/${nameOrPid}`),
  listOntologies: () => req<{ ontologies: { name: string; display_name: string; valid: boolean; errors: string[] }[] }>("/ontologies"),

  // Ontology learning (M4-I14, docs/08 §8)
  learnOntology: (name: string) =>
    req<OntologyLearnResult>(`/ontologies/${name}/learn`, { method: "POST" }),
  learnOntologyLlm: (name: string) =>
    req<OntologyLearnResult>(`/ontologies/${name}/learn-llm`, { method: "POST" }),
  applyOntology: (name: string, candidateIds: string[]) =>
    req<{ name: string; version: number; applied: { id: string; kind: string; summary: string }[] }>(
      `/ontologies/${name}/apply`,
      { method: "POST", body: JSON.stringify({ candidate_ids: candidateIds }) },
    ),
  getOntologyHistory: (name: string) =>
    req<OntologyHistory>(`/ontologies/${name}/history`),
  getOntologyDiff: (name: string, fromV?: number, toV?: number) => {
    const q = new URLSearchParams();
    if (fromV != null) q.set("from_version", String(fromV));
    if (toV != null) q.set("to_version", String(toV));
    return req<OntologyDiff>(`/ontologies/${name}/diff?${q.toString()}`);
  },
  cqCheck: (name: string) => req<CqCheck>(`/ontologies/${name}/cq-check`),

  // Auth (M8-I26/I28)
  authMe: () =>
    req<{ user_id: string; name: string; is_admin: boolean; source: "session" | "local" }>("/auth/me"),
  login: (userId: string, password: string) =>
    req<{ user_id: string; name: string }>("/auth/login", {
      method: "POST", body: JSON.stringify({ user_id: userId, password }),
    }),
  logout: () => req<{ ok: boolean }>("/auth/logout", { method: "POST" }),

  // Users / identity (M5-I19)
  listUsers: () =>
    req<{ users: { id: string; name: string; email?: string | null }[]; current: string; current_name: string }>("/users"),
  registerUser: (name: string) =>
    req<{ id: string; name: string }>("/users", { method: "POST", body: JSON.stringify({ name }) }),
  switchIdentity: (userId: string) =>
    req<{ current: string; name: string; previous: string }>(
      "/session/identity", { method: "POST", body: JSON.stringify({ user_id: userId }) },
    ),

  // Project members & roles (M8-I27)
  listMembers: (pid: string) =>
    req<{ members: { user_id: string; role: string; name?: string; created_at: string }[] }>(
      `/projects/${pid}/members`,
    ),
  addMember: (pid: string, body: { user_id: string; role?: string }) =>
    req<{ project_id: string; user_id: string; role: string }>(
      `/projects/${pid}/members`, { method: "POST", body: JSON.stringify(body) },
    ),
  changeMemberRole: (pid: string, body: { user_id: string; role: string }) =>
    req<{ project_id: string; user_id: string; role: string }>(
      `/projects/${pid}/members`, { method: "PATCH", body: JSON.stringify(body) },
    ),
  removeMember: (pid: string, userId: string) =>
    req<{ removed: boolean }>(`/projects/${pid}/members/${userId}`, { method: "DELETE" }),

  // Automation rules (M9-I29/I30): trigger × condition × action, event-sourced.
  listAutomations: (pid: string) =>
    req<{ rules: AutomationRule[] }>(`/projects/${pid}/automations`),
  createAutomation: (pid: string, body: AutomationRuleIn) =>
    req<AutomationRule>(`/projects/${pid}/automations`, { method: "POST", body: JSON.stringify(body) }),
  patchAutomation: (pid: string, ruleId: string, body: Partial<AutomationRuleIn>) =>
    req<AutomationRule>(`/projects/${pid}/automations/${ruleId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteAutomation: (pid: string, ruleId: string) =>
    req<{ deleted: boolean }>(`/projects/${pid}/automations/${ruleId}`, { method: "DELETE" }),
  testAutomation: (pid: string, ruleId: string) =>
    req<AutomationTestRun>(`/projects/${pid}/automations/${ruleId}/test`, { method: "POST" }),
  automationHistory: (pid: string, ruleId: string) =>
    req<{ runs: AutomationRun[]; total: number }>(`/projects/${pid}/automations/${ruleId}/runs`),

  // Outbound webhooks (M10-I32/I33): signed event push with delivery records.
  listWebhooks: (pid: string) =>
    req<{ webhooks: Webhook[] }>(`/projects/${pid}/webhooks`),
  createWebhook: (pid: string, body: { url: string; events: string[]; enabled?: boolean }) =>
    req<Webhook>(`/projects/${pid}/webhooks`, { method: "POST", body: JSON.stringify(body) }),
  patchWebhook: (pid: string, hookId: string, body: { url?: string; events?: string[]; enabled?: boolean }) =>
    req<Webhook>(`/projects/${pid}/webhooks/${hookId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteWebhook: (pid: string, hookId: string) =>
    req<{ deleted: boolean }>(`/projects/${pid}/webhooks/${hookId}`, { method: "DELETE" }),
  rotateWebhookSecret: (pid: string, hookId: string) =>
    req<{ webhook_id: string; secret: string }>(`/projects/${pid}/webhooks/${hookId}/rotate`, { method: "POST" }),
  replayWebhookDelivery: (pid: string, hookId: string, deliveryId: string) =>
    req<DeliveryRecord>(`/projects/${pid}/webhooks/${hookId}/replay/${deliveryId}`, { method: "POST" }),
  pingWebhook: (pid: string, hookId: string) =>
    req<DeliveryRecord>(`/projects/${pid}/webhooks/${hookId}/ping`, { method: "POST" }),

  // Notification center (M10-I34): per-user feed with event-sourced read state.
  listNotifications: () =>
    req<{ notifications: { id: string; project_id: string; user_id: string; kind: string;
      summary: string; ref_event_id: number | null; read: number; created_at: string }[];
      unread: number; user_id: string; email_enabled: boolean }>("/notifications"),
  markNotificationsRead: (body: { ids?: string[]; all?: boolean }) =>
    req<{ ok: boolean }>("/notifications/read", { method: "POST", body: JSON.stringify(body) }),
  setNotificationPrefs: (body: { email_enabled: boolean }) =>
    req<{ user_id: string; email_enabled: boolean }>("/notifications/prefs", { method: "POST", body: JSON.stringify(body) }),
  getFeedKey: () =>
    req<{ user_id: string; feed_key: string; created: boolean }>("/me/feed-key"),
  rotateFeedKey: () =>
    req<{ user_id: string; feed_key: string }>("/me/feed-key/rotate", { method: "POST" }),

  exportOntology: (name: string) =>
    req<Record<string, unknown>>(`/ontologies/${name}/export`),
  importOntology: (pack: Record<string, unknown>, asName: string) =>
    req<{ name: string; version: number; roles: { id: string; action: string }[] }>(
      `/ontologies/import`,
      { method: "POST", body: JSON.stringify({ pack, as_name: asName }) },
    ),

  // Assets (I12)
  listAssets: (params?: { library?: string; kind?: string; q?: string }) => {
    const q = new URLSearchParams();
    Object.entries(params ?? {}).forEach(([k, v]) => v && q.set(k, v));
    return req<{ assets: Asset[] }>(`/assets?${q.toString()}`);
  },

  // Template packs (M7-I23/I24)
  listTemplatePacks: () => req<{ packs: TemplatePack[] }>("/template-packs"),
  previewTemplatePack: (name: string) => req<TemplatePackPreview>(`/template-packs/${name}`),
  instantiateTemplatePack: (name: string, body: { project_name: string; requirement?: string }) =>
    req<Project>(`/template-packs/${name}/instantiate`, { method: "POST", body: JSON.stringify(body) }),
  assetToPack: (assetId: string, packName: string) =>
    req<{ name: string; origin_ontology: string; source: string }>("/template-packs/from-asset", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, pack_name: packName }),
    }),

  // NL commands (I10)
  uiCommand: (utterance: string, page_state: Record<string, unknown>) =>
    req<{
      id: string; actions: { action: string; params: Record<string, unknown>; read_only: boolean; status?: string }[];
      requires_confirmation: boolean; reply?: string;
    }>("/ui_commands", { method: "POST", body: JSON.stringify({ utterance, page_state }) }),
  confirmUiCommand: (id: string) => req<{ status: string }>(`/ui_commands/${id}/confirm`, { method: "POST" }),
};
