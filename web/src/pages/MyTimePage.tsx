/** Personal time-tracking calendar (M20-I62, docs/01 §S.1, OpenProject 16.0
 * "My time tracking"): week/month grids of my own entries with daily totals;
 * click a day to quick-log (form semantics mirror TimeLogModal, spent_on
 * prefilled). Pure views over GET /my/timelog — no new events.
 * M28-I86: timesheet submission/approval panel (period submit → owner decides
 * → approved periods freeze writes). */
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import type { TimeEntry, Timesheet } from "../lib/api";
import { Card, Empty } from "../components/ui";
import { fmtMinutes } from "../components/TimeLogModal";
import { cx } from "../components/ui";

const DAY = 86_400_000;
const iso = (d: Date) => d.toISOString().slice(0, 10);
const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

/** Monday-based start of the week containing d (UTC arithmetic keeps ISO
 * dates stable across timezones — entries are plain YYYY-MM-DD strings). */
function weekStart(d: Date): Date {
  const utc = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const wd = (utc.getUTCDay() + 6) % 7;
  return new Date(utc.getTime() - wd * DAY);
}

export function MyTimePage() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<"week" | "month">("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [openDay, setOpenDay] = useState<string | null>(null);

  const feed = useQuery({
    queryKey: ["my-timelog"],
    queryFn: () => api.getMyTimelog(60),
    refetchInterval: 15_000,
  });
  const work = useQuery({ queryKey: ["my-work"], queryFn: api.getMyWork });

  const byDay = useMemo(() => {
    const m = new Map<string, { total: number; entries: NonNullable<typeof feed.data>["days"][number]["entries"] }>();
    for (const d of feed.data?.days ?? []) m.set(d.date, { total: d.total_minutes, entries: d.entries });
    return m;
  }, [feed.data]);

  const cells = useMemo(() => {
    if (mode === "week") {
      const start = weekStart(anchor);
      return Array.from({ length: 7 }, (_, i) => new Date(start.getTime() + i * DAY));
    }
    const first = new Date(Date.UTC(anchor.getFullYear(), anchor.getMonth(), 1));
    const start = weekStart(new Date(first.getUTCFullYear(), first.getUTCMonth(), first.getUTCDate()));
    return Array.from({ length: 42 }, (_, i) => new Date(start.getTime() + i * DAY));
  }, [mode, anchor]);

  const anchorMonth = Date.UTC(anchor.getFullYear(), anchor.getMonth(), 1);
  const todayIso = iso(new Date());
  const shift = (dir: number) => {
    const a = new Date(anchor);
    if (mode === "week") setAnchor(new Date(a.getTime() + dir * 7 * DAY));
    else setAnchor(new Date(Date.UTC(a.getFullYear(), a.getMonth() + dir, 1)));
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-sm font-semibold">⏱ 我的工时</span>
        <span className="text-xs text-mut">个人记时日历 · 近 60 天 · 点日期格快捷记时</span>
        <span className="ml-auto flex items-center gap-2 text-xs text-mut">
          <span className="rounded bg-accbg px-1.5 py-0.5 font-medium text-acc">
            窗口合计 {fmtMinutes(feed.data?.total_minutes ?? 0)}
          </span>
          <button onClick={() => setMode(mode === "week" ? "month" : "week")}
            className="rounded-lg border border-line px-2 py-1 hover:border-acc">
            {mode === "week" ? "月视图" : "周视图"}
          </button>
          <button onClick={() => shift(-1)} className="rounded-lg border border-line px-2 py-1 hover:border-acc">‹</button>
          <button onClick={() => setAnchor(new Date())} className="rounded-lg border border-line px-2 py-1 hover:border-acc">今天</button>
          <button onClick={() => shift(1)} className="rounded-lg border border-line px-2 py-1 hover:border-acc">›</button>
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="mb-2 text-xs text-mut">
          {anchor.getFullYear()} 年 {anchor.getMonth() + 1} 月{mode === "week" && " · 本周"}
        </div>
        <div className="grid grid-cols-7 gap-1.5">
          {WEEKDAYS.map((w) => (
            <div key={w} className="pb-1 text-center text-[10px] text-mut">周{w}</div>
          ))}
          {cells.map((d) => {
            const key = iso(d);
            const day = byDay.get(key);
            const dim = mode === "month" && Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) !== anchorMonth;
            const isToday = key === todayIso;
            return (
              <button key={key} onClick={() => setOpenDay(key)}
                className={cx("flex min-h-24 flex-col rounded-xl border p-1.5 text-left transition-colors hover:border-acc",
                  dim ? "border-line/50 opacity-45" : "border-line",
                  isToday && "border-acc")}>
                <div className="flex items-center justify-between">
                  <span className={cx("text-[10px]", isToday ? "font-semibold text-acc" : "text-mut")}>
                    {d.getUTCDate()}
                  </span>
                  {!!day?.total && (
                    <span className="rounded bg-accbg px-1 text-[10px] font-medium text-acc">{fmtMinutes(day.total)}</span>
                  )}
                </div>
                <div className="mt-1 space-y-1 overflow-hidden">
                  {(day?.entries ?? []).slice(0, 3).map((t) => (
                    <div key={t.id} className="truncate rounded bg-bg px-1 py-0.5 text-[10px]" title={`${t.item_title ?? t.item_id} · ${fmtMinutes(t.minutes)}${t.note ? ` · ${t.note}` : ""}`}>
                      {t.item_title ?? t.item_id} <span className="text-acc">{fmtMinutes(t.minutes)}</span>
                    </div>
                  ))}
                  {(day?.entries.length ?? 0) > 3 && (
                    <div className="text-[10px] text-mut">+{day!.entries.length - 3} 更多</div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
        {!feed.data?.days.length && (
          <Empty title="近 60 天还没有记时" hint="打开工作项的 ⏱ 抽屉，或点上面任意日期格快捷记时" />
        )}
      </div>
      {openDay && (
        <DayLogModal day={openDay}
          items={(work.data?.items ?? []).map((it) => ({ id: it.id, label: `${it.project_name ?? ""} · ${it.title}` }))}
          entries={byDay.get(openDay)?.entries ?? []}
          onClose={() => setOpenDay(null)}
          onChanged={() => qc.invalidateQueries()} />
      )}
      <TimesheetPanel />
    </div>
  );
}

const TS_TONE: Record<Timesheet["status"], string> = {
  submitted: "bg-warnbg text-warn",
  approved: "bg-okbg text-ok",
  rejected: "bg-danbg text-dan",
};
const TS_LABEL: Record<Timesheet["status"], string> = {
  submitted: "待审批",
  approved: "已批准·已锁定",
  rejected: "已驳回",
};

function TimesheetPanel() {
  const qc = useQueryClient();
  const [start, setStart] = useState(() => iso(weekStart(new Date())));
  const [end, setEnd] = useState(() => iso(new Date()));
  const [pid, setPid] = useState("");
  const mine = useQuery({ queryKey: ["my-timesheets"], queryFn: api.myTimesheets, refetchInterval: 15_000 });
  const feed = useQuery({ queryKey: ["my-timelog"], queryFn: () => api.getMyTimelog(60), refetchInterval: 15_000 });

  // projects I have logged time in → submission candidates (shared cache with
  // the calendar grid above: same query key, no extra round trip)
  const projects = useMemo(() => {
    const m = new Map<string, string>();
    for (const d of feed.data?.days ?? [])
      for (const e of d.entries)
        if (e.project_id) m.set(e.project_id, e.project_name ?? e.project_id);
    return [...m.entries()].map(([id, name]) => ({ id, name }));
  }, [feed.data]);

  // pending approvals across projects where I can decide (owner/admin);
  // Promise.all 并行拉取（原串行瀑布随 15s 轮询反复执行）
  const approvals = useQuery({
    queryKey: ["ts-approvals"],
    queryFn: async () => {
      const pids = [...new Set((mine.data?.timesheets ?? []).map((t) => t.project_id))];
      const results = await Promise.all(pids.map(async (p) => {
        try {
          return await api.listTimesheets(p);
        } catch { return null; } // viewer on a project — skip
      }));
      const out: { row: Timesheet; can: boolean }[] = [];
      for (const r of results) {
        if (!r) continue;
        for (const row of r.timesheets) out.push({ row, can: r.can_approve });
      }
      return out;
    },
    enabled: (mine.data?.timesheets.length ?? 0) > 0,
  });
  const pending = (approvals.data ?? []).filter((x) => x.row.status === "submitted");

  const submit = async () => {
    if (!pid) { toast.error("先选择项目"); return; }
    if (start > end) { toast.error("期间起止颠倒"); return; }
    try {
      await api.submitTimesheet({ project_id: pid, period_start: start, period_end: end });
      toast.success("已提交审批");
      qc.invalidateQueries();
    } catch (e) {
      toast.error(`提交失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const decide = async (id: string, ok: boolean) => {
    try {
      if (ok) await api.approveTimesheet(id);
      else {
        const reason = window.prompt("驳回原因（会展示给提交人）") ?? "";
        await api.rejectTimesheet(id, reason);
      }
      toast.success(ok ? "已批准，该期间工时已锁定" : "已驳回");
      qc.invalidateQueries();
    } catch (e) {
      toast.error(`操作失败：${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <Card className="mx-4 mb-4 p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold">🧾 工时审批</span>
        <span className="text-[10px] text-mut">Redmine 计薪语义：批准后期间锁定，记时/修改/删除被拒</span>
      </div>
      <div className="flex flex-wrap items-end gap-2 text-xs">
        <label className="text-[10px] text-mut">
          期间起
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
            className="mt-0.5 block rounded-lg border border-line bg-bg px-2 py-1 text-xs text-ink" />
        </label>
        <label className="text-[10px] text-mut">
          期间止
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
            className="mt-0.5 block rounded-lg border border-line bg-bg px-2 py-1 text-xs text-ink" />
        </label>
        <label className="text-[10px] text-mut">
          项目
          <select value={pid} onChange={(e) => setPid(e.target.value)}
            className="mt-0.5 block rounded-lg border border-line bg-bg px-2 py-1 text-xs text-ink">
            <option value="">选择有记时的项目…</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <button onClick={submit}
          className="rounded-lg bg-acc px-3 py-1.5 font-medium text-accbg hover:opacity-90">提交审批</button>
      </div>
      {!!mine.data?.timesheets.length && (
        <div className="mt-3 space-y-1">
          <div className="text-[10px] text-mut">我的提交</div>
          {mine.data.timesheets.slice(0, 6).map((t) => (
            <div key={t.id} className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-xs">
              <span className="w-28 shrink-0 truncate">{t.project_name ?? t.project_id}</span>
              <span className="text-mut">{t.period_start} ~ {t.period_end}</span>
              <span className="rounded bg-accbg px-1 font-medium text-acc">{fmtMinutes(t.total_minutes)}</span>
              <span className="text-mut">{t.entry_count} 笔</span>
              <span className={cx("ml-auto rounded px-1.5 py-0.5 text-[10px] font-medium", TS_TONE[t.status])}>
                {TS_LABEL[t.status]}{t.status === "rejected" && t.reason ? ` · ${t.reason}` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
      {!!pending.length && (
        <div className="mt-3 space-y-1">
          <div className="text-[10px] text-mut">待我审批</div>
          {pending.map(({ row, can }) => (
            <div key={row.id} className="flex items-center gap-2 rounded-lg border border-amber-500/40 px-2.5 py-1.5 text-xs">
              <span className="w-28 shrink-0 truncate">{row.user_name ?? row.user_id}</span>
              <span className="w-28 shrink-0 truncate text-mut">{row.project_name ?? row.project_id}</span>
              <span className="text-mut">{row.period_start} ~ {row.period_end}</span>
              <span className="rounded bg-accbg px-1 font-medium text-acc">{fmtMinutes(row.total_minutes)}</span>
              {can ? (
                <span className="ml-auto flex gap-1.5">
                  <button onClick={() => decide(row.id, true)}
                    className="rounded-lg bg-ok px-2 py-1 text-[10px] font-medium text-white">✓ 批准</button>
                  <button onClick={() => decide(row.id, false)}
                    className="rounded-lg border border-line px-2 py-1 text-[10px] hover:border-dan hover:text-dan">✕ 驳回</button>
                </span>
              ) : <span className="ml-auto text-[10px] text-mut">无审批权</span>}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function DayLogModal({ day, items, entries, onClose, onChanged }: {
  day: string;
  items: { id: string; label: string }[];
  entries: (TimeEntry & { item_title?: string | null })[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const [itemId, setItemId] = useState(items[0]?.id ?? "");
  const [minutes, setMinutes] = useState("60");
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState<TimeEntry | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const m = parseInt(minutes, 10);
    if (!m || m <= 0) { toast.error("时长须为正整数分钟"); return; }
    if (!editing && !itemId) { toast.error("先在「我的工作」被指派工作项，或从工作项卡片 ⏱ 记时"); return; }
    setBusy(true);
    try {
      if (editing) await api.editTimeEntry(editing.id, { minutes: m, note: note.trim() });
      else await api.logTime(itemId, { minutes: m, spent_on: day, note: note.trim() });
      toast.success(editing ? "已更新" : "已记时");
      setEditing(null); setNote(""); setMinutes("60");
      onChanged();
    } catch (e) {
      toast.error(`失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteTimeEntry(id);
      if (editing?.id === id) setEditing(null);
      onChanged();
    } catch (e) {
      toast.error(`删除失败：${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <Card className="fixed inset-x-4 top-16 z-50 mx-auto max-w-md p-4 shadow-xl">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold">⏱ {day}{editing ? " · 编辑条目" : ""}</span>
        <button onClick={() => { setEditing(null); onClose(); }} className="text-xs text-mut hover:text-ink">✕</button>
      </div>
      <div className="max-h-56 space-y-1.5 overflow-y-auto">
        {entries.map((t) => (
          <div key={t.id} className={cx("group flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-xs",
            editing?.id === t.id && "border-acc")}>
            <button className="flex-1 truncate text-left" title="点击编辑"
              onClick={() => { setEditing(t); setMinutes(String(t.minutes)); setNote(t.note); }}>
              <span className="font-medium">{t.item_title ?? t.item_id}</span>
              <span className="ml-1.5 rounded bg-accbg px-1 font-medium text-acc">{fmtMinutes(t.minutes)}</span>
              {t.note && <span className="ml-1.5 text-mut">{t.note}</span>}
            </button>
            <button onClick={() => remove(t.id)} className="text-[10px] text-mut opacity-0 hover:text-dan group-hover:opacity-100">✕</button>
          </div>
        ))}
        {!entries.length && <div className="py-4 text-center text-xs text-mut">这一天还没有记录</div>}
      </div>
      <div className="mt-3 space-y-2">
        {!editing && (
          <select value={itemId} onChange={(e) => setItemId(e.target.value)}
            className="w-full rounded-lg border border-line bg-bg px-2 py-1.5 text-xs">
            {items.length
              ? items.map((it) => <option key={it.id} value={it.id}>{it.label}</option>)
              : <option value="">（分配给我的工作项为空）</option>}
          </select>
        )}
        <div className="grid grid-cols-[1fr_2fr] gap-2">
          <label className="text-[10px] text-mut">
            分钟
            <input type="number" min={1} max={1440} value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              className="mt-0.5 w-full rounded-lg border border-line bg-bg px-2 py-1.5 text-xs text-ink" />
          </label>
          <div className="flex items-end gap-2">
            <button onClick={submit} disabled={busy}
              className="flex-1 rounded-lg bg-acc px-3 py-1.5 text-xs font-medium text-accbg disabled:opacity-50">
              {editing ? "保存修改" : "记到这天"}
            </button>
            {editing && (
              <button onClick={() => { setEditing(null); setNote(""); }}
                className="rounded-lg border border-line px-3 py-1.5 text-xs">取消</button>
            )}
          </div>
        </div>
        <textarea rows={2} placeholder="备注（做了什么）" value={note}
          onChange={(e) => setNote(e.target.value)}
          className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-xs" />
        <div className="text-[10px] text-mut">编辑仅改时长与备注（改日期请在工作项 ⏱ 抽屉操作）；删除按条目 ✕</div>
      </div>
    </Card>
  );
}
