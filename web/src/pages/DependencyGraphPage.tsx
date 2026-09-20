/** Dependency graph page (M40-I124, docs/01 §AM.3, Jira Plans dependencies
 *  map): a layered SVG view of the project's depends_on/blocks edges —
 *  topological levels run top-down, nodes are colored by state (done gray,
 *  blocked red: unfinished with an unfinished upstream, else green) and the
 *  CPM critical chain gets an amber ring (critical-path API). Pure frontend:
 *  everything is read from existing list/relations/critical-path endpoints. */
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Card, Empty, cx } from "../components/ui";

const NODE_W = 168;
const NODE_H = 44;
const GAP_X = 22;
const GAP_Y = 46;

type Edge = { from: string; to: string; kind: "depends_on" | "blocks" };

export function DependencyGraphPage() {
  const { pid } = useParams();
  const items = useQuery({ queryKey: ["deps-items", pid], queryFn: () => api.listItems(pid!) });
  const cp = useQuery({ queryKey: ["critical-path", pid], queryFn: () => api.getCriticalPath(pid!) });
  const [onlyBlocked, setOnlyBlocked] = useState(false);

  // relations only ship on the item detail payload (established timeline
  // pattern): one detail fetch per item, fine at single-project scale
  const itemIds = (items.data?.items ?? []).map((i) => i.id).join(",");
  const details = useQuery({
    queryKey: ["dep-details", pid, itemIds],
    queryFn: async () => {
      const out: Record<string, import("../lib/api").Item> = {};
      await Promise.all((items.data?.items ?? []).map(async (i) => { out[i.id] = await api.getItem(i.id); }));
      return out;
    },
    enabled: !!pid && (items.data?.items.length ?? 0) > 0,
  });

  // edges from per-item relations; dedupe bidirectional bookkeeping
  const edges = useMemo<Edge[]>(() => {
    const seen = new Set<string>();
    const out: Edge[] = [];
    for (const it of Object.values(details.data ?? {})) {
      for (const r of it.relations ?? []) {
        if (r.relation_type !== "depends_on" && r.relation_type !== "blocks") continue;
        const key = `${r.from_item}>${r.to_item}:${r.relation_type}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ from: r.from_item, to: r.to_item, kind: r.relation_type as Edge["kind"] });
      }
    }
    return out;
  }, [details.data]);

  const byId = useMemo(() => {
    const m = new Map<string, { id: string; title: string; status: string; status_group: string }>();
    for (const it of items.data?.items ?? [])
      m.set(it.id, { id: it.id, title: it.title, status: it.status, status_group: it.status_group });
    return m;
  }, [items.data]);

  // blocked = unfinished item with an unfinished upstream (depends_on source
  // or an unfinished blocks blocker)
  const blockedIds = useMemo(() => {
    const bad = new Set<string>();
    for (const e of edges) {
      const upstream = byId.get(e.from);
      if (!upstream || upstream.status_group === "done" || upstream.status_group === "cancelled") continue;
      const down = byId.get(e.to);
      if (down && down.status_group !== "done" && down.status_group !== "cancelled") bad.add(e.to);
    }
    return bad;
  }, [edges, byId]);

  // topological levels: level(x) = 0 without upstream edges, else max(up)+1
  const levels = useMemo(() => {
    const up = new Map<string, string[]>();
    for (const e of edges) up.set(e.to, [...(up.get(e.to) ?? []), e.from]);
    const level = new Map<string, number>();
    const depth = new Map<string, number>();
    const calc = (id: string, d: number): number => {
      if (depth.has(id) && depth.get(id)! >= d) return level.get(id) ?? 0;
      depth.set(id, d);
      if (d > 50) return 0; // cycle guard
      const parents = up.get(id) ?? [];
      const lv = parents.length ? Math.max(...parents.map((p) => calc(p, d + 1))) + 1 : 0;
      level.set(id, Math.max(level.get(id) ?? 0, lv));
      return level.get(id) ?? 0;
    };
    for (const id of byId.keys()) calc(id, 0);
    const rows = new Map<number, string[]>();
    for (const id of byId.keys()) {
      const lv = level.get(id) ?? 0;
      rows.set(lv, [...(rows.get(lv) ?? []), id]);
    }
    return rows;
  }, [edges, byId]);

  const layout = useMemo(() => {
    const pos = new Map<string, { x: number; y: number }>();
    let y = 20;
    const sortedLevels = [...levels.keys()].sort((a, b) => a - b);
    let maxRowWidth = 0;
    for (const lv of sortedLevels) {
      const row = levels.get(lv)!;
      const width = row.length * (NODE_W + GAP_X) - GAP_X;
      maxRowWidth = Math.max(maxRowWidth, width);
      row.forEach((id, i) => pos.set(id, { x: 20 + i * (NODE_W + GAP_X), y }));
      y += NODE_H + GAP_Y;
    }
    return { pos, width: maxRowWidth + 40, height: y };
  }, [levels]);

  const critical = new Set(cp.data?.chain ?? []);
  const visibleIds = useMemo(() => {
    if (!onlyBlocked) return [...byId.keys()];
    return [...byId.keys()].filter((id) => blockedIds.has(id));
  }, [onlyBlocked, blockedIds, byId]);
  const visible = new Set(onlyBlocked ? visibleIds : byId.keys());

  if (items.data && byId.size === 0) {
    return (
      <div className="mx-auto max-w-4xl p-4 md:p-6">
        <h1 className="text-lg font-semibold">🔗 依赖图</h1>
        <Empty title="没有工作项" hint="建卡并连上 depends_on/blocks 后，这里画出谁挡着谁" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-semibold">🔗 依赖图</h1>
        {cp.data?.cycle && <Badge tone="red">依赖成环——关键路径不可计算</Badge>}
        <label className="ml-auto flex items-center gap-1.5 text-xs text-mut">
          <input type="checkbox" checked={onlyBlocked} onChange={(e) => setOnlyBlocked(e.target.checked)} />
          只看被阻塞的
        </label>
      </div>
      <p className="text-xs text-mut">
        分层＝拓扑层级；灰＝已完成、绿＝进行中、红＝被未完成上游阻塞；琥珀描边＝CPM 关键链。
      </p>
      <Card className="overflow-auto p-2">
        <svg width={Math.max(layout.width, 400)} height={Math.max(layout.height, 120)}>
          {edges.filter((e) => visible.has(e.from) && visible.has(e.to)).map((e, i) => {
            const a = layout.pos.get(e.from);
            const b = layout.pos.get(e.to);
            if (!a || !b) return null;
            const x1 = a.x + NODE_W / 2, y1 = a.y + NODE_H;
            const x2 = b.x + NODE_W / 2, y2 = b.y;
            const onChain = critical.has(e.from) && critical.has(e.to) && e.kind === "depends_on";
            return (
              <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={onChain ? "#f59e0b" : e.kind === "blocks" ? "#f97316" : "#94a3b8"}
                strokeWidth={onChain ? 2.5 : 1.5}
                strokeDasharray={e.kind === "blocks" ? undefined : "5 4"}
                markerEnd="" />
            );
          })}
          {[...byId.entries()].filter(([id]) => visible.has(id)).map(([id, it]) => {
            const p = layout.pos.get(id);
            if (!p) return null;
            const done = it.status_group === "done";
            const blocked = blockedIds.has(id);
            const fill = done ? "#e2e8f0" : blocked ? "#fee2e2" : "#dcfce7";
            const stroke = done ? "#cbd5e1" : blocked ? "#ef4444" : "#22c55e";
            return (
              <g key={id} data-dep-node={id}>
                <rect x={p.x} y={p.y} width={NODE_W} height={NODE_H} rx={10}
                  fill={fill} stroke={critical.has(id) ? "#f59e0b" : stroke}
                  strokeWidth={critical.has(id) ? 3 : 1.5} />
                <text x={p.x + 10} y={p.y + 18} fontSize={12} fontWeight={600}
                  className="select-none" fill="#0f172a">
                  {it.title.length > 16 ? `${it.title.slice(0, 15)}…` : it.title}
                </text>
                <text x={p.x + 10} y={p.y + 34} fontSize={10} fill="#64748b" className="select-none">
                  {it.status}{blocked ? " · 被阻塞" : ""}{critical.has(id) ? " · 关键链" : ""}
                </text>
              </g>
            );
          })}
          {byId.size > 0 && visible.size === 0 && (
            <text x={20} y={40} fontSize={12} fill="#64748b">当前过滤下没有节点</text>
          )}
        </svg>
      </Card>
      <div className="flex gap-3 text-[10px] text-mut">
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-slate-200" />已完成</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-okln" />进行中</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-red-200" />被阻塞</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-warnln" />关键链</span>
        <span className={cx(critical.size ? "" : "hidden")}>链长 {critical.size}</span>
      </div>
    </div>
  );
}
