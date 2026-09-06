/** Cross-project member workload (M28-I87, docs/01 §AA.2): one row per
 * assignee across every project the caller can see — active items, overdue,
 * 7-day logged time and per-project distribution chips (OpenProject resource
 * planner slice, read-only; the drag-to-plan team calendar stays in backlog). */
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { MemberWorkload } from "../lib/api";
import { Card, Empty } from "../components/ui";
import { fmtMinutes } from "../components/TimeLogModal";
import { cx } from "../components/ui";

export function WorkloadPage() {
  const wl = useQuery({ queryKey: ["workload"], queryFn: api.portfolioWorkload, refetchInterval: 15_000 });
  const members = wl.data?.members ?? [];
  const maxActive = Math.max(1, ...members.map((m) => m.active));

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 md:p-6">
      <div>
        <h1 className="text-lg font-semibold">👥 成员负载</h1>
        <p className="mt-0.5 text-xs text-mut">
          全部可见项目的成员横切——活跃项/超期/近 7 天工时（对调用方可见性裁剪，不可见项目的工时不会计入）
        </p>
      </div>
      {!wl.isLoading && !members.length && (
        <Empty title="暂无负载" hint="给工作项指派成员后，这里按人聚合活跃工作" />
      )}
      {members.map((m) => (
        <MemberRow key={m.user_id} m={m} maxActive={maxActive} />
      ))}
    </div>
  );
}

function MemberRow({ m, maxActive }: { m: MemberWorkload; maxActive: number }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-3">
        <span className="w-24 shrink-0 truncate text-sm font-medium">{m.user_name}</span>
        {m.on_leave && (
          <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-medium text-sky-500" title="今天在登记的休假日期段内">🏖 休假中</span>
        )}
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-bg">
          <div className={cx("h-full rounded-full", m.overdue ? "bg-red-400" : "bg-acc")}
            style={{ width: `${(m.active / maxActive) * 100}%` }} />
        </div>
        <span className="w-16 shrink-0 text-right text-xs font-medium">活跃 {m.active}</span>
        <span className="w-16 shrink-0 text-right text-xs text-mut">⏱ {fmtMinutes(m.minutes_7d)}/7d</span>
        {m.overdue > 0 && (
          <span className="rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] font-medium text-red-500">
            超期 {m.overdue}
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {Object.entries(m.projects).map(([name, n]) => (
          <span key={name} className="rounded border border-line px-1.5 py-0.5 text-[10px] text-mut">
            {name} × {n}
          </span>
        ))}
      </div>
    </Card>
  );
}
