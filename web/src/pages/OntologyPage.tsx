/** Ontology page: read-only browsing of the project's type system + validation
 *  + the ontology-learning flywheel (M4-I14, docs/08 §8: scan → review → apply). */
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useState } from "react";
import { api, type OntologyLearnResult } from "../lib/api";
import { Badge, Button, Card } from "../components/ui";

export function OntologyPage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const onto = useQuery({
    queryKey: ["ontology", pid],
    queryFn: () => api.getOntology(pid!, true),
    enabled: !!pid,
  });
  const o = onto.data;
  const [scan, setScan] = useState<OntologyLearnResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  if (!o) return <div className="p-6 text-sm text-mut">加载本体…</div>;

  const runLearn = async () => {
    setScanning(true);
    try {
      const r = await api.learnOntology(o.name);
      setScan(r);
      setSelected(new Set());
      if (!r.candidates.length) toast.info("数据与本体一致，暂无可归纳的变更候选");
    } catch (e) {
      toast.error(`扫描失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setScanning(false);
    }
  };

  const runApply = async () => {
    if (!selected.size) return;
    setApplying(true);
    try {
      const r = await api.applyOntology(o.name, [...selected]);
      toast.success(`已应用 ${r.applied.length} 项候选，本体升级到 v${r.version}`);
      setScan(null);
      setSelected(new Set());
      await qc.invalidateQueries({ queryKey: ["ontology", pid] });
    } catch (e) {
      toast.error(`应用失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setApplying(false);
    }
  };

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="space-y-4 p-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{o.display_name}</span>
          <Badge tone="violet">{o.name} · v{o.version}</Badge>
          <Badge tone={o.errors.length ? "red" : "green"}>
            {o.errors.length ? `校验失败（${o.errors.length}）` : "校验通过 ✓"}
          </Badge>
          <span className="ml-auto font-mono text-xs text-mut">ontology/ontology.yaml</span>
        </div>
        {o.errors.length > 0 && (
          <ul className="mt-2 space-y-0.5 text-xs text-dan">
            {o.errors.map((e, i) => <li key={i}>· {e}</li>)}
          </ul>
        )}
        <div className="mt-3 grid grid-cols-3 gap-3 text-xs text-mut">
          <div>概念 {o.concepts.length} / 12</div>
          <div>阶段 {o.phases.length}</div>
          <div>资产类型 {o.asset_kinds.length} · 库 {o.libraries.length}</div>
        </div>
      </Card>

      <LearnPanel
        scan={scan} scanning={scanning} applying={applying} selected={selected}
        onLearn={runLearn} onApply={runApply} onToggle={toggle}
      />

      <div>
        <div className="mb-2 text-xs font-semibold text-mut">Competency Questions（验收锚点）</div>
        <Card className="p-3">
          <ul className="space-y-1 text-xs">
            {o.competency_questions.map((q, i) => <li key={i}>❓ {q}</li>)}
          </ul>
        </Card>
      </div>

      <div>
        <div className="mb-2 text-xs font-semibold text-mut">概念（工作项类型系统）</div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          {o.concepts.map((c) => (
            <Card key={c.id} className="p-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <span>{c.icon}</span> {c.name}
                <span className="font-mono text-[10px] text-mut">{c.id}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {c.states.map((s) => (
                  <Badge key={s.id} tone={
                    s.group === "done" ? "green" : s.group === "in_progress" ? "amber" :
                    s.group === "todo" ? "indigo" : "neutral"
                  }>{s.name}</Badge>
                ))}
              </div>
              <div className="mt-2 text-[11px] text-mut">
                角色：{c.agent_roles.join(", ") || "—"}
                {c.artifact_kinds.length > 0 && <> · 工件：{c.artifact_kinds.map((a) => a.id).join(", ")}</>}
              </div>
            </Card>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="mb-2 text-xs font-semibold text-mut">阶段图（Phase + Gate）</div>
          <Card className="p-3">
            <div className="flex flex-wrap items-center gap-1 text-xs">
              {o.phases.map((p, i) => (
                <span key={p.id} className="flex items-center gap-1">
                  {i > 0 && <span className="text-mut">→</span>}
                  <span className="rounded-lg border border-line px-2 py-1">{p.name}</span>
                  {p.gate && <span className="text-warn">◆{p.gate}</span>}
                </span>
              ))}
            </div>
          </Card>
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold text-mut">资产库注册</div>
          <Card className="divide-y divide-line">
            {o.libraries.map((l) => (
              <div key={l.id} className="flex items-center gap-2 px-3 py-2 text-xs">
                <span className="font-medium">{libIcon(l.id)} {l.name}</span>
                <span className="ml-auto text-mut">accepts: {l.accepts.join(", ")}</span>
              </div>
            ))}
            {!o.libraries.length && <div className="p-3 text-xs text-mut">无</div>}
          </Card>
        </div>
      </div>
    </div>
  );
}

function libIcon(id: string) {
  return { product: "📦", test: "🧪", doc: "📚" }[id] ?? "🗃️";
}

const RULE_META: Record<string, { label: string; tone: string }> = {
  "L1-add-field": { label: "字段显式化", tone: "indigo" },
  "L2-register-relation": { label: "关系补注册", tone: "amber" },
  "L3-wire-deposit": { label: "沉淀链接补全", tone: "violet" },
  "L4-add-role": { label: "角色覆盖", tone: "green" },
};

/** Ontology-learning panel (semantica 模式融合)：scan data → review → apply. */
function LearnPanel({
  scan, scanning, applying, selected, onLearn, onApply, onToggle,
}: {
  scan: OntologyLearnResult | null; scanning: boolean; applying: boolean;
  selected: Set<string>;
  onLearn: () => void; onApply: () => void; onToggle: (id: string) => void;
}) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">🔬 本体学习</span>
        <Badge tone="neutral">semantica 模式 · 从数据归纳</Badge>
        <span className="ml-auto flex items-center gap-2">
          {scan && (
            <span className="font-mono text-[11px] text-mut">
              扫描 {scan.scanned.projects} 项目 · {scan.scanned.items} 工作项 · {scan.scanned.relations} 关系 · {scan.scanned.artifact_links} 资产链接
            </span>
          )}
          <Button size="sm" variant="outline" disabled={scanning || applying} onClick={onLearn}>
            {scanning ? "扫描中…" : scan ? "重新扫描" : "扫描项目数据"}
          </Button>
          {scan && scan.candidates.length > 0 && (
            <Button size="sm" variant="primary" disabled={applying || !selected.size} onClick={onApply}>
              {applying ? "应用中…" : `应用选中（${selected.size}）`}
            </Button>
          )}
        </span>
      </div>
      {scan && (
        <div className="mt-3 space-y-2">
          {scan.candidates.map((c) => {
            const rule = RULE_META[c.provenance.rule] ?? { label: c.provenance.rule, tone: "neutral" };
            return (
              <label key={c.id} className="flex cursor-pointer items-start gap-2 rounded-lg border border-line bg-bg px-3 py-2">
                <input
                  type="checkbox" className="mt-1 accent-indigo-500"
                  checked={selected.has(c.id)} onChange={() => onToggle(c.id)}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={rule.tone as never}>{rule.label}</Badge>
                    <span className="text-xs text-ink">{c.summary}</span>
                  </span>
                  <span className="mt-1 block font-mono text-[10px] text-mut">
                    {c.provenance.rule} · support {c.provenance.support}
                    {c.provenance.sample_item_ids?.length ? ` · 样本 ${c.provenance.sample_item_ids.join(", ")}` : ""}
                    {c.provenance.sample_run_ids?.length ? ` · runs ${c.provenance.sample_run_ids.join(", ")}` : ""}
                    {c.provenance.sample_asset_ids?.length ? ` · assets ${c.provenance.sample_asset_ids.join(", ")}` : ""}
                  </span>
                </span>
              </label>
            );
          })}
          {!scan.candidates.length && (
            <div className="rounded-lg border border-line bg-bg px-3 py-2 text-xs text-mut">
              未发现可执行的变更候选。
            </div>
          )}
          {scan.observations.unused_concepts.length > 0 && (
            <div className="rounded-lg border border-dashed border-line px-3 py-2 text-[11px] text-mut">
              观察（不参与应用）：以下概念在本体覆盖的所有项目中零使用，可考虑精简 —— {scan.observations.unused_concepts.join("、")}
            </div>
          )}
        </div>
      )}
      {!scan && (
        <p className="mt-2 text-xs text-mut">
          扫描该本体下所有项目的实际数据（字段使用、遗留关系、资产沉淀、角色执行），
          生成带 provenance 的变更候选；勾选并应用后本体 YAML 版本 +1 并落审计事件。
        </p>
      )}
    </Card>
  );
}
