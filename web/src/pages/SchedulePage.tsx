/** Personal cross-project schedule (M29-I89, docs/01 §AB.1, OpenProject
 * calendar semantics): a month grid of my dated items across all visible
 * projects — drag a card onto a day to reschedule (single PATCH, span kept),
 * drag-select a day range to create a task prefilled with the dates. */
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import type { MyScheduleItem } from "../lib/api";
import { Card, cx } from "../components/ui";
import { Button } from "../components/ui";

const DAY = 86_400_000;
const iso = (d: Date) => d.toISOString().slice(0, 10);
const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

function weekStart(d: Date): Date {
  const utc = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const wd = (utc.getUTCDay() + 6) % 7;
  return new Date(utc.getTime() - wd * DAY);
}

const PROJECT_TINTS = ["bg-indigo-500", "bg-violet-500", "bg-emerald-500", "bg-amber-500", "bg-rose-500", "bg-sky-500"];

export function SchedulePage() {
  const qc = useQueryClient();
  const [anchor, setAnchor] = useState(() => new Date());
  const [dragOver, setDragOver] = useState<string | null>(null);
  // drag-select range for quick task creation
  const [rangeAnchor, setRangeAnchor] = useState<string | null>(null);
  const [rangeHover, setRangeHover] = useState<string | null>(null);
  const [createRange, setCreateRange] = useState<{ start: string; end: string } | null>(null);

  const schedule = useQuery({ queryKey: ["my-schedule"], queryFn: api.getMySchedule, refetchInterval: 15_000 });
  const items = schedule.data?.items ?? [];
  const today = schedule.data?.today ?? iso(new Date());

  const cells = useMemo(() => {
    const first = new Date(Date.UTC(anchor.getFullYear(), anchor.getMonth(), 1));
    const start = weekStart(new Date(first.getUTCFullYear(), first.getUTCMonth(), first.getUTCDate()));
    return Array.from({ length: 42 }, (_, i) => iso(new Date(start.getTime() + i * DAY)));
  }, [anchor]);

  const byDay = useMemo(() => {
    const m = new Map<string, MyScheduleItem[]>();
    for (const it of items) {
      // a multi-day item shows on every day it spans (OpenProject calendar)
      const s = it.start_date ?? it.due_date!;
      const e = it.due_date ?? it.start_date!;
      for (let t = new Date(s + "T00:00:00Z").getTime(); t <= new Date(e + "T00:00:00Z").getTime(); t += DAY) {
        const day = iso(new Date(t));
        (m.get(day) ?? m.set(day, []).get(day)!).push(it);
      }
    }
    return m;
  }, [items]);

  const tints = useMemo(() => {
    const m = new Map<string, string>();
    items.forEach((it) => { if (!m.has(it.project_id)) m.set(it.project_id, PROJECT_TINTS[m.size % PROJECT_TINTS.length]); });
    return m;
  }, [items]);

  const drop = async (target: string, raw: string) => {
    setDragOver(null);
    let payload: { id: string; start: string | null; due: string | null };
    try { payload = JSON.parse(raw); } catch { return; }
    const patch: Record<string, string> = {};
    if (payload.start) {
      const delta = Math.round((new Date(target + "T00:00:00Z").getTime()
        - new Date(payload.start + "T00:00:00Z").getTime()) / DAY);
      if (!delta) return;
      patch.start_date = target;
      if (payload.due) patch.due_date = iso(new Date(new Date(payload.due + "T00:00:00Z").getTime() + delta * DAY));
    } else if (payload.due) {
      if (target === payload.due) return;
      patch.due_date = target;
    } else return;
    try {
      await api.patchItem(payload.id, patch);
      toast.success(`已改期 → ${patch.start_date ?? ""}${patch.due_date ? ` ~ ${patch.due_date}` : ""}`);
      qc.invalidateQueries();
    } catch (e) {
      toast.error(`改期失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const rangeSel = (() => {
    if (!rangeAnchor || !rangeHover) return null;
    return [rangeAnchor, rangeHover].sort();
  })();

  return (
    <div className="flex h-full flex-col">
      <div className="no-print flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-sm font-semibold">📅 我的日程</span>
        <span className="text-xs text-mut">跨项目指派给我的有日期任务 · 拖卡片改期（工期保持）/ 拖选空白格建任务</span>
        <span className="ml-auto flex items-center gap-2 text-xs text-mut">
          <button onClick={() => setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1))}
            className="rounded-lg border border-line px-2 py-1 hover:border-acc">‹</button>
          <span className="font-medium">{anchor.getFullYear()} 年 {anchor.getMonth() + 1} 月</span>
          <button onClick={() => setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1))}
            className="rounded-lg border border-line px-2 py-1 hover:border-acc">›</button>
          <button onClick={() => setAnchor(new Date())} className="rounded-lg border border-line px-2 py-1 hover:border-acc">今天</button>
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <div className="grid grid-cols-7 gap-1">
          {WEEKDAYS.map((w) => (
            <div key={w} className="pb-1 text-center text-[10px] text-mut">周{w}</div>
          ))}
          {cells.map((day) => {
            const list = byDay.get(day) ?? [];
            const dim = new Date(day + "T00:00:00Z").getUTCMonth() !== anchor.getMonth();
            const inRange = rangeSel && day >= rangeSel[0] && day <= rangeSel[1];
            return (
              <div key={day}
                onMouseDown={(e) => { if (e.button === 0 && !list.length) { setRangeAnchor(day); setRangeHover(day); } }}
                onMouseEnter={() => { if (rangeAnchor) setRangeHover(day); }}
                onMouseUp={() => {
                  if (rangeAnchor && inRange) setCreateRange({ start: rangeSel![0], end: rangeSel![1] });
                  setRangeAnchor(null); setRangeHover(null);
                }}
                onDragOver={(e) => { e.preventDefault(); setDragOver(day); }}
                onDragLeave={() => setDragOver((d) => (d === day ? null : d))}
                onDrop={(e) => {
                  e.preventDefault();
                  const raw = e.dataTransfer.getData("text/plain");
                  if (raw) drop(day, raw);
                }}
                className={cx("min-h-24 rounded-lg border p-1 transition-colors",
                  dim ? "border-line/50 opacity-45" : "border-line",
                  day === today && "border-acc",
                  dragOver === day && "border-acc bg-accbg/40",
                  inRange && "bg-accbg/60 border-acc")}>
                <div className={cx("px-0.5 text-[10px]", day === today ? "font-semibold text-acc" : "text-mut")}>
                  {new Date(day + "T00:00:00Z").getUTCDate()}
                </div>
                <div className="mt-0.5 space-y-0.5">
                  {list.slice(0, 4).map((it) => (
                    <div key={it.id + day} draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData("text/plain",
                          JSON.stringify({ id: it.id, start: it.start_date, due: it.due_date }));
                        setRangeAnchor(null);
                      }}
                      title={`${it.project_name} · ${it.title}${it.status_group === "done" ? " · 已完成" : ""}`}
                      className={cx("flex cursor-grab items-center gap-1 rounded px-1 py-0.5 text-[10px] leading-3",
                        it.status_group === "done" ? "opacity-50 line-through" : "hover:bg-accbg",
                        "bg-bg border border-line/60")}>
                      <span className={cx("h-1.5 w-1.5 shrink-0 rounded-full", tints.get(it.project_id) ?? "bg-acc")} />
                      <span className="truncate">{it.title}</span>
                    </div>
                  ))}
                  {list.length > 4 && <div className="px-1 text-[9px] text-mut">+{list.length - 4} 更多</div>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {createRange && (
        <CreateModal range={createRange}
          onClose={() => setCreateRange(null)}
          onCreated={() => { setCreateRange(null); qc.invalidateQueries(); }} />
      )}
    </div>
  );
}

function CreateModal({ range, onClose, onCreated }: {
  range: { start: string; end: string };
  onClose: () => void; onCreated: () => void;
}) {
  const [pid, setPid] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const work = useQuery({ queryKey: ["my-work"], queryFn: api.getMyWork });
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const projects = work.data?.projects ?? [];
  const ontology = useQuery({
    queryKey: ["ontology", pid],
    queryFn: () => api.getOntology(pid, true),
    enabled: !!pid,
  });
  const concepts = (ontology.data?.concepts ?? []).filter((c) => c.id !== "milestone");
  const concept = concepts.find((c) => c.id === "task") ?? concepts[0];

  const submit = async () => {
    if (!pid || !concept || !title.trim()) { toast.error("选项目、概念并填写标题"); return; }
    setBusy(true);
    try {
      await api.createItem(pid, {
        concept_id: concept.id, title: title.trim(),
        start_date: range.start, due_date: range.end,
        assignee_type: "human", assignee_id: users.data?.current,
      });
      toast.success(`已创建并指派给自己：${range.start} ~ ${range.end}`);
      onCreated();
    } catch (e) {
      toast.error(`创建失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-6" onClick={onClose}>
      <Card className="mt-16 w-full max-w-md p-4" onClick={(e) => e.stopPropagation()}>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold">🆕 新任务 · {range.start}{range.end !== range.start ? ` ~ ${range.end}` : ""}</span>
          <button onClick={onClose} className="text-xs text-mut hover:text-ink">✕</button>
        </div>
        <div className="space-y-2 text-xs">
          <select value={pid} onChange={(e) => setPid(e.target.value)}
            className="w-full rounded-lg border border-line bg-bg px-2 py-1.5">
            <option value="">选择项目…</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <select value={concept?.id ?? ""} onChange={() => undefined} disabled={!pid}
            className="w-full rounded-lg border border-line bg-bg px-2 py-1.5 disabled:opacity-50">
            {concept ? <option value={concept.id}>{concept.name}</option> : <option value="">（选项目后出现概念）</option>}
          </select>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="任务标题"
            className="w-full rounded-lg border border-line bg-bg px-2 py-1.5" />
          <div className="flex items-center justify-between pt-1">
            <span className="text-[10px] text-mut">创建后自动指派给你，起止日期为所选范围</span>
            <Button size="sm" variant="primary" disabled={busy} onClick={submit}>创建</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
