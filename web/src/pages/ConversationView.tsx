/** Conversation view: persistent, interruptible human-agent interaction (docs/06 §3.3).
 * I138: assistant 生成内容经 run.token_delta 瞬态增量逐字渲染（不入库），
 * message.created 落库后自动切回权威全文。 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
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
  const nav = useNavigate();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [ctxOpen, setCtxOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [refetchTimer, setRefetchTimer] = useState<number | null>(null);
  // I138: 当前 run 的流式增量缓冲——message.created 落库后清空（权威全文接管）
  const [streamBuf, setStreamBuf] = useState("");
  const [streamNode, setStreamNode] = useState<string | null>(null);
  // I208: `/` 唤起指令模板浮层（草稿非快捷键——选中填入可改后发送）
  const [tplOpen, setTplOpen] = useState(false);
  const [tplIndex, setTplIndex] = useState(0);
  const [mgrOpen, setMgrOpen] = useState(false);

  const templatesQ = useQuery({
    queryKey: ["prompt-templates", pid],
    queryFn: () => api.listPromptTemplates(pid!),
    enabled: !!pid,
  });
  const tplMatches = (templatesQ.data?.templates ?? []).filter((t) => {
    if (!text.startsWith("/")) return false;
    const q = text.slice(1).trim().toLowerCase();
    return !q || t.title.toLowerCase().includes(q);
  });

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

  const startRun = async (role?: string, itemIdOverride?: string | null) => {
    const kind = conv.data?.kind ?? "adhoc";
    const agentRole = role ?? roleForKind(kind);
    try {
      // I212: 一次性工件绑定——选择器指定的 item 只作用于本次 run，
      // 不写回对话的预绑定（conv.item_id 语义不变）。
      await api.startRun({
        conversation_id: cid!, agent_role: agentRole,
        item_id: itemIdOverride !== undefined ? itemIdOverride : conv.data?.item_id,
      });
      toast.success(`已启动 ${agentRole}`, {
        description: itemIdOverride ? "本次运行绑定所选工件" : undefined,
      });
    } catch (e) {
      toast.error(`启动 ${agentRole} 失败`, { description: String(e) });
    }
    qc.invalidateQueries({ queryKey: ["runs", "conv", cid] });
    qc.invalidateQueries({ queryKey: ["conversation", cid] });
  };

  const hasActiveRun = (runs.data ?? []).some((r) => ["running", "interrupted", "pending"].includes(r.status));

  // I212: 工件选择器数据源——本体声明 artifact_kinds 的概念下的活跃工件项
  const ontoQ = useQuery({
    queryKey: ["ontology", pid],
    queryFn: () => api.getOntology(pid!, true),
    enabled: !!pid,
  });
  const artifactConcepts = useMemo(
    () => new Set((ontoQ.data?.concepts ?? []).filter((c) => (c.artifact_kinds ?? []).length).map((c) => c.id)),
    [ontoQ.data],
  );
  const artifactItems = useQuery({
    queryKey: ["items", pid, "artifact-picker"],
    queryFn: () => api.listItems(pid!, { limit: 200 }),
    enabled: !!pid && artifactConcepts.size > 0,
    select: (d: { items: import("../lib/api").Item[] }) =>
      d.items.filter((i) => artifactConcepts.has(i.concept_id)
        && ["open", "ready", "in_progress"].includes(i.status)),
  });
  const [pickItem, setPickItem] = useState("");
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
            <>
              {artifactItems.data && artifactItems.data.length > 0 && (
                <select value={pickItem} onChange={(e) => setPickItem(e.target.value)}
                  className="rounded-lg border border-line bg-surface px-2 py-1 text-xs"
                  title="本次运行绑定的工件（一次性——不改变对话的预绑定）">
                  <option value="">工件：{c.item_id ? "对话预绑定" : "不绑定"}</option>
                  {artifactItems.data.map((i) => (
                    <option key={i.id} value={i.id}>📌 {i.title}</option>
                  ))}
                </select>
              )}
              <Button size="sm" variant="outline"
                onClick={() => startRun(undefined, pickItem || undefined)}>▶ 让 Agent 执行</Button>
            </>
          )}
          {/* M66-I198: ChatGPT "Branch in new chat" — child conversation on the
              parent_conversation_id lineage; the tree view surfaces it. */}
          {c.status !== "archived" && (
            <Button size="sm" variant="ghost" title="以本对话为父建立分支对话（树形视图可见血缘）"
              onClick={async () => {
                try {
                  const child = await api.createConversation({
                    project_id: c.project_id,
                    feature_id: c.feature_id,
                    kind: c.kind,
                    title: `${c.title ?? "对话"} · 分支`,
                    instruction: c.instruction,
                    parent_conversation_id: cid,
                  });
                  toast.success("已建分支对话", { description: "树形列表可见血缘" });
                  nav(`/p/${c.project_id}/c/${child.id}`);
                } catch (e) {
                  toast.error("分支失败", { description: String(e) });
                }
              }}>⑂ 分支</Button>
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
          <Button size="sm" variant="ghost" onClick={() => setMgrOpen(true)}
            title="指令模板库——常用指令存为可复用草稿（Copilot .prompt.md 语义）">📋 模板</Button>
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
        <div className="relative flex items-end gap-2">
          {tplOpen && tplMatches.length > 0 && (
            <div className="absolute bottom-full left-0 z-30 mb-1 w-96 rounded-xl border border-line bg-surface p-1 shadow-lg">
              <div className="px-2 py-1 text-[10px] text-mut">指令模板（↑↓ 选择 · Enter 填入 · Esc 关闭）——填入后可编辑再发送</div>
              {tplMatches.map((t, i) => (
                <button key={t.id}
                  className={cx("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs",
                    i === tplIndex ? "bg-accbg text-acc" : "hover:bg-bg")}
                  onMouseEnter={() => setTplIndex(i)}
                  onClick={() => pickTemplate(t)}>
                  <span className="font-medium">📋 {t.title}</span>
                  {t.agent_role && <Badge tone="violet">{t.agent_role}</Badge>}
                  <span className="min-w-0 flex-1 truncate text-[10px] text-mut">{t.body}</span>
                </button>
              ))}
            </div>
          )}
          <Textarea
            rows={2}
            placeholder={c.status === "running" ? "输入消息（发送即打断并注入）…（/ 唤起指令模板）" : "输入消息…（/ 唤起指令模板）"}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setTplOpen(e.target.value.startsWith("/"));
              setTplIndex(0);
            }}
            onKeyDown={(e) => {
              if (tplOpen && tplMatches.length > 0) {
                if (e.key === "ArrowDown") { e.preventDefault(); setTplIndex((i) => (i + 1) % tplMatches.length); return; }
                if (e.key === "ArrowUp") { e.preventDefault(); setTplIndex((i) => (i - 1 + tplMatches.length) % tplMatches.length); return; }
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); pickTemplate(tplMatches[tplIndex]); return; }
                if (e.key === "Escape") { e.preventDefault(); setTplOpen(false); return; }
              }
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
          />
          <Button variant="primary" onClick={send} disabled={!text.trim()}>发送</Button>
        </div>
      </div>

      <ContextDrawer open={ctxOpen} onClose={() => setCtxOpen(false)} cid={cid} ctx={ctx.data} />
      {mgrOpen && <TemplatesDrawer pid={pid!} onClose={() => setMgrOpen(false)} />}
    </div>
  );

  function pickTemplate(t: import("../lib/api").PromptTemplate) {
    setText(t.body);
    setTplOpen(false);
  }
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

/** I208: 指令模板管理抽屉——列表/新建/编辑/删除。模板是草稿不是快捷键：
 * body 填入输入框后仍可编辑，发送前的人审不绕过。 */
function TemplatesDrawer({ pid, onClose }: { pid: string; onClose: () => void }) {
  const qc = useQueryClient();
  const templates = useQuery({
    queryKey: ["prompt-templates", pid],
    queryFn: () => api.listPromptTemplates(pid),
  });
  const onto = useQuery({
    queryKey: ["ontology", pid],
    queryFn: () => api.getOntology(pid, true),
  });
  const roleOptions = [...new Set((onto.data?.concepts ?? []).flatMap((c) => c.agent_roles ?? []))];
  const [editId, setEditId] = useState<string | null>(null); // null=新建
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [role, setRole] = useState("");
  const [busy, setBusy] = useState(false);

  const openNew = () => { setEditId(null); setTitle(""); setBody(""); setRole(""); };
  const openEdit = (t: import("../lib/api").PromptTemplate) => {
    setEditId(t.id); setTitle(t.title); setBody(t.body); setRole(t.agent_role ?? "");
  };

  const submit = async () => {
    setBusy(true);
    try {
      if (editId) await api.updatePromptTemplate(editId, { title, body, agent_role: role || null });
      else await api.createPromptTemplate(pid, { title, body, agent_role: role || null });
      toast.success(editId ? "模板已更新" : "模板已创建");
      qc.invalidateQueries({ queryKey: ["prompt-templates", pid] });
      openNew();
    } catch (e) {
      toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (t: import("../lib/api").PromptTemplate) => {
    if (!window.confirm(`删除模板「${t.title}」？`)) return;
    try {
      await api.deletePromptTemplate(t.id);
      if (editId === t.id) openNew();
      qc.invalidateQueries({ queryKey: ["prompt-templates", pid] });
      toast.info("模板已删除");
    } catch (e) {
      toast.error(`删除失败：${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <Drawer open onClose={onClose} title="📋 指令模板库" width="48%">
      <div className="space-y-3 text-xs">
        {(templates.data?.templates ?? []).map((t) => (
          <div key={t.id} className={cx("rounded-xl border p-2.5", editId === t.id ? "border-acc" : "border-line")}>
            <div className="flex items-center gap-2">
              <span className="font-medium">📋 {t.title}</span>
              {t.agent_role && <Badge tone="violet">{t.agent_role}</Badge>}
              <span className="text-[10px] text-mut">v{t.version} · {clockOf(t.updated_at)}</span>
              <span className="ml-auto flex gap-1">
                <button className="text-[11px] text-mut hover:text-acc" onClick={() => openEdit(t)}>✎ 编辑</button>
                <button className="text-[11px] text-mut hover:text-dan" onClick={() => remove(t)}>🗑</button>
              </span>
            </div>
            <div className="mt-1 whitespace-pre-wrap text-[11px] text-mut">{t.body}</div>
          </div>
        ))}
        {!templates.data?.templates.length && (
          <Empty icon="📋" title="还没有指令模板"
            hint="把高频发起指令（如「生成 XX 功能 PRD」）存为模板，对话输入框输入 / 即可唤起" />
        )}
        {/* I215: watch-rules 对称面——导出项目无关 JSON，导入他项目（重名跳过） */}
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={!templates.data?.templates.length}
            onClick={async () => {
              try {
                const x = await api.exportPromptTemplates(pid);
                const blob = new Blob([JSON.stringify(x, null, 2)], { type: "application/json" });
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = `prompt-templates-${pid}.json`;
                a.click();
                URL.revokeObjectURL(a.href);
              } catch (e) {
                toast.error(`导出失败：${e instanceof Error ? e.message : e}`);
              }
            }}>⬇ 导出</Button>
          <label className="cursor-pointer rounded-lg border border-line px-2 py-1 text-[11px] hover:border-acc">
            ⬆ 导入 JSON
            <input type="file" accept=".json,application/json" className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (!f) return;
                try {
                  const parsed = JSON.parse(await f.text());
                  const r = await api.importPromptTemplates(pid, parsed.templates ?? []);
                  toast.success(`导入完成：新增 ${r.imported} · 重名跳过 ${r.skipped}`);
                  qc.invalidateQueries({ queryKey: ["prompt-templates", pid] });
                } catch (err) {
                  toast.error(`导入失败：${err instanceof Error ? err.message : err}`);
                }
              }} />
          </label>
          <span className="text-[10px] text-mut">导入到其他项目时重名模板自动跳过，不会覆盖本地修改</span>
        </div>
        <div className="space-y-2 rounded-xl border border-line p-2.5">
          <div className="font-medium">{editId ? "✎ 编辑模板" : "＋ 新建模板"}</div>
          <div className="flex gap-2">
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="模板名称（如：生成 PRD）"
              className="min-w-0 flex-1 rounded-lg border border-line bg-bg px-2 py-1.5" />
            <select value={role} onChange={(e) => setRole(e.target.value)}
              className="rounded-lg border border-line bg-bg px-2 py-1.5" title="建议角色（可选）">
              <option value="">角色：不限</option>
              {roleOptions.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <Textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)}
            placeholder="指令内容——选中后填入输入框，可改再发送" />
          <div className="flex justify-end gap-2">
            {editId && <Button size="sm" variant="ghost" onClick={openNew}>取消编辑</Button>}
            <Button size="sm" variant="primary" disabled={busy || !title.trim() || !body.trim()} onClick={submit}>
              {editId ? "保存" : "创建"}
            </Button>
          </div>
        </div>
      </div>
    </Drawer>
  );
}

function roleForKind(kind: string) {
  return { drafting: "pm-agent", executing: "dev-agent", reviewing: "release-agent", adhoc: "pm-agent", ui_command: "pm-agent" }[kind] ?? "dev-agent";
}
