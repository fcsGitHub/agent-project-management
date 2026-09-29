/** Artifacts page (I217, docs/01 §BQ.2): project-wide artifact browser —
 * the read half of list_artifacts finally consumed. One card per artifact
 * (path / updated / versions), click opens the I214 preview drawer, 🗑
 * deletes via git rm (history IS the soft delete — audit trail intact). */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import { Badge, Card, Empty } from "../components/ui";
import { ArtifactPreviewDrawer } from "../components/ArtifactPreviewDrawer";
import { artifactShortName } from "../lib/artifactRefs";

export function ArtifactsPage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const arts = useQuery({
    queryKey: ["artifacts", pid],
    queryFn: () => api.listArtifacts(pid!),
    enabled: !!pid,
  });
  const [preview, setPreview] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const remove = async (path: string) => {
    if (!window.confirm(`删除工件「${path}」？git 历史仍可追溯（软删）。`)) return;
    setDeleting(path);
    try {
      await api.deleteArtifact(pid!, path);
      toast.success("工件已删除", { description: "git 历史可追溯；搜索已同步移除" });
      qc.invalidateQueries({ queryKey: ["artifacts", pid] });
      qc.invalidateQueries({ queryKey: ["search"] });
    } catch (e) {
      toast.error(`删除失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setDeleting(null);
    }
  };

  const rows = arts.data?.artifacts ?? [];
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-sm font-semibold">📄 工件</span>
        <Badge tone="neutral">{rows.length}</Badge>
        <button
          className="ml-auto rounded-lg border border-line px-2 py-1 text-xs text-mut hover:border-acc hover:text-acc disabled:opacity-50"
          disabled={!rows.length}
          title="git archive 打包 artifacts/ 子树（zip·锚定当前 commit 可复现）"
          onClick={async () => {
            try {
              const blob = await api.exportArtifacts(pid!);
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = `artifacts-${pid!.slice(0, 8)}.zip`;
              a.click();
              URL.revokeObjectURL(a.href);
              toast.success("工件包已导出");
              qc.invalidateQueries({ queryKey: ["artifacts", pid] });
            } catch (e) {
              toast.error(e instanceof Error ? e.message : String(e));
            }
          }}>📦 导出工件包</button>
        <span className="text-[10px] text-mut">
          agent 产出与手动编辑的 PRD/WBS/报告都在这里；点击预览，🗑 删除（git 历史可追溯）
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {!rows.length && !arts.isLoading && (
          <Empty icon="📄" title="还没有工件"
            hint="让 Agent 执行任务后，产出的 PRD/WBS/报告会出现在这里；全局搜索第四类也能搜到它们" />
        )}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((a) => (
            <Card key={a.path} className="group p-3 text-xs transition-all hover:border-acc">
              <button className="flex w-full items-center gap-2 text-left"
                onClick={() => setPreview(a.path)} title="预览工件">
                <span className="min-w-0 flex-1 truncate font-mono font-medium">📄 {artifactShortName(a.path)}</span>
                <Badge tone="neutral">v{a.versions}</Badge>
              </button>
              <div className="mt-1 truncate font-mono text-[10px] text-mut" title={a.path}>{a.path}</div>
              <div className="mt-1.5 flex items-center gap-2">
                <span className="text-[10px] text-mut">{a.updated_at ? timeAgo(a.updated_at) : "—"}</span>
                {a.deposits_to && <Badge tone="violet">沉淀 {a.deposits_to}</Badge>}
                <button className="ml-auto text-[11px] text-mut opacity-0 transition-opacity hover:text-dan group-hover:opacity-100"
                  disabled={deleting === a.path}
                  onClick={() => remove(a.path)}
                  title="删除工件（git rm——历史可追溯）">🗑 删除</button>
              </div>
            </Card>
          ))}
        </div>
      </div>
      {preview && <ArtifactPreviewDrawer pid={pid!} path={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
