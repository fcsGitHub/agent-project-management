/** Work-item comments drawer (M18-I57): thread list + composer with @mention
 * completion against project members/users. Reused by Board cards and slices.
 * M20-I64: bodies render as read-only GFM (marked + DOMPurify, docs/01 §S.3);
 * storage stays plain text, composer gains an edit/preview toggle. */
import { useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { renderCommentMd } from "../lib/md";
import { Button, Modal } from "./ui";

const MD_BODY = "mt-1 text-ink [&_a]:text-acc [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-line [&_blockquote]:pl-2 [&_code]:rounded [&_code]:bg-bg [&_code]:px-1 [&_h1]:text-sm [&_h1]:font-semibold [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:font-semibold [&_img]:max-w-full [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-4 [&_p]:my-1 [&_pre]:overflow-x-auto [&_pre]:rounded [&_pre]:bg-bg [&_pre]:p-2 [&_td]:border [&_td]:border-line [&_td]:px-1.5 [&_th]:border [&_th]:border-line [&_th]:px-1.5 [&_ul]:list-disc [&_ul]:pl-4";

export function CommentsModal({ itemId, title, onClose }: {
  itemId: string; title?: string; onClose: () => void;
}) {
  const qc = useQueryClient();
  const { pid } = useParams();
  const [draft, setDraft] = useState("");
  const [preview, setPreview] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const comments = useQuery({
    queryKey: ["comments", itemId],
    queryFn: () => api.listItemComments(itemId),
  });
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });

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
                <button onClick={() => remove(c.id)}
                  className="ml-auto text-[10px] text-mut opacity-0 transition-opacity hover:text-dan group-hover:opacity-100"
                  title="删除评论">✕</button>
              </div>
              <div className={MD_BODY}
                onClick={onBodyClick(c.id)}
                dangerouslySetInnerHTML={{ __html: renderCommentMd(c.body, (users.data?.users ?? []).map((u) => u.name), {
                  extracted: new Map((comments.data?.extracted ?? [])
                    .filter((x) => x.comment_id === c.id)
                    .map((x) => [x.text, x.item_id])),
                  extractable: true,
                  boardPath: pid ? `#/p/${pid}/board` : undefined,
                }) }} />
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
            <textarea
              ref={inputRef}
              className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-xs"
              rows={3}
              placeholder="写下评论… 用 @ 提及同事，支持 Markdown（表格 / 清单 / 代码块）"
              value={draft}
              onChange={(e) => { setDraft(e.target.value); setMentionOpen(e.target.value.includes("@")); }}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); }}
            />
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
