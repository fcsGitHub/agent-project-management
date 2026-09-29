/** Assets page: org-level library (product/test/doc) with search + detail drawer. */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import type { Asset } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import { Badge, Button, Card, Drawer, Empty, Input, cx } from "../components/ui";
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
  const [toPack, setToPack] = useState<{ id: string; title: string } | null>(null);
  const assets = useQuery({
    queryKey: ["assets", lib, q],
    queryFn: () => api.listAssets({ library: lib || undefined, q: q || undefined }),
  });
  // M57-I172: 使用洞察——消费/引用遥测的读侧投影（使用 Top + 久未复用）
  const insights = useQuery({ queryKey: ["asset-insights"], queryFn: api.getAssetInsights });
  const insList = insights.data?.assets ?? [];
  const topUsed = insList.filter((a) => a.consumed_count > 0).slice(0, 5);
  const staleList = insList.filter((a) => a.stale);
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
            <Input className="w-36 sm:w-48" placeholder="🔍 搜索资产…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {insList.length > 0 && (
            <Card className="mb-3 p-3 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">📊 使用洞察</span>
                <span className="text-[11px] text-mut">复用是否真实发生，一目了然（消费计数来自资产使用事件，零埋点）</span>
              </div>
              <div className="mt-2 grid gap-3 md:grid-cols-2">
                <div>
                  <div className="text-[11px] text-mut">使用 Top</div>
                  {topUsed.length ? topUsed.map((a) => (
                    <button key={a.id} className="mt-1 block w-full truncate text-left hover:text-acc"
                      onClick={() => setDetail(a.id)}
                      title={`${a.title} · 消费 ${a.consumed_count} 次`}>
                      🏆 {a.title} · 消费 {a.consumed_count} 次{a.last_consumed ? ` · 最近 ${timeAgo(a.last_consumed)}` : ""}
                    </button>
                  )) : <div className="mt-1 text-[11px] text-mut">尚无消费记录——从项目里消费一次资产就会出现在这里</div>}
                </div>
                <div>
                  <div className="text-[11px] text-mut">久未复用（已发布 · 零消费 · 入库超 90 天）</div>
                  {staleList.length ? staleList.slice(0, 5).map((a) => (
                    <button key={a.id} className="mt-1 block w-full truncate text-left hover:text-acc"
                      onClick={() => setDetail(a.id)}
                      title={`${a.title} · 入库 ${a.age_days} 天未复用——候选弃用`}>
                      <span className="rounded bg-warn/10 px-1 text-[10px] text-warn">久未复用</span> {a.title} · 入库 {a.age_days} 天
                    </button>
                  )) : <div className="mt-1 text-[11px] text-mut">没有吃灰的已发布资产 ✓</div>}
                </div>
              </div>
            </Card>
          )}
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
                <button
                  onClick={(e) => { e.stopPropagation(); setToPack({ id: a.id, title: a.title }); }}
                  className="mt-2 rounded-md border border-line px-1.5 py-0.5 text-[11px] text-mut hover:border-acc hover:text-acc">
                  🧩 沉淀为模板包
                </button>
              </Card>
            ))}
          </div>
          {!list.length && <Empty icon="📚" title="暂无资产" hint="在工件详情中点「沉淀为资产」，经入库评审后进入资产库" />}
        </div>
      </div>
      <AssetDrawer id={detail} onClose={() => setDetail(null)} />
      <ToPackModal asset={toPack} onClose={() => setToPack(null)} />
    </div>
  );
}

/** 资产 → 模板包（M7-I24）：以来源项目本体为底注册入库（发 pack.registered）。 */
function ToPackModal({ asset, onClose }: { asset: { id: string; title: string } | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Drawer open={!!asset} onClose={onClose} title="沉淀为模板包" width="34%">
      {asset && (
        <div className="space-y-3 text-xs">
          <div className="text-mut">来源资产：<span className="font-medium text-ink">{asset.title}</span></div>
          <div className="text-mut">以其来源项目的本体为底，注册为可一键建项目的模板包。</div>
          <Input placeholder="模板包名（ASCII，如 weekly-ops）" value={name} onChange={(e) => setName(e.target.value)} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>取消</Button>
            <Button variant="primary" disabled={!name.trim() || busy} onClick={async () => {
              setBusy(true);
              try {
                const r = await api.assetToPack(asset.id, name.trim());
                await qc.invalidateQueries({ queryKey: ["template-packs"] });
                toast.success("已注册为模板包", { description: `${r.name}（源自 ${r.origin_ontology}），可在模板中心查看` });
                onClose();
              } catch (e) {
                toast.error("注册失败", { description: String(e) });
              } finally {
                setBusy(false);
              }
            }}>注册入库</Button>
          </div>
        </div>
      )}
    </Drawer>
  );
}

function AssetDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const asset = useQuery({
    queryKey: ["asset", id],
    queryFn: () => api.getAsset(id!),
    enabled: !!id,
  });
  if (!id) return null;
  const a = asset.data;
  return (
    <Drawer open onClose={onClose} title={a?.title ?? id} width="44%">
      {asset.isError && <div className="text-sm text-dan">资产加载失败，请关闭重试。</div>}
      {!a && !asset.isError && <div className="text-sm text-mut">加载资产…</div>}
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
                ? (a.provenance ?? []).map((p, i) => <div key={i} className="text-mut">· {p.project_id ?? ""} {p.path ?? p.ref ?? ""}</div>)
                : <div className="text-mut">—</div>}
            </Card>
            <Card className="p-2">
              <div className="mb-1 font-semibold text-mut">引用链 usage</div>
              {(a.usages ?? []).length
                ? (a.usages ?? []).map((p, i) => <div key={i} className="text-mut">· {p.project_id ?? ""} {p.path ?? p.ref ?? ""}</div>)
                : <div className="text-mut">—</div>}
            </Card>
          </div>
          <AssetHistoryCard id={id} version={a.version} />
          <AssetActionsCard asset={a} onClose={onClose} />
        </div>
      )}
    </Drawer>
  );
}

/** I225: 退役/归档——asset.deprecated/archived 的发射方（此前零生产者）。
 * 退役=标记 deprecated 保留在库、退出吃灰判定；归档=从清单隐没（详情仍可读）。 */
function AssetActionsCard({ asset, onClose }: { asset: Asset & { content?: string | null }; onClose: () => void }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
      qc.invalidateQueries({ queryKey: ["assets"] });
      qc.invalidateQueries({ queryKey: ["asset", asset.id] });
      qc.invalidateQueries({ queryKey: ["asset-insights"] });
    } catch (e) {
      toast.error(`操作失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };
  if (asset.status === "archived") {
    return (
      <Card className="p-2 text-xs">
        <span className="text-mut">该资产已归档（清单中隐没，详情仍可读）。</span>
      </Card>
    );
  }
  return (
    <Card className="p-2 text-xs">
      <div className="flex items-center gap-2">
        <span className="font-semibold text-mut">处置</span>
        {asset.status !== "deprecated" && (
          <Button size="sm" variant="outline" disabled={busy} title="标记 deprecated：保留在库、退出吃灰判定"
            onClick={() => { if (window.confirm(`退役资产「${asset.title}」？（保留在库，可随时重新评估）`)) act(() => api.deprecateAsset(asset.id), "已退役"); }}>
            退役
          </Button>
        )}
        <Button size="sm" variant="ghost" disabled={busy} title="归档：从资产清单隐没（详情仍可读）"
          onClick={() => { if (window.confirm(`归档资产「${asset.title}」？（清单中隐没）`)) act(() => api.archiveAsset(asset.id), "已归档"); onClose(); }}>
          归档
        </Button>
        <span className="ml-auto text-[10px] text-mut">退役≠删除——git 资产仓历史即账本</span>
      </div>
    </Card>
  );
}

/** I210: 版本历史读侧——write_asset 每次 commit，账本早就在，这里翻开它。
 * 恢复是 append-only：旧版重写为新版本（version+1），历史永不回卷。 */
function AssetHistoryCard({ id, version }: { id: string; version: number }) {
  const qc = useQueryClient();
  const [sel, setSel] = useState<string[]>([]);
  const hist = useQuery({
    queryKey: ["asset-history", id],
    queryFn: () => api.getAssetHistory(id),
  });
  const from = sel.length === 2 ? sel[1] : null;
  const to = sel.length === 2 ? sel[0] : null;
  const diff = useQuery({
    queryKey: ["asset-diff", id, from, to],
    queryFn: () => api.getAssetDiff(id, from!, to!),
    enabled: !!from && !!to,
  });
  const rows = hist.data?.history ?? [];
  const toggle = (sha: string) =>
    setSel((s) => (s.includes(sha) ? s.filter((x) => x !== sha) : [...s, sha].slice(-2)));
  const restore = async (sha: string) => {
    if (!window.confirm(`恢复到 ${sha.slice(0, 7)}？将以新版本追加（历史不回卷）。`)) return;
    try {
      await api.restoreAssetVersion(id, sha);
      toast.success("已恢复为新版本");
      setSel([]);
      qc.invalidateQueries({ queryKey: ["asset-history", id] });
      qc.invalidateQueries({ queryKey: ["asset", id] });
    } catch (e) {
      toast.error(`恢复失败：${e instanceof Error ? e.message : e}`);
    }
  };
  return (
    <Card className="p-2 text-xs">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-semibold text-mut">🕘 版本历史（v{version}）</span>
        <span className="text-[10px] text-mut">点选两版对比 · 恢复=追加新版</span>
      </div>
      {rows.length ? (
        <div className="space-y-0.5">
          {rows.map((h) => (
            <div key={h.commit} className={cx("flex items-center gap-2 rounded px-1 py-0.5", sel.includes(h.commit) && "bg-accbg")}>
              <button className="font-mono text-acc hover:underline" title="选中对比" onClick={() => toggle(h.commit)}>
                {h.commit.slice(0, 7)}
              </button>
              <span className="min-w-0 flex-1 truncate text-mut" title={h.message}>{h.message}</span>
              <span className="text-[10px] text-mut">{h.date?.slice(0, 16).replace("T", " ")}</span>
              <button className="text-[10px] text-mut hover:text-acc" title="恢复此版本（追加新版）"
                onClick={() => restore(h.commit)}>↩ 恢复</button>
            </div>
          ))}
        </div>
      ) : <div className="text-mut">—</div>}
      {from && to && (
        <div className="mt-2">
          <div className="mb-1 text-[10px] text-mut">
            对比 {from.slice(0, 7)} → {to.slice(0, 7)}
          </div>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-bg p-2 font-mono text-[10px] leading-relaxed">
            {diff.data?.patch || "（两版内容相同）"}
          </pre>
        </div>
      )}
    </Card>
  );
}
