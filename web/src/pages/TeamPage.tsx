/** M116-I353/I354（docs/01 §DG，Paperclip 吸纳轮）：Agent 团队总览与治理面。
 * org 级页面（/team，与 /activity 同形态）：GET /agents 三源合并目录——
 * YAML 声明（能力）×治理覆盖层（暂停/预算）×runs 聚合（谁在忙/成本/成功率）。
 * 治理动作（暂停/恢复/预算）admin 门在后端（403 语义），前端按 is_admin 显隐。 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type AgentTeamMember } from "../lib/api";
import { Badge, Button, Card, Empty, Input, cx } from "../components/ui";

function relTime(ts: string | null) {
  if (!ts) return "从未运行";
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return ts.slice(0, 10);
}

function StatusBadge({ a }: { a: AgentTeamMember }) {
  if (a.status === "paused") {
    return <Badge className="border-dan/40 bg-danbg text-dan">⏸ 已暂停</Badge>;
  }
  if (a.stats.active_runs > 0) {
    return <Badge className="border-acc/40 bg-accbg text-acc">▶ 运行中 ×{a.stats.active_runs}</Badge>;
  }
  return <Badge className="border-line bg-surface text-mut">空闲</Badge>;
}

function BudgetRow({ a, isAdmin, onSaved }: { a: AgentTeamMember; isAdmin: boolean; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(a.budget_usd != null ? String(a.budget_usd) : "");
  const month = a.stats.month_cost_usd;
  const budget = a.budget_usd;

  const save = async () => {
    const v = value.trim() === "" ? 0 : Number(value);
    if (Number.isNaN(v) || v < 0) {
      toast.error("预算须为非负数（0=关闭护栏）");
      return;
    }
    try {
      await api.patchAgentBudget(a.id, v);
      toast.success(v === 0 ? `已关闭 ${a.display_name} 的预算护栏` : `已设 ${a.display_name} 月度预算 $${v}`);
      setEditing(false);
      onSaved();
    } catch (e) {
      toast.error(String((e as Error).message ?? e));
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {editing ? (
        <>
          <Input aria-label={`${a.display_name} 月度预算美元`} className="h-7 w-24 text-xs"
            value={value} placeholder="0=关闭"
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && save()} />
          <Button size="sm" variant="primary" onClick={save}>保存</Button>
          <Button size="sm" onClick={() => setEditing(false)}>取消</Button>
        </>
      ) : (
        <>
          <span className="text-mut">
            本月 <b className="text-ink">${month.toFixed(2)}</b>
            {budget ? <> / 预算 <b className={cx(month >= budget ? "text-dan" : month >= budget * 0.8 ? "text-warn" : "text-ink")}>${budget.toFixed(2)}</b></> : " · 未设预算"}
          </span>
          {isAdmin && (
            <button type="button" className="text-[11px] text-acc hover:underline" onClick={() => setEditing(true)}>
              设预算
            </button>
          )}
        </>
      )}
    </div>
  );
}

export function TeamPage() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.authMe });
  const team = useQuery({
    queryKey: ["agents"],
    queryFn: api.listAgents,
    refetchInterval: 15_000,
  });
  const isAdmin = !!me.data?.is_admin;

  const invalidate = () => qc.invalidateQueries({ queryKey: ["agents"] });

  const toggle = async (a: AgentTeamMember) => {
    try {
      if (a.status === "paused") {
        await api.resumeAgent(a.id);
        toast.success(`${a.display_name} 已恢复接活`);
      } else {
        await api.pauseAgent(a.id);
        toast.success(`${a.display_name} 已暂停——新派活将被拒绝（409）`);
      }
      invalidate();
    } catch (e) {
      toast.error(String((e as Error).message ?? e));
    }
  };

  const agents = team.data?.agents ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 md:p-6">
      <h1 className="text-lg font-semibold">🤖 Agent 团队</h1>
      <p className="-mt-3 text-xs text-mut">
        角色化 Agent 的统筹面板：谁在忙、成本与成功率一屏可见——治理（暂停/恢复/预算）仅管理员。
      </p>

      {team.isLoading && <div className="text-xs text-mut">加载团队…</div>}
      {team.isError && <Card className="p-4 text-sm text-dan">团队目录加载失败：{String((team.error as Error)?.message)}</Card>}
      {!team.isLoading && !agents.length && (
        <Empty title="没有注册的角色" hint="agents/roles/*.yaml 声明的角色会出现在这里" />
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {agents.map((a) => {
          const total = a.stats.total_runs;
          const rate = total ? Math.round((a.stats.succeeded / total) * 100) : null;
          return (
            <Card key={a.id} className={cx("space-y-2 p-4", a.status === "paused" && "opacity-80")}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-semibold">{a.display_name}</span>
                    <StatusBadge a={a} />
                  </div>
                  <code className="text-[11px] text-mut">{a.id}</code>
                </div>
                {isAdmin && (
                  <Button size="sm" variant={a.status === "paused" ? "primary" : "default"}
                    onClick={() => toggle(a)}
                    title={a.status === "paused" ? "恢复该角色接新活" : "暂停后新派活 409 拒绝（运行中的 run 不受影响）"}>
                    {a.status === "paused" ? "▸ 恢复" : "⏸ 暂停"}
                  </Button>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-mut">
                <span className="rounded-full border border-line px-2 py-0.5" title="模型档位（tier 三档路由 M48）">
                  {a.tier ?? "custom"}
                </span>
                {a.model && <span className="truncate" title={`模型 ${a.model}`}>{a.model}</span>}
                {a.concepts.map((c) => (
                  <span key={c} className="rounded-full border border-line px-2 py-0.5">{c}</span>
                ))}
              </div>

              <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-mut">
                <span>运行 <b className="text-ink">{total}</b></span>
                <span>成功率 <b className="text-ink">{rate == null ? "—" : `${rate}%`}</b></span>
                <span title="输入+输出 tokens 累计">tokens <b className="text-ink">{a.stats.total_tokens.toLocaleString()}</b></span>
                <span title="runs 台账 estimated_cost_usd 累计（事件溯源红利：零埋点）">成本 <b className="text-ink">${a.stats.estimated_cost_usd.toFixed(2)}</b></span>
                <span title={a.stats.last_started_at ?? undefined}>最近 {relTime(a.stats.last_started_at)}</span>
              </div>

              <BudgetRow a={a} isAdmin={isAdmin} onSaved={invalidate} />
            </Card>
          );
        })}
      </div>
    </div>
  );
}
