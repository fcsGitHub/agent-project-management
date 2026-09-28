/** I214 (docs/01 §BP.2): universal artifact preview drawer — Cloudscape
 * "artifact previews" semantics: the preview lives where the output appears
 * (write-back comments, run details, search hits), one click, no navigation.
 * The getArtifact endpoint already returns content + history + diff vs
 * previous; this is the shared read-side view. FeaturePage keeps its own
 * inline implementation (working-context control, zero regression). */
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Drawer, Badge, Empty } from "./ui";

export function ArtifactPreviewDrawer({ pid, path, onClose }: {
  pid: string; path: string | null; onClose: () => void;
}) {
  const art = useQuery({
    queryKey: ["artifact", pid, path],
    queryFn: () => api.getArtifact(pid, path!),
    enabled: !!pid && !!path,
  });
  if (!path) return null;
  const a = art.data;
  return (
    <Drawer open onClose={onClose} title={<span className="font-mono text-sm">📄 {path}</span>} width="46%">
      {art.isLoading && <div className="text-sm text-mut">加载工件…</div>}
      {art.isError && <div className="text-sm text-dan">工件加载失败（可能已删除或无权限）。</div>}
      {a && (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="indigo">v{a.history?.length ?? 1}</Badge>
            {a.history?.[0] && (
              <span className="text-[10px] text-mut">
                最近 {a.history[0].commit.slice(0, 7)} · {a.history[0].message}
              </span>
            )}
          </div>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-[12px] border border-line bg-surface p-3 text-xs leading-relaxed">
            {a.content || "（空工件）"}
          </pre>
          {a.diff_vs_previous && (
            <div>
              <div className="mb-1 text-xs font-semibold text-mut">相对上一版的变化</div>
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-bg p-2 font-mono text-[10px] leading-relaxed">
                {a.diff_vs_previous}
              </pre>
            </div>
          )}
          {a.history?.length > 1 && (
            <div className="text-[11px] text-mut">
              版本史：{a.history.map((h) => h.commit.slice(0, 7)).join(" ← ")}
            </div>
          )}
        </div>
      )}
      {!a && !art.isLoading && !art.isError && <Empty icon="📄" title="暂无内容" />}
    </Drawer>
  );
}
