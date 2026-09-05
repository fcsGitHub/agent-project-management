/** Dashboard: milestone bar, approvals waiting, feature progress, activity feed.
 * M23-I72: cross-project portfolio overview card on top. */
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import { fmtMinutes } from "../components/TimeLogModal";
import { Badge, Card, Empty, Button, PrintButton, cx } from "../components/ui";

const ICON: Record<string, string> = { human: "👤", agent: "🤖", system: "⚙️", ui_agent: "⌨️" };

export function Dashboard() {
  const { pid } = useParams();
  const project = useQuery({ queryKey: ["project", pid], queryFn: () => api.getProject(pid!), enabled: !!pid });
  const phases = useQuery({ queryKey: ["phases", pid], queryFn: () => api.getPhases(pid!), enabled: !!pid });
  const approvals = useQuery({ queryKey: ["approvals", pid, "pending"], queryFn: () => api.listApprovals({ status: "pending", project_id: pid }), enabled: !!pid });
  const runs = useQuery({ queryKey: ["runs", pid], queryFn: () => api.listRuns(pid!), enabled: !!pid });
  const events = useQuery({ queryKey: ["events", pid], queryFn: () => api.listEvents({ project_id: pid, limit: 25 }), enabled: !!pid });
  const convs = useQuery({ queryKey: ["conversations", pid], queryFn: () => api.listConversations(pid!), enabled: !!pid });
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.getPortfolioReport, refetchInterval: 15_000 });
  const health = useQuery({ queryKey: ["portfolio-health"], queryFn: api.portfolioHealth, refetchInterval: 15_000 });

  if (!pid) return null;
  const counts = project.data?.item_counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const done = counts.done ?? 0;
  const pct = total ? Math.round((done / total) * 100) : 0;

  const convCount = new Set(runs.data?.runs.map((r) => r.conversation_id)).size;
  const healthMap = new Map((health.data?.projects ?? []).map((h) => [h.project_id, h.score]));

  return (
    <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-3">
      {/* M23-I72: cross-project portfolio overview */}
      <Card className="p-4 md:col-span-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold">🗺 组合总览</span>
          <span className="flex items-center gap-3">
            <Link to="/roadmap" className="text-xs text-acc hover:underline">📅 路线图</Link>
            <Link to="/workload" className="text-xs text-acc hover:underline">👥 负载</Link>
            <PrintButton />
            <span className="text-xs text-mut">
            {portfolio.data?.projects.length ?? 0} 个可见项目 · 合计 活跃 {portfolio.data?.totals.items_active ?? 0} ·
            超期 {portfolio.data?.totals.overdue ?? 0} · 待审 Gate {portfolio.data?.totals.gates_pending ?? 0} ·
            工时 {fmtMinutes(portfolio.data?.totals.timelog_minutes ?? 0)}
            </span>
          </span>
        </div>
        <div className="space-y-1">
          {[...(portfolio.data?.projects ?? [])]
            .sort((x, y) => (healthMap.get(x.project_id) ?? 999) - (healthMap.get(y.project_id) ?? 999))
            .map((p) => {
            const score = healthMap.get(p.project_id);
            return (
            <Link key={p.project_id} to={`/p/${p.project_id}`}
              className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-xs hover:border-acc">
              <span className="w-32 shrink-0 truncate font-medium">{p.name}</span>
              <span title="项目健康评分（CHAOSS 多因子语义：超期/滞留/吞吐/Gate 四因子加权）">
                {score != null ? (
                  <Badge tone={score >= 80 ? "green" : score >= 60 ? "amber" : "red"}>
                    {score >= 80 ? "♥" : score >= 60 ? "♥" : "♥"} {score}
                  </Badge>
                ) : (
                  <Badge tone="neutral">♥ —</Badge>
                )}
              </span>
              <div className="flex h-1.5 flex-1 gap-px overflow-hidden rounded-full bg-bg">
                {(["backlog", "todo", "in_progress", "done", "cancelled"] as const).map((k) => (
                  <div key={k} title={`${k}: ${p.funnel[k] ?? 0}`}
                    className={cx("h-full", k === "done" ? "bg-ag" : k === "in_progress" ? "bg-acc" : "bg-line")}
                    style={{ width: `${p.items_active + p.funnel.done ? (p.funnel[k] ?? 0) / Math.max(Object.values(p.funnel).reduce((a, b) => a + b, 0), 1) * 100 : 0}%` }} />
                ))}
              </div>
              <span className="w-20 shrink-0 text-right text-mut">活跃 {p.items_active}</span>
              <span className="w-16 shrink-0 text-right text-mut">⏱ {fmtMinutes(p.timelog_minutes)}</span>
              {p.overdue > 0 && <Badge tone="red">超期 {p.overdue}</Badge>}
              {p.gates_pending > 0 && <Badge tone="amber">◆ {p.gates_pending}</Badge>}
            </Link>
            );
          })}
          {!portfolio.data?.projects.length && <div className="py-2 text-center text-xs text-mut">没有可见项目</div>}
        </div>
      </Card>

      {/* milestone / progress */}
      <Card className="p-4 md:col-span-2">
        <div className="flex items-center justify-between text-xs text-mut">
          <span>进度 · 任务 {done}/{total} · 对话 {convCount} · Runs {runs.data?.runs.length ?? 0}</span>
          <span className="font-mono">{pct}%</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-bg">
          <div className="h-full rounded-full bg-acc transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {(phases.data?.phases ?? []).map((p) => (
            <Badge key={p.id} tone={p.status === "passed" ? "green" : p.status === "active" ? "amber" : p.status === "skipped" ? "neutral" : "neutral"}>
              {p.name}{p.gate_label ? ` · ${p.gate_label}` : ""}
              {p.status === "passed" ? " ✓" : p.status === "active" ? " ●" : p.status === "skipped" ? " ⤼" : ""}
            </Badge>
          ))}
        </div>
        <div className="mt-4 space-y-1.5">
          {(project.data?.features ?? []).map((f) => (
            <Link key={f.id} to={`/p/${pid}/f/${f.id}`} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-bg">
              <span className="w-28 truncate">{f.title}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg">
                <div className="h-full rounded-full bg-ag" style={{ width: "0%" }} />
              </div>
              <span className="text-[10px] text-mut">{timeAgo(f.updated_at)}</span>
            </Link>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <Link to={`/p/${pid}/c/${firstDrafting(convs.data?.conversations ?? []) ?? ""}`}>
            <Button variant="primary" size="sm">和 PM-Agent 谈需求 →</Button>
          </Link>
          <Button size="sm" variant="outline" onClick={async () => {
            const r = await api.deliver(pid);
            location.hash = `#/p/${pid}/c/${r.conversation_id}`;
          }}>
            生成交付（Release-Agent）
          </Button>
        </div>
      </Card>

      {/* approvals waiting */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">🔔 待我处理</span>
          <Link to={`/p/${pid}/approvals`} className="text-xs text-acc hover:underline">审批中心 →</Link>
        </div>
        <div className="mt-3 space-y-2">
          {(approvals.data?.approvals ?? []).slice(0, 5).map((a) => (
            <Link key={a.id} to={`/p/${pid}/approvals`} className="block rounded-lg border border-line px-3 py-2 text-xs hover:border-acc">
              <div className="font-medium">
                {a.kind === "gate" ? `◆ ${a.payload_snapshot.gate}` : `⚠ ${a.payload_snapshot.tool}`}
              </div>
              <div className="mt-0.5 text-mut">{timeAgo(a.requested_at)} · {a.payload_snapshot.summary}</div>
            </Link>
          ))}
          {!approvals.data?.approvals.length && <div className="py-6 text-center text-xs text-mut">暂无待审批 ✓</div>}
        </div>
      </Card>

      {/* activity feed */}
      <Card className="p-4 md:col-span-3">
        <div className="mb-2 text-sm font-semibold">项目活动流（人机混排 · 实时）</div>
        <div className="space-y-1">
          {(events.data?.events ?? []).map((e) => (
            <div key={e.id} className="flex items-center gap-2 px-1 py-1 text-xs">
              <span className="w-12 shrink-0 font-mono text-mut">{timeAgo(e.ts)}</span>
              <span>{ICON[e.actor_type] ?? "•"}</span>
              <span className="w-20 shrink-0 truncate text-mut">{e.actor_id.split(":")[0]}</span>
              <span className="font-medium">{e.event_type}</span>
              <span className="truncate text-mut">{summaryOf(e)}</span>
            </div>
          ))}
          {!events.data?.events.length && <Empty title="暂无活动" hint="创建对话并发起一次 Agent 运行试试" />}
        </div>
      </Card>
    </div>
  );
}

function summaryOf(e: { event_type: string; payload: Record<string, unknown> }) {
  const p = e.payload as Record<string, any>;
  switch (e.event_type) {
    case "message.created": return String(p.content ?? "").slice(0, 60);
    case "approval.requested": return (p.snapshot?.gate ?? p.snapshot?.tool ?? "");
    case "item.created": return p.title;
    case "conversation.created": return p.title ?? p.kind;
    case "run.succeeded": return p.output?.artifact ?? "";
    default: return "";
  }
}

function firstDrafting(list: { id: string; kind: string }[]): string | undefined {
  return (list.find((c) => c.kind === "drafting") ?? list[0])?.id;
}
