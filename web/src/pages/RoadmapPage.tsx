/** Cross-project milestone roadmap (M27-I84): every milestone of every project
 * visible to the caller on one date axis — one row per project, one bar per
 * milestone (progress fill + overdue red + today line). Pure projection query
 * (GitLab epic #1105 gap, closed here by the _visible aggregation). */
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Card, Empty } from "../components/ui";

const DAY = 86_400_000;

export function RoadmapPage() {
  const roadmap = useQuery({ queryKey: ["roadmap"], queryFn: api.portfolioRoadmap });

  const view = useMemo(() => {
    const today = roadmap.data?.today ? new Date(roadmap.data.today + "T00:00:00Z").getTime() : Date.now();
    let min = today - 15 * DAY;
    let max = today + 45 * DAY;
    for (const p of roadmap.data?.projects ?? []) {
      for (const m of p.milestones) {
        const t = new Date(m.due_date + "T00:00:00Z").getTime();
        if (!Number.isNaN(t)) { min = Math.min(min, t - 7 * DAY); max = Math.max(max, t + 7 * DAY); }
      }
    }
    const days = Math.max(Math.round((max - min) / DAY) + 1, 14);
    const pct = (t: number) => ((t - min) / DAY / days) * 100;
    const ticks: { pct: number; label: string }[] = [];
    for (let i = 0; i <= days; i += 14) {
      ticks.push({ pct: (i / days) * 100, label: new Date(min + i * DAY).toISOString().slice(0, 7) + "-" + new Date(min + i * DAY).toISOString().slice(8, 10) });
    }
    return { todayPct: pct(today), ticks, pct };
  }, [roadmap.data]);

  const projects = roadmap.data?.projects ?? [];
  const totalMs = projects.reduce((n, p) => n + p.milestones.length, 0);

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 md:p-6">
      <div>
        <h1 className="text-lg font-semibold">📅 跨项目路线图</h1>
        <p className="mt-0.5 text-xs text-mut">
          全部可见项目的里程碑时间线——进度按关联项完成比例，红色=已超期（对调用方可见性裁剪，与组合总览同口径）
        </p>
      </div>

      {!roadmap.isLoading && totalMs === 0 && (
        <Empty title="暂无里程碑" hint="在项目里创建里程碑并设置截止日期后，这里会按时间轴排布" />
      )}

      {projects.map((p) => (
        <Card key={p.project_id} className="p-4">
          <div className="mb-2 flex items-center justify-between">
            <Link to={`/p/${p.project_id}`} className="text-sm font-medium hover:text-acc">{p.name}</Link>
            <span className="text-[10px] text-mut">{p.milestones.length} 个里程碑</span>
          </div>
          <div className="relative space-y-1.5">
            {view.ticks.map((t) => (
              <div key={t.pct} className="pointer-events-none absolute top-0 h-full border-l border-line/60"
                style={{ left: `${t.pct}%` }}>
                <span className="absolute top-full whitespace-nowrap text-[9px] text-mut">{t.label}</span>
              </div>
            ))}
            <div className="pointer-events-none absolute top-0 z-10 h-full border-l-2 border-dashed border-acc/60"
              style={{ left: `${view.todayPct}%` }} title="今天" />
            {p.milestones.map((m) => {
              const t = new Date(m.due_date + "T00:00:00Z").getTime();
              const left = view.pct(t) - 2;
              const ratio = m.progress.done_ratio ?? 0;
              return (
                <div key={m.id} className="relative h-6" title={`${m.title} · ${m.due_date} · 完成 ${m.progress.items_done}/${m.progress.items_total}`}>
                  <div className="absolute top-1 h-4 min-w-[10px] overflow-hidden rounded-full border border-line bg-bg"
                    style={{ left: `${Math.max(left, 0)}%` }}>
                    <div className="h-full bg-accbg" style={{ width: `${ratio}%` }} />
                  </div>
                  <span className={`absolute top-1 ml-2 whitespace-nowrap text-[10px] leading-4 ${m.overdue ? "font-medium text-dan" : "text-mut"}`}
                    style={{ left: `${Math.max(left, 0)}%` }}>
                    ◆ {m.title} {m.overdue ? "· 超期" : ""} {m.progress.done_ratio != null ? `· ${Math.round(m.progress.done_ratio * 100)}%` : ""}
                  </span>
                </div>
              );
            })}
            <div className="h-4" />
          </div>
        </Card>
      ))}
    </div>
  );
}
