/** My work page (M12-I39): the cross-project "my page" (docs/01 §K.1) —
 * active items assigned to me plus gates awaiting my decision. Assignment is
 * authorization: items show regardless of membership; gates follow the same
 * decision rights as approval notifications (owner / instance admin).
 * M21-I66: iCal calendar subscription card (docs/01 §T.3). */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
        <ApiTokenCard />
        <PushConfigCard />
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

/** M66-I199: personal access tokens (docs/01 §BK.2) — machine access with
 * GitHub PAT semantics: raw shown once, optional expiry, last-used badge,
 * immediate revoke. Bearer acts as this user; fine-grained scopes cut. */
function ApiTokenCard() {
  const qc = useQueryClient();
  const tokens = useQuery({ queryKey: ["api-tokens"], queryFn: api.listTokens });
  const [name, setName] = useState("");
  const [days, setDays] = useState<string>("30");
  const [fresh, setFresh] = useState<{ token: string } | null>(null);
  const rows = tokens.data?.tokens ?? [];
  return (
    <Card className="p-4 md:col-span-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-semibold">🔑 API 令牌</span>
        <span className="text-xs text-mut">外部脚本/agent 以你的身份调 API：请求头 Authorization: Bearer apm_…（明文只显示一次）</span>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="用途，如 CI 发布脚本"
          className="w-48 rounded-lg border border-line bg-surface px-2 py-1" />
        <select value={days} onChange={(e) => setDays(e.target.value)}
          className="rounded-lg border border-line bg-surface px-2 py-1" aria-label="订阅链接有效期">
          <option value="7">7 天过期</option>
          <option value="30">30 天过期</option>
          <option value="60">60 天过期</option>
          <option value="90">90 天过期</option>
          <option value="">永不过期</option>
        </select>
        <Button size="sm" variant="primary" onClick={async () => {
          if (!name.trim()) { toast.error("先填令牌用途名"); return; }
          try {
            const r = await api.createToken({ name: name.trim(), expires_in_days: days ? Number(days) : null });
            setFresh({ token: r.token });
            setName("");
            qc.invalidateQueries({ queryKey: ["api-tokens"] });
          } catch (e) { toast.error(`创建失败：${e instanceof Error ? e.message : e}`); }
        }}>创建令牌</Button>
        {fresh && (
          <code data-testid="fresh-token" className="max-w-md truncate rounded bg-accbg px-2 py-1 font-medium text-acc"
            title="关闭后无法再次查看，请立即复制">
            {fresh.token}
          </code>
        )}
        {fresh && <Button size="sm" onClick={async () => {
          try { await navigator.clipboard.writeText(fresh.token); toast.success("已复制令牌"); }
          catch { toast.error("复制失败——请手动选择"); }
        }}>复制</Button>}
      </div>
      <div className="space-y-1.5">
        {rows.map((t) => (
          <div key={t.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs">
            <code className="shrink-0 text-mut">{t.prefix}…</code>
            <span className="flex-1 truncate font-medium">{t.name}</span>
            <Badge tone={t.revoked_at ? "dan" : t.expires_at && t.expires_at <= new Date().toISOString() ? "amber" : "ok"}>
              {t.revoked_at ? "已吊销" : t.expires_at ? `至 ${t.expires_at.slice(0, 10)}` : "永不过期"}
            </Badge>
            <span className="shrink-0 text-mut">{t.last_used_at ? `最近使用 ${timeAgo(t.last_used_at)}` : "从未使用"}</span>
            {!t.revoked_at && (
              <Button size="sm" variant="ghost" onClick={async () => {
                try { await api.revokeToken(t.id); toast.success("已吊销"); qc.invalidateQueries({ queryKey: ["api-tokens"] }); }
                catch (e) { toast.error(`吊销失败：${e instanceof Error ? e.message : e}`); }
              }}>吊销</Button>
            )}
          </div>
        ))}
        {!rows.length && <Empty title="还没有 API 令牌" hint="创建后即可用 curl / 脚本免登录调用 API" />}
      </div>
    </Card>
  );
}

/** M67-I202 (docs/01 §BL.2): ntfy push target — the third physical delivery
 * channel. Own-data runtime preference; SSRF guard applies server-side. */
function PushConfigCard() {
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: ["push-config"], queryFn: api.getPushConfig });
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  return (
    <Card className="p-4 md:col-span-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">📲 推送通知（ntfy）</span>
        <span className="text-xs text-mut">
          自托管 ntfy 主题 URL（https）；配置后在铃铛偏好里按事件类型开推送——静默时段对推送同样生效
        </span>
        {cfg.data?.push_url && <Badge tone="ok">已配置</Badge>}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <input value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder={cfg.data?.push_url ?? "https://ntfy.example.com/我的主题"}
          className="w-72 rounded-lg border border-line bg-surface px-2 py-1" />
        <input value={token} onChange={(e) => setToken(e.target.value)} type="password"
          placeholder={cfg.data?.has_token ? "访问令牌已存（重填可更换）" : "访问令牌（可选）"}
          className="w-56 rounded-lg border border-line bg-surface px-2 py-1" />
        <Button size="sm" variant="primary" onClick={async () => {
          try {
            await api.setPushConfig({ push_url: url.trim() || null, push_token: token.trim() || null });
            toast.success("推送配置已保存");
            setUrl(""); setToken("");
            qc.invalidateQueries({ queryKey: ["push-config"] });
          } catch (e) {
            toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
          }
        }}>保存</Button>
        {cfg.data?.push_url && (
          <Button size="sm" variant="ghost" onClick={async () => {
            try {
              await api.setPushConfig({ push_url: null, push_token: null });
              toast.success("已清除推送配置");
              qc.invalidateQueries({ queryKey: ["push-config"] });
            } catch (e) {
              toast.error(`清除失败：${e instanceof Error ? e.message : e}`);
            }
          }}>清除</Button>
        )}
      </div>
    </Card>
  );
}
