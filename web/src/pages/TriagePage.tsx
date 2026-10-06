/** M117-I358（docs/01 §DH，候选池①转正·Linear Triage 语义）：分诊队列页。
 * 外部入流（intake/IMAP）落本体 triage 态等人决定——本页=队列视图+三个
 * 决定动作：✅ 接受（→正常流转·可指派）/ ✕ 拒绝（→cancelled 组状态）/
 * 💤 暂缓 N 天（sweep 到期复浮——暂缓不是丢弃）。读面全走既有
 * list_items(status=triage)（事件溯源红利：零新读端点）。 */
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Badge, Button, Card, Empty, cx } from "../components/ui";

function relDays(iso: string): number {
  return Math.ceil((new Date(iso + "T00:00:00").getTime() - Date.now()) / 86_400_000);
}

export function TriagePage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const [showSnoozed, setShowSnoozed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const members = useQuery({
    queryKey: ["members", pid],
    queryFn: () => api.listMembers(pid!),
    enabled: !!pid,
  });
  const queue = useQuery({
    queryKey: ["triage-queue", pid],
    queryFn: () => api.listItems(pid!, { status: "triage", limit: 200 }),
    enabled: !!pid,
    refetchInterval: 15_000,
  });

  const rows = queue.data?.items ?? [];
  const today = new Date().toISOString().slice(0, 10);
  const snoozed = rows.filter((x) => x.snoozed_until && x.snoozed_until > today);
  const visible = showSnoozed ? rows : rows.filter((x) => !x.snoozed_until || x.snoozed_until <= today);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["triage-queue", pid] });
    qc.invalidateQueries({ queryKey: ["items", pid] });
  };

  const decide = async (iid: string, action: "accept" | "decline" | "snooze",
                        opts?: { days?: number; assignee_id?: string }) => {
    setBusy(iid);
    try {
      const r = await api.triageItem(iid, action, opts);
      toast.success(action === "accept" ? `已接受（→${r.status}）`
        : action === "decline" ? `已拒绝（→${r.status}）`
        : `已暂缓至 ${r.snoozed_until}（到期自动回队）`);
      invalidate();
    } catch (e) {
      toast.error(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  const memberOptions = useMemo(
    () => (members.data?.members ?? []).filter((m) => m.role !== "viewer"),
    [members.data]);

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">📥 分诊队列</h1>
          <p className="-mt-2 text-xs text-mut">
            外部入流先进分诊等人决定——接受进正常流转、拒绝进取消态、暂缓 N 天后自动回队（共 {rows.length} 项{!showSnoozed && snoozed.length ? ` · 另有 ${snoozed.length} 项暂缓中` : ""}）。
          </p>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-mut">
          <input type="checkbox" checked={showSnoozed}
            onChange={(e) => setShowSnoozed(e.target.checked)} />
          显示已暂缓
        </label>
      </div>

      {queue.isLoading && <div className="text-xs text-mut">加载队列…</div>}
      {queue.isError && <Card className="p-4 text-sm text-dan">队列加载失败：{String((queue.error as Error)?.message)}</Card>}
      {!queue.isLoading && !visible.length && (
        <Empty icon="📥" title="分诊队列为空"
          hint="外部 intake / 邮件入流的工作项会落在这里等人决定" />
      )}

      <div className="space-y-2">
        {visible.map((it) => {
          const snoozedDays = it.snoozed_until ? relDays(it.snoozed_until) : null;
          return (
            <Card key={it.id} className={cx("flex flex-wrap items-center gap-3 p-3",
              snoozedDays != null && snoozedDays > 0 && "opacity-70")}>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate text-sm font-medium">{it.title}</span>
                  <Badge>{it.concept_id}</Badge>
                  {it.priority && <Badge tone="amber">{it.priority}</Badge>}
                  {snoozedDays != null && snoozedDays > 0 && (
                    <Badge tone="neutral" title={`snoozed_until ${it.snoozed_until}`}>
                      💤 {snoozedDays} 天后回队
                    </Badge>
                  )}
                </div>
                <div className="text-[11px] text-mut" title={it.created_at}>
                  报告人 {it.assignee_id ?? "外部"} · {it.created_at.slice(0, 10)} 入队
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {memberOptions.length > 0 && (
                  <select aria-label={`接受 ${it.title} 后指派给`}
                    className="h-8 rounded-lg border border-line bg-surface px-2 text-xs"
                    defaultValue=""
                    onChange={(e) => e.target.value &&
                      decide(it.id, "accept", { assignee_id: e.target.value })}>
                    <option value="">✅ 接受并指派…</option>
                    {memberOptions.map((m) => (
                      <option key={m.user_id} value={m.user_id}>{m.name || m.user_id}</option>
                    ))}
                  </select>
                )}
                <Button size="sm" variant="primary" disabled={busy === it.id}
                  onClick={() => decide(it.id, "accept")}
                  title="进入正常流转（概念初始态）">✅ 接受</Button>
                <Button size="sm" disabled={busy === it.id}
                  onClick={() => decide(it.id, "snooze")}
                  title="暂缓 3 天——sweep 到期自动回队">💤 暂缓</Button>
                <Button size="sm" variant="danger" disabled={busy === it.id}
                  onClick={() => decide(it.id, "decline")}
                  title="拒绝——进入概念的取消态（task→cancelled / bug→wont_fix）">✕ 拒绝</Button>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
