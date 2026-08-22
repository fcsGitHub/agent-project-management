/** Assets page: org-level library (product/test/doc) with search + detail drawer. */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import { Badge, Card, Drawer, Empty, Input, cx } from "../components/ui";
import Markdown0 from "react-markdown";

const libIcon = (id: string) => ({ product: "📦", test: "🧪", doc: "📚" }[id] ?? "🗃️");

const LIBS = [
  { id: "", label: "全部", icon: "🗂️" },
  { id: "product", label: "产品库", icon: "📦" },
  { id: "test", label: "测试库", icon: "🧪" },
  { id: "doc", label: "文档库", icon: "📚" },
];

export function AssetsPage() {
  const [lib, setLib] = useState("");
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState<string | null>(null);
  const assets = useQuery({
    queryKey: ["assets", lib, q],
    queryFn: () => api.listAssets({ library: lib || undefined, q: q || undefined }),
  });
  const list = assets.data?.assets ?? [];

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
          <span className="text-sm font-semibold">📚 资产库</span>
          <span className="text-xs text-mut">项目是临时的 · 资产是复利的</span>
          <div className="ml-auto flex items-center gap-2">
            {LIBS.map((l) => (
              <button key={l.id} onClick={() => setLib(l.id)}
                className={cx("rounded-full border px-2.5 py-1 text-xs",
                  lib === l.id ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink")}>
                {l.icon} {l.label}
              </button>
            ))}
            <Input className="w-48" placeholder="🔍 搜索资产…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {list.map((a) => (
              <Card key={a.id} className="cursor-pointer p-3 text-xs hover:border-acc" onClick={() => setDetail(a.id)}>
                <div className="truncate font-medium">{a.title}</div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1">
                  <Badge tone="violet">{libIcon(a.library_id)} {a.library_id}</Badge>
                  <Badge tone="neutral">{a.kind}</Badge>
                  {a.status !== "published" && <Badge tone="amber">{a.status}</Badge>}
                </div>
                <div className="mt-2 text-[11px] text-mut">被引用 {a.citation_count} 次 · {timeAgo(a.updated_at)}</div>
              </Card>
            ))}
          </div>
          {!list.length && <Empty icon="📚" title="暂无资产" hint="在工件详情中点「沉淀为资产」，经入库评审后进入资产库" />}
        </div>
      </div>
      <AssetDrawer id={detail} onClose={() => setDetail(null)} />
    </div>
  );
}

function AssetDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const asset = useQuery({
    queryKey: ["asset", id],
    queryFn: async () => {
      const r = await fetch(`/api/assets/${id}`);
      return r.json();
    },
    enabled: !!id,
  });
  if (!id) return null;
  const a = asset.data;
  return (
    <Drawer open onClose={onClose} title={a?.title ?? id} width="44%">
      {a && (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-1.5">
            <Badge tone="violet">{libIcon(a.library_id)} {a.library_id}</Badge>
            <Badge tone="neutral">{a.kind}</Badge>
            <Badge tone={a.status === "published" ? "green" : "amber"}>{a.status}</Badge>
            <Badge tone="indigo">v{a.version}</Badge>
          </div>
          <div className="prose prose-zinc prose-sm max-w-none">
            <Markdown0>{a.content ?? a.excerpt ?? "（正文见资产仓）"}</Markdown0>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <Card className="p-2">
              <div className="mb-1 font-semibold text-mut">来源链 provenance</div>
              {(a.provenance ?? []).length
                ? (a.provenance).map((p: any, i: number) => <div key={i} className="text-mut">· {p.project_id ?? ""} {p.path ?? p.ref ?? ""}</div>)
                : <div className="text-mut">—</div>}
            </Card>
            <Card className="p-2">
              <div className="mb-1 font-semibold text-mut">引用链 usage</div>
              {(a.usages ?? []).length
                ? (a.usages).map((p: any, i: number) => <div key={i} className="text-mut">· {p.project_id ?? ""} {p.path ?? p.ref ?? ""}</div>)
                : <div className="text-mut">—</div>}
            </Card>
          </div>
        </div>
      )}
    </Drawer>
  );
}
