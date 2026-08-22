/** Runs browser: list + drawer with span tree, gantt and human-machine timeline. */
import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
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
  const setOpen = (id: string | null) => {
    const usp = new URLSearchParams(params);
    if (id) usp.set("run", id); else usp.delete("run");
    setParams(usp, { replace: true });
  };

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm font-semibold">Runs · 轨迹浏览器</span>
        <span className="text-xs text-mut">{runs.data?.runs.length ?? 0} 次运行</span>
      </div>
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
        {!runs.data?.runs.length && <Empty icon="🪵" title="暂无运行" hint="从看板或对话发起一次 Agent 运行" />}
      </div>
      <RunDrawer runId={openRun} onClose={() => setOpen(null)} pid={pid} />
    </div>
  );
}

function RunDrawer({ runId, onClose, pid }: { runId: string | null; onClose: () => void; pid?: string }) {
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
                await fetch(`/api/runs/${runId}/retry`, { method: "POST" });
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
                    <span className="w-52 shrink-0 truncate font-mono text-mut" title={s.name}>
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
