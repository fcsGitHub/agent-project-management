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
  // M62-I188: agent spend surface (docs/01 §BG.3) — the human side above, the agent side below
  const usage = useQuery({ queryKey: ["agent-usage"], queryFn: () => api.agentUsage(30) });

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

      {usage.data && usage.data.roles.length > 0 && (
        <Card className="p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold">🤖 Agent 用量</span>
            <span className="text-[10px] text-mut"
              title="runs 记账（M44 起 token/成本入流）的读侧聚合——「钱花在哪类工作上」；可见性同负载口径">
              近 {usage.data.days} 天 · 完成率=成功/(成功+失败)
            </span>
          </div>
          <div className="space-y-1 text-xs">
            {usage.data.roles.map((r) => (
              <div key={r.agent_role} className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5">
                <span className="min-w-0 flex-1 truncate font-medium">🤖 {r.agent_role}</span>
                <span className="w-16 text-right text-mut" title="运行数">{r.runs} 次</span>
                <span className="w-20 text-right text-mut" title="完成率（成功/(成功+失败)）">
                  {r.success_rate != null ? `✓ ${Math.round(r.success_rate * 100)}%` : "—"}
                </span>
                <span className="w-24 text-right text-mut" title="输入/输出 token">
                  {r.input_tokens.toLocaleString()} / {r.output_tokens.toLocaleString()} tok
                </span>
                <span className="w-20 text-right font-medium" title="估算成本合计">${r.cost_usd.toFixed(2)}</span>
              </div>
            ))}
            <div className="flex items-center gap-2 px-2.5 pt-1 text-[10px] text-mut">
              <span className="min-w-0 flex-1">合计 {usage.data.totals.runs} 次运行</span>
              <span className="w-20 text-right" title="成功运行数">✓ {usage.data.totals.succeeded}</span>
              <span className="w-20" />
              <span className="w-24 text-right" title="token 合计">
                {usage.data.totals.input_tokens.toLocaleString()} / {usage.data.totals.output_tokens.toLocaleString()}
              </span>
              <span className="w-20 text-right font-medium">${usage.data.totals.cost_usd.toFixed(2)}</span>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function MemberRow({ m, maxActive }: { m: MemberWorkload; maxActive: number }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-3">
        <span className="w-24 shrink-0 truncate text-sm font-medium">{m.user_name}</span>
        {m.overloaded && (
          <span className="rounded bg-danbg px-1.5 py-0.5 text-[10px] font-medium text-dan" title={`活跃任务超过阈值 ${m.active} 项——建议人工重新均衡`}>⚠ 超载</span>
        )}
        {m.on_leave && (
          <span className="rounded bg-accbg px-1.5 py-0.5 text-[10px] font-medium text-acc" title="今天在登记的休假日期段内">🏖 休假中</span>
        )}
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-bg">
          <div className={cx("h-full rounded-full", m.overdue ? "bg-dan" : "bg-acc")}
            style={{ width: `${(m.active / maxActive) * 100}%` }} />
        </div>
        <span className="w-16 shrink-0 text-right text-xs font-medium">活跃 {m.active}</span>
        <span className="w-16 shrink-0 text-right text-xs text-mut">⏱ {fmtMinutes(m.minutes_7d)}/7d</span>
        {m.overdue > 0 && (
          <span className="rounded bg-danbg px-1.5 py-0.5 text-[10px] font-medium text-dan">
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
      {/* M53-I160: 未来两周到期负载（OpenProject 17.7 Resource planner 的读视图切片） */}
      {!!m.weeks?.length && (
        <div className="mt-2 flex gap-2">
          {m.weeks.map((w, i) => {
            const label = i === 0 ? "本周" : "下下周";
            const cls = w.on_leave
              ? "bg-sky-500/30"
              : w.est_hours === 0
                ? "bg-bg"
                : w.est_hours <= 8 ? "bg-ag" : w.est_hours <= 20 ? "bg-amber-500" : "bg-dan";
            return (
              <div key={w.week_start}
                className="flex flex-1 items-center gap-1.5 rounded border border-line px-2 py-1"
                title={w.on_leave
                  ? `${label}（${w.week_start} 起）整周休假`
                  : `${label}（${w.week_start} 起）到期 ${w.due_items} 项 · 约 ${w.est_hours}h`}>
                <span className="text-[10px] text-mut">{label}</span>
                <div className={cx("h-2 flex-1 overflow-hidden rounded-full", cls)} />
                <span className="w-20 shrink-0 text-right text-[10px] text-mut">
                  {w.on_leave ? "🏖 整周休假" : `${w.due_items} 项 · ${w.est_hours}h`}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
