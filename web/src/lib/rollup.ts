/** I102: subtask progress rollup (docs/01 §AF.2, GitHub sub-issue progress
 *  semantics) — per parent: done/total direct children + summed spent minutes.
 *  Pure function over already-fetched items; only direct children roll up. */
export type RollupInput = {
  id: string;
  parent_id?: string | null;
  status_group?: string | null;
  spent_minutes?: number | null;
};

export type SubProgress = { done: number; total: number; spent: number };

export function subtaskProgress(items: RollupInput[]): Map<string, SubProgress> {
  const m = new Map<string, SubProgress>();
  for (const it of items) {
    if (!it.parent_id) continue;
    const rec = m.get(it.parent_id) ?? { done: 0, total: 0, spent: 0 };
    rec.total += 1;
    if (it.status_group === "done") rec.done += 1;
    rec.spent += it.spent_minutes ?? 0;
    m.set(it.parent_id, rec);
  }
  return m;
}

/** I116 (docs/01 §AK.1, Jira Plans roll-up + MS Project %Work Complete
 *  semantics): hierarchical progress — every parent aggregates its direct
 *  children weighted by estimate_hours (missing/zero estimates fall back to
 *  1.0, matching the I106 S-curve caliber), and grandchildren roll upward
 *  through the chain. Depth-capped defensively; parents with no children are
 *  never in the result. */
export type RollupItem = RollupInput & { estimate_hours?: number | null };

export type WeightedProgress = {
  percent: number; // 0..100, estimate-weighted
  done: number; // rolled-up done count (all descendants)
  total: number; // rolled-up total count
  spent: number; // rolled-up spent minutes
};

const MAX_ROLLUP_DEPTH = 10;

export function weightedProgress(items: RollupItem[]): Map<string, WeightedProgress> {
  const childrenOf = new Map<string, RollupItem[]>();
  for (const it of items) {
    if (it.parent_id) {
      const kids = childrenOf.get(it.parent_id) ?? [];
      kids.push(it);
      childrenOf.set(it.parent_id, kids);
    }
  }

  const weightOf = (it: RollupItem): number =>
    it.estimate_hours && it.estimate_hours > 0 ? it.estimate_hours : 1.0;

  // fraction done for one item (0..1); parents aggregate children recursively
  const fractionOf = (it: RollupItem, depth: number): number => {
    if (depth > MAX_ROLLUP_DEPTH) return it.status_group === "done" ? 1 : 0;
    const kids = childrenOf.get(it.id) ?? [];
    if (!kids.length) return it.status_group === "done" ? 1 : 0;
    let num = 0;
    let den = 0;
    for (const k of kids) {
      const w = weightOf(k);
      num += w * fractionOf(k, depth + 1);
      den += w;
    }
    return den > 0 ? num / den : 0;
  };

  // rolled-up done/total/spent counts per parent (all descendants); iterative
  // with a visited set so pathological cycles can't hang and depth is unlimited
  const rollupCounts = (root: RollupItem): { done: number; total: number; spent: number } => {
    const seen = new Set<string>([root.id]);
    const stack = [...(childrenOf.get(root.id) ?? [])];
    let done = 0;
    let total = 0;
    let spent = 0;
    while (stack.length) {
      const it = stack.pop()!;
      if (seen.has(it.id)) continue;
      seen.add(it.id);
      total += 1;
      if (it.status_group === "done") done += 1;
      spent += it.spent_minutes ?? 0;
      stack.push(...(childrenOf.get(it.id) ?? []));
    }
    return { done, total, spent };
  };

  const m = new Map<string, WeightedProgress>();
  for (const it of items) {
    if (!childrenOf.has(it.id)) continue; // parents only
    const kids = childrenOf.get(it.id) ?? [];
    let num = 0;
    let den = 0;
    for (const k of kids) {
      const w = weightOf(k);
      num += w * fractionOf(k, 1);
      den += w;
    }
    const counts = rollupCounts(it);
    m.set(it.id, {
      percent: den > 0 ? Math.round((num / den) * 100) : 0,
      done: counts.done,
      total: counts.total,
      spent: counts.spent,
    });
  }
  return m;
}
