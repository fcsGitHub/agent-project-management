/** Approval center: pending list, bulk approve, diff preview, edit-and-resume. */
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import { Badge, Button, Card, Drawer, Empty, Input, cx } from "../components/ui";
import Markdown from "react-markdown";

export function ApprovalsPage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<{ path: string; content: string; diff: string } | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [comment, setComment] = useState("");

  const approvals = useQuery({
    queryKey: ["approvals", pid, "pending"],
    queryFn: () => api.listApprovals({ status: "pending", project_id: pid }),
    enabled: !!pid,
    refetchInterval: 4_000,
  });
  const decided = useQuery({
    queryKey: ["approvals", pid, "history"],
    queryFn: () => api.listApprovals({ project_id: pid }),
    enabled: !!pid,
  });

  const list = approvals.data?.approvals ?? [];
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["approvals"] });
    qc.invalidateQueries({ queryKey: ["runs"] });
  };

  const decide = async (id: string, decision: "approved" | "rejected" | "edit_and_resume", comment?: string) => {
    try {
      await api.decide(id, decision, comment);
      toast.success(decision === "approved" ? "已批准" : decision === "rejected" ? "已拒绝" : "已修改后恢复");
      refresh();
    } catch (e) {
      toast.error("决策失败", { description: String(e) });
    }
  };

  const openPreview = async (path?: string) => {
    if (!path || !pid) return;
    const art = await api.getArtifact(pid, path);
    setPreview({ path, content: art.content, diff: art.diff_vs_previous });
  };

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm font-semibold">审批中心</span>
        <Badge tone="amber">{list.length} 待处理</Badge>
        {selected.size > 0 && (
          <Button size="sm" variant="primary" className="ml-auto" onClick={async () => {
            await api.bulkDecide([...selected]);
            toast.success(`批量批准 ${selected.size} 项`);
            setSelected(new Set());
            refresh();
          }}>⏭ 批量批准（{selected.size}）</Button>
        )}
      </div>

      <div className="space-y-2">
        {list.map((a) => (
          <Card key={a.id} className={cx("p-3", selected.has(a.id) && "ring-2 ring-acc")}>
            <div className="flex items-start gap-3">
              <input type="checkbox" className="mt-1" checked={selected.has(a.id)} onChange={() => toggle(a.id)} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={a.kind === "gate" ? "amber" : "red"}>
                    {a.kind === "gate" ? `◆ ${a.payload_snapshot.gate}` : `⚠ ${a.payload_snapshot.tool}`}
                  </Badge>
                  {a.payload_snapshot.role && <Badge tone="violet">🤖 {a.payload_snapshot.role}</Badge>}
                  <span className="text-xs text-mut">{timeAgo(a.requested_at)}</span>
                  {a.conversation_id && pid && (
                    <Link to={`/p/${pid}/c/${a.conversation_id}`} className="text-xs text-acc hover:underline">转入对话 →</Link>
                  )}
                </div>
                <div className="mt-1 text-sm">{a.payload_snapshot.summary}</div>
                {a.payload_snapshot.artifact?.path && (
                  <button className="mt-1 text-xs text-acc hover:underline" onClick={() => openPreview(a.payload_snapshot.artifact!.path)}>
                    预览 {a.payload_snapshot.artifact.path}（commit {(a.payload_snapshot.artifact.commit ?? "").slice(0, 8)}）· diff
                  </button>
                )}
                {a.payload_snapshot.revise_notes?.length ? (
                  <div className="mt-1 text-xs text-warn">修订注入：{a.payload_snapshot.revise_notes.join("；")}</div>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col gap-1.5">
                <Button size="sm" variant="primary" onClick={() => decide(a.id, "approved", "中心批准")}>批准</Button>
                <Button size="sm" variant="outline" onClick={() => decide(a.id, "edit_and_resume", "修改后继续")}>修改后恢复</Button>
                <Button size="sm" variant="ghost" onClick={() => { setRejecting(a.id); setComment(""); }}>拒绝…</Button>
              </div>
            </div>
          </Card>
        ))}
        {!list.length && <Empty icon="✅" title="没有待审批" hint="Agent 到达阶段门或调用危险工具时会出现在这里" />}
      </div>

      {(decided.data?.approvals ?? []).filter((a) => a.status !== "pending").length > 0 && (
        <>
          <div className="mb-2 mt-6 text-xs font-semibold text-mut">已决策（最近）</div>
          <div className="space-y-1">
            {(decided.data?.approvals ?? [])
              .filter((a) => a.status !== "pending")
              .slice(0, 10)
              .map((a) => (
                <div key={a.id} className="flex items-center gap-2 px-1 text-xs text-mut">
                  <Badge tone={a.status === "approved" ? "green" : a.status === "rejected" ? "red" : "neutral"}>{a.status}</Badge>
                  <span>{a.payload_snapshot.gate ?? a.payload_snapshot.tool}</span>
                  <span>{a.comment}</span>
                  <span className="ml-auto">{timeAgo(a.decided_at)}</span>
                </div>
              ))}
          </div>
        </>
      )}

      <Drawer open={!!preview} onClose={() => setPreview(null)} title={preview?.path ?? ""} width="50%">
        {preview && (
          <div className="space-y-3">
            <div className="prose prose-zinc prose-sm max-w-none">
              <Markdown>{preview.content}</Markdown>
            </div>
            {preview.diff && (
              <details open>
                <summary className="cursor-pointer text-xs text-mut">diff vs 上一版</summary>
                <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-[11px]">{preview.diff}</pre>
              </details>
            )}
          </div>
        )}
      </Drawer>

      {rejecting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setRejecting(null)}>
          <div className="absolute inset-0 bg-black/25" />
          <Card className="relative z-10 w-full max-w-md p-4" onClick={(e) => e.stopPropagation()}>
            <div className="text-sm font-semibold">拒绝审批（理由必填 · fail-closed）</div>
            <Input className="mt-3" placeholder="拒绝理由" value={comment} onChange={(e) => setComment(e.target.value)} autoFocus />
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setRejecting(null)}>取消</Button>
              <Button variant="danger" disabled={!comment.trim()} onClick={async () => {
                await decide(rejecting, "rejected", comment);
                setRejecting(null);
              }}>拒绝</Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
