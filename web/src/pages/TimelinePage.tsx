/** Timeline page (M13-I42): a Gantt-lite date axis — bars for scheduled items
 * grouped by concept, diamonds for milestones, dependency connectors for
 * depends_on relations. Conflicts (dependent starting before its prerequisite
 * ends) are flagged red; there is no automatic rescheduling (docs/01 §L.1).
 * M20-I63 (docs/01 §S.2): bars are draggable — move shifts start/due together,
 * the right edge resizes due only — PATCHing through the existing endpoint so
 * M14 rescheduled audit and conflict recomputation apply; Esc cancels.
 * M25-I78 (docs/01 §X.2): edges per relation type — depends_on stays a red
 * dashed conflict line, blocks gets an orange solid line, precedes a grey
 * dashed one and relates a dotted one. */
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import type { Item } from "../lib/api";
import { Card, Empty, cx } from "../components/ui";
import { weightedProgress } from "../lib/rollup";

const DAY = 86_400_000;
const ROW_H = 40;

// I78 edge styles per relation type; dash undefined → solid.
// depends_on_ok (M27 审阅即修): an aligned (non-conflicting) depends_on edge —
// drawn muted so the lag gap is visible without crying wolf; conflicts stay red.
const EDGE_STYLE: Record<string, { stroke: string; dash?: string }> = {
  depends_on: { stroke: "rgb(239 68 68)", dash: "4 3" },
  depends_on_ok: { stroke: "rgb(148 163 184)", dash: "4 3" },
  blocks: { stroke: "rgb(251 146 60)" },
  precedes: { stroke: "rgb(148 163 184)", dash: "4 3" },
  relates: { stroke: "rgb(148 163 184)", dash: "2 4" },
};

type Dated = { item: Item; start: Date; due: Date; conflict: boolean };

function parseDay(s?: string | null): Date | null {
  if (!s) return null;
  const d = new Date(`${s}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function TimelinePage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const items = useQuery({ queryKey: ["items", pid], queryFn: () => api.listItems(pid!), enabled: !!pid });
  const milestones = useQuery({ queryKey: ["milestones", pid], queryFn: () => api.listMilestones(pid!), enabled: !!pid });
  const ontology = useQuery({ queryKey: ["ontology", pid], queryFn: () => api.getOntology(pid!, true), enabled: !!pid });
  // I71/I76: baseline history — ghosts for one selected baseline or all of them
  const baselinesQ = useQuery({ queryKey: ["baselines", pid], queryFn: () => api.listBaselines(pid!), enabled: !!pid });
  const [blFilter, setBlFilter] = useState<string>("all");
  const blList = baselinesQ.data?.baselines ?? [];
  const [varianceOpen, setVarianceOpen] = useState(false);
  // I101: CPM critical chain toggle + red-frame highlight
  const cp = useQuery({ queryKey: ["critical-path", pid], queryFn: () => api.getCriticalPath(pid!), enabled: !!pid });
  const [showCP, setShowCP] = useState(false);
  const criticalIds = useMemo(() => new Set(showCP && !cp.data?.cycle ? cp.data?.chain ?? [] : []), [showCP, cp.data]);
  // I102/I116: weighted progress for the mini progress bars on parent bars
  const subProgress = useMemo(() => weightedProgress(items.data?.items ?? []), [items.data]);
  const variance = useQuery({
    queryKey: ["variance", pid, blFilter],
    queryFn: () => api.baselineVariance(pid!, blFilter === "all" ? undefined : blFilter),
    enabled: !!pid && varianceOpen && blList.length > 0,
  });

  // I63 drag-to-reschedule state: delta is whole days since pointer-down.
  type Drag = {
    id: string; mode: "move" | "resize";
    origStart: Date; origDue: Date; hasStart: boolean;
    clientX0: number; pxPerDay: number; delta: number;
  };
  const [drag, setDrag] = useState<Drag | null>(null);

  const beginDrag = (e: React.PointerEvent, d: Dated, mode: "move" | "resize") => {
    e.preventDefault();
    e.stopPropagation();
    const track = e.currentTarget.parentElement as HTMLElement;
    const w = track.getBoundingClientRect().width;
    if (w <= 0) return;
    setDrag({
      id: d.item.id, mode,
      origStart: d.start, origDue: d.due, hasStart: !!d.item.start_date,
      clientX0: e.clientX, pxPerDay: w / view.days, delta: 0,
    });
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const onDragMove = (e: React.PointerEvent) => {
    if (!drag) return;
    const raw = Math.round((e.clientX - drag.clientX0) / drag.pxPerDay);
    // resize keeps due on/after start; move keeps the original span
    const delta = drag.mode === "move"
      ? raw
      : Math.max(raw, Math.round((drag.origStart.getTime() - drag.origDue.getTime()) / DAY));
    if (delta !== drag.delta) setDrag({ ...drag, delta });
  };

  const endDrag = async (cancel = false) => {
    if (!drag) return;
    const d = drag;
    setDrag(null);
    if (cancel || d.delta === 0) return;
    const shift = (x: Date) => new Date(x.getTime() + d.delta * DAY).toISOString().slice(0, 10);
    const body: Record<string, unknown> = { due_date: shift(d.origDue) };
    if (d.mode === "move" && d.hasStart) body.start_date = shift(d.origStart);
    try {
      await api.patchItem(d.id, body);
      toast.success(`已改期 ${d.delta > 0 ? "+" : ""}${d.delta} 天${d.mode === "resize" ? "（仅截止）" : ""}——依赖与冲突已重算`);
      qc.invalidateQueries();
    } catch (err) {
      toast.error(`改期失败：${err instanceof Error ? err.message : err}`);
    }
  };

  // I65: drag from a bar's endpoint circle onto another bar to create
  // depends_on (dragged bar depends on the drop target). Rubber-band line
  // renders in the connector SVG's coordinate space (% x, px y).
  const svgRef = useRef<SVGSVGElement | null>(null);
  const linkMeta = useRef<{ rect: DOMRect; fromId: string; from: { x: number; y: number }; cancelled: boolean } | null>(null);
  const [linkLine, setLinkLine] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);

  const toSvgPoint = (rect: DOMRect, x: number, y: number) => ({
    px: ((x - rect.left) / rect.width) * 100,
    py: y - rect.top,
  });

  const cancelLink = () => {
    if (linkMeta.current) linkMeta.current.cancelled = true;
    setLinkLine(null);
  };

  // Esc cancels both an in-progress date drag and a dependency link drag
  useEffect(() => {
    if (!drag && !linkLine) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setDrag(null); cancelLink(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drag, linkLine]);

  const beginLinkDrag = (e: React.PointerEvent, d: Dated) => {
    e.preventDefault();
    e.stopPropagation();
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const from = { x: e.clientX, y: e.clientY };
    linkMeta.current = { rect, fromId: d.item.id, from, cancelled: false };
    const p1 = toSvgPoint(rect, from.x, from.y);
    setLinkLine({ x1: p1.px, y1: p1.py, x2: p1.px, y2: p1.py });
    const move = (ev: PointerEvent) => {
      if (linkMeta.current?.cancelled) return;
      const p2 = toSvgPoint(rect, ev.clientX, ev.clientY);
      setLinkLine({ x1: p1.px, y1: p1.py, x2: p2.px, y2: p2.py });
    };
    const up = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      const meta = linkMeta.current;
      linkMeta.current = null;
      setLinkLine(null);
      if (!meta || meta.cancelled) return;
      const el = document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null;
      const toId = el?.closest("[data-item-id]")?.getAttribute("data-item-id");
      if (!toId || toId === meta.fromId) return;
      api.addRelation(meta.fromId, { to_item: toId, relation_type: "depends_on" })
        .then(() => {
          toast.success("已建立依赖：前置完成后本任务才能开始");
          qc.invalidateQueries();
        })
        .catch((err) => toast.error(`建立依赖失败：${err instanceof Error ? err.message : err}`));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
  };

  const all = items.data?.items ?? [];
  const dated = all.filter((i) => i.start_date || i.due_date);
  const msRow = milestones.data?.milestones ?? [];

  // Dependency edges between dated items need each item's relations → one
  // detail fetch per dated item (fine at single-project scale; relations only
  // ship on the detail payload).
  const details = useQuery({
    queryKey: ["item-details", pid, dated.map((d) => d.id).join(",")],
    queryFn: async () => {
      const out: Record<string, Item> = {};
      await Promise.all(dated.map(async (d) => { out[d.id] = await api.getItem(d.id); }));
      return out;
    },
    enabled: !!pid && dated.length > 0,
  });

  const conceptName = (cid: string) =>
    ontology.data?.concepts.find((c) => c.id === cid)?.name ?? cid;

  const msCount = msRow.length;
  const view = useMemo(() => {
    const today = new Date(new Date().toISOString().slice(0, 10) + "T00:00:00Z");
    let min = today.getTime() - 15 * DAY;
    let max = today.getTime() + 30 * DAY;
    for (const it of dated) {
      for (const s of [it.start_date, it.due_date]) {
        const d = parseDay(s);
        if (d) { min = Math.min(min, d.getTime()); max = Math.max(max, d.getTime()); }
      }
    }
    for (const m of msRow) {
      const d = parseDay(m.due_date);
      if (d) { min = Math.min(min, d.getTime()); max = Math.max(max, d.getTime()); }
    }
    min -= 2 * DAY; max += 2 * DAY;
    const days = Math.max(Math.round((max - min) / DAY) + 1, 7);
    const pct = (d: Date) => ((d.getTime() - min) / DAY / days) * 100;

    const byConcept = new Map<string, Dated[]>();
    for (const it of dated) {
      const start = parseDay(it.start_date) ?? parseDay(it.due_date)!;
      const due = parseDay(it.due_date) ?? start;
      byConcept.set(it.concept_id, [
        ...(byConcept.get(it.concept_id) ?? []),
        { item: it, start, due, conflict: false },
      ]);
    }

    // M24-I76: lane packing per concept row (interval-graph greedy, CLRS) —
    // sort by start, drop each bar into the first sub-lane whose last bar ends
    // at/before it, else open a new lane. Fixes same-concept bar overlap.
    const rows = [...byConcept.entries()].map(([cid, list]) => {
      const sorted = [...list].sort((a, b) => a.start.getTime() - b.start.getTime() || a.item.id.localeCompare(b.item.id));
      const laneEnds: number[] = [];
      const laneOf = new Map<string, number>();
      for (const d of sorted) {
        let lane = laneEnds.findIndex((end) => end <= d.start.getTime());
        if (lane === -1) { lane = laneEnds.length; laneEnds.push(d.due.getTime()); }
        laneEnds[lane] = Math.max(laneEnds[lane], d.due.getTime());
        laneOf.set(d.item.id, lane);
      }
      const laneCount = Math.max(laneEnds.length, 1);
      return { cid, list: sorted, laneOf, laneCount, height: ROW_H * laneCount };
    });
    const rowTops: number[] = [];
    let acc = msCount * ROW_H;
    for (const r of rows) { rowTops.push(acc); acc += r.height; }

    // dependency conflicts: "from depends_on to" → from must not start before to ends.
    // I78: other typed edges (blocks/precedes/relates) draw from the blocker's
    // due edge to the dependent's start; depends_on keeps its conflict-only rule.
    // I83: edges carry the relation lag for the "+N 天" annotation.
    const connectors: { x1: number; y1: number; x2: number; y2: number; key: string; kind: string; lag?: number | null }[] = [];
    const detailsMap = details.data ?? {};
    const pos = new Map<string, { top: number; lane: number }>();
    rows.forEach((r, i) => {
      for (const d of r.list) pos.set(d.item.id, { top: rowTops[i], lane: r.laneOf.get(d.item.id) ?? 0 });
    });
    // bar centers host the bars; same-row conflicts route along the bar's
    // sub-lane bottom edge so the dashed line stays visible under the bars.
    const yOf = (itemId: string, edge = false) => {
      const p = pos.get(itemId);
      if (!p) return 0;
      return edge ? p.top + (p.lane + 1) * ROW_H - 4 : p.top + (p.lane + 0.5) * ROW_H;
    };
    for (const row of rows) {
      for (const d of row.list) {
        const rels = detailsMap[d.item.id]?.relations ?? [];
        for (const rel of rels) {
          if (rel.to_item === d.item.id) continue; // draw each edge once, from its source
          if (rel.relation_type === "depends_on") {
            const dep = detailsMap[rel.to_item];
            if (!dep) continue;
            const depStart = parseDay(dep.start_date) ?? parseDay(dep.due_date);
            const depDue = parseDay(dep.due_date) ?? depStart;
            if (!depStart || !depDue) continue;
            if (d.start.getTime() < depDue.getTime()) {
              d.conflict = true;
              const sameRow = pos.get(d.item.id)!.top === pos.get(rel.to_item)?.top;
              connectors.push({
                x1: pct(d.start), y1: yOf(d.item.id, sameRow),
                x2: pct(depDue), y2: yOf(rel.to_item, sameRow),
                key: `${d.item.id}->${rel.to_item}`, kind: "depends_on",
              });
            } else {
              // aligned edge (M27 审阅即修): draw muted + lag annotation, so an
              // I83 lag gap is visible instead of the edge silently disappearing
              const sameRow = pos.get(d.item.id)!.top === pos.get(rel.to_item)?.top;
              connectors.push({
                x1: pct(depDue), y1: yOf(rel.to_item, sameRow),
                x2: pct(d.start), y2: yOf(d.item.id, sameRow),
                key: `ok:${d.item.id}->${rel.to_item}`, kind: "depends_on_ok",
                lag: rel.lag_days ?? null,
              });
            }
            continue;
          }
          const style = EDGE_STYLE[rel.relation_type];
          if (!style) continue;
          const dep = detailsMap[rel.to_item];
          if (!dep) continue;
          const depStart = parseDay(dep.start_date) ?? parseDay(dep.due_date);
          if (!depStart) continue;
          const sameRow = pos.get(d.item.id)!.top === pos.get(rel.to_item)?.top;
          connectors.push({
            x1: pct(d.due), y1: yOf(d.item.id, sameRow),
            x2: pct(depStart), y2: yOf(rel.to_item, sameRow),
            key: `${rel.relation_type}:${d.item.id}->${rel.to_item}`, kind: rel.relation_type,
            lag: rel.lag_days ?? null,
          });
        }
      }
    }
    const ticks: { pct: number; label: string }[] = [];
    for (let i = 0; i <= days; i += 7) {
      ticks.push({ pct: (i / days) * 100, label: new Date(min + i * DAY).toISOString().slice(5, 10) });
    }
    return { days, pct, rows, rowInfos: rows, connectors, ticks, todayPct: pct(today) };
  }, [dated, msRow, details.data, msCount]);

  const hasData = view.rows.length > 0 || msCount > 0;

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-4">
      <Card className="min-w-[640px] p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-semibold">📅 时间线</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-mut">
              {dated.length} 个排期项 · {msCount} 个里程碑 · 红条/虚线 = 依赖冲突 · 拖动条形改期 / 拖右缘改截止 / 悬停条形拖端点圆圈到另一条形建依赖（Esc 取消）
            </span>
            {blList.length > 0 && (
              <>
                <select value={blFilter} onChange={(e) => setBlFilter(e.target.value)}
                  className="rounded-lg border border-line bg-surface px-2 py-1 text-xs">
                  {blList.map((b) => (
                    <option key={b.id} value={b.id}>基线 {String(b.created_at ?? "").slice(5, 16).replace("T", " ")}</option>
                  ))}
                  {blList.length > 1 && <option value="all">全部基线</option>}
                </select>
                <button onClick={() => setVarianceOpen(true)}
                  className="rounded-lg border border-line px-2 py-1 text-xs text-mut hover:border-acc hover:text-acc">📊 偏差表</button>
              </>
            )}
            {blList.length > 0 ? (
              <button onClick={async () => { await api.clearBaseline(pid!); toast.success("已清除全部基线"); qc.invalidateQueries(); }}
                className="rounded-lg border border-line px-2 py-1 text-xs text-mut hover:border-acc hover:text-acc">清除基线</button>
            ) : (
              <button onClick={async () => { await api.setBaseline(pid!); toast.success("已设为基线（当前日期快照）"); qc.invalidateQueries(); }}
                className="rounded-lg border border-line px-2 py-1 text-xs text-mut hover:border-acc hover:text-acc">📌 设为基线</button>
            )}
            <button onClick={() => setShowCP((v) => !v)}
              title={cp.data?.cycle ? "依赖图中存在环，无法计算关键路径" : "CPM 正逆传递：float≤0 的任务链决定项目终点"}
              className={cx("rounded-lg border px-2 py-1 text-xs",
                showCP ? "border-red-500 bg-red-500/10 text-red-400" : "border-line text-mut hover:border-acc hover:text-acc")}>
              ⛔ 关键路径
            </button>
          </div>
        </div>

        {/* date header */}
        <div className="relative ml-32 mr-2 h-5">
          {view.ticks.map((t) => (
            <span key={t.label + t.pct} className="absolute -translate-x-1/2 font-mono text-[10px] text-mut"
                  style={{ left: `${t.pct}%` }}>{t.label}</span>
          ))}
        </div>

        <div className="relative">
          {/* grid backdrop */}
          <div className="absolute inset-0 ml-32 mr-2" aria-hidden>
            {view.ticks.map((t) => (
              <div key={t.pct} className="absolute top-0 bottom-0 w-px bg-line" style={{ left: `${t.pct}%` }} />
            ))}
            <div className="absolute top-0 bottom-0 w-px bg-amber-400" style={{ left: `${view.todayPct}%` }} />
          </div>

          {/* milestone row */}
          {msCount > 0 && (
            <div className="flex items-center" style={{ height: ROW_H }}>
              <div className="w-32 shrink-0 pr-2 text-right text-xs text-mut">◆ 里程碑</div>
              <div className="relative h-full flex-1 mr-2">
                {msRow.map((m) => {
                  const d = parseDay(m.due_date);
                  if (!d) return null;
                  return (
                    <div
                      key={m.id}
                      title={`${m.title} · 截止 ${m.due_date} · 完成 ${Math.round((m.progress?.done_ratio ?? 0) * 100)}% · 逾期 ${m.progress?.overdue_items ?? 0}`}
                      className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rotate-45 border border-amber-500 bg-amber-300"
                      style={{ left: `${view.pct(d)}%` }}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* concept rows — sub-lane packed (M24-I76), height adapts to lanes */}
          {view.rowInfos.map((row) => (
            <div key={row.cid} className="flex items-start border-t border-line/60" style={{ height: row.height }}>
              <div className="w-32 shrink-0 truncate pr-2 text-right text-xs text-mut" style={{ paddingTop: row.height / 2 - 8 }} title={row.cid}>
                {conceptName(row.cid)}
              </div>
              <div className="relative h-full flex-1 mr-2">
                {row.list.map((d) => {
                  // I71/I76: ghost bars at baseline positions (drift → amber);
                  // multiple baselines stack with a small vertical offset
                  const shown = blFilter === "all" ? blList : blList.filter((b) => b.id === blFilter);
                  const ghostList = shown
                    .map((b, bi) => ({ b, bi }))
                    .filter(({ b }) => b.snapshot?.items?.[d.item.id])
                    .map(({ b, bi }) => {
                      const s = b.snapshot.items[d.item.id];
                      const bs = parseDay(s[0]) ?? parseDay(s[1]);
                      const bd = parseDay(s[1]) ?? parseDay(s[0]);
                      if (!bs || !bd) return null;
                      const drifted = s[0] !== d.item.start_date || s[1] !== d.item.due_date;
                      return {
                        gl: view.pct(bs), gw: Math.max(view.pct(bd) - view.pct(bs), 0.8),
                        drifted, label: `${s[0]} ~ ${s[1]}`, bi,
                      };
                    })
                    .filter((g): g is NonNullable<typeof g> => g !== null);
                  const lane = row.laneOf.get(d.item.id) ?? 0;
                  const laneTop = lane * ROW_H;
                  // live preview while this bar is dragged (half-transparent, ANKO-style)
                  const dragging = drag?.id === d.item.id && drag.delta !== 0;
                  const start = dragging && drag!.mode === "move"
                    ? new Date(d.start.getTime() + drag!.delta * DAY)
                    : d.start;
                  const due = dragging && drag
                    ? new Date(d.due.getTime() + drag.delta * DAY)
                    : d.due;
                  const left = view.pct(start);
                  const width = Math.max(view.pct(due) - left, 0.8);
                  const tone = d.item.status_group === "done" ? "bg-ag"
                    : d.item.status_group === "cancelled" ? "bg-line"
                    : d.conflict ? "bg-red-500 ring-2 ring-red-300" : "bg-acc";
                  const fmt = (x: Date) => x.toISOString().slice(0, 10);
                  return (
                    <div key={d.item.id}>
                      {ghostList.map((g, i) => (
                        <div key={i}
                          title={`📌 基线 ${g.label}${g.drifted ? "（已偏离基线）" : ""}`}
                          className={`pointer-events-none absolute h-4 -translate-y-1/2 rounded-full border border-dashed ${g.drifted ? "border-amber-500" : "border-line"}`}
                          style={{ left: `${g.gl}%`, width: `${g.gw}%`, top: laneTop + ROW_H / 2 - 8 + i * 5 }}
                        />
                      ))}
                      <div
                        data-item-id={d.item.id}
                        title={`${d.item.title} · ${d.item.status}${d.item.auto_scheduled ? " · ⏱ 自动排期" : ""}${d.conflict ? " · 依赖冲突：开始早于前置项完成" : ""}${dragging && drag ? ` → 改为 ${fmt(start)} ~ ${fmt(due)}` : ""}`}
                        onPointerDown={(e) => beginDrag(e, d, "move")}
                        onPointerMove={onDragMove}
                        onPointerUp={() => endDrag(false)}
                        onPointerCancel={() => endDrag(true)}
                        className={`group absolute h-4 -translate-y-1/2 cursor-grab touch-none rounded-full active:cursor-grabbing ${tone} ${dragging ? "opacity-50" : ""} ${criticalIds.has(d.item.id) ? "ring-2 ring-red-500 ring-offset-1 ring-offset-transparent" : ""}`}
                        style={{ left: `${left}%`, width: `${width}%`, top: laneTop + ROW_H / 2 }}
                      >
                        {subProgress.get(d.item.id) && (
                          <div className="absolute bottom-0 left-1 right-1 h-0.5 overflow-hidden rounded bg-black/25">
                            <div className="h-full rounded bg-emerald-400"
                              style={{ width: `${subProgress.get(d.item.id)!.percent}%` }} />
                          </div>
                        )}
                        <div
                          onPointerDown={(e) => beginDrag(e, d, "resize")}
                          title="拖动右缘改截止日"
                          className="absolute right-0 top-0 h-full w-1.5 cursor-ew-resize rounded-r-full bg-black/20 hover:bg-black/40"
                        />
                        {(["left", "right"] as const).map((pt) => (
                          <span key={pt}
                            onPointerDown={(e) => beginLinkDrag(e, d)}
                            title="拖到目标条形建立依赖（本任务 depends_on 目标）"
                            className={`absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full border border-white bg-indigo-500 opacity-0 shadow transition-opacity group-hover:opacity-100 cursor-crosshair ${pt === "left" ? "-left-1.5" : "-right-1.5"}`}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {/* typed relation connectors (I78: style per EDGE_STYLE — depends_on
              conflict lines, blocks solid orange, precedes dashed, relates dotted)
              + I65 rubber-band line while dragging a new dependency */}
          <svg ref={svgRef} className="pointer-events-none absolute inset-0 ml-32 h-full w-[calc(100%-8.5rem)]" aria-hidden>
            {view.connectors.map((c) => {
              const s = EDGE_STYLE[c.kind] ?? EDGE_STYLE.depends_on;
              return (
                <g key={c.key}>
                  <line x1={`${c.x1}%`} y1={c.y1} x2={`${c.x2}%`} y2={c.y2}
                        stroke={s.stroke} strokeDasharray={s.dash} strokeWidth="1.5" />
                  {c.lag != null && c.lag !== 0 && (
                    <text x={`${(c.x1 + c.x2) / 2}%`} y={Math.min(c.y1, c.y2) - 4}
                          textAnchor="middle" fontSize="9" fill={s.stroke}>
                      {c.lag > 0 ? `+${c.lag}天` : `${c.lag}天`}
                    </text>
                  )}
                </g>
              );
            })}
            {linkLine && (
              <line x1={`${linkLine.x1}%`} y1={linkLine.y1} x2={`${linkLine.x2}%`} y2={linkLine.y2}
                    stroke="rgb(99 102 241)" strokeWidth="2" strokeDasharray="6 4" />
            )}
          </svg>
        </div>

        {!hasData && (
          <Empty title="暂无排期数据" hint="给工作项设置起止日期（start_date/due_date）或创建里程碑后在此排布" />
        )}
      </Card>

      {/* M25-I77: baseline variance drawer */}
      {varianceOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-6" onClick={() => setVarianceOpen(false)}>
          <Card className="mt-10 w-full max-w-2xl p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold">📊 基线偏差表</span>
              <button onClick={() => setVarianceOpen(false)} className="text-xs text-mut hover:text-ink">✕</button>
            </div>
            {!variance.data && <div className="py-6 text-center text-xs text-mut">加载中…</div>}
            {variance.data && variance.data.variances.length === 0 && (
              <div className="py-6 text-center text-xs text-mut">全部工作项与基线一致 ✓</div>
            )}
            {variance.data && variance.data.variances.length > 0 && (
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-line text-mut">
                    <th className="py-1.5">任务</th><th>基线起止</th><th>当前起止</th><th className="text-right">偏差（天）</th>
                  </tr>
                </thead>
                <tbody>
                  {variance.data.variances.map((v) => (
                    <tr key={v.item_id} className="border-b border-line/60">
                      <td className="py-1.5 font-medium">{v.title}</td>
                      <td className="text-mut">{v.baseline_start ?? "—"} ~ {v.baseline_due ?? "—"}</td>
                      <td>{v.current_start ?? "—"} ~ {v.current_due ?? "—"}</td>
                      <td className="text-right">
                        {v.start_deviation != null && v.start_deviation !== 0 && (
                          <span className={v.start_deviation > 0 ? "text-red-500" : "text-green-600"}>
                            开始 {v.start_deviation > 0 ? "+" : ""}{v.start_deviation}{" "}
                          </span>
                        )}
                        {v.due_deviation != null && v.due_deviation !== 0 && (
                          <span className={v.due_deviation > 0 ? "text-red-500" : "text-green-600"}>
                            截止 {v.due_deviation > 0 ? "+" : ""}{v.due_deviation}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {variance.data && (
              <div className="mt-2 text-[10px] text-mut">
                共 {variance.data.summary.count} 项偏差 · 最大截止延迟 {variance.data.summary.max_due_delay} 天 · 正数=比基线晚
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
