/** Board: five-bucket kanban with NL-aware filters, multi-select, inline batch start.
 * Supports custom-field grouping (M6-I21): ?group=field:<id> switches columns.
 * M25-I79: list view renders progressively (LIST_PAGE rows per page + load more). */
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { customFieldBadges } from "../lib/fmt";
import { isTypingTarget } from "../lib/shortcuts";
import { subtaskProgress } from "../lib/rollup";
import { CommentsModal } from "../components/CommentsModal";
import { TimeLogModal, fmtMinutes } from "../components/TimeLogModal";
import { Badge, Button, Card, GROUP_NAME, GROUP_TONE, Modal, PrintButton, cx } from "../components/ui";

const LIST_PAGE = 20;

export function Board() {
  const { pid } = useParams();
  const [params, setParams] = useSearchParams();
  const featureId = params.get("feature") ?? undefined;
  const priority = params.get("priority") ?? "";
  const assignee = params.get("assignee") ?? "";
  const group = params.get("group") ?? "";
  const viewId = params.get("view") ?? "";
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [view, setView] = useState<"board" | "list">("board");
  const [viewsOpen, setViewsOpen] = useState(false);
  const [newViewName, setNewViewName] = useState("");
  const [newViewPublic, setNewViewPublic] = useState(false);
  const [commentsFor, setCommentsFor] = useState<import("../lib/api").Item | null>(null);
  const [timelogFor, setTimelogFor] = useState<import("../lib/api").Item | null>(null);
  const [quickEditFor, setQuickEditFor] = useState<import("../lib/api").Item | null>(null);

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

  const board = useQuery({
    queryKey: ["board", pid, featureId, group],
    queryFn: () => api.getBoard(pid!, featureId, group || undefined),
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

  const matches = (item: { priority?: string; assignee_id?: string }) =>
    (!priority || item.priority === priority) && (!assignee || item.assignee_id === assignee);

  // M22-I70: the flat list currently shown in list view (select-all scope)
  const listed = (board.data?.buckets ?? []).flatMap((b) => b.items.filter(matches));

  // M24-I74: hierarchy — parent titles, collapsible tree rows, descendant scope
  const allItems = useMemo(() => (board.data?.buckets ?? []).flatMap((b) => b.items), [board.data]);
  const titleMap = useMemo(() => Object.fromEntries(allItems.map((i) => [i.id, i.title])) as Record<string, string>, [allItems]);
  // I102: per-parent subtask progress (GitHub sub-issue progress semantics)
  const subProgress = useMemo(() => subtaskProgress(allItems), [allItems]);
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
      const cf = typeof item.custom_fields === "string"
        ? JSON.parse(item.custom_fields || "{}")
        : item.custom_fields ?? {};
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
      qc.invalidateQueries();
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
    qc.invalidateQueries();
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
      qc.invalidateQueries();
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
                            {subProgress.get(item.id) && (
                              <span className="text-[10px] text-mut" title="子任务完成进度">
                                🧩 {subProgress.get(item.id)!.done}/{subProgress.get(item.id)!.total}
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
                  <span className="text-xs font-medium text-red-500"
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
                {items.map((item) => {
                  const run = runByItem.get(item.id);
                  return (
                    <Card
                      key={item.id}
                      data-kb={item.id}
                      onClick={() => toggle(item.id)}
                      className={cx(
                        "cursor-pointer p-2.5 text-xs transition-all",
                        selected.has(item.id) && "ring-2 ring-acc",
                        listed[kbIndex]?.id === item.id && "ring-2 ring-amber-400",
                      )}
                    >
                      <div className="flex items-start gap-1.5">
                        <input type="checkbox" checked={selected.has(item.id)} readOnly className="mt-0.5" />
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium">{item.title}</div>
                          {item.parent_id && titleMap[item.parent_id] && (
                            <div className="mt-0.5 truncate text-[10px] text-mut" title="父任务">↳ {titleMap[item.parent_id]}</div>
                          )}
                          <div className="mt-1 flex flex-wrap items-center gap-1">
                            <Badge tone={GROUP_TONE[item.status_group]}>{item.status}</Badge>
                            {item.priority === "high" && <Badge tone="red">高优</Badge>}
                            {subProgress.get(item.id) && (
                              <Badge tone={subProgress.get(item.id)!.done === subProgress.get(item.id)!.total ? "green" : "neutral"}
                                title="子任务完成进度">
                                🧩 {subProgress.get(item.id)!.done}/{subProgress.get(item.id)!.total}
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
                                  qc.invalidateQueries();
                                } catch (err) {
                                  toast.error(`归档失败：${err instanceof Error ? err.message : err}`);
                                }
                              }}
                              className="text-[10px] text-mut hover:text-acc" title="归档（回收站可恢复）"
                            >
                              🗄
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); setTimelogFor(item); }}
                              className="ml-auto text-[10px] text-mut hover:text-acc" title="工时"
                            >
                              ⏱
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); setCommentsFor(item); }}
                              className="ml-auto text-[10px] text-mut hover:text-acc" title="评论"
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
                                qc.invalidateQueries();
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
                {!items.length && <div className="px-2 py-4 text-center text-[11px] text-mut">空</div>}
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
      {quickEditFor && (
        <QuickEditModal item={quickEditFor} concepts={onto.data?.concepts ?? []}
          onClose={() => setQuickEditFor(null)}
          onSaved={() => { setQuickEditFor(null); qc.invalidateQueries(); }} />
      )}
      {createOpen && pid && (
        <CreateTaskModal pid={pid}
          onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); qc.invalidateQueries(); }} />
      )}
      {trashOpen && pid && (
        <TrashDrawer pid={pid} onClose={() => setTrashOpen(false)} onRestored={() => qc.invalidateQueries()} />
      )}
      {importOpen && (
        <Modal open onClose={() => setImportOpen(false)} title="⬆ 导入工作项 CSV">
          <div className="space-y-3 text-xs">
            <div className="flex items-center gap-2">
              <a href={`/api/projects/${pid}/items/import-template`} className="text-acc hover:underline">下载模板</a>
              <a href={`/api/projects/${pid}/items.csv`} className="text-acc hover:underline">导出当前工作项</a>
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
                    qc.invalidateQueries();
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
      await qc.invalidateQueries();
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
  const [busy, setBusy] = useState(false);
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });

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
        <div className="flex items-center justify-between pt-1">
          <span className="text-[10px] text-mut">变更走既有 PATCH——流转白名单/闭锁/WIP 全部生效</span>
          <Button size="sm" variant="primary" disabled={busy} onClick={submit}>保存</Button>
        </div>
      </div>
    </Modal>
  );
}
