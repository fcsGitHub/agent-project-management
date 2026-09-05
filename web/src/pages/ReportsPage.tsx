/** Reports page (M12-I39): funnel, pending gates, overdue/stale list and
 * throughput sparkline — read-only widgets over the pure projection report
 * API (docs/01 §K.1: OpenProject-style widget dashboards, zero ETL). */
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Card, Empty, PrintButton } from "../components/ui";

const BUCKET_LABEL: Record<string, string> = {
  backlog: "待办池", todo: "就绪", in_progress: "进行中", done: "已完成", cancelled: "已取消",
};
const BUCKET_ORDER = ["backlog", "todo", "in_progress", "done", "cancelled"];

export function ReportsPage() {
  const { pid } = useParams();
  const report = useQuery({
    queryKey: ["report", pid],
    queryFn: () => api.getProjectReport(pid!),
    enabled: !!pid,
    refetchInterval: 15_000,
  });
  const hist = useQuery({
    queryKey: ["health-history", pid],
    queryFn: () => api.getHealthHistory(pid!),
    enabled: !!pid,
    refetchInterval: 30_000,
  });
  if (!pid) return null;
  const r = report.data;
  const maxBucket = r ? Math.max(1, ...BUCKET_ORDER.map((b) => r.funnel[b] ?? 0)) : 1;
  const maxDay = r ? Math.max(1, ...r.throughput.series.map((d) => Math.max(d.created, d.done))) : 1;

  return (
    <div className="grid grid-cols-1 gap-4 overflow-y-auto p-4 md:grid-cols-3">
      {/* funnel */}
      <Card className="p-4 md:col-span-2">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-semibold">阶段漏斗</span>
          <span className="flex items-center gap-2">
            <PrintButton />
            <span className="text-xs text-mut">按五桶状态机计数 · 实时投影</span>
          </span>
        </div>
        <div className="space-y-2">
          {BUCKET_ORDER.map((b) => {
            const n = r?.funnel[b] ?? 0;
            return (
              <div key={b} className="flex items-center gap-2 text-xs">
                <span className="w-14 shrink-0 text-mut">{BUCKET_LABEL[b]}</span>
                <div className="h-4 flex-1 overflow-hidden rounded bg-bg">
                  <div
                    className={`h-full rounded ${b === "done" ? "bg-ag" : b === "cancelled" ? "bg-line" : "bg-acc"}`}
                    style={{ width: `${(n / maxBucket) * 100}%` }}
                  />
                </div>
                <span className="w-8 shrink-0 text-right font-mono">{n}</span>
              </div>
            );
          })}
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {Object.entries(r?.concepts ?? {}).map(([c, n]) => (
            <Badge key={c} tone="neutral">{c} × {n}</Badge>
          ))}
          {!r && <span className="text-xs text-mut">加载中…</span>}
        </div>
      </Card>

      {/* pending gates */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">◆ 挂起 Gate</span>
          <Link to={`/p/${pid}/approvals`} className="text-xs text-acc hover:underline">审批中心 →</Link>
        </div>
        <div className="mt-3 space-y-2">
          {(r?.gates_pending ?? []).map((g) => (
            <Link
              key={g.id}
              to={`/p/${pid}/approvals`}
              className="block rounded-lg border border-line px-3 py-2 text-xs hover:border-acc"
            >
              <div className="font-medium">{g.kind === "gate" ? `◆ ${g.payload_snapshot?.gate ?? "阶段门"}` : `⚠ ${g.payload_snapshot?.tool ?? "工件审批"}`}</div>
              <div className="mt-0.5 text-mut">
                {g.payload_snapshot?.summary ?? ""}{g.requested_at ? ` · 等待中` : ""}
              </div>
            </Link>
          ))}
          {!r?.gates_pending.length && (
            <Empty title="无挂起审批" hint="阶段门与工件审批会出现在这里" />
          )}
        </div>
      </Card>

      {/* overdue / stale */}
      <Card className="p-4 md:col-span-2">
        <div className="mb-2 text-sm font-semibold">
          ⏰ 超期与滞留
          <span className="ml-2 text-xs font-normal text-mut">due 已过或活跃超 14 天 · 已完成不参与</span>
        </div>
        <div className="space-y-1.5">
          {(r?.overdue ?? []).map((it) => (
            <div key={it.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-xs">
              <span className="flex-1 truncate font-medium">{it.title}</span>
              <Badge tone="amber">{it.reason}</Badge>
            </div>
          ))}
          {!r?.overdue.length && <Empty title="没有超期或滞留项" hint="保持节奏 ✓" />}
        </div>
      </Card>

      {/* throughput */}
      <Card className="col-span-1 p-4">
        <div className="mb-1 text-sm font-semibold">吞吐 · 近 14 天</div>
        <div className="text-xs text-mut">新建 {r?.throughput.created_total ?? 0} · 完成 {r?.throughput.done_total ?? 0}</div>
        <div className="mt-3 flex h-28 items-end gap-1">
          {(r?.throughput.series ?? []).map((d) => (
            <div key={d.date} className="flex flex-1 flex-col items-center gap-0.5" title={`${d.date} 新建${d.created} 完成${d.done}`}>
              <div className="flex h-24 w-full items-end justify-center gap-px">
                <div className="w-1/2 rounded-t bg-acc" style={{ height: `${(d.created / maxDay) * 100}%`, minHeight: d.created ? 2 : 0 }} />
                <div className="w-1/2 rounded-t bg-ag" style={{ height: `${(d.done / maxDay) * 100}%`, minHeight: d.done ? 2 : 0 }} />
              </div>
            </div>
          ))}
          {!r && <span className="text-xs text-mut">加载中…</span>}
        </div>
        <div className="mt-1 flex justify-center gap-3 text-[10px] text-mut">
          <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-acc" />新建</span>
          <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-ag" />完成</span>
        </div>
      </Card>

      {/* timelog (M19-I61): per-user totals + per-day trend */}
      <TimelogCard pid={pid} />

      {/* burndown (M27-I85): event-replayed remaining curve vs ideal line */}
      <BurndownCard pid={pid} />

      {/* health trend (M30-I93): replayed score series */}
      <HealthCard hist={hist.data} />

      {/* responsiveness (M31-I97): approval latency + comment first response */}
      <ResponsivenessCard pid={pid} />
    </div>
  );
}

function HealthCard({ hist }: { hist?: { series: { date: string; score: number | null; active: number; overdue: number; gates: number }[] } | null }) {
  const series = hist?.series ?? [];
  const pts = series.filter((p) => p.score != null);
  const cur = pts.length ? pts[pts.length - 1] : null;
  const score = cur?.score ?? null;

  const line = (() => {
    if (pts.length < 2) return null;
    const coords = pts.map((p, i) => `${(i / (pts.length - 1)) * 100},${(3 + (1 - p.score! / 100) * 37).toFixed(1)}`);
    return { polyline: coords.join(" "), last: coords[coords.length - 1] };
  })();

  return (
    <Card className="p-4 md:col-span-2">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold">💚 健康趋势</span>
        {score != null && (
          <Badge tone={score >= 80 ? "green" : score >= 60 ? "amber" : "red"}>
            当前 {score >= 80 ? "♥" : score >= 60 ? "♥" : "♥"} {score}
          </Badge>
        )}
      </div>
      {line ? (
        <>
          <div className="text-xs text-mut">
            事件重放 {series.filter((p) => p.active > 0).length} 个周界 · 当前活跃 {cur?.active} ·
            超期 {cur?.overdue} · Gate 挂起 {cur?.gates}
          </div>
          <svg viewBox="0 0 100 43" className="mt-2 h-28 w-full" preserveAspectRatio="none">
            <polyline points={line.polyline} fill="none" stroke="currentColor"
              className="text-ag" strokeWidth="1" />
            <circle cx={line.last.split(",")[0]} cy={line.last.split(",")[1]} r="1.2" className="fill-ag" />
          </svg>
          <div className="mt-1 text-center text-[10px] text-mut">
            超期率 40% · 滞留率 20% · 吞吐动量 30% · Gate 挂起 10%（每 5 天一采样，事件重放）
          </div>
        </>
      ) : (
        <Empty title="暂无趋势数据" hint="项目有了活跃工作项后，这里会重放出评分趋势线" />
      )}
    </Card>
  );
}

const DAY_MS = 86_400_000;

type RespSlice = { count: number; avg_h: number; median_h: number; over_48h: number };

/** I97 (docs/01 §AD.3, CHAOSS Time to First Response): approval decision
 *  latency + comment first-response, honest None when the window is empty. */
function ResponsivenessCard({ pid }: { pid: string }) {
  const resp = useQuery({
    queryKey: ["responsiveness", pid],
    queryFn: () => api.getResponsiveness(pid),
    refetchInterval: 30_000,
  });
  const d = resp.data;
  const slice = (s: RespSlice | null) =>
    s ? `${s.count} 次 · 平均 ${s.avg_h}h · 中位 ${s.median_h}h · 超 48h 占 ${(s.over_48h * 100).toFixed(0)}%` : null;
  const a = slice(d?.approvals ?? null);
  const c = slice(d?.comments ?? null);
  return (
    <Card className="p-4">
      <div className="mb-2 text-sm font-semibold">⏱ 响应力</div>
      <div className="space-y-2 text-xs">
        <div className="rounded-lg border border-line px-3 py-2">
          <div className="font-medium">Gate 审批响应</div>
          <div className="mt-0.5 text-mut">{a ?? "窗口内暂无已决审批——诚实空态，不编数字"}</div>
        </div>
        <div className="rounded-lg border border-line px-3 py-2">
          <div className="font-medium">评论首响应</div>
          <div className="mt-0.5 text-mut">
            {c ?? "窗口内暂无被回复的评论"}
            {d != null && d.comments_unanswered > 0 && ` · 待响应 ${d.comments_unanswered}`}
          </div>
        </div>
      </div>
      <div className="mt-2 text-[10px] text-mut">
        审批读投影 requested→decided；首响应 = 下一非作者评论或状态变更（事件流重放，作者自评不计）
      </div>
    </Card>
  );
}

function BurndownCard({ pid }: { pid: string }) {
  const ms = useQuery({
    queryKey: ["milestones", pid],
    queryFn: () => api.listMilestones(pid),
    enabled: !!pid,
  });
  const [mid, setMid] = useState("");
  const list = ms.data?.milestones ?? [];
  const selected = mid || list[0]?.id || "";
  const bd = useQuery({
    queryKey: ["burndown", selected],
    queryFn: () => api.getMilestoneBurndown(selected),
    enabled: !!selected,
  });

  const d = bd.data;
  // x normalizes every date onto the created→due window so actual and ideal
  // lines share one scale; y maps remaining onto the 40-unit SVG height
  const view = (() => {
    if (!d || !d.total) return null;
    const t0 = d.series[0]?.date ?? d.ideal[0]?.date;
    if (!t0) return null;
    const start = new Date(t0 + "T00:00:00Z").getTime();
    const end = new Date(d.due_date + "T00:00:00Z").getTime();
    const window = Math.max(end - start, DAY_MS);
    const x = (date: string) => ((new Date(date + "T00:00:00Z").getTime() - start) / window) * 100;
    const y = (n: number) => 3 + (1 - n / d.total) * 37;
    const pts = (arr: { date: string; remaining: number }[]) =>
      arr.map((p) => `${x(p.date).toFixed(2)},${y(p.remaining).toFixed(2)}`).join(" ");
    const today = new Date().toISOString().slice(0, 10);
    return { x, y, actual: pts(d.series), ideal: pts(d.ideal), todayPct: x(today) };
  })();

  return (
    <Card className="p-4 md:col-span-2">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold">🔥 燃尽</span>
        <select value={selected} onChange={(e) => setMid(e.target.value)}
          className="rounded-lg border border-line bg-bg px-2 py-1 text-xs text-ink">
          {list.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
          {!list.length && <option value="">（无里程碑）</option>}
        </select>
      </div>
      {d && view ? (
        <>
          <div className="text-xs text-mut">
            关联 {d.total} 项 · 剩余 <span className="font-medium text-acc">{d.remaining}</span> ·
            近 {d.velocity.days} 天完成 {d.velocity.done} 项 ·
            {d.remaining <= 0 ? " 已清零 ✓" : ` 截止 ${d.due_date}`}
          </div>
          <svg viewBox="0 0 100 43" className="mt-2 h-36 w-full" preserveAspectRatio="none">
            {view.todayPct >= 0 && view.todayPct <= 100 && (
              <line x1={view.todayPct} y1="0" x2={view.todayPct} y2="42"
                stroke="currentColor" className="text-acc/50" strokeWidth="0.4" strokeDasharray="2 1.5" />
            )}
            <polyline points={view.ideal} fill="none" stroke="currentColor"
              className="text-mut/60" strokeWidth="0.6" strokeDasharray="2 2" />
            <polyline points={view.actual} fill="none" stroke="currentColor"
              className="text-acc" strokeWidth="1" />
          </svg>
          <div className="mt-1 flex justify-center gap-3 text-[10px] text-mut">
            <span><i className="mr-1 inline-block h-0.5 w-3 bg-acc align-middle" />实际剩余</span>
            <span><i className="mr-1 inline-block h-0.5 w-3 border-b border-dashed border-mut align-middle" />理想线（建→截止）</span>
            <span><i className="mr-1 inline-block h-2 w-0 border-l border-dashed border-acc align-middle" />今天</span>
          </div>
        </>
      ) : (
        <Empty
          title={list.length ? "暂无关联项" : "暂无里程碑"}
          hint={list.length ? "给里程碑关联任务后，这里按事件重放出剩余曲线" : "先在项目里创建里程碑"}
        />
      )}
    </Card>
  );
}

function TimelogCard({ pid }: { pid: string }) {
  const tl = useQuery({
    queryKey: ["timelog-report", pid],
    queryFn: () => api.getTimelogReport(pid),
    enabled: !!pid,
    refetchInterval: 15_000,
  });
  const t = tl.data;
  const total = t?.total_minutes ?? 0;
  const fmt = (m: number) => (m < 60 ? `${m}m` : `${Math.floor(m / 60)}h${m % 60 ? (m % 60).toString().padStart(2, "0") : ""}`);
  const maxUser = t ? Math.max(1, ...t.by_user.map((u) => u.minutes)) : 1;
  const maxDay = t ? Math.max(1, ...t.by_day.map((d) => d.minutes)) : 1;
  return (
    <Card className="p-4 md:col-span-3">
      <div className="mb-1 flex items-baseline justify-between">
        <div className="text-sm font-semibold">⏱ 工时 · 近 {t?.window_days ?? 14} 天</div>
        <div className="text-xs text-mut">合计 <span className="font-medium text-acc">{fmt(total)}</span></div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <div className="mb-1 text-[10px] text-mut">按人</div>
          <div className="space-y-1.5">
            {(t?.by_user ?? []).map((u) => (
              <div key={u.user_id} className="flex items-center gap-2 text-xs" title={u.user_name ?? u.user_id}>
                <span className="w-16 shrink-0 truncate">{u.user_name ?? u.user_id}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-bg">
                  <div className="h-full rounded-full bg-acc" style={{ width: `${(u.minutes / maxUser) * 100}%` }} />
                </div>
                <span className="w-12 shrink-0 text-right font-medium">{fmt(u.minutes)}</span>
              </div>
            ))}
            {!t?.by_user.length && <div className="text-xs text-mut">还没有工时记录——在看板卡片点 ⏱ 记一笔</div>}
          </div>
        </div>
        <div>
          <div className="mb-1 text-[10px] text-mut">按日</div>
          <div className="flex h-20 items-end gap-1">
            {(t?.by_day ?? []).map((d) => (
              <div key={d.date} className="flex flex-1 flex-col items-center" title={`${d.date} ${fmt(d.minutes)}`}>
                <div className="w-full rounded-t bg-ag" style={{ height: `${(d.minutes / maxDay) * 100}%`, minHeight: d.minutes ? 2 : 0 }} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
