/** All conversations of the project, grouped by status. */
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import { Badge, Card, CONV_STATUS, Empty } from "../components/ui";

export function ConversationsPage() {
  const { pid } = useParams();
  const convs = useQuery({
    queryKey: ["conversations", pid],
    queryFn: () => api.listConversations(pid!),
    enabled: !!pid,
  });
  const list = convs.data?.conversations ?? [];
  const order = ["running", "awaiting_review", "interrupted", "active", "archived"];
  const sorted = [...list].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status));
  if (!list.length) return <Empty icon="💬" title="暂无对话" hint="在功能页或看板发起第一个对话" />;
  return (
    <div className="space-y-2 p-4">
      {sorted.map((c) => {
        const s = CONV_STATUS[c.status] ?? { label: c.status, tone: "neutral" };
        return (
          <Link key={c.id} to={`/p/${pid}/c/${c.id}`}>
            <Card className="flex items-center gap-3 p-3 text-sm hover:border-acc">
              <Badge tone="indigo">
                {{ drafting: "起草", executing: "执行", reviewing: "评审", adhoc: "临时", ui_command: "操作" }[c.kind] ?? c.kind}
              </Badge>
              <span className="min-w-0 flex-1 truncate font-medium">{c.title ?? c.id}</span>
              <span className="max-w-[36ch] truncate text-xs text-mut">{c.instruction ?? ""}</span>
              <Badge tone={s.tone}>{s.label}</Badge>
              <span className="w-20 text-right text-xs text-mut">{timeAgo(c.updated_at)}</span>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}
