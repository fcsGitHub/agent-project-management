/** Dependency-graph semantics extracted from DependencyGraphPage (M119-I367)
 *  so the direction contract is unit-testable outside the component. */
export type DepEdge = { from: string; to: string; kind: "depends_on" | "blocks" };
export type DepNodeState = { status_group: string };

const FINISHED = new Set(["done", "cancelled"]);

/** node → its upstream prerequisite ids (who must go first).
 *  M119-I367 方向契约：depends_on 是 from=依赖方、to=前置（与本库自动排程/
 *  blocked 旗标/CPM 同向）——依赖方的上游是前置；blocks 是 from=阻塞者、
 *  to=被阻塞——被阻塞者的上游是阻塞者。页面旧实现把 e.from 一律当上游，
 *  depends_on 家族整体反向（层级倒挂 + 被阻塞旗标标到前置头上）。 */
export function upstreamMap(edges: DepEdge[]): Map<string, string[]> {
  const up = new Map<string, string[]>();
  for (const e of edges) {
    const [down, upstream] = e.kind === "depends_on" ? [e.from, e.to] : [e.to, e.from];
    up.set(down, [...(up.get(down) ?? []), upstream]);
  }
  return up;
}

/** unfinished nodes whose upstream is unfinished (Businessmap I128 blocked
 *  flag); unknown-status (🔒 external) upstreams are honestly not counted. */
export function computeBlocked(
  nodes: Map<string, DepNodeState>, edges: DepEdge[],
): Set<string> {
  const bad = new Set<string>();
  for (const e of edges) {
    const [downId, upId] = e.kind === "depends_on" ? [e.from, e.to] : [e.to, e.from];
    const upstream = nodes.get(upId);
    if (!upstream || FINISHED.has(upstream.status_group)
      || upstream.status_group === "external-unknown") continue;
    const down = nodes.get(downId);
    if (down && !FINISHED.has(down.status_group)) bad.add(downId);
  }
  return bad;
}

/** topological level: 0 without upstream edges, else max(up)+1 (cycle-safe). */
export function computeLevels(
  ids: Iterable<string>, edges: DepEdge[],
): Map<string, number> {
  const up = upstreamMap(edges);
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
  for (const id of ids) calc(id, 0);
  return level;
}
