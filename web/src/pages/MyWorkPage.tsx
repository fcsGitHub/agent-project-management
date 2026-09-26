/** My work page (M12-I39): the cross-project "my page" (docs/01 §K.1) —
 * active items assigned to me plus gates awaiting my decision. Assignment is
 * authorization: items show regardless of membership; gates follow the same
 * decision rights as approval notifications (owner / instance admin).
 * M21-I66: iCal calendar subscription card (docs/01 §T.3). */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { fmtMinutes } from "../components/TimeLogModal";
import { api } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import { Badge, Button, Card, Empty } from "../components/ui";

const GROUP_LABEL: Record<string, string> = {
  backlog: "待办池", todo: "就绪", in_progress: "进行中", done: "已完成", cancelled: "已取消",
};

export function MyWorkPage() {
  const work = useQuery({ queryKey: ["my-work"], queryFn: api.getMyWork, refetchInterval: 15_000 });
  // M59-I177: 行动视角——「什么在等我动手」（与任务视角正交；分区点击跳原生操作页）
  const attention = useQuery({ queryKey: ["my-attention"], queryFn: api.getMyAttention, refetchInterval: 15_000 });
  const att = attention.data;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-sm font-semibold">📋 我的工作</span>
        <span className="text-xs text-mut">跨项目聚合 · 指派给我的活跃项 + 等我决策的 Gate</span>
        <span className="ml-auto text-xs text-mut">
          {work.data?.items.length ?? 0} 项工作 · {work.data?.approvals.length ?? 0} 个待决策
          {(work.data?.week_minutes ?? 0) > 0 &&
            <> · 本周工时 <span className="font-medium text-acc">{fmtMinutes(work.data!.week_minutes ?? 0)}</span></>}
        </span>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto p-4 md:grid-cols-3">
        {att && (att.counts.approvals + att.counts.runs + att.counts.due > 0) && (
          <Card className="p-4 md:col-span-3">
            <div className="mb-2 text-sm font-semibold">⏳ 等待我</div>
            <div className="grid gap-3 text-xs md:grid-cols-3">
              <div>
                <Link to={att.approvals[0] ? `/p/${att.approvals[0].project_id}/approvals` : "#"}
                  className="font-medium text-acc hover:underline">
                  待我审批 · {att.counts.approvals}
                </Link>
                {att.approvals.slice(0, 3).map((a) => (
                  <Link key={a.id} to={`/p/${a.project_id}/approvals`}
                    className="mt-1 block truncate text-mut hover:text-acc" title={a.project_name}>
                    · {a.project_name} · {a.kind === "gate" ? "阶段门" : "工件审批"}
                  </Link>
                ))}
              </div>
              <div>
                <Link to={att.runs[0] ? `/p/${att.runs[0].project_id}/runs` : "#"}
                  className="font-medium text-acc hover:underline">
                  等我恢复的运行 · {att.counts.runs}
                </Link>
                {att.runs.slice(0, 3).map((r) => (
                  <Link key={r.id} to={`/p/${r.project_id}/runs?run=${r.id}`}
                    className="mt-1 block truncate text-mut hover:text-acc" title={r.project_name}>
                    · {r.project_name} · {r.agent_role ?? "agent"}
                  </Link>
                ))}
              </div>
              <div>
                <span className="font-medium text-acc">我的临期项 · {att.counts.due}</span>
                {att.due.slice(0, 3).map((d) => (
                  <Link key={d.id} to={`/p/${d.project_id}/board?item=${d.id}`}
                    className="mt-1 block truncate text-mut hover:text-acc" title={d.title}>
                    · {d.due_date} {d.title}
                  </Link>
                ))}
              </div>
            </div>
          </Card>
        )}
        <Card className="p-4 md:col-span-2">
          <div className="mb-2 text-sm font-semibold">分配给我</div>
          <div className="space-y-1.5">
            {(work.data?.items ?? []).map((it) => (
              <Link
                key={it.id}
                to={`/p/${it.project_id}/board`}
                className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs hover:border-acc"
              >
                <span className="w-28 shrink-0 truncate text-mut">{it.project_name}</span>
                <span className="flex-1 truncate font-medium">{it.title}</span>
                <Badge tone="neutral">{it.concept_id}</Badge>
                <Badge tone={it.status_group === "in_progress" ? "amber" : "neutral"}>
                  {GROUP_LABEL[it.status_group] ?? it.status_group}
                </Badge>
                <span className="shrink-0 text-mut">{timeAgo(it.updated_at)}</span>
              </Link>
            ))}
            {work.isError && <Empty title="加载失败" hint="我的工作项拉取失败，请刷新重试" />}
            {!work.isError && work.isLoading && <div className="py-6 text-center text-xs text-mut">加载中…</div>}
            {!work.isError && !work.isLoading && !work.data?.items.length && (
              <Empty title="暂无指派给我的工作项" hint="在看板卡片上被指派后会出现在这里" />
            )}
          </div>
        </Card>

        <Card className="p-4">
          <div className="mb-2 text-sm font-semibold">◆ 等我决策</div>
          <div className="space-y-2">
            {(work.data?.approvals ?? []).map((a) => (
              <Link
                key={a.id}
                to={`/p/${a.project_id}/approvals`}
                className="block rounded-lg border border-line px-3 py-2 text-xs hover:border-acc"
              >
                <div className="flex items-center gap-2">
                  <span className="flex-1 truncate font-medium">{a.project_name}</span>
                  <Badge tone="amber">{a.kind === "gate" ? "阶段门" : "工件审批"}</Badge>
                </div>
                <div className="mt-0.5 text-mut">{a.requested_at ? timeAgo(a.requested_at) : ""} 请求</div>
              </Link>
            ))}
            {!work.data?.approvals.length && <Empty title="没有待你决策的审批" hint="项目 Owner 的 Gate 请求会出现在这里" />}
          </div>
        </Card>

        <CalendarSubCard />
      </div>
    </div>
  );
}

/** M21-I66: personal iCal subscription — the URL carries the M11 feed key, so
 * the calendar client authenticates without cookies (rotate invalidates). */
function CalendarSubCard() {
  const [key, setKey] = useState<string | null>(null);
  const url = key ? `${location.origin}/api/my/calendar.ics?key=${key}` : "";
  return (
    <Card className="p-4 md:col-span-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-sm font-semibold">📅 订阅日历</span>
        <span className="text-mut">指派给我的截止 + 可见项目的里程碑，导入本地日历（只读）</span>
        {!key ? (
          <Button size="sm" variant="primary" className="ml-auto"
            onClick={async () => {
              try { setKey((await api.getFeedKey()).feed_key); }
              catch (e) { toast.error(`获取订阅密钥失败：${e instanceof Error ? e.message : e}`); }
            }}>
            显示订阅链接
          </Button>
        ) : (
          <>
            <code data-testid="ical-url" className="ml-auto max-w-md truncate rounded bg-bg px-2 py-1">{url}</code>
            <Button size="sm" onClick={async () => {
              try { await navigator.clipboard.writeText(url); toast.success("已复制订阅链接"); }
              catch { toast.error("复制失败——请手动选择链接"); }
            }}>复制</Button>
            <Button size="sm" variant="ghost" title="换发后旧链接立即失效"
              onClick={async () => {
                try { setKey((await api.rotateFeedKey()).feed_key); toast.success("已换发订阅密钥"); }
                catch (e) { toast.error(`换发失败：${e instanceof Error ? e.message : e}`); }
              }}>换发密钥</Button>
          </>
        )}
      </div>
    </Card>
  );
}
