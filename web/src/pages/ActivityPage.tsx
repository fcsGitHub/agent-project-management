/** Cross-project activity feed (M36-I110, docs/01 §AI.1, OpenProject
 * "My activity" semantics): one timeline of everything that happened in the
 * projects you can see — the visible event stream rendered directly, no new
 * tables, no replay (event-sourcing dividend #7). Filters: project, kind. */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Card, Empty } from "../components/ui";

const KINDS = [
  { value: "", label: "全部类型" },
  { value: "item", label: "🆕🔁 工作项" },
  { value: "comment", label: "💬 评论" },
  { value: "milestone", label: "🚩🏁 里程碑" },
  { value: "approval", label: "⏳✅⛔ 审批" },
];

function relTime(ts: string) {
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return ts.slice(0, 10);
}

export function ActivityPage() {
  const [projectId, setProjectId] = useState("");
  const [kind, setKind] = useState("");
  const overview = useQuery({ queryKey: ["portfolio-report"], queryFn: api.getPortfolioReport });
  const feed = useQuery({
    queryKey: ["portfolio-activity", projectId, kind],
    queryFn: () => api.portfolioActivity({
      project_id: projectId || undefined, kind: kind || undefined, limit: 100,
    }),
    refetchInterval: 30_000,
  });

  const projects = overview.data?.projects ?? [];
  const acts = feed.data?.activities ?? [];
  // I115: the Atom subscription URL is the credential (feed_key, M11 semantics)
  const feedKey = useQuery({ queryKey: ["feed-key"], queryFn: api.getFeedKey });
  const atomUrl = feedKey.data ? `${location.origin}/api/portfolio/activity.atom?key=${feedKey.data.feed_key}` : null;

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 md:p-6">
      <h1 className="text-lg font-semibold">📰 项目动态</h1>
      <p className="-mt-3 text-xs text-mut">你可见的项目里最近发生的一切——直接读事件流，谁在何时动了什么。</p>

      <Card className="p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)}
            className="rounded-lg border border-line bg-bg px-2 py-1 text-xs text-ink">
            <option value="">全部项目</option>
            {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.name}</option>)}
          </select>
          <select value={kind} onChange={(e) => setKind(e.target.value)}
            className="rounded-lg border border-line bg-bg px-2 py-1 text-xs text-ink">
            {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </select>
          <span className="ml-auto text-[10px] text-mut">最近 {acts.length} 条 · 30 秒自动刷新</span>
          {atomUrl && (
            <button
              onClick={async () => { await navigator.clipboard.writeText(atomUrl); toast.success("Atom 订阅链接已复制"); }}
              className="rounded border border-line px-1.5 py-0.5 text-[10px] text-mut hover:border-acc hover:text-acc"
              title={atomUrl}>
              🔗 Atom
            </button>
          )}
        </div>

        {acts.length ? (
          <div className="space-y-0.5">
            {acts.map((a) => (
              <div key={a.event_id} className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 hover:bg-bg">
                <span className="mt-0.5 text-sm">{a.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs text-ink">
                    <span className="font-medium">{a.actor_name}</span>
                    <span className="text-mut"> {a.summary}</span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-mut">
                    <Link to={`/p/${a.project_id}/board`} className="hover:text-acc">{a.project_name}</Link>
                    <span title={a.ts}>{relTime(a.ts)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty title="暂无动态" hint="你可见的项目里有新动作后，这里会按时间倒序流出" />
        )}
      </Card>
    </div>
  );
}
