/** All conversations of the project — linear list or lineage tree (I198). */
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type ConversationTreeNode } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import { Badge, Card, CONV_STATUS, Empty } from "../components/ui";

const KIND_LABEL: Record<string, string> = {
  drafting: "起草", executing: "执行", reviewing: "评审", adhoc: "临时", ui_command: "操作",
};

function RunBadge({ runStatus }: { runStatus?: string | null }) {
  if (!runStatus) return null;
  if (runStatus === "running")
    return <Badge tone="indigo">▶ 运行中</Badge>;
  if (runStatus === "awaiting_review")
    return <Badge tone="warn">⏸ 待审</Badge>;
  if (runStatus === "failed")
    return <Badge tone="dan">✕ 失败</Badge>;
  if (runStatus === "completed")
    return <Badge tone="ok">✓ 完成</Badge>;
  return null;
}

export function ConversationsPage() {
  const { pid } = useParams();
  const [mode, setMode] = useState<"linear" | "tree">("linear");
  const convs = useQuery({
    queryKey: ["conversations", pid],
    queryFn: () => api.listConversations(pid!),
    enabled: !!pid,
  });
  const tree = useQuery({
    queryKey: ["conversation-tree", pid],
    queryFn: () => api.getConversationTree(pid!),
    enabled: !!pid && mode === "tree",
  });
  const list = convs.data?.conversations ?? [];
  const roots = tree.data?.roots ?? [];
  // The lineage spine: ancestor path down to the most recently updated node —
  // "where the work currently stands" in the tree view.
  const spine = (() => {
    let newestId = "";
    let newestTs = "";
    const walkTs = (nodes: ConversationTreeNode[]) => {
      for (const n of nodes) {
        if ((n.updated_at ?? "") >= newestTs) { newestTs = n.updated_at ?? ""; newestId = n.id; }
        walkTs(n.children);
      }
    };
    walkTs(roots);
    const marks = new Set<string>();
    if (!newestId) return marks;
    const walkPath = (nodes: ConversationTreeNode[]): boolean => {
      for (const n of nodes) {
        if (n.id === newestId || walkPath(n.children)) { marks.add(n.id); return true; }
      }
      return false;
    };
    walkPath(roots);
    return marks;
  })();
  if (!list.length) return <Empty icon="💬" title="暂无对话" hint="在功能页或看板发起第一个对话" />;
  return (
    <div className="space-y-2 p-4">
      <div className="flex items-center gap-2">
        <div className="flex overflow-hidden rounded-lg border border-line text-xs">
          <button
            onClick={() => setMode("linear")}
            className={mode === "linear" ? "bg-acc/10 px-2.5 py-1 text-acc" : "px-2.5 py-1 text-mut hover:text-ink"}
          >☰ 列表</button>
          <button
            onClick={() => setMode("tree")}
            title="按 parent_conversation_id 血缘显示分支（分叉的支线在这里可见）"
            className={mode === "tree" ? "bg-acc/10 px-2.5 py-1 text-acc" : "px-2.5 py-1 text-mut hover:text-ink"}
          >⑂ 树形</button>
        </div>
        {mode === "tree" && tree.data && (
          <span className="text-xs text-mut">{tree.data.total} 个对话 · 分支随 run 分叉生长</span>
        )}
      </div>
      {mode === "linear" && (() => {
        const order = ["running", "awaiting_review", "interrupted", "active", "archived"];
        const sorted = [...list].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status));
        return sorted.map((c) => {
          const s = CONV_STATUS[c.status] ?? { label: c.status, tone: "neutral" };
          return (
            <Link key={c.id} to={`/p/${pid}/c/${c.id}`}>
              <Card className="flex items-center gap-3 p-3 text-sm hover:border-acc">
                <Badge tone="indigo">{KIND_LABEL[c.kind] ?? c.kind}</Badge>
                <span className="min-w-0 flex-1 truncate font-medium">{c.title ?? c.id}</span>
                <span className="max-w-[36ch] truncate text-xs text-mut">{c.instruction ?? ""}</span>
                <Badge tone={s.tone}>{s.label}</Badge>
                <span className="w-20 text-right text-xs text-mut">{timeAgo(c.updated_at)}</span>
              </Card>
            </Link>
          );
        });
      })()}
      {mode === "tree" && roots.map((root) => (
        <TreeNodeRow key={root.id} node={root} depth={0} spine={spine} pid={pid!} />
      ))}
      {mode === "tree" && !roots.length && (
        <div className="py-6 text-center text-xs text-mut">加载中…</div>
      )}
    </div>
  );
}

function TreeNodeRow({ node, depth, spine, pid }: {
  node: ConversationTreeNode; depth: number; spine: Set<string>; pid: string;
}) {
  const s = CONV_STATUS[node.status] ?? { label: node.status, tone: "neutral" };
  const onSpine = spine.has(node.id);
  return (
    <div>
      <div className={depth > 0 ? "ml-6 border-l border-line pl-4" : ""}>
        <Link to={`/p/${pid}/c/${node.id}`}>
          <Card className={
            "flex items-center gap-2 p-2.5 text-sm hover:border-acc" +
            (onSpine ? " border-acc/60" : "")
          }>
            {node.children.length > 0 && <span className="text-xs text-mut">⑂{node.children.length}</span>}
            <Badge tone="indigo">{KIND_LABEL[node.kind] ?? node.kind}</Badge>
            <span className={"min-w-0 flex-1 truncate " + (onSpine ? "font-semibold text-acc" : "font-medium")}>
              {node.title ?? node.id}
            </span>
            <span className="max-w-[28ch] truncate text-xs text-mut">{node.instruction ?? ""}</span>
            <RunBadge runStatus={node.run_status} />
            <Badge tone={s.tone}>{s.label}</Badge>
            <span className="w-20 text-right text-xs text-mut">{timeAgo(node.updated_at)}</span>
          </Card>
        </Link>
      </div>
      {node.children.map((ch) => (
        <TreeNodeRow key={ch.id} node={ch} depth={depth + 1} spine={spine} pid={pid} />
      ))}
    </div>
  );
}
