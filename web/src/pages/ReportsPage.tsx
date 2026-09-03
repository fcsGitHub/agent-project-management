/** Reports page (M12-I39): funnel, pending gates, overdue/stale list and
 * throughput sparkline — read-only widgets over the pure projection report
 * API (docs/01 §K.1: OpenProject-style widget dashboards, zero ETL). */
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Card, Empty } from "../components/ui";

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
          <span className="text-xs text-mut">按五桶状态机计数 · 实时投影</span>
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
    </div>
  );
}
