/** Cross-project activity feed (M36-I110, docs/01 §AI.1, OpenProject
 * "My activity" semantics): one timeline of everything that happened in the
 * projects you can see — the visible event stream rendered directly, no new
 * tables, no replay (event-sourcing dividend #7). Filters: project, kind. */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Card, Empty, cx } from "../components/ui";

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
  // M61-I183: instance-level event store observation, admin-only (same gate as rebuild)
  const me = useQuery({ queryKey: ["me"], queryFn: api.authMe });
  const stats = useQuery({
    queryKey: ["event-store-stats"],
    queryFn: api.eventStoreStats,
    enabled: !!me.data?.is_admin,
  });
  // M62-I186: endpoint latency observation, admin-only (in-memory ring buckets)
  const slow = useQuery({
    queryKey: ["slow-endpoints"],
    queryFn: api.slowEndpoints,
    enabled: !!me.data?.is_admin,
    refetchInterval: 15_000,
  });

  const fmtBytes = (n: number) =>
    n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : n >= 1 << 10 ? `${(n / (1 << 10)).toFixed(1)} KB` : `${n} B`;
  const topDist = (stats.data?.distribution ?? []).slice(0, 5);

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 md:p-6">
      <h1 className="text-lg font-semibold">📰 项目动态</h1>
      <p className="-mt-3 text-xs text-mut">你可见的项目里最近发生的一切——直接读事件流，谁在何时动了什么。</p>

      {me.data?.is_admin && (
        <Card className="p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold">🗄 事件库</span>
            <span className="text-[10px] text-mut" title="事件日志只增是事件溯源的本质（归档=导出非删除）；先测后治，若未来需要治理动作则组合既有导出与备份工具">
              只增日志 · 纯读观测 · 归档=导出非删除
            </span>
          </div>
          {stats.data ? (
            <div className="space-y-1 text-xs">
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-mut">
                <span>事件 <b className="text-ink">{stats.data.total_events.toLocaleString()}</b> 条</span>
                <span>库体积 <b className="text-ink">{fmtBytes(stats.data.db_bytes)}</b></span>
                {stats.data.oldest_ts && <span title={stats.data.oldest_ts}>最早 {stats.data.oldest_ts.slice(0, 10)}</span>}
                {stats.data.newest_ts && <span title={stats.data.newest_ts}>最新 {stats.data.newest_ts.slice(0, 10)}</span>}
              </div>
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {topDist.map((d) => (
                  <span key={`${d.agg_type}/${d.event_type}`} title={`${d.agg_type} / ${d.event_type}`}
                    className="rounded-full border border-line px-2 py-0.5 text-[10px] text-mut">
                    {d.event_type} · {d.count.toLocaleString()}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <div className="py-1 text-xs text-mut">加载事件库统计…</div>
          )}
        </Card>
      )}

      {me.data?.is_admin && slow.data && (
        <Card className="p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold">⏱ 慢端点</span>
            <span className="text-[10px] text-mut" title={`内存环形桶按路径记账（阈值 ${slow.data.threshold_ms}ms 保样本）；遥测是运行时数据不进事件流`}>
              阈值 {slow.data.threshold_ms}ms · 内存观测 · 不进事件流
            </span>
          </div>
          <div className="space-y-1 text-xs">
            {slow.data.endpoints.slice(0, 5).map((e) => (
              <div key={e.path} className="flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate text-[11px]" title={e.path}>{e.path}</code>
                <span className="w-14 text-right text-mut">{e.count} 次</span>
                <span className="w-20 text-right text-mut" title="平均耗时">均 {e.mean_ms}ms</span>
                <span className={cx("w-20 text-right", e.max_ms >= slow.data!.threshold_ms ? "text-dan" : "text-mut")}
                  title="最大耗时">最 {e.max_ms}ms</span>
              </div>
            ))}
            {!slow.data.endpoints.length && <div className="py-1 text-mut">尚无请求记录——有流量后按路径聚合</div>}
            {slow.data.slow_samples.length > 0 && (
              <div className="border-t border-line pt-1 text-[10px] text-mut">
                慢样本 {slow.data.slow_samples.length}：最新 {slow.data.slow_samples[0].method} {slow.data.slow_samples[0].path} · {slow.data.slow_samples[0].ms}ms
              </div>
            )}
          </div>
        </Card>
      )}

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
        ) : feed.isError ? (
          <div className="py-6 text-center text-xs text-dan">动态流加载失败，请刷新重试。</div>
        ) : feed.isLoading ? (
          <div className="py-6 text-center text-xs text-mut">加载动态…</div>
        ) : (
          <Empty title="暂无动态" hint="你可见的项目里有新动作后，这里会按时间倒序流出" />
        )}
      </Card>
    </div>
  );
}
