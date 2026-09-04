/** Board: five-bucket kanban with NL-aware filters, multi-select, inline batch start.
 * Supports custom-field grouping (M6-I21): ?group=field:<id> switches columns. */
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { customFieldBadges } from "../lib/fmt";
import { CommentsModal } from "../components/CommentsModal";
import { TimeLogModal, fmtMinutes } from "../components/TimeLogModal";
import { Badge, Button, Card, GROUP_NAME, GROUP_TONE, cx } from "../components/ui";

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

  const viewsQ = useQuery({
    queryKey: ["views", pid],
    queryFn: () => api.listViews(pid!),
    enabled: !!pid,
  });

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

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2">
        <span className="text-sm font-semibold">看板</span>
        <div className="flex overflow-hidden rounded-lg border border-line">
          {(["board", "list"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={cx("px-2.5 py-1 text-xs", view === v ? "bg-accbg text-acc" : "text-mut hover:text-ink")}>
              {v === "board" ? "▦ 看板" : "☰ 列表"}
            </button>
          ))}
        </div>
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
        <div className="ml-auto flex items-center gap-2 text-xs">
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
              <Button size="sm" variant="primary" onClick={batchStart}>▶ 让 Agent 做</Button>
              <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>清除</Button>
            </>
          )}
        </div>
      </div>

      {view === "list" && (
        <div className="overflow-x-auto p-4">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead>
              <tr className="border-b border-line text-mut">
                <th className="py-2">标题</th><th>概念</th><th>状态</th><th>优先级</th><th>执行者</th><th>字段</th><th>更新</th>
              </tr>
            </thead>
            <tbody>
              {(board.data?.buckets ?? []).flatMap((b) => b.items.filter(matches)).map((item) => (
                <tr key={item.id} className="border-b border-line/60 hover:bg-bg">
                  <td className="py-2 font-medium">{item.title}</td>
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
                </tr>
              ))}
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
          return (
            <div key={col.id} className="flex w-64 shrink-0 flex-col rounded-[12px] border border-line bg-surface/50">
              <div className="flex items-center justify-between px-3 py-2">
                <Badge tone={col.tone}>{col.label}</Badge>
                <span className="text-xs text-mut">{items.length}</span>
              </div>
              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-2 pb-3">
                {items.map((item) => {
                  const run = runByItem.get(item.id);
                  return (
                    <Card
                      key={item.id}
                      onClick={() => toggle(item.id)}
                      className={cx(
                        "cursor-pointer p-2.5 text-xs transition-all",
                        selected.has(item.id) && "ring-2 ring-acc",
                      )}
                    >
                      <div className="flex items-start gap-1.5">
                        <input type="checkbox" checked={selected.has(item.id)} readOnly className="mt-0.5" />
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium">{item.title}</div>
                          <div className="mt-1 flex flex-wrap items-center gap-1">
                            <Badge tone={GROUP_TONE[item.status_group]}>{item.status}</Badge>
                            {item.priority === "high" && <Badge tone="red">高优</Badge>}
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
        <CommentsModal itemId={commentsFor.id} title={commentsFor.title}
          onClose={() => { setCommentsFor(null); if (focusItem) setFilter("item", ""); }} />
      )}
      {timelogFor && (
        <TimeLogModal itemId={timelogFor.id} title={timelogFor.title}
          onClose={() => setTimelogFor(null)} />
      )}
    </div>
  );
}
