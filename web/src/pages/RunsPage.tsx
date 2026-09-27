/** Runs browser: list + drawer with span tree, gantt and human-machine timeline. */
import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { clockOf, timeAgo } from "../lib/fmt";
import { Badge, Button, Card, Drawer, Empty, KV, cx } from "../components/ui";

const STATUS_TONE: Record<string, string> = {
  pending: "neutral", running: "violet", interrupted: "amber",
  succeeded: "green", failed: "red", cancelled: "neutral",
};

export function RunsPage() {
  const { pid } = useParams();
  const [params, setParams] = useSearchParams();
  const openRun = params.get("run") ?? null;
  const runs = useQuery({
    queryKey: ["runs", pid],
    queryFn: () => api.listRuns(pid!),
    enabled: !!pid,
    refetchInterval: 3_000,
  });
  const report = useQuery({
    queryKey: ["runs-report", pid],
    queryFn: () => api.getRunsReport(pid!),
    enabled: !!pid,
    refetchInterval: 15_000,
  });
  // M44: the zero-tokens caveat only applies to the replay provider
  const llm = useQuery({ queryKey: ["llm-status"], queryFn: api.llmStatus, staleTime: 60_000 });
  const setOpen = (id: string | null) => {
    const usp = new URLSearchParams(params);
    if (id) usp.set("run", id); else usp.delete("run");
    setParams(usp, { replace: true });
  };

  const rep = report.data;
  const maxStatus = rep ? Math.max(1, ...Object.values(rep.by_status)) : 1;

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm font-semibold">Runs · 轨迹浏览器</span>
        <span className="text-xs text-mut">{runs.data?.runs.length ?? 0} 次运行</span>
        {pid && <WatchAgentToggle pid={pid} />}
      </div>
      {rep && rep.total > 0 && (
        <Card className="no-print mb-3 p-4">
          <div className="mb-2 text-sm font-semibold">📊 运行报表</div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-mut">
            <span>共 <span className="font-medium text-ink">{rep.total}</span> 次</span>
            <span>成功率 <span className="font-medium text-ink">{rep.success_rate != null ? `${Math.round(rep.success_rate * 100)}%` : "—"}</span></span>
            <span>平均时长 <span className="font-medium text-ink">{rep.avg_duration_seconds != null ? `${rep.avg_duration_seconds}s` : "—"}</span></span>
            <span>Gate 挂起率 <span className="font-medium text-ink">{rep.gate_pending_rate != null ? `${Math.round(rep.gate_pending_rate * 100)}%` : "—"}</span></span>
            <span>平均步骤数 <span className="font-medium text-ink">{rep.avg_steps_per_run ?? "—"}</span></span>
            <span title={llm.data?.provider_mode === "replay" ? "replay provider 记零，接入真实 provider 后即有数" : `真实模型 ${llm.data?.model ?? ""} 的实际 token 用量`}>tokens <span className="font-medium text-ink">{rep.tokens.input}/{rep.tokens.output}</span></span>
          </div>
          <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-bg">
            {Object.entries(rep.by_status).map(([k, n]) => (
              n > 0 && (
                <div key={k} title={`${k}: ${n}`} className={cx(
                  k === "succeeded" ? "bg-ag" : k === "failed" ? "bg-dan" :
                  k === "interrupted" ? "bg-warn" : "bg-line")} style={{ width: `${(n / maxStatus) * 100}%` }} />
              )
            ))}
          </div>
          {!!rep.by_role.length && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {rep.by_role.map((r) => (
                <Badge key={r.agent_role} tone="neutral" title={`成功率 ${r.success_rate != null ? `${Math.round(r.success_rate * 100)}%` : "—"}`}>
                  {r.agent_role} × {r.runs}{r.success_rate != null ? ` · ${Math.round(r.success_rate * 100)}%` : ""}
                </Badge>
              ))}
            </div>
          )}
        </Card>
      )}
      <div className="space-y-2">
        {(runs.data?.runs ?? []).map((r) => (
          <Card
            key={r.id}
            className="flex cursor-pointer items-center gap-3 p-3 text-sm hover:border-acc"
            onClick={() => setOpen(r.id)}
          >
            <Badge tone={STATUS_TONE[r.status] ?? "neutral"}>{r.status}</Badge>
            <span className="font-mono text-xs">🤖 {r.agent_role}</span>
            <span className="min-w-0 flex-1 truncate">
              {r.item_title ?? r.conversation_title ?? r.id}
            </span>
            <span className="text-xs text-mut">{timeAgo(r.started_at)}</span>
          </Card>
        ))}
        {runs.isLoading && <div className="py-6 text-center text-sm text-mut">加载运行…</div>}
        {!runs.isLoading && !runs.data?.runs.length && <Empty icon="🪵" title="暂无运行" hint="从看板或对话发起一次 Agent 运行" />}
      </div>
      <RunDrawer runId={openRun} onClose={() => setOpen(null)} pid={pid} />
    </div>
  );
}

function RunDrawer({ runId, onClose, pid }: { runId: string | null; onClose: () => void; pid?: string }) {
  const qc = useQueryClient();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.getRun(runId!), enabled: !!runId });
  const spans = useQuery({ queryKey: ["spans", runId], queryFn: () => api.getSpans(runId!), enabled: !!runId });
  const timeline = useQuery({ queryKey: ["timeline", runId], queryFn: () => api.getTimeline(runId!), enabled: !!runId });

  const bounds = useMemo(() => {
    const list = (spans.data?.spans ?? []).filter((s) => s.ts_start);
    if (!list.length) return null;
    const times = list.flatMap((s) => [new Date(s.ts_start!).getTime(), new Date(s.ts_end ?? s.ts_start!).getTime()]);
    return { min: Math.min(...times), max: Math.max(...times) || 1 };
  }, [spans.data]);

  if (!runId) return null;
  const r = run.data;
  return (
    <Drawer open onClose={onClose} title={
      <span className="flex items-center gap-2">
        Run {runId?.slice(0, 12)}…
        {r && <Badge tone={STATUS_TONE[r.status] ?? "neutral"}>{r.status}</Badge>}
        {r && <Badge tone="violet">🤖 {r.agent_role}</Badge>}
      </span>
    } width="56%">
      {r && (
        <div className="space-y-4">
          <Card className="p-3">
            <KV k="对话" v={<Link className="text-acc hover:underline" to={`/p/${pid}/c/${r.conversation_id}`}>{r.conversation_title ?? r.conversation_id} →</Link>} />
            <KV k="工作项" v={r.item_title ?? r.item_id ?? "—"} />
            <KV k="开始/结束" v={`${r.started_at ?? "—"} → ${r.ended_at ?? (r.status === "running" ? "…" : "—")}`} />
            {r.error && <KV k="错误" v={<span className="text-dan">{r.error}</span>} />}
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="outline" onClick={async () => {
                try {
                  await api.retryRun(runId);
                  toast.success("已从检查点重试");
                  qc.invalidateQueries({ queryKey: ["runs"] });
                  qc.invalidateQueries({ queryKey: ["run", runId] });
                } catch (e) {
                  toast.error("重试失败", { description: String(e) });
                }
              }}>↺ 从检查点重试</Button>
            </div>
          </Card>

          <div>
            <div className="mb-1.5 text-xs font-semibold text-mut">Span 树 + 甘特瀑布</div>
            <div className="space-y-0.5">
              {(spans.data?.spans ?? []).map((s) => {
                const left = bounds ? ((new Date(s.ts_start ?? bounds.min).getTime() - bounds.min) / (bounds.max - bounds.min)) * 100 : 0;
                const width = bounds
                  ? Math.max(1.5, ((new Date(s.ts_end ?? s.ts_start ?? bounds.min).getTime() - new Date(s.ts_start ?? bounds.min).getTime()) / (bounds.max - bounds.min)) * 100)
                  : 0;
                const tone =
                  s.status === "error" ? "bg-dan" :
                  s.span_kind === "gate" ? "bg-warn" :
                  s.span_kind === "tool" ? "bg-ag" :
                  s.span_kind === "generation" ? "bg-indigo-400" : "bg-acc";
                return (
                  <div key={s.id} className="group flex items-center gap-2 text-[11px]">
                    <span className="w-32 shrink-0 truncate font-mono text-mut sm:w-52" title={s.name}>
                      {iconOf(s.span_kind)} {s.name}
                    </span>
                    <div className="relative h-3.5 flex-1 overflow-hidden rounded bg-bg">
                      <div
                        className={cx("absolute h-full rounded opacity-80", tone)}
                        style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }}
                        title={`${s.ts_start} → ${s.ts_end ?? "?"}`}
                      />
                    </div>
                    <span className="w-20 shrink-0 text-right font-mono text-mut">
                      {s.attributes?.["gen_ai.usage.input_tokens"] ? `${s.attributes["gen_ai.usage.input_tokens"]}→${s.attributes["gen_ai.usage.output_tokens"]}` : ""}
                    </span>
                  </div>
                );
              })}
              {!spans.data?.spans.length && <div className="text-xs text-mut">暂无 span</div>}
            </div>
          </div>

          <div>
            <div className="mb-1.5 text-xs font-semibold text-mut">人机交织时间线</div>
            <div className="space-y-0.5">
              {(timeline.data?.entries ?? []).map((e, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <span className="w-12 shrink-0 font-mono text-mut">{clockOf(e.ts)}</span>
                  <span>{e.actor_type === "human" ? "👤" : e.actor_type === "agent" ? "🤖" : e.actor_type === "ui_agent" ? "⌨️" : "⚙️"}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {e.kind === "span" ? `${e.name} ${e.status === "ok" ? "✓" : e.status ?? ""}` : `${e.event_type} ${e.summary ?? ""}`}
                  </span>
                </div>
              ))}
              {!timeline.data?.entries.length && <div className="text-xs text-mut">暂无时间线</div>}
            </div>
          </div>
        </div>
      )}
    </Drawer>
  );
}

function iconOf(kind: string) {
  return { agent: "▣", generation: "⚙", tool: "🔧", gate: "◆", chain: "●", human_action: "👤", ui_command: "⌨" }[kind] ?? "•";
}

// M58-I175: 一键关注 agent 动态——幂等建/删 run.succeeded+run.failed 规则对
// （CI「路由给触发者」语义：运行完成/失败双通道提醒；通道关断与免打扰在铃铛偏好细调）
const RUN_WATCH_EVENTS = ["run.succeeded", "run.failed"];

function WatchAgentToggle({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["watch-rules"], queryFn: api.listWatchRules });
  const mine = (rules.data?.rules ?? []).filter(
    (r) => r.project_id === pid && RUN_WATCH_EVENTS.includes(r.event_type));
  const allOn = mine.length === RUN_WATCH_EVENTS.length;
  const toggle = async () => {
    try {
      if (allOn) {
        for (const t of RUN_WATCH_EVENTS) await api.removeWatchRule(pid, t);
        toast.info("已退订 agent 动态");
      } else {
        for (const t of RUN_WATCH_EVENTS) {
          if (!mine.some((r) => r.event_type === t)) await api.addWatchRule(pid, t);
        }
        toast.success("已关注 agent 动态：运行成功/失败都会提醒你");
      }
      await qc.invalidateQueries({ queryKey: ["watch-rules"] });
    } catch (e) {
      toast.error(`操作失败：${e instanceof Error ? e.message : e}`);
    }
  };
  return (
    <button onClick={toggle} disabled={rules.isLoading}
      title="关注本项目的 agent 运行成功/失败（随时退订；通道与免打扰在铃铛偏好里细调）"
      className={cx("ml-auto rounded-full border px-2.5 py-1 text-xs",
        allOn ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink")}>
      👁 {allOn ? "已关注 agent 动态" : "关注 agent 动态"}
    </button>
  );
}
