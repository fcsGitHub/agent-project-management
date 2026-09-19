/** Work-item comments drawer (M18-I57): thread list + composer with @mention
 * completion against project members/users. Reused by Board cards and slices.
 * M20-I64: bodies render as read-only GFM (marked + DOMPurify, docs/01 §S.3);
 * storage stays plain text, composer gains an edit/preview toggle.
 * M26-I81: author-only inline editing with an "edited" badge and a revision
 * history expansion (event-sourced comment_revisions — GitLab #3706, closed). */
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { renderCommentMd } from "../lib/md";
import { Button, Modal, cx } from "./ui";

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

export function CommentsModal({ itemId, title, onClose, autoQuote = false }: {
  itemId: string; title?: string; onClose: () => void;
  /** I109: pre-fill the draft with a quote of the last comment on open (R key) */
  autoQuote?: boolean;
}) {
  const qc = useQueryClient();
  const { pid } = useParams();
  const [draft, setDraft] = useState("");
  const [preview, setPreview] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [historyId, setHistoryId] = useState<string | null>(null);
  // I108: GitHub Saved Replies — filterable panel + insert at caret
  const [repliesOpen, setRepliesOpen] = useState(false);
  const [replyFilter, setReplyFilter] = useState("");
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const comments = useQuery({
    queryKey: ["comments", itemId],
    queryFn: () => api.listItemComments(itemId),
  });
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const replies = useQuery({
    queryKey: ["saved-replies"],
    queryFn: api.listSavedReplies,
    enabled: repliesOpen,
  });
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
      qc.invalidateQueries({ queryKey: ["comments", itemId] });
    },
    onError: (e) => toast.error(`编辑失败：${e instanceof Error ? e.message : e}`),
  });

  // I67: delegated clicks on the per-comment「转为子任务」buttons
  const extract = useMutation({
    mutationFn: (v: { commentId: string; text: string }) => api.extractTask(v.commentId, { text: v.text }),
    onSuccess: (r) => {
      toast.success(`已转为子任务：${r.item.title}`);
      qc.invalidateQueries({ queryKey: ["comments", itemId] });
      qc.invalidateQueries({ queryKey: ["board"] });
      qc.invalidateQueries({ queryKey: ["feature"] });
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

  // 渲染缓存：marked+DOMPurify 解析按评论 id 记忆化（随评论/用户/提取表变化
  // 才重建）——否则编辑框每敲一个字，全列表每条评论都重跑一遍解析净化。
  const names = useMemo(() => (users.data?.users ?? []).map((u) => u.name), [users.data]);
  const extractedByComment = useMemo(() => {
    const m = new Map<string, Map<string, string>>();
    for (const x of comments.data?.extracted ?? []) {
      const cur = m.get(x.comment_id) ?? new Map<string, string>();
      cur.set(x.text, x.item_id);
      m.set(x.comment_id, cur);
    }
    return m;
  }, [comments.data]);
  const renderComment = useMemo(() => {
    const cache = new Map<string, string>();
    return (c: { id: string; body: string }) => {
      let html = cache.get(c.id);
      if (html === undefined) {
        html = renderCommentMd(c.body, names, {
          extracted: extractedByComment.get(c.id),
          extractable: true,
          boardPath: pid ? `#/p/${pid}/board` : undefined,
        });
        cache.set(c.id, html);
      }
      return html;
    };
  }, [extractedByComment, names, pid]);

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

  // M30-I94 (docs/01 §AC.3, GitHub quote-reply semantics): blockquote the
  // comment body into the draft — storage stays plain text, rendering is free.
  // The @author line stays on its own line: a mid-line `> ` is not a
  // blockquote in markdown, so the quoted lines must start each line.
  const quote = (c: { author_name?: string | null; author_id: string; body: string }) => {
    const quoted = c.body.split("\n").map((l) => `> ${l}`).join("\n");
    setDraft(`@${c.author_name ?? c.author_id} 引用：\n${quoted}\n\n`);
    setPreview(false);
    setEditingId(null);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  // I109: R opens the modal pre-filled with a quote of the last comment —
  // applied once, only when the draft is still empty (quote-reply semantics).
  const autoQuotedRef = useRef(false);
  const list = comments.data?.comments ?? [];
  useEffect(() => {
    if (!autoQuote || autoQuotedRef.current || !list.length || draft) return;
    autoQuotedRef.current = true;
    quote(list[list.length - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoQuote, list.length, draft]);

  // I108: insert a saved reply at the caret (panel click / Enter selection).
  // Functional setDraft — the keydown closure may hold a stale draft.
  const insertReply = (body: string) => {
    const el = inputRef.current;
    const at = el?.selectionStart ?? -1;
    const end = el?.selectionEnd ?? -1;
    setDraft((cur) => {
      const s = at >= 0 ? at : cur.length;
      const e2 = end >= 0 ? end : cur.length;
      return cur.slice(0, s) + body + cur.slice(e2);
    });
    setRepliesOpen(false);
    setReplyFilter("");
    setPreview(false);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at + body.length, at + body.length);
    });
  };

  // I108: stash the current selection as a canned reply
  const stashSelection = async () => {
    const el = inputRef.current;
    const sel = el ? draft.slice(el.selectionStart ?? 0, el.selectionEnd ?? 0).trim() : "";
    if (!sel) { toast.info("先在评论框选中一段文本，再点「存为常用回复」"); return; }
    try {
      await api.addSavedReply(sel.slice(0, 60), sel);
      toast.success("已存为常用回复");
      qc.invalidateQueries({ queryKey: ["saved-replies"] });
    } catch (e) {
      toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const filteredReplies = (replies.data?.replies ?? [])
    .filter((r) => !replyFilter || r.title.includes(replyFilter) || r.body.includes(replyFilter));

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
                <button
                  onClick={() => quote(c)}
                  className="ml-auto text-[10px] text-mut opacity-0 transition-opacity hover:text-acc group-hover:opacity-100"
                  title="引用回复">❝</button>
                {c.author_id === me && editingId !== c.id && (
                  <button
                    onClick={() => { setEditingId(c.id); setEditDraft(c.body); setHistoryId(null); }}
                    className={cx("text-[10px] text-mut opacity-0 transition-opacity hover:text-acc group-hover:opacity-100",
                      c.author_id !== me && "ml-auto")}
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
                  dangerouslySetInnerHTML={{ __html: renderComment(c) }} />
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
              <button type="button" title="常用回复（Ctrl+.）"
                onMouseDown={(e) => { e.preventDefault(); setRepliesOpen((v) => !v); }}
                className="rounded border border-line px-1.5 py-0.5 text-[10px] text-mut hover:border-acc hover:text-acc">
                ⌨ 常用回复
              </button>
              <button type="button" title="把选中文本存为常用回复"
                onMouseDown={(e) => { e.preventDefault(); stashSelection(); }}
                className="rounded border border-line px-1.5 py-0.5 text-[10px] text-mut hover:border-acc hover:text-acc">
                ☆ 存为常用
              </button>
            </div>
            {repliesOpen && (
              <div className="mb-1 rounded-lg border border-line bg-bg p-1.5">
                <input
                  autoFocus
                  value={replyFilter}
                  onChange={(e) => setReplyFilter(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      // read the live input value — render closures go stale
                      const q = (e.target as HTMLInputElement).value;
                      const hit = (replies.data?.replies ?? [])
                        .find((r) => !q || r.title.includes(q) || r.body.includes(q));
                      if (hit) { e.preventDefault(); insertReply(hit.body); }
                    }
                    if (e.key === "Escape") { setRepliesOpen(false); setReplyFilter(""); }
                  }}
                  placeholder="过滤常用回复… Enter 插入第一条（Ctrl+. 唤起）"
                  className="mb-1 w-full rounded border border-line bg-bg px-2 py-1 text-[11px] text-ink"
                />
                {(filteredReplies.length ? filteredReplies : []).map((r) => (
                  <div key={r.id} className="group/r flex items-start gap-1 rounded px-1 py-0.5 hover:bg-bg">
                    <button type="button" onClick={() => insertReply(r.body)}
                      className="min-w-0 flex-1 text-left">
                      <div className="truncate text-[11px] font-medium text-ink">{r.title}</div>
                      <div className="truncate text-[10px] text-mut">{r.body}</div>
                    </button>
                    <button type="button"
                      onClick={async () => { await api.deleteSavedReply(r.id); qc.invalidateQueries({ queryKey: ["saved-replies"] }); }}
                      className="text-[10px] text-mut opacity-0 transition-opacity hover:text-dan group-hover/r:opacity-100" title="删除">✕</button>
                  </div>
                ))}
                {!filteredReplies.length && (
                  <div className="px-1 py-1 text-[10px] text-mut">
                    {replies.data?.replies.length ? "没有匹配的常用回复" : "还没有常用回复——选中评论框文本点「☆ 存为常用」"}
                  </div>
                )}
              </div>
            )}
            <textarea
              ref={inputRef}
              className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-xs"
              rows={3}
              placeholder="写下评论… 用 @ 提及同事，支持 Markdown（表格 / 清单 / 代码块）"
              value={draft}
              onChange={(e) => { setDraft(e.target.value); setMentionOpen(e.target.value.includes("@")); }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit();
                // I108: Ctrl+. / Cmd+. toggles the saved-replies panel
                if (e.key === "." && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  setRepliesOpen((v) => !v);
                }
              }}
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
