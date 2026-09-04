/** Global search results (M22-I68, docs/01 §U.1): GET /search with type chips;
 * items jump to the board drawer (?item=), comments jump to their item. */
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Card, Empty } from "../components/ui";

const TYPES = [
  { key: "items", label: "工作项" },
  { key: "comments", label: "评论" },
] as const;

export function SearchPage() {
  const [params] = useSearchParams();
  const q = (params.get("q") ?? "").trim();
  const [types, setTypes] = useState<string>("items,comments");

  const results = useQuery({
    queryKey: ["search", q, types],
    queryFn: () => api.globalSearch(q, types),
    enabled: !!q,
  });

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-sm font-semibold">🔍 全局搜索</span>
        {q && <code className="rounded bg-bg px-2 py-0.5 text-xs">{q}</code>}
        <span className="ml-auto flex gap-1">
          {TYPES.map((t) => {
            const on = types.includes(t.key);
            return (
              <button key={t.key}
                onClick={() => setTypes(on ? types.replace(t.key, "").replace(/^[,\s]+|[,\s]+$/g, "").replace(/,+,/g, ",") : (types ? `${types},${t.key}` : t.key))}
                className={`rounded-lg border px-2 py-1 text-xs ${on ? "border-acc text-acc" : "border-line text-mut hover:border-acc"}`}>
                {t.label}
              </button>
            );
          })}
        </span>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {!q && <Empty title="输入关键词开始搜索" hint="⌘K 面板或顶部命令栏输入「搜索 '关键词'」也可直达本页" />}
        {q && (
          <>
            <Card className="p-4">
              <div className="mb-2 text-sm font-semibold">工作项 · {results.data?.items.length ?? "…"}</div>
              <div className="space-y-1.5">
                {(results.data?.items ?? []).map((it) => (
                  <Link key={it.id} to={`/p/${it.project_id}/board?item=${it.id}`}
                    className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs hover:border-acc">
                    <span className="w-28 shrink-0 truncate text-mut">{it.project_name}</span>
                    <span className="flex-1 truncate font-medium">{it.title}</span>
                    <Badge tone="neutral">{it.concept_id}</Badge>
                    <Badge tone={it.status_group === "in_progress" ? "amber" : "neutral"}>{it.status}</Badge>
                  </Link>
                ))}
                {results.data && !results.data.items.length && (
                  <div className="py-3 text-center text-xs text-mut">没有匹配的工作项</div>
                )}
              </div>
            </Card>
            <Card className="p-4">
              <div className="mb-2 text-sm font-semibold">评论 · {results.data?.comments.length ?? "…"}</div>
              <div className="space-y-1.5">
                {(results.data?.comments ?? []).map((c) => (
                  <Link key={c.id} to={`/p/${c.project_id}/board?item=${c.item_id}`}
                    className="block rounded-lg border border-line px-3 py-2 text-xs hover:border-acc">
                    <div className="flex items-center gap-2">
                      <span className="w-28 shrink-0 truncate text-mut">{c.project_name}</span>
                      <span className="flex-1 truncate font-medium">{c.item_title}</span>
                    </div>
                    <div className="mt-1 line-clamp-2 text-mut">{c.body}</div>
                  </Link>
                ))}
                {results.data && !results.data.comments.length && (
                  <div className="py-3 text-center text-xs text-mut">没有匹配的评论</div>
                )}
              </div>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
