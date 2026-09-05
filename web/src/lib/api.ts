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
  milestone_id?: string | null; auto_scheduled?: number | boolean; parent_id?: string | null;
  custom_fields?: Record<string, unknown> | null;
  spent_minutes?: number;
  created_at: string; updated_at: string;
  relations?: { id: string; from_item: string; to_item: string; relation_type: string; lag_days?: number | null }[];
};
export type Milestone = {
  id: string; project_id: string; title: string; description?: string | null;
  due_date: string; status: string; created_at: string; updated_at: string;
  progress?: { items_total: number; items_done: number; done_ratio: number | null; overdue_items: number };
  items?: Pick<Item, "id" | "title" | "concept_id" | "status" | "status_group" | "assignee_id">[];
};
export type SavedView = {
  id: string; project_id: string; name: string; owner_id: string | null;
  is_public: number; is_default?: number; definition: Record<string, string>;
  created_at: string; updated_at: string;
};
export type ItemComment = {
  id: string; item_id: string; project_id: string; author_id: string;
  author_name?: string | null; body: string; mentions: string;
  created_at: string; edited_at?: string | null; deleted_at: string | null;
};
export type TimeEntry = {
  id: string; item_id: string; project_id: string; user_id: string;
  user_name?: string | null; minutes: number; spent_on: string;
  note: string; created_at: string; deleted_at: string | null;
};
export type MyTimelogDay = {
  date: string;
  entries: (TimeEntry & { item_title?: string | null; project_name?: string | null })[];
  total_minutes: number;
};
export type MyTimelog = {
  user_id: string; days: MyTimelogDay[]; total_minutes: number;
  window: { start: string; end: string; days: number };
};
export type PortfolioRow = {
  project_id: string; name: string; ontology: string;
  funnel: Record<string, number>; items_active: number;
  gates_pending: number; overdue: number; timelog_minutes: number;
};
export type PortfolioReport = {
  projects: PortfolioRow[]; totals: PortfolioRow;
  generated_at: string;
};
export type RoadmapMilestone = {
  id: string; title: string; due_date: string; status: string; overdue: boolean;
  progress: { items_total: number; items_done: number; done_ratio: number | null };
};
export type RoadmapData = {
  projects: { project_id: string; name: string; milestones: RoadmapMilestone[] }[];
  today: string;
  generated_at: string;
};
export type MemberWorkload = {
  user_id: string; user_name: string;
  active: number; overdue: number; minutes_7d: number;
  projects: Record<string, number>;
};
export type WorkloadData = { members: MemberWorkload[]; today: string; generated_at: string };
export type MyScheduleItem = {
  id: string; title: string; status_group: string; priority?: string | null;
  start_date?: string | null; due_date?: string | null;
  project_id: string; project_name: string;
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
  week_minutes?: number;
};
export type TimelogReport = {
  project_id: string;
  total_minutes: number;
  by_user: { user_id: string; user_name?: string | null; minutes: number }[];
  by_day: { date: string; minutes: number }[];
  window_days: number;
};
export type Timesheet = {
  id: string; project_id: string; user_id: string; user_name?: string | null;
  project_name?: string | null;
  period_start: string; period_end: string;
  total_minutes: number; entry_count: number;
  status: "submitted" | "approved" | "rejected";
  decided_by?: string | null; decided_at?: string | null; reason?: string | null;
  created_at: string; updated_at: string;
};
export type BoardData = {
  project_id: string; feature_id?: string; applied_view_id?: string; group_by: string;
  buckets: { id: string; name: string; items: Item[] }[];
  columns: { id: string; concept_id: string; concept_name: string; status: string; name: string; group: string }[];
  field?: { id: string; name: string; type: string } | null;
  groups?: { id: string; name: string; items: Item[] }[] | null;
  disabled_fields?: string[];
  wip?: Record<string, number>;
  wip_limits?: Record<string, number>;
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
  action: { type: string; user_id?: string; value?: string | number | boolean | (string | number)[]; field_id?: string; status?: string; concept_id?: string; title?: string };
  enabled: boolean; created_at: string; updated_at: string;
};
export type AutomationRuleIn = {
  name: string; trigger_event: string;
  condition: { concept_id?: string; fields?: Record<string, string | number | boolean> };
  action: { type: string; user_id?: string; value?: string | number | boolean | (string | number)[]; field_id?: string; status?: string; concept_id?: string; title?: string };
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

  listProjects: (includeArchived = false) =>
    req<{ projects: Project[] }>(`/projects${includeArchived ? "?include_archived=true" : ""}`),
  getPortfolioReport: () =>
    req<PortfolioReport>("/portfolio/report"),
  portfolioRoadmap: () =>
    req<RoadmapData>("/portfolio/roadmap"),
  portfolioWorkload: () =>
    req<WorkloadData>("/portfolio/workload"),
  portfolioHealth: () =>
    req<{ projects: { project_id: string; name: string; score: number | null;
          factors: { active: number; overdue: number; stale: number; done_7d: number; gates: number } }[] }>(
      "/portfolio/health"),
  archiveProject: (pid: string) =>
    req<Project>(`/projects/${pid}/archive`, { method: "POST" }),
  reopenProject: (pid: string) =>
    req<Project>(`/projects/${pid}/reopen`, { method: "POST" }),
  cloneProject: (pid: string, body: { name: string; structure?: boolean; items?: boolean; milestones?: boolean }) =>
    req<{ project: Project; counts: Record<string, number> }>(`/projects/${pid}/clone`, { method: "POST", body: JSON.stringify(body) }),
  createProject: (body: { name: string; ontology: string; requirement?: string; description?: string }) =>
    req<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id: string) => req<Project>(`/projects/${id}`),
  getProjectReport: (id: string) => req<ProjectReport>(`/projects/${id}/report`),
  getTimelogReport: (id: string, days = 14) =>
    req<TimelogReport>(`/projects/${id}/timelog_report?days=${days}`),
  getMyWork: () => req<MyWork>("/my/work"),
  getMySchedule: () =>
    req<{ items: MyScheduleItem[]; today: string }>("/my/schedule"),
  getMyTimelog: (days = 60) => req<MyTimelog>(`/my/timelog?days=${days}`),

  listMilestones: (pid: string) => req<{ milestones: Milestone[] }>(`/projects/${pid}/milestones`),
  getMilestoneBurndown: (mid: string) =>
    req<{ milestone_id: string; title: string; due_date: string; total: number; remaining: number;
          series: { date: string; remaining: number }[]; ideal: { date: string; remaining: number }[];
          velocity: { days: number; done: number } }>(`/milestones/${mid}/burndown`),
  submitTimesheet: (body: { project_id: string; period_start: string; period_end: string }) =>
    req<Timesheet>("/me/timesheets/submit", { method: "POST", body: JSON.stringify(body) }),
  myTimesheets: () =>
    req<{ timesheets: Timesheet[] }>("/me/timesheets"),
  listTimesheets: (pid: string) =>
    req<{ timesheets: Timesheet[]; can_approve: boolean }>(`/projects/${pid}/timesheets`),
  approveTimesheet: (id: string) =>
    req<Timesheet>(`/timesheets/${id}/approve`, { method: "POST" }),
  rejectTimesheet: (id: string, reason: string) =>
    req<Timesheet>(`/timesheets/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),
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
  makeViewDefault: (id: string) => req<SavedView>(`/views/${id}/make-default`, { method: "POST" }),

  oidcStatus: () =>
    req<{ enabled: boolean; issuer: string | null; client_id: string | null; redirect_uri: string | null; allowed_groups: string[] }>("/auth/oidc/status"),

  listItemComments: (itemId: string) =>
    req<{ comments: ItemComment[]; participants: { user_id: string; source: string }[]; extracted?: { comment_id: string; text: string; item_id: string; item_title?: string | null }[] }>(`/items/${itemId}/comments`),
  createComment: (itemId: string, body: { body: string }) =>
    req<ItemComment>(`/items/${itemId}/comments`, { method: "POST", body: JSON.stringify(body) }),
  deleteComment: (id: string) => req<{ deleted: string }>(`/comments/${id}`, { method: "DELETE" }),
  editComment: (id: string, body: { body: string }) =>
    req<ItemComment>(`/comments/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  listCommentRevisions: (id: string) =>
    req<{ comment_id: string; revisions: { id: string; body: string; edited_by: string; editor_name?: string | null; created_at: string }[] }>(`/comments/${id}/revisions`),
  extractTask: (commentId: string, body: { text: string; concept_id?: string }) =>
    req<{ extraction_id: string; text: string; item: { id: string; title: string } }>(`/comments/${commentId}/extract-task`, { method: "POST", body: JSON.stringify(body) }),
  subscribeItem: (itemId: string) =>
    req<{ item_id: string; subscribed: boolean }>(`/items/${itemId}/subscription`, { method: "POST" }),
  unsubscribeItem: (itemId: string) =>
    req<{ item_id: string; subscribed: boolean }>(`/items/${itemId}/subscription`, { method: "DELETE" }),
  listTimeEntries: (itemId: string) =>
    req<{ entries: TimeEntry[]; total_minutes: number; participants: { user_id: string; source: string }[] }>(`/items/${itemId}/time_entries`),
  logTime: (itemId: string, body: { minutes: number; spent_on: string; note?: string }) =>
    req<TimeEntry>(`/items/${itemId}/time_entries`, { method: "POST", body: JSON.stringify(body) }),
  editTimeEntry: (id: string, body: { minutes?: number; spent_on?: string; note?: string }) =>
    req<TimeEntry>(`/time_entries/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteTimeEntry: (id: string) => req<{ deleted: string }>(`/time_entries/${id}`, { method: "DELETE" }),
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

  listItems: (pid: string, params?: { feature_id?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.feature_id) q.set("feature_id", params.feature_id);
    if (params?.limit != null) q.set("limit", String(params.limit));
    if (params?.offset != null) q.set("offset", String(params.offset));
    const qs = q.toString();
    return req<{ items: Item[]; total: number }>(`/projects/${pid}/items${qs ? `?${qs}` : ""}`);
  },
  getItem: (iid: string) => req<Item>(`/items/${iid}`),
  patchItem: (iid: string, body: Record<string, unknown>) =>
    req<Item>(`/items/${iid}`, { method: "PATCH", body: JSON.stringify(body) }),
  addRelation: (iid: string, body: { to_item: string; relation_type: string; lag_days?: number }) =>
    req<{ id: string }>(`/items/${iid}/relations`, { method: "POST", body: JSON.stringify(body) }),
  globalSearch: (q: string, types = "items,comments") =>
    req<{ q: string; items: { id: string; title: string; status: string; status_group: string; concept_id: string; project_id: string; project_name: string }[]; comments: { id: string; body: string; item_id: string; project_id: string; item_title?: string | null; project_name?: string | null }[] }>(`/search?q=${encodeURIComponent(q)}&types=${types}`),
  getBaseline: (pid: string) =>
    req<{ project_id: string; baseline: { items: Record<string, [string | null, string | null]>; milestones: Record<string, string> } | null; created_at?: string; baseline_id?: string }>(`/projects/${pid}/baseline`),
  listBaselines: (pid: string) =>
    req<{ project_id: string; baselines: { id: string; created_at: string; snapshot: { items: Record<string, [string | null, string | null]>; milestones: Record<string, string> } }[] }>(`/projects/${pid}/baselines`),
  baselineVariance: (pid: string, baselineId?: string, includeSame = false) =>
    req<{ project_id: string; baseline_id: string; created_at: string; variances: { item_id: string; title: string; status: string; baseline_start: string | null; baseline_due: string | null; current_start: string | null; current_due: string | null; start_deviation: number | null; due_deviation: number | null }[]; summary: { count: number; max_due_delay: number } }>(`/projects/${pid}/baseline-variance?include_same=${includeSame}${baselineId ? `&baseline_id=${baselineId}` : ""}`),
  setBaseline: (pid: string) =>
    req<{ project_id: string; baseline: unknown }>(`/projects/${pid}/baseline`, { method: "POST" }),
  clearBaseline: (pid: string) =>
    req<{ project_id: string; baseline: null }>(`/projects/${pid}/baseline`, { method: "DELETE" }),
  getBoard: (pid: string, featureId?: string, groupBy?: string) => {
    const q = new URLSearchParams();
    if (featureId) q.set("feature_id", featureId);
    if (groupBy) q.set("group_by", groupBy);
    const qs = q.toString();
    return req<BoardData>(`/projects/${pid}/board${qs ? `?${qs}` : ""}`);
  },
  batchStart: (ids: string[]) =>
    req<{ started: { item_id: string; run_id?: string; conversation_id: string }[]; skipped: { item_id: string; reason: string }[] }>("/orchestrator/batch-start", { method: "POST", body: JSON.stringify({ item_ids: ids }) }),
  batchPatch: (pid: string, ids: string[], patch: Record<string, unknown>) =>
    req<{ results: { id: string; ok: boolean; error?: string }[]; updated: number }>(`/projects/${pid}/items/batch-patch`, { method: "POST", body: JSON.stringify({ ids, patch }) }),
  createItem: (pid: string, body: { concept_id: string; title: string; parent_id?: string; status?: string; priority?: string; assignee_type?: string; assignee_id?: string; start_date?: string; due_date?: string; milestone_id?: string }) =>
    req<Item>(`/projects/${pid}/items`, { method: "POST", body: JSON.stringify(body) }),
  importItems: (pid: string, csv: string) =>
    req<{ created: number; failed: number; results: { line: number; title: string; ok: boolean; error?: string; item_id?: string }[] }>(`/projects/${pid}/items/import`, { method: "POST", body: JSON.stringify({ csv }) }),

  listRuns: (pid: string) => req<{ runs: Run[] }>(`/runs?project_id=${pid}`),
  getHealthHistory: (pid: string, days = 30) =>
    req<{ project_id: string; days: number;
          series: { date: string; score: number | null; active: number; overdue: number; gates: number }[] }>(
      `/projects/${pid}/health/history?days=${days}`),
  getRunsReport: (pid: string) =>
    req<{ total: number; by_status: Record<string, number>; success_rate: number | null;
          avg_duration_seconds: number | null; gate_pending_rate: number | null;
          avg_steps_per_run: number | null;
          by_role: { agent_role: string; runs: number; success_rate: number | null }[];
          tokens: { input: number; output: number; estimated_cost_usd: number } }>(
      `/projects/${pid}/runs/report`),
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
  // I98: manual trigger of the daily sweep (heartbeat makes it idempotent)
  sweepAutomations: () =>
    req<{ swept: boolean; date: string; fired: number; created: number }>(
      "/automations/sweep", { method: "POST", body: JSON.stringify({}) }),
  // I99: external intake — owner token management + public no-login submission
  getIntakeToken: (pid: string) =>
    req<{ issued: boolean; token?: string; concept_id?: string }>(`/projects/${pid}/intake-token`),
  issueIntakeToken: (pid: string) =>
    req<{ token: string; concept_id?: string }>(`/projects/${pid}/intake-token`, { method: "POST", body: JSON.stringify({}) }),
  revokeIntakeToken: (pid: string) =>
    req<{ ok: boolean }>(`/projects/${pid}/intake-token`, { method: "DELETE" }),
  submitIntake: (token: string, body: { title: string; priority?: string }) =>
    req<{ ok: boolean; item_id: string; title: string }>(`/intake/${token}`, { method: "POST", body: JSON.stringify(body) }),
  // I101: CPM critical chain (backward pass, float<=0 items in chain order)
  getCriticalPath: (pid: string) =>
    req<{ project_id: string; cycle: boolean; chain: string[]; float: Record<string, number> }>(
      `/projects/${pid}/critical-path`),

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
      summary: string; ref_event_id: number | null; item_id?: string; read: number; created_at: string }[];
      unread: number; user_id: string; email_enabled: boolean }>("/notifications"),
  markNotificationsRead: (body: { ids?: string[]; all?: boolean }) =>
    req<{ ok: boolean }>("/notifications/read", { method: "POST", body: JSON.stringify(body) }),
  setNotificationPrefs: (body: { email_enabled: boolean }) =>
    req<{ user_id: string; email_enabled: boolean }>("/notifications/prefs", { method: "POST", body: JSON.stringify(body) }),
  // I96: per-kind × channel matrix (GitLab Custom level); mention is locked on.
  getNotificationPrefs: () =>
    req<{ email_enabled: boolean; kinds: { kind: string; label: string; inapp: boolean; email: boolean }[] }>(
      "/me/notification-prefs"),
  putNotificationPrefs: (body: { prefs: { kind: string; inapp: boolean; email: boolean }[] }) =>
    req<{ ok: boolean }>("/me/notification-prefs", { method: "PUT", body: JSON.stringify(body) }),
  // I97: responsiveness (CHAOSS Time to First Response semantics); slices are
  // null when the window has no samples — honest empty state, not zero.
  getResponsiveness: (pid: string) =>
    req<{ project_id: string; days: number;
      approvals: { count: number; avg_h: number; median_h: number; over_48h: number } | null;
      comments: { count: number; avg_h: number; median_h: number; over_48h: number } | null;
      comments_unanswered: number; generated_at: string }>(
      `/projects/${pid}/responsiveness`),
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
