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
