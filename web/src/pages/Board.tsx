/** Board: five-bucket kanban with NL-aware filters, multi-select, inline batch start.
 * Supports custom-field grouping (M6-I21): ?group=field:<id> switches columns.
 * M25-I79: list view renders progressively (LIST_PAGE rows per page + load more). */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, API_BASE } from "../lib/api";
import { customFieldBadges } from "../lib/fmt";
import { isTypingTarget } from "../lib/shortcuts";
import { weightedProgress } from "../lib/rollup";
import { CommentsModal } from "../components/CommentsModal";
import { TimeLogModal, fmtMinutes } from "../components/TimeLogModal";
import { Badge, Button, Card, Drawer, GROUP_NAME, GROUP_TONE, Modal, PrintButton, cx } from "../components/ui";

/** 看板写操作后的定向失效：覆盖条目投影的读方（board/feature/project/
 * events/milestones/trash），替代无差别全量失效——后者会连带 portfolio、
 * ontology、runs、conversations 等全应用 active query 一起 refetch。 */
const invalidateItemData = (qc: QueryClient) => {
  for (const k of ["board", "feature", "project", "events", "milestones", "trash"]) {
    qc.invalidateQueries({ queryKey: [k] });
  }
};

/** M48-I146: 看板列渐进渲染页大小（与列表视图 LIST_PAGE 同思路）。 */
const COLUMN_PAGE = 12;

const LIST_PAGE = 20;

export function Board() {
  const { pid } = useParams();
  const [params, setParams] = useSearchParams();
  const featureId = params.get("feature") ?? undefined;
  const priority = params.get("priority") ?? "";
  const assignee = params.get("assignee") ?? "";
  const group = params.get("group") ?? "";
  const cycleId = params.get("cycle") ?? "";
  const viewId = params.get("view") ?? "";
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [view, setView] = useState<"board" | "list">("board");
  const [viewsOpen, setViewsOpen] = useState(false);
  const [newViewName, setNewViewName] = useState("");
  const [newViewPublic, setNewViewPublic] = useState(false);
  const [commentsFor, setCommentsFor] = useState<import("../lib/api").Item | null>(null);
  const [timelogFor, setTimelogFor] = useState<import("../lib/api").Item | null>(null);
  const [attachmentsFor, setAttachmentsFor] = useState<import("../lib/api").Item | null>(null);
  const [quickEditFor, setQuickEditFor] = useState<import("../lib/api").Item | null>(null);
  const [cycleOpen, setCycleOpen] = useState(false);
  const [retroCycle, setRetroCycle] = useState<string | null>(null);
  // M48-I146: 看板列渐进渲染计数（列 id → 已显示卡片数）
  const [colVisible, setColVisible] = useState<Record<string, number>>({});
  const [cycleName, setCycleName] = useState("");
  const [cycleStart, setCycleStart] = useState("");
  const [cycleEnd, setCycleEnd] = useState("");

  const viewsQ = useQuery({
    queryKey: ["views", pid],
    queryFn: () => api.listViews(pid!),
    enabled: !!pid,
  });
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const [batchStatus, setBatchStatus] = useState("");
  const [batchPriority, setBatchPriority] = useState("");
  const [batchAssignee, setBatchAssignee] = useState("");

  // 直开 ?view=<id>（分享链接缺过滤参数时）自动补齐视图定义；显式 params 优先。
  useEffect(() => {
    if (!viewId) return;
    const v = viewsQ.data?.views.find((x) => x.id === viewId);
    if (!v) return;
    const usp = new URLSearchParams(params);
    let changed = false;
    const put = (k: string, v: string | undefined) => {
      if (v && !usp.has(k)) { usp.set(k, v); changed = true; }
    };
    put("priority", v.definition?.priority);
    put("assignee", v.definition?.assignee_id);
    put("group", v.definition?.group_by);
    if (changed) setParams(usp, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewId, viewsQ.data]);

  // M65-I196: swimlane — second grouping dimension (Taiga/Kanboard semantics)
  const swimlane = params.get("swimlane") ?? "";
  const board = useQuery({
    queryKey: ["board", pid, featureId, group, cycleId, swimlane],
    queryFn: () => api.getBoard(pid!, featureId, group || undefined, cycleId || undefined, swimlane || undefined),
    enabled: !!pid,
  });
  // I119: iteration time boxes for the board filter dropdown
  const cyclesQ = useQuery({
    queryKey: ["cycles", pid],
    queryFn: () => api.listCycles(pid!),
    enabled: !!pid,
  });
  const onto = useQuery({
    queryKey: ["ontology", pid],
    queryFn: () => api.getOntology(pid!, true),
    enabled: !!pid,
  });
  // chip 优先显示 URL 选中的视图，其次后端落的默认视图（I52）
  const currentView =
    viewsQ.data?.views.find((v) => v.id === viewId) ??
    viewsQ.data?.views.find((v) => v.id === board.data?.applied_view_id);

  // ?item=<id>（通知跳转/分享）直接打开该工作项的评论区（M18-I57）
  const focusItem = params.get("item") ?? "";
  useEffect(() => {
    if (!focusItem || commentsFor) return;
    const found = (board.data?.buckets ?? []).flatMap((b) => b.items).find((i) => i.id === focusItem);
    if (found) setCommentsFor(found);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusItem, board.data]);

  // Distinct custom fields across concepts → grouping selector options (M6-I21),
  // minus the project-deactivated ones (M7-I25).
  const fieldOptions = useMemo(() => {
    const off = new Set(board.data?.disabled_fields ?? []);
    const m = new Map<string, string>();
    for (const c of onto.data?.concepts ?? [])
      for (const f of c.fields ?? []) {
        if (off.has(f.id) || m.has(f.id)) continue;
        m.set(f.id, f.name);
      }
    return [...m];
  }, [onto.data, board.data]);
  const runs = useQuery({ queryKey: ["runs", pid], queryFn: () => api.listRuns(pid!), enabled: !!pid });
  const approvals = useQuery({
    queryKey: ["approvals", pid, "pending"],
    queryFn: () => api.listApprovals({ status: "pending", project_id: pid }),
    enabled: !!pid,
    refetchInterval: 6_000,
  });
  const pendingByItem = useMemo(() => {
    const m = new Map<string, import("../lib/api").Approval>();
    for (const a of approvals.data?.approvals ?? []) {
      const run = (runs.data?.runs ?? []).find((r) => r.id === a.run_id);
      if (run?.item_id) m.set(run.item_id, a);
    }
    return m;
  }, [approvals.data, runs.data]);

  const runByItem = useMemo(() => {
    const m = new Map<string, { id: string; status: string; conversation_id: string }>();
    for (const r of runs.data?.runs ?? []) {
      if (r.item_id && !m.has(r.item_id)) m.set(r.item_id, r);
    }
    return m;
  }, [runs.data]);

  // 备忘化过滤：matches/listed 依赖 board.data 与过滤参数，避免勾选/键盘等
  // 任意重渲染都重跑全量 O(n) 过滤（下游 scopedListed/listRows 全链失效）。
  const matches = useCallback(
    (item: { priority?: string; assignee_id?: string }) =>
      (!priority || item.priority === priority) && (!assignee || item.assignee_id === assignee),
    [priority, assignee],
  );

  // M22-I70: the flat list currently shown in list view (select-all scope)
  const listed = useMemo(
    () => (board.data?.buckets ?? []).flatMap((b) => b.items.filter(matches)),
    [board.data, matches],
  );

  // M24-I74: hierarchy — parent titles, collapsible tree rows, descendant scope
  const allItems = useMemo(() => (board.data?.buckets ?? []).flatMap((b) => b.items), [board.data]);
  const titleMap = useMemo(() => Object.fromEntries(allItems.map((i) => [i.id, i.title])) as Record<string, string>, [allItems]);
  // I102/I116: per-parent weighted progress (estimate_hours, recursive roll-up)
  const wpProgress = useMemo(() => weightedProgress(allItems), [allItems]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [scopeDesc, setScopeDesc] = useState<{ id: string; title: string } | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importCsv, setImportCsv] = useState("");
  const [importResult, setImportResult] = useState<{ created: number; failed: number; results: { line: number; title: string; ok: boolean; error?: string }[] } | null>(null);
  // I95: keyboard-first board — j/k moves the card cursor, Enter opens its
  // comments, C opens quick create. The cursor is an index into `listed`.
  const [kbIndex, setKbIndex] = useState(-1);
  const [createOpen, setCreateOpen] = useState(false);
  // I109: R opens the selected card's comments pre-filled with a quote of its
  // last comment (GitHub quote reply); Enter opens without the auto-quote.
  const [autoQuote, setAutoQuote] = useState(false);
  const anyModalOpen = !!commentsFor || !!timelogFor || !!quickEditFor || createOpen || viewsOpen || !!scopeDesc || importOpen;

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;
      const key = e.key.toLowerCase();
      if (key === "j" || key === "k") {
        const n = listed.length;
        if (!n) return;
        e.preventDefault();
        setKbIndex((i) => (i < 0 ? 0 : Math.max(0, Math.min(n - 1, key === "j" ? i + 1 : i - 1))));
      } else if (e.key === "Enter") {
        if (anyModalOpen || kbIndex < 0 || kbIndex >= listed.length) return;
        e.preventDefault();
        setAutoQuote(false);
        setCommentsFor(listed[kbIndex]);
      } else if (key === "r") {
        if (anyModalOpen || kbIndex < 0 || kbIndex >= listed.length) return;
        e.preventDefault();
        setAutoQuote(true);
        setCommentsFor(listed[kbIndex]);
      } else if (key === "c") {
        if (anyModalOpen || !pid) return;
        e.preventDefault();
        setCreateOpen(true);
      } else if (e.key === "Escape") {
        setKbIndex(-1);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [listed, kbIndex, anyModalOpen, pid]);

  // Keep the focused card visible when the j/k cursor moves
  useEffect(() => {
    const id = kbIndex >= 0 ? listed[kbIndex]?.id : undefined;
    if (!id) return;
    document.querySelector(`[data-kb="${id}"]`)?.scrollIntoView({ block: "nearest" });
  }, [kbIndex, listed]);

  const scopedListed = useMemo(() => {
    if (!scopeDesc) return listed;
    const children: Record<string, string[]> = {};
    for (const it of allItems) (children[it.parent_id ?? ""] ??= []).push(it.id);
    const keep = new Set<string>();
    const stack = [scopeDesc.id];
    while (stack.length) {
      for (const ch of children[stack.pop()!] ?? []) {
        if (!keep.has(ch)) { keep.add(ch); stack.push(ch); }
      }
    }
    return listed.filter((i) => keep.has(i.id));
  }, [scopeDesc, listed, allItems]);

  const listRows = useMemo(() => {
    const ids = new Set(scopedListed.map((i) => i.id));
    const children: Record<string, typeof scopedListed> = {};
    const roots: typeof scopedListed = [];
    for (const it of scopedListed) {
      if (it.parent_id && ids.has(it.parent_id)) (children[it.parent_id] ??= []).push(it);
      else roots.push(it);
    }
    const out: { item: (typeof scopedListed)[number]; depth: number }[] = [];
    const walk = (list: typeof scopedListed, depth: number) => {
      for (const it of list) {
        out.push({ item: it, depth });
        if (children[it.id] && !collapsed.has(it.id)) walk(children[it.id], depth + 1);
      }
    };
    walk(roots, 0);
    return out;
  }, [scopedListed, collapsed]);

  // M25-I79: list view renders progressively ("load more") so the visible tree
  // stays small on big projects; the data itself is already project-scoped.
  // Reset when the filtered set's *content* changes (search/scope/new items) —
  // keyed by id signature, not array identity, so a refetch that returns the
  // same rows (focus/polling) never collapses the expanded list.
  const [visibleCount, setVisibleCount] = useState(LIST_PAGE);
  const listSignature = useMemo(() => scopedListed.map((i) => i.id).join(","), [scopedListed]);
  useEffect(() => { setVisibleCount(LIST_PAGE); }, [listSignature]);
  const pagedRows = useMemo(() => listRows.slice(0, visibleCount), [listRows, visibleCount]);

  // I100: list-view group-by with per-group count/spent headers (Airtable
  // semantics). Groups preserve the underlying (tree-ordered) row sequence and
  // operate on already-displayed rows, so I79 progressive rendering keeps working.
  const [listGroup, setListGroup] = useState("");
  const [groupCollapsed, setGroupCollapsed] = useState<Set<string>>(new Set());
  // I103: trash drawer state
  const [trashOpen, setTrashOpen] = useState(false);
  const groupKeyOf = (item: (typeof scopedListed)[number]): string => {
    if (listGroup === "concept") return item.concept_id || "—";
    if (listGroup === "status") return item.status || "—";
    if (listGroup === "priority") return item.priority || "—";
    if (listGroup === "assignee")
      return item.assignee_id ? `${item.assignee_type === "agent" ? "🤖 " : "👤 "}${item.assignee_id}` : "未指派";
    if (listGroup) {
      // 坏 JSON 容错：custom_fields 是外部导入可写的自由文本，不得让列表整页崩
      let cf: Record<string, unknown> = {};
      if (typeof item.custom_fields === "string" && item.custom_fields) {
        try { cf = JSON.parse(item.custom_fields); } catch { cf = {}; }
      } else if (item.custom_fields && typeof item.custom_fields === "object") {
        cf = item.custom_fields as Record<string, unknown>;
      }
      const v = cf[listGroup];
      return Array.isArray(v) ? v.join("、") : v != null ? String(v) : "—";
    }
    return "";
  };

  const addSubtask = async (parent: { id: string; concept_id: string; project_id: string }) => {
    const title = window.prompt("子任务标题");
    if (!title) return;
    try {
      await api.createItem(parent.project_id, { concept_id: parent.concept_id, title, parent_id: parent.id });
      toast.success("已创建子任务");
      invalidateItemData(qc);
    } catch (e) {
      toast.error(`创建失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const setFilter = (k: string, v: string) => {
    const usp = new URLSearchParams(params);
    if (v) usp.set(k, v); else usp.delete(k);
    setParams(usp, { replace: true });
  };

  /** M16-I51: a view is a named snapshot of the filter params; applying it
   * writes the definition back into the URL (feature slice is preserved). */
  const applyView = (v: import("../lib/api").SavedView) => {
    const usp = new URLSearchParams();
    if (featureId) usp.set("feature", featureId);
    const d = v.definition ?? {};
    if (d.priority) usp.set("priority", d.priority);
    if (d.assignee_id) usp.set("assignee", d.assignee_id);
    if (d.group_by) usp.set("group", d.group_by);
    usp.set("view", v.id);
    setParams(usp);
    setViewsOpen(false);
  };

  const saveCurrentAsView = async () => {
    if (!pid || !newViewName.trim()) return;
    const definition: Record<string, string> = {};
    if (priority) definition.priority = priority;
    if (assignee) definition.assignee_id = assignee;
    if (group) definition.group_by = group;
    try {
      const v = await api.createView(pid, { name: newViewName.trim(), definition, is_public: newViewPublic });
      const usp = new URLSearchParams(params);
      usp.set("view", v.id);
      setParams(usp, { replace: true });
      setNewViewName("");
      setNewViewPublic(false);
      setViewsOpen(false);
      qc.invalidateQueries({ queryKey: ["views", pid] });
      toast.success(`视图「${v.name}」已保存`);
    } catch (e) {
      toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const removeView = async (id: string) => {
    try {
      await api.deleteView(id);
      if (viewId === id) setFilter("view", "");
      qc.invalidateQueries({ queryKey: ["views", pid] });
      toast.info("视图已删除");
    } catch (e) {
      toast.error(`删除失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const batchStart = async () => {
    const r = await api.batchStart([...selected]);
    toast.success(`已启动 ${r.started.length} 个 Agent 运行`, {
      description: r.skipped.length ? `${r.skipped.length} 个跳过：${r.skipped[0].reason}` : undefined,
    });
    setSelected(new Set());
    invalidateItemData(qc);
  };

  // M22-I70: bulk edit — one PATCH per item server-side, per-item results
  const applyBatch = async (patch: Record<string, unknown>) => {
    if (!Object.keys(patch).length) { toast.error("先选择要修改的值"); return; }
    try {
      const r = await api.batchPatch(pid!, [...selected], patch);
      const fails = r.results.filter((x) => !x.ok);
      if (fails.length) toast.error(`${r.updated} 项成功，${fails.length} 项失败`, { description: fails[0].error });
      else toast.success(`已批量更新 ${r.updated} 项`);
      setBatchStatus(""); setBatchPriority(""); setBatchAssignee("");
      invalidateItemData(qc);
    } catch (e) {
      toast.error(`批量更新失败：${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="no-print flex flex-wrap items-center gap-2 border-b border-line px-4 py-2">
        <span className="text-sm font-semibold">看板</span>
        <div className="flex overflow-hidden rounded-lg border border-line">
          {(["board", "list"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={cx("px-2.5 py-1 text-xs", view === v ? "bg-accbg text-acc" : "text-mut hover:text-ink")}>
              {v === "board" ? "▦ 看板" : "☰ 列表"}
            </button>
          ))}
          <button onClick={() => setTrashOpen(true)}
            className="px-2.5 py-1 text-xs text-mut hover:text-ink" title="归档项与恢复">🗑</button>
        </div>
        <PrintButton />
        {featureId && <Badge tone="indigo">功能切片</Badge>}
        <div className="relative">
          <button
            onClick={() => setViewsOpen((v) => !v)}
            className={cx(
              "flex items-center gap-1 rounded-lg border px-2 py-1 text-xs",
              currentView ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink",
            )}
            title="保存的视图（过滤快照）"
          >
            {currentView ? `👁 ${currentView.name}` : "👁 视图"} ▾
          </button>
          {viewsOpen && (
            <div className="absolute left-0 top-9 z-40 w-72 rounded-xl border border-line bg-surface p-2 shadow-lg">
              <div className="space-y-0.5">
                {(viewsQ.data?.views ?? []).map((v) => (
                  <div key={v.id} className="group flex items-center gap-1.5 rounded-lg px-2 py-1.5 hover:bg-bg">
                    <button onClick={() => applyView(v)} className="min-w-0 flex-1 truncate text-left text-xs"
                      title="应用此视图">
                      <span className={cx("font-medium", v.id === viewId && "text-acc")}>{v.name}</span>
                      {!!v.is_public && <Badge tone="violet">公开</Badge>}
                      {v.is_default ? <Badge tone="amber">默认</Badge> : null}
                      {v.id === viewId && <span className="ml-1 text-[10px] text-acc">当前</span>}
                    </button>
                    {!v.is_default && (
                      <button onClick={async () => {
                        try {
                          await api.makeViewDefault(v.id);
                          qc.invalidateQueries({ queryKey: ["views", pid] });
                          toast.success(`「${v.name}」已设为项目默认视图`);
                        } catch (e) { toast.error(String(e)); }
                      }}
                        className="shrink-0 text-[10px] text-mut opacity-0 transition-opacity hover:text-acc group-hover:opacity-100"
                        title="设为项目默认视图（打开看板直达）">默认</button>
                    )}
                    <button onClick={() => removeView(v.id)}
                      className="shrink-0 text-[11px] text-mut opacity-0 transition-opacity hover:text-dan group-hover:opacity-100"
                      title="删除视图">✕</button>
                  </div>
                ))}
                {!viewsQ.data?.views.length && (
                  <div className="px-2 py-2 text-xs text-mut">暂无视图——设置好过滤后保存</div>
                )}
              </div>
              <div className="mt-2 space-y-1.5 border-t border-line pt-2">
                <input
                  className="w-full rounded-lg border border-line bg-bg px-2 py-1.5 text-xs"
                  placeholder="保存当前过滤为视图…"
                  value={newViewName}
                  onChange={(e) => setNewViewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveCurrentAsView()}
                />
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-1.5 text-[11px] text-mut">
                    <input type="checkbox" checked={newViewPublic} onChange={(e) => setNewViewPublic(e.target.checked)} />
                    项目内公开
                  </label>
                  <Button size="sm" variant="outline" onClick={saveCurrentAsView} disabled={!newViewName.trim()}>
                    保存
                  </Button>
                </div>
                {currentView && (
                  <button onClick={() => { setFilter("view", ""); setViewsOpen(false); }}
                    className="text-[11px] text-mut hover:text-acc">
                    退出当前视图（保留过滤）
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
        {/* 控件反映实际生效分组：显式 ?group= 优先，否则显示后端落的（默认视图）值 */}
        <select value={cycleId} onChange={(e) => setFilter("cycle", e.target.value)}
          className="rounded-lg border border-line bg-surface px-2 py-1.5 text-xs"
          title="按迭代周期过滤（I119）">
          <option value="">周期：全部</option>
          {(cyclesQ.data?.cycles ?? []).map((c) => (
            <option key={c.id} value={c.id}>周期：{c.name}</option>
          ))}
        </select>
        <Button size="sm" variant="ghost" onClick={() => setCycleOpen(true)}
          title="新建迭代周期（Plane Cycles 语义）">＋周期</Button>
        {/* M65-I196: swimlane selector — second grouping dimension */}
        <select value={swimlane} onChange={(e) => setFilter("swimlane", e.target.value)}
          className="rounded-lg border border-line bg-surface px-2 py-1.5 text-xs"
          title="泳道：列之外的行维度（Taiga/Kanboard 语义）——按执行者/功能/优先级在列内分行">
          <option value="">泳道：无</option>
          <option value="assignee_id">泳道：执行者</option>
          <option value="feature_id">泳道：功能</option>
          <option value="priority">泳道：优先级</option>
        </select>
        {cycleId && (
          <Button size="sm" variant="ghost" onClick={() => setRetroCycle(cycleId)}
            title="周期回顾包（完成率/拖入/超期/阻塞 top —— M48-I145）">📋 回顾</Button>
        )}
        <select value={group || board.data?.group_by || ""} onChange={(e) => setFilter("group", e.target.value)}
          className="rounded-lg border border-line bg-surface px-2 py-1.5 text-xs">
          <option value="">分组：生命周期</option>
          {fieldOptions.map(([fid, fname]) => (
            <option key={fid} value={`field:${fid}`}>分组：{fname}</option>
          ))}
        </select>
        <button onClick={() => setImportOpen(true)}
          className="rounded-lg border border-line bg-surface px-2 py-1.5 text-xs text-mut hover:border-acc hover:text-acc">
          ⬆ 导入 CSV
        </button>
        <div className="ml-auto flex items-center gap-2 text-xs">
          {scopeDesc && (
            <button onClick={() => setScopeDesc(null)}
              className="rounded-lg border border-acc px-2 py-1 text-acc"
              title="清除后代范围">仅看「{scopeDesc.title}」后代 ✕</button>
          )}
          <select value={priority} onChange={(e) => setFilter("priority", e.target.value)}
            className="rounded-lg border border-line bg-surface px-2 py-1.5">
            <option value="">优先级（全部）</option>
            <option value="high">高</option>
            <option value="medium">中</option>
            <option value="low">低</option>
          </select>
          <select value={assignee} onChange={(e) => setFilter("assignee", e.target.value)}
            className="rounded-lg border border-line bg-surface px-2 py-1.5">
            <option value="">执行者（全部）</option>
            <option value="dev-agent">🤖 dev-agent</option>
            <option value="planner-agent">🤖 planner-agent</option>
          </select>
          {selected.size > 0 && (
            <>
              <span className="text-mut">已选 {selected.size}</span>
              {(() => {
                const sel = (board.data?.buckets ?? []).flatMap((b) => b.items.filter(matches)).filter((i) => selected.has(i.id));
                const concepts = new Set(sel.map((i) => i.concept_id));
                const sameConcept = concepts.size === 1 ? [...concepts][0] : null;
                const states = sameConcept ? (onto.data?.concepts.find((c) => c.id === sameConcept)?.states ?? []) : [];
                return (
                  <>
                    <select value={batchStatus}
                      onChange={(e) => { setBatchStatus(e.target.value); if (e.target.value) applyBatch({ status: e.target.value }); }}
                      disabled={!sameConcept}
                      title={sameConcept ? "批量改状态" : "所选工作项概念不同，无法统一改状态"}
                      className="rounded-lg border border-line bg-surface px-2 py-1.5 disabled:opacity-50">
                      <option value="">{sameConcept ? "改状态…" : "改状态（概念不同）"}</option>
                      {states.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                    <select value={batchPriority}
                      onChange={(e) => { setBatchPriority(e.target.value); if (e.target.value) applyBatch({ priority: e.target.value }); }}
                      className="rounded-lg border border-line bg-surface px-2 py-1.5">
                      <option value="">改优先级…</option>
                      <option value="high">高</option>
                      <option value="medium">中</option>
                      <option value="low">低</option>
                    </select>
                    <select value={batchAssignee}
                      onChange={(e) => { setBatchAssignee(e.target.value); if (e.target.value) applyBatch({ assignee_type: "human", assignee_id: e.target.value }); }}
                      className="rounded-lg border border-line bg-surface px-2 py-1.5">
                      <option value="">指派…</option>
                      {(users.data?.users ?? []).map((u) => <option key={u.id} value={u.id}>👤 {u.name}</option>)}
                    </select>
                  </>
                );
              })()}
              <Button size="sm" variant="primary" onClick={batchStart}>▶ 让 Agent 做</Button>
              <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>清除</Button>
            </>
          )}
        </div>
      </div>

      {view === "list" && (
        <div className="overflow-x-auto p-4">
          <div className="mb-2 flex items-center gap-2 text-xs">
            <span className="text-mut">按组聚合</span>
            <select value={listGroup} onChange={(e) => setListGroup(e.target.value)}
              className="rounded-lg border border-line bg-surface px-2 py-1.5">
              <option value="">不分组</option>
              <option value="concept">概念</option>
              <option value="status">状态</option>
              <option value="priority">优先级</option>
              <option value="assignee">执行者</option>
              {[...fieldOptions].map(([fid, name]) => <option key={fid} value={fid}>{name}</option>)}
            </select>
            {listGroup && (
              <button className="text-[11px] text-mut hover:text-acc"
                onClick={() => setGroupCollapsed(new Set())}>全部展开</button>
            )}
          </div>
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead>
              <tr className="border-b border-line text-mut">
                <th className="py-2">
                  <input type="checkbox" title="全选/全不选（当前列表）"
                    checked={pagedRows.length > 0 && pagedRows.every(({ item }) => selected.has(item.id))}
                    onChange={(e) => {
                      const next = new Set(selected);
                      for (const { item } of pagedRows) e.target.checked ? next.add(item.id) : next.delete(item.id);
                      setSelected(next);
                    }} />
                </th>
                <th className="py-2">标题</th><th>概念</th><th>状态</th><th>优先级</th><th>执行者</th><th>字段</th><th>更新</th>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const groups: { key: string; rows: { item: (typeof scopedListed)[number]; depth: number }[] }[] = [];
                if (!listGroup) groups.push({ key: "", rows: pagedRows });
                else
                  for (const row of pagedRows) {
                    const k = groupKeyOf(row.item);
                    let g = groups.find((x) => x.key === k);
                    if (!g) { g = { key: k, rows: [] }; groups.push(g); }
                    g.rows.push(row);
                  }
                const out: React.ReactElement[] = [];
                for (const g of groups) {
                  if (listGroup) {
                    const spent = g.rows.reduce((s, r) => s + (r.item.spent_minutes ?? 0), 0);
                    const isCollapsed = groupCollapsed.has(g.key);
                    out.push(
                      <tr key={`g:${g.key}`} className="cursor-pointer bg-bg"
                        title="点击折叠/展开该组" onClick={() => {
                          const next = new Set(groupCollapsed);
                          isCollapsed ? next.delete(g.key) : next.add(g.key);
                          setGroupCollapsed(next);
                        }}>
                        <td colSpan={8} className="py-1.5 font-medium">
                          {isCollapsed ? "▸" : "▾"} {g.key}
                          <span className="ml-2 font-normal text-mut">
                            {g.rows.length} 项 · ⏱ {fmtMinutes(spent)}
                          </span>
                        </td>
                      </tr>,
                    );
                    if (isCollapsed) continue;
                  }
                  for (const { item, depth } of g.rows) {
                    out.push(
                      <tr key={item.id} className="border-b border-line/60 hover:bg-bg">
                        <td className="py-2">
                          <input type="checkbox" checked={selected.has(item.id)} readOnly
                            onClick={(e) => {
                              const next = new Set(selected);
                              e.currentTarget.checked ? next.add(item.id) : next.delete(item.id);
                              setSelected(next);
                            }} />
                        </td>
                        <td className="py-2" style={{ paddingLeft: depth * 16 }}>
                          <div className="flex items-center gap-1">
                            {scopedListed.some((i) => i.parent_id === item.id) ? (
                              <button className="w-3 text-mut" title={collapsed.has(item.id) ? "展开子任务" : "折叠子任务"}
                                onClick={() => {
                                  const next = new Set(collapsed);
                                  next.has(item.id) ? next.delete(item.id) : next.add(item.id);
                                  setCollapsed(next);
                                }}>{collapsed.has(item.id) ? "▸" : "▾"}</button>
                            ) : <span className="w-3" />}
                            <span className="font-medium">{item.title}</span>
                            {item.blocked && (
                              <span className="text-[10px] text-dan" title="存在未完成的阻塞上游">🚧</span>
                            )}
                            {wpProgress.get(item.id) && (
                              <span className="text-[10px] text-mut" title="子任务加权进度（estimate_hours 逐级上卷）">
                                🧩 {wpProgress.get(item.id)!.percent}% · {wpProgress.get(item.id)!.done}/{wpProgress.get(item.id)!.total}
                              </span>
                            )}
                            <button title="添加子任务" className="text-[10px] text-mut hover:text-acc"
                              onClick={() => addSubtask(item)}>＋子</button>
                            <button title="仅看该任务的后代" className="text-[10px] text-mut hover:text-acc"
                              onClick={() => setScopeDesc({ id: item.id, title: item.title })}>后代</button>
                            <button title="快捷编辑（状态/优先级/执行者/截止日）" className="text-[10px] text-mut hover:text-acc"
                              onClick={() => setQuickEditFor(item)}>⚡</button>
                          </div>
                        </td>
                        <td className="text-mut">{item.concept_id}</td>
                        <td><Badge tone={GROUP_TONE[item.status_group]}>{item.status}</Badge></td>
                        <td>{item.priority ?? "—"}</td>
                        <td>{item.assignee_id ? `${item.assignee_type === "agent" ? "🤖" : "👤"} ${item.assignee_id}` : "—"}</td>
                        <td>
                          {customFieldBadges(item, onto.data?.concepts).length ? (
                            customFieldBadges(item, onto.data?.concepts).map((b) => (
                              <span key={b.label} className="mr-1 whitespace-nowrap text-mut">{b.label}: {b.text}</span>
                            ))
                          ) : "—"}
                        </td>
                        <td className="text-mut">{item.updated_at?.slice(5, 16)}</td>
                      </tr>,
                    );
                  }
                }
                if (pagedRows.length < listRows.length) {
                  out.push(
                    <tr key="loadmore" className="border-b border-line/60">
                      <td colSpan={8} className="py-2 text-center">
                        <button className="text-xs text-acc hover:underline"
                          onClick={() => setVisibleCount((n) => n + LIST_PAGE)}>
                          加载更多（已显示 {pagedRows.length} / 共 {listRows.length} 项）
                        </button>
                      </td>
                    </tr>,
                  );
                }
                return out;
              })()}
            </tbody>
          </table>
        </div>
      )}
      <div className={cx("min-h-0 flex-1 gap-3 overflow-x-auto p-4", view === "list" && "hidden")}>
        {(board.data?.groups
          ? board.data.groups.map((g) => ({
              id: g.id,
              label: board.data.field?.name ? `${board.data.field.name}: ${g.name}` : g.name,
              tone: "neutral" as const,
              items: g.items,
            }))
          : (board.data?.buckets ?? []).map((b) => ({
              id: b.id,
              label: GROUP_NAME[b.id],
              tone: GROUP_TONE[b.id],
              items: b.items,
            }))
        ).map((col) => {
          const items = col.items.filter(matches);
          if (priority && !items.length) return null;
          // M48-I146: 看板列渐进渲染——默认 12 张，列尾「显示更多」递增；
          // 列表视图（I79）同思路，避免几百项的列全量渲染卡顿。
          const visible = colVisible[col.id] ?? COLUMN_PAGE;
          const shown = items.slice(0, visible);
          // M26-I80: WIP limit badge (Kanboard soft signal) — lifecycle buckets
          // only; the count shown here is the project-wide one from the API
          // (unfiltered, per Kanboard's "count all open tasks" fix).
          const wipLimit = !board.data?.groups ? board.data?.wip_limits?.[col.id] : undefined;
          const wipCount = board.data?.wip?.[col.id];
          const overWip = wipLimit != null && wipCount != null && wipCount > wipLimit;
          return (
            <div key={col.id} className="flex w-64 shrink-0 flex-col rounded-[12px] border border-line bg-surface/50">
              <div className="flex items-center justify-between px-3 py-2">
                <Badge tone={overWip ? "red" : col.tone}>{col.label}</Badge>
                {overWip ? (
                  <span className="text-xs font-medium text-dan"
                    title={`超出在制品上限（${wipCount}/${wipLimit}）——建议先完成再取新任务`}>
                    {wipCount}/{wipLimit} ⚠
                  </span>
                ) : wipLimit != null && wipCount != null ? (
                  <span className="text-xs text-mut" title={`在制品上限 ${wipLimit}`}>{wipCount}/{wipLimit}</span>
                ) : (
                  <span className="text-xs text-mut">{items.length}</span>
                )}
              </div>
              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-2 pb-3">
                {/* M65-I196: swimlane sub-rows within the column — lane order
                    follows the API's swimlanes (count desc); "（空）" last. */}
                {swimlane && board.data?.swimlanes?.length
                  ? board.data.swimlanes.map((lane) => {
                      const laneItems = shown.filter((i) => (i as Record<string, unknown>).swimlane === lane.id);
                      if (!laneItems.length) return null;
                      return (
                        <div key={lane.id} className="rounded-lg border border-line/70 p-1.5">
                          <div className="mb-1 flex items-center justify-between px-0.5">
                            <span className="truncate text-[10px] font-semibold text-mut"
                              title={`泳道 ${board.data!.swimlane_by}: ${lane.id}`}>
                              ▤ {lane.id}
                            </span>
                            <span className="text-[10px] text-mut">{laneItems.length}</span>
                          </div>
                          <div className="space-y-2">
                            {laneItems.map((item) => {
                              return (
                      <Card
                        key={item.id}
                        data-kb={item.id}
                        onClick={() => toggle(item.id)}
                        className={cx(
                          "cursor-pointer p-2.5 text-xs transition-all",
                          selected.has(item.id) && "ring-2 ring-acc",
                          listed[kbIndex]?.id === item.id && "ring-2 ring-warnln",
                        )}
                      >
                        <div className="flex items-start gap-1.5">
                          <input type="checkbox" checked={selected.has(item.id)} readOnly className="mt-0.5" />
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-medium">{item.title}</div>
                            {item.parent_id && titleMap[item.parent_id] && (
                              <div className="mt-0.5 truncate text-[10px] text-mut" title="父任务">↳ {titleMap[item.parent_id]}</div>
                            )}
                            {item.checklist && (() => {
                              try {
                                const cl = JSON.parse(item.checklist) as { done: boolean }[];
                                const d = cl.filter((c) => c.done).length;
                                if (cl.length) return (
                                  <span className="mt-0.5 inline-block text-[10px] text-mut"
                                    title="行内清单进度（advisory，不计入健康分）">☑ {d}/{cl.length}</span>
                                );
                              } catch { /* corrupt row — skip badge */ }
                              return null;
                            })()}
                            <div className="mt-1 flex flex-wrap items-center gap-1">
                              <Badge tone={GROUP_TONE[item.status_group]}>{item.status}</Badge>
                              {item.blocked && <Badge tone="red" title="存在未完成的阻塞上游">🚧</Badge>}
                              {item.priority === "high" && <Badge tone="red">高优</Badge>}
                              {item.assignee_id && (
                                <Badge tone={item.assignee_type === "agent" ? "violet" : "neutral"}>
                                  {item.assignee_type === "agent" ? "🤖" : "👤"} {item.assignee_id}
                                </Badge>
                              )}
                              {(item.spent_minutes ?? 0) > 0 && (
                                <Badge tone="neutral" title="实际投入工时">⏱ {fmtMinutes(item.spent_minutes ?? 0)}</Badge>
                              )}
                            </div>
                          </div>
                        </div>
                      </Card>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })
                  : null}
                {(!swimlane || !board.data?.swimlanes?.length) && shown.map((item) => {
                  const run = runByItem.get(item.id);
                  return (
                    <Card
                      key={item.id}
                      data-kb={item.id}
                      onClick={() => toggle(item.id)}
                      className={cx(
                        "cursor-pointer p-2.5 text-xs transition-all",
                        selected.has(item.id) && "ring-2 ring-acc",
                        listed[kbIndex]?.id === item.id && "ring-2 ring-warnln",
                      )}
                    >
                      <div className="flex items-start gap-1.5">
                        <input type="checkbox" checked={selected.has(item.id)} readOnly className="mt-0.5" />
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium">{item.title}</div>
                          {item.parent_id && titleMap[item.parent_id] && (
                            <div className="mt-0.5 truncate text-[10px] text-mut" title="父任务">↳ {titleMap[item.parent_id]}</div>
                          )}
                          {item.checklist && (() => {
                            // M63-I191: checklist progress badge on the card
                            try {
                              const cl = JSON.parse(item.checklist) as { done: boolean }[];
                              const d = cl.filter((c) => c.done).length;
                              if (cl.length) return (
                                <span className="mt-0.5 inline-block text-[10px] text-mut"
                                  title="行内清单进度（advisory，不计入健康分）">☑ {d}/{cl.length}</span>
                              );
                            } catch { /* corrupt row — skip badge */ }
                            return null;
                          })()}
                          <div className="mt-1 flex flex-wrap items-center gap-1">
                            <Badge tone={GROUP_TONE[item.status_group]}>{item.status}</Badge>
                            {item.blocked && (
                              <Badge tone="red" title="存在未完成的阻塞上游（blocks/depends_on）">🚧 被阻塞</Badge>
                            )}
                            {!!item.recurrence_days && (
                              <Badge tone="indigo" title={`完成 ${item.recurrence_days} 天后自动重建下一期`}>
                                🔄 {item.recurrence_days}天
                              </Badge>
                            )}
                            {item.priority === "high" && <Badge tone="red">高优</Badge>}
                            {wpProgress.get(item.id) && (
                              <Badge tone={wpProgress.get(item.id)!.percent >= 100 ? "green" : "neutral"}
                                title="子任务加权完成进度（estimate_hours 加权，逐级上卷）">
                                🧩 {wpProgress.get(item.id)!.percent}% · {wpProgress.get(item.id)!.done}/{wpProgress.get(item.id)!.total}
                              </Badge>
                            )}
                            {item.assignee_id && (
                              <Badge tone={item.assignee_type === "agent" ? "violet" : "neutral"}>
                                {item.assignee_type === "agent" ? "🤖" : "👤"} {item.assignee_id}
                              </Badge>
                            )}
                            {customFieldBadges(item, onto.data?.concepts).map((b) => (
                              <Badge key={b.label} tone="neutral">{b.label}: {b.text}</Badge>
                            ))}
                            {(item.spent_minutes ?? 0) > 0 && (
                              <Badge tone="neutral" title="实际投入工时">⏱ {fmtMinutes(item.spent_minutes ?? 0)}</Badge>
                            )}
                            <button
                              onClick={(e) => { e.stopPropagation(); setQuickEditFor(item); }}
                              className="text-[10px] text-mut hover:text-acc" title="快捷编辑（状态/优先级/执行者/截止日）"
                              aria-label="快捷编辑"
                            >
                              ⚡
                            </button>
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (!window.confirm(`归档「${item.title}」？可随时在回收站恢复。`)) return;
                                try {
                                  await api.archiveItem(item.id);
                                  toast.success("已归档——回收站可恢复");
                                  invalidateItemData(qc);
                                } catch (err) {
                                  toast.error(`归档失败：${err instanceof Error ? err.message : err}`);
                                }
                              }}
                              className="text-[10px] text-mut hover:text-acc" title="归档（回收站可恢复）"
                              aria-label="归档工作项"
                            >
                              🗄
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); setTimelogFor(item); }}
                              className="ml-auto text-[10px] text-mut hover:text-acc" title="工时"
                              aria-label="记录工时"
                            >
                              ⏱
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); setAttachmentsFor(item); }}
                              className="text-[10px] text-mut hover:text-acc" title="附件"
                              aria-label="附件"
                            >
                              📎
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); setCommentsFor(item); }}
                              className="ml-auto text-[10px] text-mut hover:text-acc" title="评论"
                              aria-label="评论"
                            >
                              💬
                            </button>
                          </div>
                          {run && (
                            <Link
                              to={`/p/${pid}/c/${run.conversation_id}`}
                              onClick={(e) => e.stopPropagation()}
                              className="mt-1 block text-[11px] text-acc hover:underline"
                            >
                              {run.status === "running" ? "▶ 运行中" : run.status === "interrupted" ? "⏸ 挂起" : run.status === "succeeded" ? "✓ 完成" : "● " + run.status} · 查看对话 →
                            </Link>
                          )}
                          {item.status === "awaiting_review" && pendingByItem.get(item.id) && (
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                await api.decide(pendingByItem.get(item.id)!.id, "approved", "看板内联批准");
                                invalidateItemData(qc);
                              }}
                              className="mt-1.5 rounded-md bg-acc px-2 py-0.5 text-[11px] font-medium text-white hover:bg-indigo-500"
                            >
                              ✓ 内联批准
                            </button>
                          )}
                        </div>
                      </div>
                    </Card>
                  );
                })}
                {!items.length && !swimlane && <div className="px-2 py-4 text-center text-[11px] text-mut">空</div>}
                {items.length > shown.length && (
                  <button
                    onClick={() => setColVisible((m) => ({ ...m, [col.id]: visible + COLUMN_PAGE }))}
                    className="w-full rounded-lg border border-dashed border-line py-1.5 text-[11px] text-mut hover:border-acc hover:text-acc"
                  >
                    显示更多（{items.length - shown.length}）
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {commentsFor && (
        <CommentsModal itemId={commentsFor.id} title={commentsFor.title} autoQuote={autoQuote}
          onClose={() => { setCommentsFor(null); setAutoQuote(false); if (focusItem) setFilter("item", ""); }} />
      )}
      {timelogFor && (
        <TimeLogModal itemId={timelogFor.id} title={timelogFor.title}
          onClose={() => setTimelogFor(null)} />
      )}
      {attachmentsFor && (
        <AttachmentModal itemId={attachmentsFor.id} title={attachmentsFor.title}
          onClose={() => setAttachmentsFor(null)} />
      )}
      {quickEditFor && (
        <QuickEditModal item={quickEditFor} concepts={onto.data?.concepts ?? []}
          onClose={() => setQuickEditFor(null)}
          onSaved={() => { setQuickEditFor(null); invalidateItemData(qc); }} />
      )}
      {createOpen && pid && (
        <CreateTaskModal pid={pid}
          onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); invalidateItemData(qc); }} />
      )}
      {trashOpen && pid && (
        <TrashDrawer pid={pid} onClose={() => setTrashOpen(false)} onRestored={() => qc.invalidateQueries()} />
      )}
      {retroCycle && <RetroDrawer cycleId={retroCycle} onClose={() => setRetroCycle(null)} />}
      {cycleOpen && pid && (
        <Modal open onClose={() => setCycleOpen(false)} title="🔁 新建迭代周期">
          <div className="space-y-3 text-xs">
            <input value={cycleName} onChange={(e) => setCycleName(e.target.value)} placeholder="周期名称（如：Sprint 1）"
              className="w-full rounded-lg border border-line bg-bg px-3 py-2" />
            <div className="flex items-center gap-2">
              <input type="date" value={cycleStart} onChange={(e) => setCycleStart(e.target.value)}
                className="rounded-lg border border-line bg-bg px-2 py-1.5" />
              <span className="text-mut">至</span>
              <input type="date" value={cycleEnd} onChange={(e) => setCycleEnd(e.target.value)}
                className="rounded-lg border border-line bg-bg px-2 py-1.5" />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-mut">与其他周期重叠会被拒绝；周期结束后，未完成项由每日扫描显式结转到下一周期</span>
              <Button size="sm" variant="primary" disabled={!cycleName.trim() || !cycleStart || !cycleEnd}
                onClick={async () => {
                  try {
                    const c = await api.createCycle(pid, cycleName.trim(), cycleStart, cycleEnd);
                    toast.success(`周期「${c.name}」已创建`);
                    setCycleOpen(false); setCycleName(""); setCycleStart(""); setCycleEnd("");
                    await qc.invalidateQueries({ queryKey: ["cycles", pid] });
                    setFilter("cycle", c.id);
                  } catch (e) {
                    toast.error(`创建失败：${e instanceof Error ? e.message : e}`);
                  }
                }}>创建</Button>
            </div>
          </div>
        </Modal>
      )}
      {importOpen && (
        <Modal open onClose={() => setImportOpen(false)} title="⬆ 导入工作项 CSV">
          <div className="space-y-3 text-xs">
            <div className="flex items-center gap-2">
              <a href={`${API_BASE}/projects/${pid}/items/import-template`} className="text-acc hover:underline">下载模板</a>
              <a href={`${API_BASE}/projects/${pid}/items.csv`} className="text-acc hover:underline">导出当前工作项</a>
              <label className="ml-auto cursor-pointer rounded-lg border border-line px-2 py-1 hover:border-acc">
                选择文件…
                <input type="file" accept=".csv,text/csv" className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    const reader = new FileReader();
                    reader.onload = () => setImportCsv(String(reader.result ?? ""));
                    reader.readAsText(f, "utf-8");
                  }} />
              </label>
            </div>
            <textarea rows={6} value={importCsv}
              onChange={(e) => setImportCsv(e.target.value)}
              placeholder={"粘贴或选择 CSV（首行表头：title,concept_id,status,priority,start_date,due_date,estimate_hours,parent_title）"}
              className="w-full rounded-lg border border-line bg-bg px-3 py-2 font-mono text-[11px]" />
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-mut">parent_title 引用已有项或同文件先导行；坏行单独报错不整批回滚</span>
              <Button size="sm" variant="primary" disabled={!importCsv.trim() || !!importResult}
                onClick={async () => {
                  try {
                    const r = await api.importItems(pid!, importCsv);
                    setImportResult(r);
                    invalidateItemData(qc);
                    toast.success(`导入完成：成功 ${r.created} · 失败 ${r.failed}`);
                  } catch (e) {
                    toast.error(`导入失败：${e instanceof Error ? e.message : e}`);
                  }
                }}>开始导入</Button>
            </div>
            {importResult && (
              <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-line p-2">
                {importResult.results.map((r) => (
                  <div key={r.line} className="flex items-center gap-2">
                    <span className="w-10 font-mono text-[10px] text-mut">#{r.line}</span>
                    <span className="flex-1 truncate">{r.title || "（空）"}</span>
                    {r.ok ? <Badge tone="green">✓</Badge> : <Badge tone="red">{r.error}</Badge>}
                  </div>
                ))}
                <button className="text-[10px] text-mut hover:text-acc"
                  onClick={() => { setImportResult(null); setImportCsv(""); setImportOpen(false); }}>完成</button>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

/** I103: trash — archived items with one-click restore (soft delete; the
 *  archived state itself is an event-sourced projection, nothing is lost). */
function TrashDrawer({ pid, onClose, onRestored }: {
  pid: string; onClose: () => void; onRestored: () => void;
}) {
  const qc = useQueryClient();
  const trash = useQuery({ queryKey: ["trash", pid], queryFn: () => api.listTrash(pid) });
  const [restoring, setRestoring] = useState<string | null>(null);
  const restore = async (id: string) => {
    setRestoring(id);
    try {
      await api.restoreItem(id);
      await invalidateItemData(qc);
      onRestored();
    } catch (e) {
      toast.error(`恢复失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setRestoring(null);
    }
  };
  return (
    <Modal open onClose={onClose} title="🗑 回收站">
      <div className="space-y-1.5 text-xs">
        {(trash.data?.items ?? []).map((t) => (
          <div key={t.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-1.5">
            <span className="min-w-0 flex-1 truncate font-medium">{t.title}</span>
            <span className="shrink-0 text-[10px] text-mut">{t.archived_at?.slice(5, 16).replace("T", " ")} 归档</span>
            <Button size="sm" variant="outline" disabled={restoring === t.id}
              onClick={() => restore(t.id)}>恢复</Button>
          </div>
        ))}
        {!trash.data?.items.length && (
          <div className="py-4 text-center text-mut">回收站是空的——归档的工作项会出现在这里，随时可恢复</div>
        )}
      </div>
    </Modal>
  );
}

/** I95: C-key quick create (docs/01 §AD.1). Board-context sibling of the
 *  SchedulePage range create — concept defaults to task, auto-assigns you. */
function CreateTaskModal({ pid, onClose, onCreated }: {
  pid: string; onClose: () => void; onCreated: () => void;
}) {
  const [conceptId, setConceptId] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const onto = useQuery({ queryKey: ["ontology", pid], queryFn: () => api.getOntology(pid, true) });
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const concepts = (onto.data?.concepts ?? []).filter((c) => c.id !== "milestone");
  const concept = concepts.find((c) => c.id === conceptId) ?? concepts.find((c) => c.id === "task") ?? concepts[0];

  const submit = async () => {
    if (!concept || !title.trim()) { toast.error("填写任务标题"); return; }
    setBusy(true);
    try {
      await api.createItem(pid, {
        concept_id: concept.id, title: title.trim(),
        assignee_type: "human", assignee_id: users.data?.current,
      });
      toast.success(`已创建并指派给你：${title.trim()}`);
      onCreated();
    } catch (e) {
      toast.error(`创建失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="🆕 新任务">
      <div className="space-y-2 text-xs">
        <select value={concept?.id ?? ""} onChange={(e) => setConceptId(e.target.value)}
          className="w-full rounded-lg border border-line bg-bg px-2 py-1.5">
          {concepts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="任务标题"
          className="w-full rounded-lg border border-line bg-bg px-2 py-1.5" />
        <div className="flex items-center justify-between pt-1">
          <span className="text-[10px] text-mut">创建后自动指派给你 · Esc 关闭</span>
          <Button size="sm" variant="primary" disabled={busy || !title.trim()} onClick={submit}>创建</Button>
        </div>
      </div>
    </Modal>
  );
}

/** M29-I90 quick edit (docs/01 §AB.2, Kanboard #3142 gap): inline-edit a card's
 * status/priority/assignee/due date without opening the drawer. Every change
 * goes through PATCH /items/{id} — patch_item, so the transition whitelist,
 * blocks closure, WIP limits and audit attribution are inherited for free. */
function QuickEditModal({ item, concepts, onClose, onSaved }: {
  item: import("../lib/api").Item;
  concepts: { id: string; name: string; states?: { id: string; name: string }[] }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [status, setStatus] = useState(item.status);
  const [priority, setPriority] = useState(item.priority ?? "");
  const [assignee, setAssignee] = useState(
    item.assignee_type === "human" ? item.assignee_id ?? "" : item.assignee_id ? `agent:${item.assignee_id}` : "",
  );
  const [due, setDue] = useState(item.due_date ?? "");
  const [cycle, setCycle] = useState(item.cycle_id ?? "");
  const [busy, setBusy] = useState(false);
  // M63-I191: in-item checklist (docs/01 §BH.3) — lightweight, advisory only
  const [checklist, setChecklist] = useState<{ text: string; done: boolean; extracted?: string }[]>(() => {
    try { return item.checklist ? JSON.parse(item.checklist) : []; } catch { return []; }
  });
  const [newCheck, setNewCheck] = useState("");
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const cyclesQ = useQuery({ queryKey: ["cycles", item.project_id], queryFn: () => api.listCycles(item.project_id) });

  const saveChecklist = async (next: { text: string; done: boolean }[]) => {
    setChecklist(next);
    if (next.length || item.checklist) {
      try { await api.patchChecklist(item.id, next); } catch (e) {
        toast.error(`清单保存失败：${e instanceof Error ? e.message : e}`);
      }
    }
  };

  const concept = concepts.find((c) => c.id === item.concept_id);
  const states = concept?.states ?? [];

  const submit = async () => {
    const patch: Record<string, unknown> = {};
    if (status && status !== item.status) patch.status = status;
    if (priority !== (item.priority ?? "")) patch.priority = priority || null;
    if (assignee !== (item.assignee_type === "human" ? item.assignee_id ?? "" : item.assignee_id ? `agent:${item.assignee_id}` : "")) {
      if (!assignee) { patch.assignee_type = null; patch.assignee_id = null; }
      else if (assignee.startsWith("agent:")) { patch.assignee_type = "agent"; patch.assignee_id = assignee.slice(6); }
      else { patch.assignee_type = "human"; patch.assignee_id = assignee; }
    }
    if (due !== (item.due_date ?? "")) patch.due_date = due || null;
    if (cycle !== (item.cycle_id ?? "")) patch.cycle_id = cycle; // "" clears the mount
    if (!Object.keys(patch).length) { onClose(); return; }
    setBusy(true);
    try {
      await api.patchItem(item.id, patch);
      toast.success("已更新");
      onSaved();
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const selectCls = "w-full rounded-lg border border-line bg-bg px-2 py-1.5 text-xs text-ink";
  return (
    <Modal open onClose={onClose} title={`⚡ 快捷编辑 · ${item.title}`}>
      <div className="space-y-2 text-xs">
        <label className="block text-[10px] text-mut">
          状态
          <select value={status} onChange={(e) => setStatus(e.target.value)} className={`mt-0.5 ${selectCls}`}>
            {states.length
              ? states.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)
              : <option value={status}>{status}</option>}
          </select>
        </label>
        <label className="block text-[10px] text-mut">
          优先级
          <select value={priority} onChange={(e) => setPriority(e.target.value)} className={`mt-0.5 ${selectCls}`}>
            <option value="">（无）</option>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </label>
        <label className="block text-[10px] text-mut">
          执行者
          <select value={assignee} onChange={(e) => setAssignee(e.target.value)} className={`mt-0.5 ${selectCls}`}>
            <option value="">（取消指派）</option>
            {(users.data?.users ?? []).map((u) => (
              <option key={u.id} value={u.id}>👤 {u.name}</option>
            ))}
          </select>
        </label>
        <label className="block text-[10px] text-mut">
          截止日
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)}
            className={`mt-0.5 ${selectCls}`} />
        </label>
        <label className="block text-[10px] text-mut">
          迭代周期
          <select value={cycle} onChange={(e) => setCycle(e.target.value)} className={`mt-0.5 ${selectCls}`}>
            <option value="">（无周期）</option>
            {(cyclesQ.data?.cycles ?? []).map((c) => (
              <option key={c.id} value={c.id}>🔁 {c.name}</option>
            ))}
          </select>
        </label>
        {/* M63-I191: checklist — 同屏轻量勾选，不做实体转换 */}
        <div className="rounded-lg border border-line bg-bg p-2">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10px] text-mut">☑ 清单 {checklist.filter((c) => c.done).length}/{checklist.length}</span>
            {checklist.length > 0 && (
              <button onClick={() => saveChecklist(checklist.filter((c) => !c.done))}
                className="text-[10px] text-mut hover:text-dan" title="移除已完成项">清除已完成</button>
            )}
          </div>
          <div className="space-y-0.5">
            {checklist.map((c, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <input type="checkbox" checked={c.done} onChange={() =>
                  saveChecklist(checklist.map((x, j) => j === i ? { ...x, done: !x.done } : x))
                } />
                <span className={cx("min-w-0 flex-1 truncate", c.done && "text-mut line-through")}>
                  {c.text}
                  {"extracted" in c && c.extracted && (
                    <Link to={`/board?item=${c.extracted}`}
                      className="ml-1 text-[10px] text-acc hover:underline" title="已转为工作项">→任务</Link>
                  )}
                </span>
                {!("extracted" in c && c.extracted) && (
                  <button title="把这项转为真实工作项（同项目 task 概念，显式点击防误触）"
                    onClick={async () => {
                      try {
                        const x = await api.extractChecklistTask(item.id, i);
                        toast.success(`已转为任务「${x.item.title}」`);
                        await saveChecklist(checklist.map((y, j) =>
                          j === i ? { ...y, extracted: x.item.id } : y));
                        onSaved();
                      } catch (e) {
                        toast.error(`转任务失败：${e instanceof Error ? e.message : e}`);
                      }
                    }}
                    className="text-[10px] text-mut hover:text-acc">→任务</button>
                )}
                <button onClick={() => saveChecklist(checklist.filter((_, j) => j !== i))}
                  className="text-[10px] text-mut hover:text-dan">✕</button>
              </div>
            ))}
          </div>
          <div className="mt-1 flex items-center gap-1">
            <input value={newCheck} onChange={(e) => setNewCheck(e.target.value)}
              onKeyDown={async (e) => {
                if (e.key === "Enter" && newCheck.trim()) {
                  if (checklist.length >= 20) { toast.error("清单最多 20 项"); return; }
                  await saveChecklist([...checklist, { text: newCheck.trim(), done: false }]);
                  setNewCheck("");
                }
              }}
              placeholder="添加清单项，回车确认（≤200 字）"
              className="w-0 flex-1 rounded border border-line bg-surface px-1.5 py-0.5" />
          </div>
        </div>
        <div className="flex items-center justify-between pt-1">
          <span className="text-[10px] text-mut">变更走既有 PATCH——流转白名单/闭锁/WIP 全部生效</span>
          <Button size="sm" variant="primary" disabled={busy} onClick={submit}>保存</Button>
        </div>
      </div>
    </Modal>
  );
}

function AttachmentModal({ itemId, title, onClose }: { itemId: string; title: string; onClose: () => void }) {
  const qc = useQueryClient();
  const att = useQuery({ queryKey: ["attachments", itemId], queryFn: () => api.listAttachments(itemId) });
  const [busy, setBusy] = useState(false);

  const fmtSize = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1024))}KB`);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try {
      await api.uploadAttachment(itemId, file);
      toast.success(`已上传 ${file.name}`);
      await qc.invalidateQueries({ queryKey: ["attachments", itemId] });
    } catch (e) {
      toast.error(`上传失败：${e instanceof Error ? e.message : e}`);
    } finally { setBusy(false); }
  };

  const remove = async (aid: string) => {
    setBusy(true);
    try {
      await api.removeAttachment(itemId, aid);
      toast.info("附件已删除");
      await qc.invalidateQueries({ queryKey: ["attachments", itemId] });
    } catch (e) {
      toast.error(`删除失败：${e instanceof Error ? e.message : e}`);
    } finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title={`📎 附件 · ${title}`}>
      <div className="space-y-2 text-xs">
        {att.isLoading && <div className="text-mut">加载中…</div>}
        {(att.data?.attachments ?? []).map((a) => (
          <div key={a.id} className="flex items-center gap-2 rounded-lg border border-line px-2 py-1.5">
            <span className="min-w-0 flex-1 truncate">{a.filename}</span>
            <span className="shrink-0 text-[10px] text-mut">{fmtSize(a.size)}</span>
            <a href={api.attachmentDownloadUrl(itemId, a.id)} className="shrink-0 text-acc hover:underline">下载</a>
            <button disabled={busy} onClick={() => remove(a.id)} className="shrink-0 text-mut hover:text-dan" title="删除">✕</button>
          </div>
        ))}
        {att.data && !att.data.attachments.length && (
          <div className="text-mut">还没有附件——文件存在服务端磁盘，元数据进事件流</div>
        )}
        <label className="block cursor-pointer rounded-lg border border-dashed border-line px-2 py-3 text-center text-mut hover:border-acc hover:text-acc">
          {busy ? "上传中…" : "＋ 选择文件上传（默认上限 10MB）"}
          <input type="file" className="hidden" disabled={busy}
            onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
      </div>
    </Modal>
  );
}


/** M48-I145 周期回顾包抽屉：一页看完成率/拖入/超期/阻塞 top/速率对比。 */
function RetroDrawer({ cycleId, onClose }: { cycleId: string; onClose: () => void }) {
  const retro = useQuery({
    queryKey: ["retro", cycleId],
    queryFn: () => api.getCycleRetrospective(cycleId),
  });
  const d = retro.data;
  const pct = d?.completion_rate != null ? `${Math.round(d.completion_rate * 100)}%` : "—";
  return (
    <Drawer open onClose={onClose} title={d ? `📋 回顾 · ${d.name}` : "📋 周期回顾"} width="44%">
      {retro.isError && <div className="text-sm text-dan">回顾数据加载失败，请关闭重试。</div>}
      {!d && !retro.isError && <div className="text-sm text-mut">加载回顾…</div>}
      {d && (
        <div className="space-y-3 text-sm print-card">
          {d.reason === "empty scope" && (
            <div className="rounded-lg border border-line bg-bg px-3 py-2 text-xs text-mut">
              本周期没有挂入任何工作项——无数据可回顾。
            </div>
          )}
          <div className="grid grid-cols-3 gap-2 text-center">
            <Card className="p-2">
              <div className="text-lg font-bold text-ink">{d.completed}/{d.committed}</div>
              <div className="text-[10px] text-mut">承诺完成</div>
            </Card>
            <Card className="p-2">
              <div className="text-lg font-bold text-ink">{pct}</div>
              <div className="text-[10px] text-mut">完成率</div>
            </Card>
            <Card className="p-2">
              <div className="text-lg font-bold text-ink">
                {d.prev_completed != null ? `${d.completed > d.prev_completed ? "↑" : d.completed < d.prev_completed ? "↓" : "→"} ${d.prev_completed}` : "—"}
              </div>
              <div className="text-[10px] text-mut">vs 上周期完成</div>
            </Card>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold text-mut">晚到拖入（{d.carried_in.length}）</div>
            {d.carried_in.length
              ? d.carried_in.map((x) => <div key={x.id} className="text-xs text-mut">· {x.title}</div>)
              : <div className="text-xs text-mut">无——scope 纪律良好</div>}
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold text-mut">周期内新增且已超期（{d.overdue_new.length}）</div>
            {d.overdue_new.length
              ? d.overdue_new.map((x) => (
                <div key={x.id} className="text-xs text-dan">· {x.title}（到期 {x.due_date}）</div>))
              : <div className="text-xs text-mut">无</div>}
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold text-mut">Top 阻塞依赖（{d.top_blockers.length}）</div>
            {d.top_blockers.length
              ? d.top_blockers.map((x) => (
                <div key={x.id} className="text-xs text-mut">· {x.title}——阻塞 {x.blocks} 项</div>))
              : <div className="text-xs text-mut">无阻塞记录</div>}
          </div>
          {d.prev_open_actions.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold text-warn">上届未结行动项（开场过账 · {d.prev_open_actions.length}）</div>
              {d.prev_open_actions.map((x) => (
                <div key={x.id} className="text-xs text-mut">· {x.title}{x.owner ? ` @${x.owner}` : ""}{x.due_date ? `（${x.due_date} 前）` : ""}</div>
              ))}
            </div>
          )}
          {d.open_actions.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold text-mut">本周期行动项（未结 {d.open_actions.length}）</div>
              {d.open_actions.map((x) => (
                <div key={x.id} className="text-xs text-mut">· {x.title}{x.owner ? ` @${x.owner}` : ""}</div>
              ))}
            </div>
          )}
          <ActionItemsForm cycleId={cycleId} onConverted={() => retro.refetch()} />
          <div className="text-[10px] text-mut">
            🤖 Run 参与：{d.runs ? `${d.runs.count} 次（成功 ${d.runs.succeeded}）· tokens ${d.runs.input_tokens}/${d.runs.output_tokens}` : "—"}
          </div>
        </div>
      )}
    </Drawer>
  );
}


/** M49-I147 行动项表单：回顾现场立即转换（title/owner/due ×3 行）——
 * 转换后走 create_item 全校验链，payload 记 retro_of 审计链。 */
function ActionItemsForm({ cycleId, onConverted }: { cycleId: string; onConverted: () => void }) {
  const [rows, setRows] = useState([
    { title: "", owner: "", due_date: "" },
    { title: "", owner: "", due_date: "" },
  ]);
  const [busy, setBusy] = useState(false);
  const valid = rows.filter((r) => r.title.trim());
  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.createActionItems(cycleId, valid.map((r) => ({
        title: r.title.trim(),
        owner: r.owner.trim() || undefined,
        due_date: r.due_date.trim() || undefined,
      })));
      toast.success(`已转换 ${r.created.length} 条行动项`,
        { description: r.skipped.length ? `${r.skipped.length} 条重复跳过` : undefined });
      setRows([{ title: "", owner: "", due_date: "" }, { title: "", owner: "", due_date: "" }]);
      onConverted();
    } catch (e) {
      toast.error("行动项转换失败", { description: String(e) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="rounded-lg border border-line p-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-semibold text-mut">行动项（立即转为任务）</span>
        <button className="text-[10px] text-acc hover:underline"
          onClick={() => setRows((r) => [...r, { title: "", owner: "", due_date: "" }])}>
          ＋ 加一行
        </button>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="mb-1 flex gap-1">
          <input className="min-w-0 flex-1 rounded border border-line bg-bg px-2 py-1 text-xs"
            placeholder="行动项标题" value={r.title}
            onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))} />
          <input className="w-20 rounded border border-line bg-bg px-2 py-1 text-xs"
            placeholder="负责人" value={r.owner}
            onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, owner: e.target.value } : x)))} />
          <input className="w-32 rounded border border-line bg-bg px-2 py-1 text-xs" type="date"
            value={r.due_date}
            onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, due_date: e.target.value } : x)))} />
        </div>
      ))}
      <Button size="sm" variant="primary" className="mt-1 w-full" disabled={!valid.length || busy} onClick={submit}>
        {busy ? "转换中…" : `转为任务（${valid.length}）`}
      </Button>
    </div>
  );
}
