/** Global search results (M22-I68, docs/01 §U.1): GET /search with type chips;
 * items jump to the board drawer (?item=), comments jump to their item.
 * M64-I193: project facet chips (pure frontend aggregation) + "no results →
 * try fewer types" guidance. */
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Card, Empty, cx } from "../components/ui";
import { ArtifactPreviewDrawer } from "../components/ArtifactPreviewDrawer";

const TYPES = [
  { key: "items", label: "工作项" },
  { key: "comments", label: "评论" },
  { key: "conversations", label: "会话" },
  { key: "artifacts", label: "工件" },
] as const;

export function SearchPage() {
  const [params] = useSearchParams();
  const q = (params.get("q") ?? "").trim();
  const [types, setTypes] = useState<string>("items,comments,conversations,artifacts");
  // M64-I193: project facet — pure frontend aggregation over returned rows
  const [facet, setFacet] = useState<string>("");
  // I214: 工件命中 → 通用预览抽屉（SearchPage 在 AppShell 外无 pid——用命中行自己的 project_id）
  const [preview, setPreview] = useState<{ pid: string; path: string } | null>(null);

  const results = useQuery({
    queryKey: ["search", q, types],
    queryFn: () => api.globalSearch(q, types),
    enabled: !!q,
  });

  const facets = useMemo(() => {
    const d = results.data;
    if (!d) return [];
    const counts = new Map<string, { name: string; n: number }>();
    const bump = (pid?: string, pname?: string | null) => {
      if (!pid) return;
      const e = counts.get(pid) ?? { name: pname || pid, n: 0 };
      e.n += 1;
      counts.set(pid, e);
    };
    d.items.forEach((x) => bump(x.project_id, x.project_name));
    d.comments.forEach((x) => bump(x.project_id, x.project_name));
    (d.conversations ?? []).forEach((x) => bump(x.project_id, x.project_name));
    (d.artifacts ?? []).forEach((x) => bump(x.project_id, x.project_name));
    return [...counts.entries()]
      .map(([pid, e]) => ({ pid, ...e }))
      .sort((a, b) => b.n - a.n);
  }, [results.data]);

  const inFacet = (pid?: string) => !facet || pid === facet;

  const fItems = (results.data?.items ?? []).filter((x) => inFacet(x.project_id));
  const fComments = (results.data?.comments ?? []).filter((x) => inFacet(x.project_id));
  const fConvs = (results.data?.conversations ?? []).filter((x) => inFacet(x.project_id));
  const fArtifacts = (results.data?.artifacts ?? []).filter((x) => inFacet(x.project_id));
  const totalHits = (results.data?.items.length ?? 0)
    + (results.data?.comments.length ?? 0)
    + (results.data?.conversations?.length ?? 0)
    + (results.data?.artifacts?.length ?? 0);

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
        {q && facets.length > 1 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <button onClick={() => setFacet("")}
              className={cx("rounded-full border px-2.5 py-0.5 text-[11px]",
                !facet ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink")}>
              全部 · {totalHits}
            </button>
            {facets.map((f) => (
              <button key={f.pid} onClick={() => setFacet(facet === f.pid ? "" : f.pid)}
                title={f.name}
                className={cx("rounded-full border px-2.5 py-0.5 text-[11px]",
                  facet === f.pid ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink")}>
                {f.name} · {f.n}
              </button>
            ))}
          </div>
        )}
        {q && (
          <>
            <Card className="p-4">
              <div className="mb-2 text-sm font-semibold">工作项 · {fItems.length}{facet && ` / ${results.data?.items.length ?? 0}`}</div>
              <div className="space-y-1.5">
                {fItems.map((it) => (
                  <Link key={it.id} to={`/p/${it.project_id}/board?item=${it.id}`}
                    className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs hover:border-acc">
                    <span className="w-28 shrink-0 truncate text-mut">{it.project_name}</span>
                    <span className="flex-1 truncate font-medium">{it.title}</span>
                    <Badge tone="neutral">{it.concept_id}</Badge>
                    <Badge tone={it.status_group === "in_progress" ? "amber" : "neutral"}>{it.status}</Badge>
                  </Link>
                ))}
                {results.data && !fItems.length && (
                  <div className="py-3 text-center text-xs text-mut">没有匹配的工作项</div>
                )}
              </div>
            </Card>
            <Card className="p-4">
              <div className="mb-2 text-sm font-semibold">评论 · {fComments.length}{facet && ` / ${results.data?.comments.length ?? 0}`}</div>
              <div className="space-y-1.5">
                {fComments.map((c) => (
                  <Link key={c.id} to={`/p/${c.project_id}/board?item=${c.item_id}`}
                    className="block rounded-lg border border-line px-3 py-2 text-xs hover:border-acc">
                    <div className="flex items-center gap-2">
                      <span className="w-28 shrink-0 truncate text-mut">{c.project_name}</span>
                      <span className="flex-1 truncate font-medium">{c.item_title}</span>
                    </div>
                    <div className="mt-1 line-clamp-2 text-mut">{c.body}</div>
                  </Link>
                ))}
                {results.data && !fComments.length && (
                  <div className="py-3 text-center text-xs text-mut">没有匹配的评论</div>
                )}
              </div>
            </Card>
            <Card className="p-4">
              <div className="mb-2 text-sm font-semibold">会话 · {fConvs.length}{facet && ` / ${results.data?.conversations?.length ?? 0}`}</div>
              <div className="space-y-1.5">
                {fConvs.map((c) => (
                  <Link key={c.message_id} to={`/p/${c.project_id}/c/${c.conversation_id}`}
                    className="block rounded-lg border border-line px-3 py-2 text-xs hover:border-acc">
                    <div className="flex items-center gap-2">
                      <span className="w-28 shrink-0 truncate text-mut">{c.project_name}</span>
                      <span className="flex-1 truncate font-medium">{c.conversation_title || c.conversation_kind}</span>
                      <Badge tone="neutral">{c.role}</Badge>
                    </div>
                    <div className="mt-1 line-clamp-2 text-mut">{c.snippet}</div>
                  </Link>
                ))}
                {results.data && !fConvs.length && (
                  <div className="py-3 text-center text-xs text-mut">没有匹配的会话消息</div>
                )}
              </div>
            </Card>
            <Card className="p-4">
              <div className="mb-2 text-sm font-semibold">工件 · {fArtifacts.length}{facet && ` / ${results.data?.artifacts?.length ?? 0}`}</div>
              <div className="space-y-1.5">
                {fArtifacts.map((a) => (
                  <button key={`${a.project_id}:${a.path}`}
                    onClick={() => setPreview({ pid: a.project_id, path: a.path })}
                    className="flex w-full items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs hover:border-acc">
                    <span className="w-28 shrink-0 truncate text-mut">{a.project_name}</span>
                    <span className="flex-1 truncate text-left font-mono">📄 {a.path}</span>
                  </button>
                ))}
                {results.data && !fArtifacts.length && (
                  <div className="py-3 text-center text-xs text-mut">没有匹配的工件</div>
                )}
              </div>
            </Card>
            {results.data && totalHits === 0 && (
              <div className="pb-4 text-center text-xs text-mut">
                四类内容都没有命中——试试更短的关键词，或检查类型片是否全被关掉
              </div>
            )}
          </>
        )}
      </div>
      {preview && (
        <ArtifactPreviewDrawer pid={preview.pid} path={preview.path} onClose={() => setPreview(null)} />
      )}
    </div>
  );
}
