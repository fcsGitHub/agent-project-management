/** Work-item comments drawer (M18-I57): thread list + composer with @mention
 * completion against project members/users. Reused by Board cards and slices. */
import { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Button, Modal } from "./ui";

export function CommentsModal({ itemId, title, onClose }: {
  itemId: string; title?: string; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [mentionOpen, setMentionOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const comments = useQuery({
    queryKey: ["comments", itemId],
    queryFn: () => api.listItemComments(itemId),
  });
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });

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
              <div className="mt-1 whitespace-pre-wrap text-ink">{highlightMentions(c.body, users.data?.users ?? [])}</div>
            </div>
          ))}
          {!comments.data?.comments.length && (
            <div className="py-6 text-center text-xs text-mut">还没有评论——用 @姓名 提及同事，他会收到通知</div>
          )}
        </div>
        <div className="relative">
          <textarea
            ref={inputRef}
            className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-xs"
            rows={3}
            placeholder="写下评论… 用 @ 提及同事"
            value={draft}
            onChange={(e) => { setDraft(e.target.value); setMentionOpen(e.target.value.includes("@")); }}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); }}
          />
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
          <span className="text-[10px] text-mut">Ctrl+Enter 发送 · @提及会发通知</span>
          <Button size="sm" variant="primary" disabled={!draft.trim()} onClick={submit}>发送</Button>
        </div>
      </div>
    </Modal>
  );
}

function highlightMentions(body: string, users: { id: string; name: string }[]) {
  const names = users.map((u) => u.name).filter((n) => body.includes(`@${n}`));
  if (!names.length) return body;
  const parts = body.split(new RegExp(`(@(?:${names.map(escapeRe).join("|")}))`, "g"));
  return parts.map((p, i) =>
    p.startsWith("@") ? (
      <span key={i} className="rounded bg-accbg px-1 font-medium text-acc">{p}</span>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
