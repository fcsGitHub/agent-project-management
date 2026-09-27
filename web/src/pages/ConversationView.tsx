/** Conversation view: persistent, interruptible human-agent interaction (docs/06 §3.3).
 * I138: assistant 生成内容经 run.token_delta 瞬态增量逐字渲染（不入库），
 * message.created 落库后自动切回权威全文。 */
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { onStreamEvent } from "../lib/sse";
import { clockOf } from "../lib/fmt";
import {
  Badge, Button, Collapse, Drawer, Empty, Textarea, CONV_STATUS, cx,
} from "../components/ui";

const STEP_ICON: Record<string, string> = {
  agent: "▣", generation: "⚙", tool: "🔧", gate: "◆", chain: "●", human_action: "👤", ui_command: "⌨",
};

export function ConversationView() {
  const { pid, cid } = useParams();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [ctxOpen, setCtxOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [refetchTimer, setRefetchTimer] = useState<number | null>(null);
  // I138: 当前 run 的流式增量缓冲——message.created 落库后清空（权威全文接管）
  const [streamBuf, setStreamBuf] = useState("");
  const [streamNode, setStreamNode] = useState<string | null>(null);

  const conv = useQuery({
    queryKey: ["conversation", cid],
    queryFn: () => api.getConversation(cid!),
    enabled: !!cid,
    refetchInterval: 2_000,
  });
  const ctx = useQuery({
    queryKey: ["context", cid],
    queryFn: () => api.getContext(cid!),
    enabled: !!cid,
  });
  const runs = useQuery({
    queryKey: ["runs", "conv", cid],
    queryFn: () => api.listRunsByConversation(cid!).then((r) => r.runs),
    enabled: !!cid,
  });

  const startRun = async (role?: string) => {
    const kind = conv.data?.kind ?? "adhoc";
    const agentRole = role ?? roleForKind(kind);
    try {
      await api.startRun({ conversation_id: cid!, agent_role: agentRole, item_id: conv.data?.item_id });
      toast.success(`已启动 ${agentRole}`);
    } catch (e) {
      toast.error(`启动 ${agentRole} 失败`, { description: String(e) });
    }
    qc.invalidateQueries({ queryKey: ["runs", "conv", cid] });
    qc.invalidateQueries({ queryKey: ["conversation", cid] });
  };

  const hasActiveRun = (runs.data ?? []).some((r) => ["running", "interrupted", "pending"].includes(r.status));
  const approvals = useQuery({
    queryKey: ["approvals", cid],
    queryFn: () => api.listApprovals({ status: "pending" }),
    enabled: !!cid,
    refetchInterval: 5_000,
  });

  const pending = (approvals.data?.approvals ?? []).find((a) => a.conversation_id === cid);

  // I138: 订阅流式增量——只认本对话的 token_delta；权威消息落库（refetch 后
  // messages 变化）即清缓冲，避免流式残影与落库文本并存。
  const lastMsgRef = useRef(conv.data?.messages?.length ?? 0);
  useEffect(() => {
    const off = onStreamEvent((e) => {
      if (e.event_type !== "run.token_delta") return;
      const d = e as unknown as { conversation_id?: string; delta?: string; node?: string };
      if (d.conversation_id !== cid || !d.delta) return;
      setStreamNode(d.node ?? null);
      setStreamBuf((b) => (b + d.delta).slice(-20_000));
    });
    return off;
  }, [cid]);
  useEffect(() => {
    const n = (conv.data?.messages?.length ?? 0);
    if (n !== lastMsgRef.current) {
      lastMsgRef.current = n;
      setStreamBuf("");
      setStreamNode(null);
    }
  }, [conv.data?.messages?.length]);
  useEffect(() => {
    // 对话切换/卸载：缓冲必须清零，防跨对话串流
    setStreamBuf("");
    setStreamNode(null);
    lastMsgRef.current = (conv.data?.messages?.length ?? 0);
  }, [cid]);
  // While a run is live, poll faster so streaming steps appear.
  useEffect(() => {
    const status = conv.data?.status;
    const interval = status === "running" ? 800 : null;
    if (interval && refetchTimer === null) {
      const t = window.setInterval(() => qc.invalidateQueries({ queryKey: ["conversation", cid] }), interval);
      setRefetchTimer(t);
    } else if (!interval && refetchTimer !== null) {
      clearInterval(refetchTimer);
      setRefetchTimer(null);
    }
    return () => {
      if (refetchTimer !== null) clearInterval(refetchTimer);
    };
  }, [conv.data?.status, cid, qc, refetchTimer]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conv.data?.messages?.length]);

  if (!cid) return null;
  const c = conv.data;
  if (conv.isError) return <div className="p-6 text-sm text-dan">对话加载失败，请刷新重试。</div>;
  if (!c) return <div className="p-6 text-sm text-mut">加载对话…</div>;

  const send = async () => {
    if (!text.trim()) return;
    const content = text;
    setText("");
    try {
      const r = await api.sendMessage(cid, content);
      if (r.interrupted) toast("已打断并注入指令", { description: "Run 将在下一可打断点挂起" });
      const kind = conv.data?.kind;
      const active = (runs.data ?? []).some((x) => ["running", "interrupted", "pending"].includes(x.status));
      if (!active && (kind === "drafting" || kind === "reviewing")) {
        await startRun();
      }
    } catch (e) {
      toast.error("发送失败", { description: String(e) });
    }
    qc.invalidateQueries({ queryKey: ["conversation", cid] });
    qc.invalidateQueries({ queryKey: ["runs", "conv", cid] });
  };

  const status = CONV_STATUS[c.status] ?? { label: c.status, tone: "neutral" };

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-sm font-semibold">{c.title ?? "对话"}</span>
        <Badge tone="indigo">{kindName(c.kind)}</Badge>
        <Badge tone={status.tone}>{status.label}</Badge>
        <div className="ml-auto flex gap-1.5">
          {(c.status === "running" || c.status === "active") && (
            <Button size="sm" onClick={async () => {
              await api.interruptConversation(cid);
              qc.invalidateQueries({ queryKey: ["conversation", cid] });
            }}>⏸ 打断</Button>
          )}
          {(c.status === "interrupted" || c.status === "awaiting_review") && (
            <Button size="sm" variant="primary" onClick={async () => {
              await api.resumeConversation(cid);
              toast.success("已恢复执行");
              qc.invalidateQueries();
            }}>▸ 继续</Button>
          )}
          {!hasActiveRun && c.status !== "archived" && (
            <Button size="sm" variant="outline" onClick={() => startRun()}>▶ 让 Agent 执行</Button>
          )}
          {/* M61-I184: Markdown transcript export (docs/01 §BF.3) */}
          <Button size="sm" variant="ghost" onClick={async () => {
            const x = await api.exportConversation(cid);
            const blob = new Blob([x.markdown], { type: "text/markdown;charset=utf-8" });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = x.filename;
            a.click();
            URL.revokeObjectURL(a.href);
          }}>⬇ 导出</Button>
          <Button size="sm" variant="ghost" onClick={() => setCtxOpen(true)}>-context 上下文</Button>
        </div>
      </div>

      {/* L3 summary line */}
      <button
        onClick={() => setCtxOpen(true)}
        className="border-b border-line bg-accbg/40 px-4 py-1.5 text-left text-xs text-mut hover:text-ink"
      >
        <span className="font-medium text-acc">L3 指令摘要：</span>
        {(c.instruction ?? "（无指令）").slice(0, 120)}
      </button>

      {/* pending approval banner */}
      {pending && (
        <div className="flex items-center gap-3 border-b border-warnln bg-warnbg px-4 py-2 text-xs">
          <span className="font-medium text-warn">
            ◆ {pending.kind === "gate" ? `等待审批：${pending.payload_snapshot.gate}` : `危险工具：${pending.payload_snapshot.tool}`}
          </span>
          <span className="min-w-0 flex-1 truncate text-mut">{pending.payload_snapshot.summary}</span>
          <Button size="sm" variant="primary" onClick={async () => {
            await api.decide(pending.id, "approved", "对话内批准");
            toast.success("已批准");
            qc.invalidateQueries();
          }}>批准</Button>
          <Button size="sm" variant="outline" onClick={async () => {
            await api.decide(pending.id, "edit_and_resume", "修改后继续");
            qc.invalidateQueries();
          }}>修改后恢复</Button>
        </div>
      )}

      {/* messages */}
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {(c.messages ?? []).map((m) => (
          <MessageRow key={m.id} m={m} pid={pid} />
        ))}
        {streamBuf && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-2xl border border-line bg-surface px-3.5 py-2 text-sm whitespace-pre-wrap break-words" data-testid="stream-bubble">
              {streamNode && <div className="mb-0.5 text-[10px] font-mono text-mut">🤖 {streamNode} · 生成中</div>}
              {streamBuf}
              <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-acc align-middle">▍</span>
            </div>
          </div>
        )}
        {!c.messages?.length && !streamBuf && (
          <Empty
            icon="💬"
            title="对话尚未开始"
            hint="发送第一条消息，或让 Agent 执行任务；执行中发送消息 = 打断并注入指令"
          />
        )}
        {c.status === "running" && !streamBuf && (
          <div className="flex items-center gap-2 px-2 text-xs text-ag">
            <span className="animate-pulse">●</span> Agent 执行中…（步骤将实时出现）
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* composer */}
      <div className="border-t border-line p-3">
        <div className="flex items-end gap-2">
          <Textarea
            rows={2}
            placeholder={c.status === "running" ? "输入消息（发送即打断并注入）…" : "输入消息…"}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
          />
          <Button variant="primary" onClick={send} disabled={!text.trim()}>发送</Button>
        </div>
      </div>

      <ContextDrawer open={ctxOpen} onClose={() => setCtxOpen(false)} cid={cid} ctx={ctx.data} />
    </div>
  );
}

function MessageRow({ m, pid }: { m: import("../lib/api").Message; pid?: string }) {
  const isUser = m.role === "user";
  const [spans, setSpans] = useState<import("../lib/api").Span[] | null>(null);
  return (
    <div className={cx("flex gap-2", isUser ? "justify-end" : "")}>
      {!isUser && (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-agbg text-xs">🤖</div>
      )}
      <div className={cx("max-w-[78%] space-y-1", isUser && "text-right")}>
        <div
          className={cx(
            "inline-block whitespace-pre-wrap rounded-[12px] px-3 py-2 text-sm",
            isUser ? "bg-acc text-white" : "border border-line bg-surface",
          )}
        >
          {m.content}
        </div>
        {m.span_id && (
          <div>
            <button
              className="text-[11px] text-mut hover:text-acc"
              onClick={async () => {
                if (spans) { setSpans(null); return; }
                // Fetch the run spans once for the step expansion
                const runId = (m.actor_id ?? "").split(":")[1];
                if (!runId) return;
                const r = await api.getSpans(runId);
                setSpans(r.spans);
              }}
            >
              ⚙ 查看执行步骤 ▾
            </button>
            {spans && (
              <div className="mt-1 space-y-1 rounded-lg border border-line bg-bg/60 p-2">
                {spans.map((s) => (
                  <div key={s.id} className="flex items-center gap-2 text-[11px] text-mut">
                    <span>{STEP_ICON[s.span_kind] ?? "•"}</span>
                    <span className="w-44 truncate font-mono">{s.name}</span>
                    <span>{s.status === "ok" ? "✓" : s.status === "interrupted" ? "⏸" : s.status}</span>
                    <span className="font-mono">
                      {s.attributes?.["gen_ai.usage.input_tokens"]
                        ? `${String(s.attributes["gen_ai.usage.input_tokens"])}→${String(s.attributes["gen_ai.usage.output_tokens"])} tok`
                        : ""}
                    </span>
                    {s.attributes?.["apm.diff_ref"] ? (
                      <span className="truncate font-mono text-acc">{String(s.attributes["apm.diff_ref"])}</span>
                    ) : null}
                  </div>
                ))}
                {pid && (
                  <a className="text-[11px] text-acc hover:underline" href={`#/p/${pid}/runs`}>
                    打开完整轨迹（左树右甘特）→
                  </a>
                )}
              </div>
            )}
          </div>
        )}
        <div className="px-1 text-[10px] text-mut">{clockOf(m.created_at)}</div>
      </div>
      {isUser && (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accbg text-xs">👤</div>
      )}
    </div>
  );
}

function ContextDrawer({
  open, onClose, cid, ctx,
}: {
  open: boolean; onClose: () => void; cid: string;
  ctx: import("../lib/api").Context | undefined;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<"L1" | "L3" | null>(null);
  const [draft, setDraft] = useState("");

  if (!ctx) return null;

  const save = async () => {
    if (!editing) return;
    await api.putContext(cid, editing, draft);
    toast.success(`${editing} 已保存为新版本（对新消息生效，历史不重写）`);
    setEditing(null);
    qc.invalidateQueries({ queryKey: ["context", cid] });
  };

  const Layer = ({ id, title, content, editable, version }: {
    id: string; title: string; content?: string | null; editable?: boolean; version?: number;
  }) => (
    <Collapse title={
      <span className="flex items-center gap-2">
        <Badge tone={id === "L1" ? "indigo" : id === "L3" ? "violet" : "neutral"}>{id}</Badge>
        {title}
        {version !== undefined && <span className="text-[10px] text-mut">v{version}</span>}
      </span>
    }>
      <pre className="max-h-56 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed">{content ?? "（空）"}</pre>
      {editable && (
        <div className="mt-2">
          {editing === id ? (
            <div className="space-y-2">
              <Textarea rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} />
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>取消</Button>
                <Button size="sm" variant="primary" onClick={save}>保存（生成版本）</Button>
              </div>
            </div>
          ) : (
            <Button size="sm" variant="outline" onClick={() => { setEditing(id as "L1" | "L3"); setDraft(content ?? ""); }}>
              ✎ 编辑
            </Button>
          )}
        </div>
      )}
    </Collapse>
  );

  return (
    <Drawer open={open} onClose={onClose} title={`上下文分层 · ${cid}`}>
      <div className="space-y-2">
        <Layer id="L0" title="全局系统提示" content={ctx.L1 ? undefined : undefined} />
        <Layer id="L1" title="项目宪章 Charter" content={ctx.L1.content} editable={ctx.L1.editable} version={ctx.L1.version} />
        <Layer id="L2" title="功能简报 Brief" content={ctx.L2.content} />
        <Layer id="L3" title="会话指令 Instruction" content={ctx.L3.content} editable={ctx.L3.editable} version={ctx.L3.version} />
        <Collapse title={<span className="flex items-center gap-2"><Badge tone="neutral">L4</Badge>角色提示词</span>}>
          <div className="text-mut">由角色 YAML 提供（agents/roles/*.yaml → prompts/roles/*.md），新 Run 生效。</div>
        </Collapse>
        <Collapse title="👁 查看合并后的有效提示词（含来源标注）" defaultOpen={false}>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed">{ctx.merged_preview}</pre>
        </Collapse>
      </div>
    </Drawer>
  );
}

function kindName(kind: string) {
  return { drafting: "起草", executing: "执行", reviewing: "评审", adhoc: "临时", ui_command: "操作" }[kind] ?? kind;
}

function roleForKind(kind: string) {
  return { drafting: "pm-agent", executing: "dev-agent", reviewing: "release-agent", adhoc: "pm-agent", ui_command: "pm-agent" }[kind] ?? "dev-agent";
}
