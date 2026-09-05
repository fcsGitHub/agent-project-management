/** Work-item comments drawer (M18-I57): thread list + composer with @mention
 * completion against project members/users. Reused by Board cards and slices.
 * M20-I64: bodies render as read-only GFM (marked + DOMPurify, docs/01 §S.3);
 * storage stays plain text, composer gains an edit/preview toggle.
 * M26-I81: author-only inline editing with an "edited" badge and a revision
 * history expansion (event-sourced comment_revisions — GitLab #3706, closed). */
import { useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { renderCommentMd } from "../lib/md";
import { Button, Modal } from "./ui";

const MD_BODY = "mt-1 text-ink [&_a]:text-acc [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-line [&_blockquote]:pl-2 [&_code]:rounded [&_code]:bg-bg [&_code]:px-1 [&_h1]:text-sm [&_h1]:font-semibold [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:font-semibold [&_img]:max-w-full [&_input]:mr-1 [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-4 [&_p]:my-1 [&_pre]:overflow-x-auto [&_pre]:rounded [&_pre]:bg-bg [&_pre]:p-2 [&_td]:border [&_td]:border-line [&_td]:px-1.5 [&_th]:border [&_th]:border-line [&_th]:px-1.5 [&_ul]:list-disc [&_ul]:pl-4";

// M23-I73: GitHub markdown-toolbar semantics — buttons wrap the textarea
// selection (or insert a placeholder) and keep focus/selection for chaining.
type Tool = { label: string; title: string; wrap?: [string, string]; linePrefix?: string };
const TOOLS: Tool[] = [
  { label: "B", title: "加粗", wrap: ["**", "**"] },
  { label: "I", title: "斜体", wrap: ["*", "*"] },
  { label: "‹›", title: "行内代码", wrap: ["`", "`"] },
  { label: "🔗", title: "链接", wrap: ["[", "](https://)"] },
  { label: "• 列表", title: "无序列表", linePrefix: "- " },
  { label: "☑ 任务", title: "任务清单", linePrefix: "- [ ] " },
  { label: "❝ 引用", title: "引用", linePrefix: "> " },
];

export function CommentsModal({ itemId, title, onClose }: {
  itemId: string; title?: string; onClose: () => void;
}) {
  const qc = useQueryClient();
  const { pid } = useParams();
  const [draft, setDraft] = useState("");
  const [preview, setPreview] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [historyId, setHistoryId] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const comments = useQuery({
    queryKey: ["comments", itemId],
    queryFn: () => api.listItemComments(itemId),
  });
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const revisions = useQuery({
    queryKey: ["comment-revisions", historyId],
    queryFn: () => api.listCommentRevisions(historyId!),
    enabled: !!historyId,
  });

  // M26-I81: save an inline edit (author-only endpoint; 403 surfaces as toast)
  const saveEdit = useMutation({
    mutationFn: (v: { id: string; body: string }) => api.editComment(v.id, { body: v.body }),
    onSuccess: () => {
      setEditingId(null);
      qc.invalidateQueries();
    },
    onError: (e) => toast.error(`编辑失败：${e instanceof Error ? e.message : e}`),
  });

  // I67: delegated clicks on the per-comment「转为子任务」buttons
  const extract = useMutation({
    mutationFn: (v: { commentId: string; text: string }) => api.extractTask(v.commentId, { text: v.text }),
    onSuccess: (r) => {
      toast.success(`已转为子任务：${r.item.title}`);
      qc.invalidateQueries();
    },
    onError: (e) => toast.error(`转换失败：${e instanceof Error ? e.message : e}`),
  });
  const onBodyClick = (commentId: string) => (e: React.MouseEvent<HTMLDivElement>) => {
    const btn = (e.target as HTMLElement).closest("[data-extract]") as HTMLElement | null;
    if (btn) extract.mutate({ commentId, text: btn.getAttribute("data-extract")! });
  };

  // mention completion candidates: names not already typed after the last '@'
  const candidates = useMemo(() => {
    const at = draft.lastIndexOf("@");
    if (at < 0) return [];
    const typed = draft.slice(at + 1);
    if (typed.includes(" ")) return [];
    return (users.data?.users ?? []).filter((u) => u.name.includes(typed)).slice(0, 6);
  }, [draft, users.data]);

  const applyMention = (name: string) => {
    const at = draft.lastIndexOf("@");
    setDraft(draft.slice(0, at + 1) + name + " ");
    setMentionOpen(false);
    inputRef.current?.focus();
  };

  const submit = async () => {
    if (!draft.trim()) return;
    try {
      await api.createComment(itemId, { body: draft.trim() });
      setDraft("");
      await qc.invalidateQueries({ queryKey: ["comments", itemId] });
    } catch (e) {
      toast.error(`评论失败：${e instanceof Error ? e.message : e}`);
    }
  };

  // M23-I73: wrap the selection (or insert a placeholder) — storage stays text
  const applyTool = (t: Tool) => {
    const el = inputRef.current;
    if (!el) return;
    const start = el.selectionStart ?? draft.length;
    const end = el.selectionEnd ?? draft.length;
    if (t.wrap) {
      const sel = draft.slice(start, end) || "文本";
      const next = draft.slice(0, start) + t.wrap[0] + sel + t.wrap[1] + draft.slice(end);
      setDraft(next);
      requestAnimationFrame(() => {
        el.focus();
        el.setSelectionRange(start + t.wrap![0].length, start + t.wrap![0].length + sel.length);
      });
      return;
    }
    const ls = draft.lastIndexOf("\n", Math.max(start - 1, 0)) + 1;
    const leAt = draft.indexOf("\n", end);
    const le = leAt === -1 ? draft.length : leAt;
    const block = draft.slice(ls, le).split("\n")
      .map((l) => (l.startsWith(t.linePrefix!) ? l : t.linePrefix + l)).join("\n");
    const next = draft.slice(0, ls) + block + draft.slice(le);
    setDraft(next);
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(ls, ls + block.length); });
  };

  const remove = async (id: string) => {
    try {
      await api.deleteComment(id);
      await qc.invalidateQueries({ queryKey: ["comments", itemId] });
    } catch (e) {
      toast.error(`删除失败：${e instanceof Error ? e.message : e}`);
    }
  };

  // M18-I58: manual watch — subscribers hear about status changes and new comments
  const me = users.data?.current;
  const subscribed = !!(comments.data?.participants ?? []).some(
    (p) => p.user_id === me && p.source === "watch");
  const toggleSub = async () => {
    try {
      if (subscribed) await api.unsubscribeItem(itemId);
      else await api.subscribeItem(itemId);
      await qc.invalidateQueries({ queryKey: ["comments", itemId] });
    } catch (e) {
      toast.error(`订阅失败：${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <Modal open onClose={onClose} title={`💬 评论${title ? ` · ${title}` : ""}`}>
      <div className="space-y-3">
        <div className="max-h-72 space-y-2 overflow-y-auto">
          {(comments.data?.comments ?? []).map((c) => (
            <div key={c.id} className="group rounded-lg border border-line px-3 py-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-medium">{c.author_name ?? c.author_id}</span>
                <span className="text-[10px] text-mut">{(c.created_at || "").slice(5, 16).replace("T", " ")}</span>
                {c.edited_at && (
                  <button title="已编辑——点击查看修订历史"
                    onClick={() => setHistoryId(historyId === c.id ? null : c.id)}
                    className="text-[10px] text-mut hover:text-acc">
                    ✎ 已编辑
                  </button>
                )}
                {c.author_id === me && editingId !== c.id && (
                  <button
                    onClick={() => { setEditingId(c.id); setEditDraft(c.body); setHistoryId(null); }}
                    className="ml-auto text-[10px] text-mut opacity-0 transition-opacity hover:text-acc group-hover:opacity-100"
                    title="编辑评论（仅作者）">✎</button>
                )}
                <button onClick={() => remove(c.id)}
                  className={`${c.author_id === me && editingId !== c.id ? "" : "ml-auto"} text-[10px] text-mut opacity-0 transition-opacity hover:text-dan group-hover:opacity-100`}
                  title="删除评论">✕</button>
              </div>
              {editingId === c.id ? (
                <div className="mt-1 space-y-1">
                  <textarea
                    className="w-full rounded-lg border border-line bg-bg px-2 py-1.5 text-xs"
                    rows={3} value={editDraft}
                    onChange={(e) => setEditDraft(e.target.value)} />
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditingId(null)}
                      className="text-[10px] text-mut hover:text-ink">取消</button>
                    <Button size="sm" variant="primary" disabled={!editDraft.trim()}
                      onClick={() => saveEdit.mutate({ id: c.id, body: editDraft.trim() })}>保存</Button>
                  </div>
                </div>
              ) : (
                <div className={MD_BODY}
                  onClick={onBodyClick(c.id)}
                  dangerouslySetInnerHTML={{ __html: renderCommentMd(c.body, (users.data?.users ?? []).map((u) => u.name), {
                    extracted: new Map((comments.data?.extracted ?? [])
                      .filter((x) => x.comment_id === c.id)
                      .map((x) => [x.text, x.item_id])),
                    extractable: true,
                    boardPath: pid ? `#/p/${pid}/board` : undefined,
                  }) }} />
              )}
              {historyId === c.id && (
                <div className="mt-1 space-y-1 rounded-lg bg-bg px-2 py-1.5">
                  <div className="text-[10px] font-medium text-mut">修订历史（旧文倒序）</div>
                  {(revisions.data?.revisions ?? []).map((r) => (
                    <div key={r.id} className="border-t border-line pt-1 text-[10px] first:border-0 first:pt-0">
                      <span className="text-mut">{(r.created_at || "").slice(5, 16).replace("T", " ")} · {r.editor_name ?? r.edited_by} 编辑前：</span>
                      <div className="whitespace-pre-wrap text-ink">{r.body}</div>
                    </div>
                  ))}
                  {!revisions.data?.revisions.length && (
                    <div className="text-[10px] text-mut">暂无修订记录</div>
                  )}
                </div>
              )}
            </div>
          ))}
          {!comments.data?.comments.length && (
            <div className="py-6 text-center text-xs text-mut">还没有评论——用 @姓名 提及同事，他会收到通知</div>
          )}
        </div>
        <div className="relative">
          {preview ? (
            <div className={`${MD_BODY} min-h-[4.5rem] rounded-lg border border-line bg-bg px-3 py-2 text-xs`}
              dangerouslySetInnerHTML={{ __html: renderCommentMd(draft, (users.data?.users ?? []).map((u) => u.name)) }} />
          ) : (
            <>
            <div className="mb-1 flex flex-wrap gap-1">
              {TOOLS.map((t) => (
                <button key={t.title} type="button" title={t.title}
                  onMouseDown={(e) => { e.preventDefault(); applyTool(t); }}
                  className="rounded border border-line px-1.5 py-0.5 text-[10px] text-mut hover:border-acc hover:text-acc">
                  {t.label}
                </button>
              ))}
            </div>
            <textarea
              ref={inputRef}
              className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-xs"
              rows={3}
              placeholder="写下评论… 用 @ 提及同事，支持 Markdown（表格 / 清单 / 代码块）"
              value={draft}
              onChange={(e) => { setDraft(e.target.value); setMentionOpen(e.target.value.includes("@")); }}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); }}
            />
            </>
          )}
          {preview && (
            <button onClick={() => { setPreview(false); setTimeout(() => inputRef.current?.focus(), 0); }}
              className="absolute bottom-2 right-2 text-[10px] text-mut hover:text-acc">返回编辑</button>
          )}
          {mentionOpen && candidates.length > 0 && (
            <div className="absolute bottom-full left-0 z-10 mb-1 w-56 rounded-lg border border-line bg-surface p-1 shadow-lg">
              {candidates.map((u) => (
                <button key={u.id} onClick={() => applyMention(u.name)}
                  className="block w-full truncate rounded px-2 py-1.5 text-left text-xs hover:bg-bg">
                  {u.name} <span className="ml-auto font-mono text-[10px] text-mut">{u.id}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button onClick={toggleSub}
              className={`rounded-lg border px-2 py-1 text-[10px] ${subscribed ? "border-acc text-acc" : "border-line text-mut hover:border-acc hover:text-acc"}`}
              title="订阅后，该工作项的状态变更与新评论都会通知你">
              {subscribed ? "🔔 已订阅" : "🔕 订阅"}
            </button>
            <button onClick={() => setPreview(!preview)}
              className="rounded-lg border border-line px-2 py-1 text-[10px] text-mut hover:border-acc hover:text-acc"
              title="Markdown 只读预览（存储仍是纯文本）">
              {preview ? "✏️ 编辑" : "👁 预览"}
            </button>
            <span className="text-[10px] text-mut">Ctrl+Enter 发送 · @提及会发通知</span>
          </div>
          <Button size="sm" variant="primary" disabled={!draft.trim()} onClick={submit}>发送</Button>
        </div>
      </div>
    </Modal>
  );
}
