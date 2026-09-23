/** M55-I166 notification bundling (docs/01 §AZ.2, Courier lesson): display-
 * layer collapsing of consecutive same-kind+same-project watch notifications
 * into one row with a count — the highest-leverage noise fix, and it never
 * touches the event stream or read semantics (expand = per-row as before). */

export type BundleInput = {
  id: string; kind: string; project_id: string; summary: string;
  read: number; created_at: string;
};

export type BundleRow<T> =
  | { kind: "single"; note: T }
  | { kind: "bundle"; key: string; notes: T[] };

export function bundleWatch<T extends BundleInput>(rows: T[]): BundleRow<T>[] {
  const out: BundleRow<T>[] = [];
  for (const n of rows) {
    const last = out[out.length - 1];
    if (n.kind === "watch" && last && last.kind === "bundle"
        && last.notes[0].project_id === n.project_id) {
      last.notes.push(n);
    } else if (n.kind === "watch") {
      out.push({ kind: "bundle", key: `watch-${n.project_id}-${n.id}`, notes: [n] });
    } else {
      out.push({ kind: "single", note: n });
    }
  }
  return out;
}
