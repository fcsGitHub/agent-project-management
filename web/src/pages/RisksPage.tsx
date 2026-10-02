/** Risk register page (M43-I131, docs/01 §AP.1, PMBOK probability×impact
 *  matrix + OpenProject native risk module): a 3×3 heat matrix plus a list
 *  sorted by score (p×i descending). Every risk carries a response plan, an
 *  owner and a review date; the lifecycle runs open → mitigated → closed. */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Badge, Button, Card, Empty, Input, cx } from "../components/ui";

const LEVEL_LABEL: Record<number, string> = { 1: "低", 2: "中", 3: "高" };
const CELL_TONE: Record<number, string> = {
  1: "bg-okbg text-ok",
  2: "bg-okbg text-ok",
  3: "bg-amber-100 text-amber-700",
  4: "bg-amber-100 text-amber-700",
  6: "bg-orange-100 text-orange-700",
  9: "bg-red-100 text-red-700",
};

export function RisksPage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const risks = useQuery({ queryKey: ["risks", pid], queryFn: () => api.listRisks(pid!) });
  const [title, setTitle] = useState("");
  const [probability, setProbability] = useState(2);
  const [impact, setImpact] = useState(2);
  const [busy, setBusy] = useState(false);

  const rows = (risks.data?.risks ?? []).filter((r) => r.status !== "closed");

  const add = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await api.createRisk(pid!, { title: title.trim(), probability, impact });
      toast.success("风险已登记");
      setTitle("");
      await qc.invalidateQueries({ queryKey: ["risks", pid] });
    } catch (e) {
      toast.error(`登记失败：${e instanceof Error ? e.message : e}`);
    } finally { setBusy(false); }
  };

  const transition = async (id: string, status: "mitigated" | "closed") => {
    try {
      await api.updateRisk(id, { status });
      toast.success(status === "mitigated" ? "已标记缓解" : "风险已关闭");
      await qc.invalidateQueries({ queryKey: ["risks", pid] });
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 md:p-6">
      <div>
        <h1 className="text-lg font-semibold">⚠ 风险登记册</h1>
        <p className="mt-0.5 text-xs text-mut">
          概率×影响打分排序（PMBOK 语义）——每条风险带应对措施、责任人与复审日期
        </p>
      </div>

      <Card className="p-4">
        <div className="mb-2 text-sm font-semibold">概率 × 影响矩阵</div>
        <div className="grid grid-cols-[auto_repeat(3,1fr)] gap-1 text-center text-xs">
          <span />
          {[1, 2, 3].map((i) => <span key={i} className="text-mut">影响 {LEVEL_LABEL[i]}</span>)}
          {[3, 2, 1].map((p) => (
            <>
              <span key={`l${p}`} className="self-center text-mut">概率 {LEVEL_LABEL[p]}</span>
              {[1, 2, 3].map((i) => {
                const cellRows = rows.filter((r) => r.probability === p && r.impact === i);
                return (
                  <div key={`${p}-${i}`}
                    className={cx("min-h-14 rounded-lg p-1.5", CELL_TONE[p * i] ?? "bg-bg")}>
                    <span className="text-[10px]">{p * i}分</span>
                    {cellRows.map((r) => (
                      <div key={r.id} className="mt-0.5 truncate rounded bg-white/70 px-1 text-[10px]"
                        title={r.title}>{r.title}</div>
                    ))}
                  </div>
                );
              })}
            </>
          ))}
        </div>
      </Card>

      <Card className="p-4">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-sm font-semibold">登记新风险</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Input className="w-56" placeholder="风险标题" value={title} onChange={(e) => setTitle(e.target.value)} />
          <select value={probability} onChange={(e) => setProbability(Number(e.target.value))}
            className="rounded-md border border-line bg-bg px-2 py-1.5 text-xs" aria-label="概率">
            {[1, 2, 3].map((v) => <option key={v} value={v}>概率 {LEVEL_LABEL[v]}</option>)}
          </select>
          <select value={impact} onChange={(e) => setImpact(Number(e.target.value))}
            className="rounded-md border border-line bg-bg px-2 py-1.5 text-xs" aria-label="影响">
            {[1, 2, 3].map((v) => <option key={v} value={v}>影响 {LEVEL_LABEL[v]}</option>)}
          </select>
          <Button size="sm" variant="primary" disabled={busy || !title.trim()} onClick={add}>登记</Button>
        </div>
      </Card>

      {!risks.isLoading && !rows.length && (
        <Empty title="登记册为空" hint="识别到不确定事件后在这里登记，按概率×影响排序" />
      )}
      {rows.length > 0 && (
        <Card className="divide-y divide-line">
          {rows.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs">
              <Badge tone={r.score >= 6 ? "red" : r.score >= 3 ? "amber" : "green"}>
                {r.score}分
              </Badge>
              <span className="font-medium">{r.title}</span>
              <span className="text-mut">
                概率 {LEVEL_LABEL[r.probability]} · 影响 {LEVEL_LABEL[r.impact]}
                {r.response ? ` · 应对：${r.response}` : ""}
                {r.owner ? ` · 责任人 ${r.owner}` : ""}
                {r.review_date ? ` · 复审 ${r.review_date}` : ""}
              </span>
              <div className="ml-auto flex items-center gap-1">
                {r.status === "open" && (
                  <Button size="sm" variant="ghost" onClick={() => transition(r.id, "mitigated")}>标记缓解</Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => transition(r.id, "closed")}>关闭</Button>
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
