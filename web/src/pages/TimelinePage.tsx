/** Timeline page (M13-I42): a Gantt-lite date axis — bars for scheduled items
 * grouped by concept, diamonds for milestones, dependency connectors for
 * depends_on relations. Conflicts (dependent starting before its prerequisite
 * ends) are flagged red; there is no automatic rescheduling (docs/01 §L.1).
 * M20-I63 (docs/01 §S.2): bars are draggable — move shifts start/due together,
 * the right edge resizes due only — PATCHing through the existing endpoint so
 * M14 rescheduled audit and conflict recomputation apply; Esc cancels. */
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import type { Item } from "../lib/api";
import { Card, Empty } from "../components/ui";

const DAY = 86_400_000;
const ROW_H = 40;

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

  // I63 drag-to-reschedule state: delta is whole days since pointer-down.
  type Drag = {
    id: string; mode: "move" | "resize";
    origStart: Date; origDue: Date; hasStart: boolean;
    clientX0: number; pxPerDay: number; delta: number;
  };
  const [drag, setDrag] = useState<Drag | null>(null);

  useEffect(() => {
    if (!drag) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setDrag(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drag]);

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
    const rows = [...byConcept.entries()].map(([cid, list]) => ({ cid, list }));

    // dependency conflicts: "from depends_on to" → from must not start before to ends
    const connectors: { x1: number; y1: number; x2: number; y2: number; key: string }[] = [];
    const detailsMap = details.data ?? {};
    const rowIdx = (itemId: string) =>
      rows.findIndex((r) => r.list.some((d) => d.item.id === itemId));
    // row centers host the bars; same-row conflicts route along the row's
    // bottom edge so the dashed line stays visible under the bars.
    const yOf = (itemId: string, edge = false) => {
      const idx = rowIdx(itemId);
      return edge ? (msCount + idx + 1) * ROW_H - 4 : (msCount + idx + 0.5) * ROW_H;
    };
    for (const row of rows) {
      for (const d of row.list) {
        const rels = detailsMap[d.item.id]?.relations ?? [];
        for (const rel of rels) {
          if (rel.relation_type !== "depends_on" || rel.to_item === d.item.id) continue;
          const dep = detailsMap[rel.to_item];
          if (!dep) continue;
          const depStart = parseDay(dep.start_date) ?? parseDay(dep.due_date);
          const depDue = parseDay(dep.due_date) ?? depStart;
          if (!depStart || !depDue) continue;
          if (d.start.getTime() < depDue.getTime()) {
            d.conflict = true;
            const sameRow = rowIdx(d.item.id) === rowIdx(rel.to_item);
            connectors.push({
              x1: pct(d.start), y1: yOf(d.item.id, sameRow),
              x2: pct(depDue), y2: yOf(rel.to_item, sameRow),
              key: `${d.item.id}->${rel.to_item}`,
            });
          }
        }
      }
    }
    const ticks: { pct: number; label: string }[] = [];
    for (let i = 0; i <= days; i += 7) {
      ticks.push({ pct: (i / days) * 100, label: new Date(min + i * DAY).toISOString().slice(5, 10) });
    }
    return { days, pct, rows, connectors, ticks, todayPct: pct(today) };
  }, [dated, msRow, details.data, msCount]);

  const hasData = view.rows.length > 0 || msCount > 0;

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-4">
      <Card className="min-w-[640px] p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-semibold">📅 时间线</span>
          <span className="text-xs text-mut">
            {dated.length} 个排期项 · {msCount} 个里程碑 · 红条/虚线 = 依赖冲突 · 拖动条形改期 / 拖右缘改截止（Esc 取消）
          </span>
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

          {/* concept rows */}
          {view.rows.map((row) => (
            <div key={row.cid} className="flex items-center border-t border-line/60" style={{ height: ROW_H }}>
              <div className="w-32 shrink-0 truncate pr-2 text-right text-xs text-mut" title={row.cid}>
                {conceptName(row.cid)}
              </div>
              <div className="relative h-full flex-1 mr-2">
                {row.list.map((d) => {
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
                    <div
                      key={d.item.id}
                      title={`${d.item.title} · ${d.item.status}${d.item.auto_scheduled ? " · ⏱ 自动排期" : ""}${d.conflict ? " · 依赖冲突：开始早于前置项完成" : ""}${dragging && drag ? ` → 改为 ${fmt(start)} ~ ${fmt(due)}` : ""}`}
                      onPointerDown={(e) => beginDrag(e, d, "move")}
                      onPointerMove={onDragMove}
                      onPointerUp={() => endDrag(false)}
                      onPointerCancel={() => endDrag(true)}
                      className={`absolute top-1/2 h-4 -translate-y-1/2 cursor-grab touch-none rounded-full active:cursor-grabbing ${tone} ${dragging ? "opacity-50" : ""}`}
                      style={{ left: `${left}%`, width: `${width}%` }}
                    >
                      <div
                        onPointerDown={(e) => beginDrag(e, d, "resize")}
                        title="拖动右缘改截止日"
                        className="absolute right-0 top-0 h-full w-1.5 cursor-ew-resize rounded-r-full bg-black/20 hover:bg-black/40"
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {/* dependency connectors (only conflict edges are drawn, per docs/01 §L.1) */}
          <svg className="pointer-events-none absolute inset-0 ml-32 h-full w-[calc(100%-8.5rem)]" aria-hidden>
            {view.connectors.map((c) => (
              <line key={c.key} x1={`${c.x1}%`} y1={c.y1} x2={`${c.x2}%`} y2={c.y2}
                    stroke="rgb(239 68 68)" strokeDasharray="4 3" strokeWidth="1.5" />
            ))}
          </svg>
        </div>

        {!hasData && (
          <Empty title="暂无排期数据" hint="给工作项设置起止日期（start_date/due_date）或创建里程碑后在此排布" />
        )}
      </Card>
    </div>
  );
}
