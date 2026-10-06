/** Dependency graph page (M40-I124, docs/01 §AM.3, Jira Plans dependencies
 *  map): a layered SVG view of the project's depends_on/blocks edges —
 *  topological levels run top-down, nodes are colored by state (done gray,
 *  blocked red: unfinished with an unfinished upstream, else green) and the
 *  CPM critical chain gets an amber ring (critical-path API). Pure frontend:
 *  relations come from the project-level bulk endpoint (M119-I366, one fetch
 *  instead of one getItem per item) and layout/blocked semantics live in
 *  lib/depgraph (M119-I367: depends_on 是 from=依赖方、to=前置——前置在上，
 *  被阻塞旗标落在依赖方头上；blocks 反之). */
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { computeBlocked, computeLevels, type DepEdge } from "../lib/depgraph";
import { Badge, Card, Empty, cx } from "../components/ui";

const NODE_W = 168;
const NODE_H = 44;
const GAP_X = 22;
const GAP_Y = 46;

export function DependencyGraphPage() {
  const { pid } = useParams();
  const items = useQuery({ queryKey: ["deps-items", pid], queryFn: () => api.listItems(pid!) });
  const cp = useQuery({ queryKey: ["critical-path", pid], queryFn: () => api.getCriticalPath(pid!) });
  const relations = useQuery({ queryKey: ["dep-relations", pid], queryFn: () => api.listRelations(pid!) });
  const [onlyBlocked, setOnlyBlocked] = useState(false);

  // M119-I366: relations ride the project-level bulk endpoint — the old
  // per-item getItem fan-out (one detail fetch per item to reach the
  // relations payload) was an N+1 across the whole project on every open.
  const edges = useMemo<DepEdge[]>(() => {
    const out: DepEdge[] = [];
    for (const r of relations.data?.relations ?? []) {
      if (r.relation_type === "depends_on" || r.relation_type === "blocks")
        out.push({ from: r.from_item, to: r.to_item, kind: r.relation_type });
    }
    return out;
  }, [relations.data]);

  const byId = useMemo(() => {
    const m = new Map<string, { id: string; title: string; status: string; status_group: string }>();
    for (const it of items.data?.items ?? [])
      m.set(it.id, { id: it.id, title: it.title, status: it.status, status_group: it.status_group });
    return m;
  }, [items.data]);

  // I237 (docs/01 §BX.1): cross-project edges used to be silently dropped
  // (foreign ids missing from byId → filtered out at render). M47-I143's
  //「外部依赖」placeholder lives in the graph endpoint (projects.py) consumed
  // by GraphView — bring /deps to the same semantics: fetch each foreign id
  // once; readable → real title + source project name, 404 → 🔒 (existence
  // details not leaked).
  const foreignIds = useMemo(() => {
    const local = new Set(byId.keys());
    const out = new Set<string>();
    for (const e of edges) {
      if (!local.has(e.from)) out.add(e.from);
      if (!local.has(e.to)) out.add(e.to);
    }
    return [...out];
  }, [edges, byId]);

  const foreignQ = useQuery({
    queryKey: ["dep-foreign", pid, foreignIds.join(",")],
    queryFn: async () => {
      const out: Record<string, { title: string; status_group: string; project_id: string; readable: boolean }> = {};
      await Promise.all(foreignIds.map(async (id) => {
        try {
          const it = await api.getItem(id);
          out[id] = { title: it.title, status_group: it.status_group, project_id: it.project_id, readable: true };
        } catch {
          out[id] = { title: "🔒 外部依赖", status_group: "external-unknown", project_id: "", readable: false };
        }
      }));
      return out;
    },
    enabled: foreignIds.length > 0,
  });

  const projectsQ = useQuery({ queryKey: ["projects-graph"], queryFn: () => api.listProjects() });

  // allNodes = 本地项 + 外部占位节点（可读显真名+来源项目名、不可读 🔒）——
  // /deps 与 graph 端点同语义；unreadable 状态未知不参与阻塞判定（宁缺勿假红，
  // 与看板 I128 SQL 口径在「不可读外部上游」子场景的已知差异，注释钉住）。
  const allNodes = useMemo(() => {
    const m = new Map<string, { id: string; title: string; status: string; status_group: string; foreignReadable?: boolean }>();
    for (const [id, it] of byId) m.set(id, { ...it });
    for (const [id, f] of Object.entries(foreignQ.data ?? {})) {
      const pname = f.project_id ? projectsQ.data?.projects.find((p) => p.id === f.project_id)?.name : null;
      m.set(id, {
        id,
        title: f.readable ? f.title : "🔒 外部依赖",
        status: f.readable ? `${pname ?? "外部项目"}` : "外部依赖",
        status_group: f.status_group,
        foreignReadable: f.readable,
      });
    }
    return m;
  }, [byId, foreignQ.data, projectsQ.data]);

  // blocked = unfinished item with an unfinished upstream (depends_on 前置
  // 或 blocks 阻塞者——M119-I367 方向修正后与看板 I128 SQL 同向)；I237:
  // foreign upstream counts too when its status is readable (board I128 SQL
  // has no project filter; unknown-status 🔒 placeholders are honestly NOT
  // counted)
  const blockedIds = useMemo(
    () => computeBlocked(allNodes, edges), [edges, allNodes]);

  // topological levels: level(x) = 0 without upstream edges, else max(up)+1
  // （M119-I367: 方向语义收口进 lib/depgraph——前置在上、依赖方在下）
  const levels = useMemo(() => {
    const level = computeLevels(allNodes.keys(), edges);
    const rows = new Map<number, string[]>();
    for (const id of allNodes.keys()) {
      const lv = level.get(id) ?? 0;
      rows.set(lv, [...(rows.get(lv) ?? []), id]);
    }
    return rows;
  }, [edges, allNodes]);

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
    if (!onlyBlocked) return [...allNodes.keys()];
    return [...allNodes.keys()].filter((id) => blockedIds.has(id));
  }, [onlyBlocked, blockedIds, allNodes]);
  const visible = new Set(onlyBlocked ? visibleIds : allNodes.keys());

  if (items.isError) {
    return (
      <div className="mx-auto max-w-4xl p-4 md:p-6">
        <h1 className="text-lg font-semibold">🔗 依赖图</h1>
        <Empty title="工作项加载失败" hint="请刷新重试" />
      </div>
    );
  }
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
            // 边从上层节点的底边画到下层节点的顶边——M119-I367 方向修正后
            // depends_on 的 from 在下、to 在上，按 y 归一避免反向画线
            const [p, q] = a.y <= b.y ? [a, b] : [b, a];
            const x1 = p.x + NODE_W / 2, y1 = p.y + NODE_H;
            const x2 = q.x + NODE_W / 2, y2 = q.y;
            const onChain = critical.has(e.from) && critical.has(e.to) && e.kind === "depends_on";
            return (
              <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={onChain || e.kind === "blocks" ? "var(--color-warn)" : "var(--color-mut)"}
                strokeWidth={onChain ? 2.5 : 1.5}
                strokeDasharray={e.kind === "blocks" ? undefined : "5 4"} />
            );
          })}
          {[...allNodes.entries()].filter(([id]) => visible.has(id)).map(([id, it]) => {
            const p = layout.pos.get(id);
            if (!p) return null;
            const done = it.status_group === "done";
            const blocked = blockedIds.has(id);
            const foreign = it.foreignReadable !== undefined;
            // M114-I341: SVG 与图例同走 --color-* 语义 token（亮暗双主题翻转，
            // ReportsPage 折线同款做法）——硬编码 slate/red/green 色在暗色主题
            // 下是贴在暗卡上的亮色拼图，图例 bg-okln/warnln 也随之失配。
            const fill = foreign ? "var(--color-bg)" : done ? "var(--color-bg)"
              : blocked ? "var(--color-danbg)" : "var(--color-okbg)";
            const stroke = foreign ? "var(--color-mut)" : done ? "var(--color-line)"
              : blocked ? "var(--color-dan)" : "var(--color-ok)";
            return (
              <g key={id} data-dep-node={id}>
                <rect x={p.x} y={p.y} width={NODE_W} height={NODE_H} rx={10}
                  fill={fill} stroke={critical.has(id) ? "var(--color-warn)" : stroke}
                  strokeWidth={critical.has(id) ? 3 : 1.5}
                  strokeDasharray={foreign ? "4 3" : undefined} />
                <text x={p.x + 10} y={p.y + 18} fontSize={12} fontWeight={600}
                  className="select-none" fill="var(--color-ink)">
                  {it.title.length > 16 ? `${it.title.slice(0, 15)}…` : it.title}
                </text>
                <text x={p.x + 10} y={p.y + 34} fontSize={10} fill="var(--color-mut)" className="select-none">
                  {it.status}{blocked ? " · 被阻塞" : ""}{critical.has(id) ? " · 关键链" : ""}
                </text>
              </g>
            );
          })}
          {allNodes.size > 0 && visible.size === 0 && (
            <text x={20} y={40} fontSize={12} fill="var(--color-mut)">当前过滤下没有节点</text>
          )}
        </svg>
      </Card>
      <div className="flex gap-3 text-[10px] text-mut">
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm border border-line bg-bg" />已完成</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-okbg ring-1 ring-okln" />进行中</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-danbg ring-1 ring-dan" />被阻塞</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-warn" />关键链</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm border border-dashed border-mut bg-bg" />外部依赖（可读显名/不可读 🔒）</span>
        <span className={cx(critical.size ? "" : "hidden")}>链长 {critical.size}</span>
      </div>
    </div>
  );
}
