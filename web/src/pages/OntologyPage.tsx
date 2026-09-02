/** Ontology page: read-only browsing of the project's type system + validation
 *  + the ontology-learning flywheel (M4-I14, docs/08 §8: scan → review → apply)
 *  + versioning with semantic diff & impact analysis (M4-I15). */
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useState } from "react";
import { api, type OntologyDiff, type OntologyLearnResult } from "../lib/api";
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
  const [diff, setDiff] = useState<OntologyDiff | null>(null);
  const [diffing, setDiffing] = useState(false);

  const history = useQuery({
    queryKey: ["ontology-history", pid],
    queryFn: () => api.getOntologyHistory(o?.name ?? ""),
    enabled: !!o,
  });
  const cq = useQuery({
    queryKey: ["ontology-cq", pid],
    queryFn: () => api.cqCheck(o!.name),
    enabled: !!o,
  });

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

  const runLearnLlm = async () => {
    setScanning(true);
    try {
      const r = await api.learnOntologyLlm(o.name);
      setScan(r);
      setSelected(new Set());
      if (r.llm?.error) toast.warning(`LLM 层降级：${r.llm.error}（pattern 层结果不受影响）`);
      else if (!r.candidates.length) toast.info("LLM 层与数据面均无可归纳的变更候选");
      else toast.success(`LLM 层：接受 ${r.llm?.accepted ?? 0} 条（合并 ${r.llm?.merged ?? 0} 条）`);
    } catch (e) {
      toast.error(`LLM 扫描失败：${e instanceof Error ? e.message : e}`);
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
      await qc.invalidateQueries({ queryKey: ["ontology-history", pid] });
      await qc.invalidateQueries({ queryKey: ["ontology-cq", pid] });
    } catch (e) {
      toast.error(`应用失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setApplying(false);
    }
  };

  const runDiff = async (fromV: number, toV?: number) => {
    setDiffing(true);
    try {
      setDiff(await api.getOntologyDiff(o!.name, fromV, toV));
    } catch (e) {
      toast.error(`diff 失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setDiffing(false);
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
        onLearn={runLearn} onLearnLlm={runLearnLlm} onApply={runApply} onToggle={toggle}
      />

      <VersionPanel
        currentVersion={o.version}
        history={history.data}
        diff={diff} diffing={diffing}
        onDiff={runDiff}
      />

      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-mut">
          Competency Questions（验收锚点 · I16 可回答性检查）
          {cq.data && <Badge tone={allAnswerable(cq.data) ? "green" : "amber"}>{cq.data.summary}</Badge>}
        </div>
        <Card className="divide-y divide-line">
          {cq.data?.questions.map((q) => (
            <div key={q.question} className="px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs">❓ {q.question}</span>
                <CqStatusBadge status={q.status} />
              </div>
              {q.evidence.length > 0 && (
                <div className="mt-1 space-y-0.5 pl-4">
                  {q.evidence.map((e) => (
                    <div key={e.source} className="font-mono text-[10px] text-mut">
                      {SOURCE_LABEL[e.source] ?? e.source}：{e.count > 0 ? `✓ ${e.count}` : "× 0"} — {e.summary}
                    </div>
                  ))}
                </div>
              )}
              {q.status === "unmapped" && (
                <div className="mt-1 pl-4 text-[10px] text-mut">
                  未声明支撑数据面——在 ontology.yaml 的 cq_mappings 中为该问题补充 supports。
                </div>
              )}
            </div>
          ))}
          {!cq.data && <div className="px-3 py-2 text-xs text-mut">检查中…</div>}
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

const KIND_TONE: Record<string, string> = {
  add_field: "indigo", add_relation: "amber", wire_deposit: "violet", add_role: "green",
};

const SOURCE_LABEL: Record<string, string> = {
  items: "工作项", relations: "关系", approvals: "审批", assets: "资产",
  runs: "Agent 运行", events: "事件流", artifacts: "内容仓工件",
};

const CQ_STATUS: Record<string, { label: string; tone: string }> = {
  answerable: { label: "可回答", tone: "green" },
  no_data: { label: "缺数据", tone: "amber" },
  unmapped: { label: "缺映射", tone: "neutral" },
};

const allAnswerable = (c: { questions: { status: string }[] }) =>
  c.questions.every((q) => q.status === "answerable");

function CqStatusBadge({ status }: { status: string }) {
  const s = CQ_STATUS[status] ?? { label: status, tone: "neutral" };
  return <Badge tone={s.tone as never}>{s.label}</Badge>;
}

/** Version timeline + semantic diff with data impact analysis (M4-I15). */
function VersionPanel({
  currentVersion, history, diff, diffing, onDiff,
}: {
  currentVersion: number;
  history?: { current_version: number; snapshots: number[]; history: { event_id: number; ts: string; previous_version: number; version: number; applied_count: number; applied: { id: string; kind: string; summary: string }[]; summary: string }[] };
  diff: OntologyDiff | null; diffing: boolean;
  onDiff: (fromV: number, toV?: number) => void;
}) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">◷ 版本与影响分析</span>
        <Badge tone="neutral">v{currentVersion} · 快照 {history?.snapshots.length ?? 0} 份</Badge>
        <span className="ml-auto text-[11px] text-mut">semantica VersionManager 轻量版（docs/08 §8.1）</span>
      </div>
      {history && history.history.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {history.history.map((h) => (
            <div key={h.event_id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-bg px-3 py-1.5">
              <span className="font-mono text-[11px] text-mut">v{h.previous_version} → v{h.version}</span>
              <span className="text-xs text-ink">{h.summary}</span>
              {h.applied.slice(0, 3).map((a) => (
                <Badge key={a.id} tone={(KIND_TONE[a.kind] ?? "neutral") as never}>
                  {a.kind}
                </Badge>
              ))}
              {h.applied.length > 3 && <span className="text-[10px] text-mut">+{h.applied.length - 3}</span>}
              <Button size="sm" variant="ghost" className="ml-auto" disabled={diffing}
                      onClick={() => onDiff(h.previous_version, h.version)}>
                对比
              </Button>
            </div>
          ))}
        </div>
      )}
      {history && history.history.length === 0 && (
        <p className="mt-2 text-xs text-mut">
          尚无版本事件——在本体学习中应用候选后，这里会出现版本时间线；也可对磁盘上的手工改动做影响分析。
        </p>
      )}
      {diff && <DiffView d={diff} />}
    </Card>
  );
}

function DiffView({ d }: { d: OntologyDiff }) {
  const g = d.diff;
  const chip = (label: string, removed = false) => (
    <span key={label}
          className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${removed ? "bg-red-500/10 text-dan" : "bg-green-500/10 text-emerald-600"}`}>
      {removed ? "−" : "+"}{label}
    </span>
  );
  return (
    <div className="mt-3 space-y-2 border-t border-line pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold">v{d.from_version} → v{d.to_version} 语义 diff</span>
        <span className="text-[11px] text-mut">{d.summary}</span>
      </div>
      {(g.concepts.added.length > 0 || g.concepts.removed.length > 0) && (
        <div className="flex flex-wrap items-center gap-1 text-xs">
          <span className="text-mut">概念：</span>
          {g.concepts.added.map((c) => chip(c.name || c.id))}
          {g.concepts.removed.map((c) => chip(c.name || c.id, true))}
        </div>
      )}
      {g.concepts.modified.map((m) => (
        <div key={m.id} className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-1.5 text-xs">
          <span className="font-medium">~ {m.name}</span>
          {m.changes.map((c, i) => (
            <span key={i} className="ml-2 font-mono text-[10px] text-amber-600">{c.type}:{c.detail}</span>
          ))}
        </div>
      ))}
      {(["relations", "phases", "asset_kinds"] as const).map((k) => {
        const label = { relations: "关系", phases: "阶段", asset_kinds: "资产类型" }[k];
        return (g[k].added.length > 0 || g[k].removed.length > 0) ? (
          <div key={k} className="flex flex-wrap items-center gap-1 text-xs">
            <span className="text-mut">{label}：</span>
            {g[k].added.map((c) => chip(c.name || c.id))}
            {g[k].removed.map((c) => chip(c.name || c.id, true))}
          </div>
        ) : null;
      })}
      {d.impact.blocking.length > 0 && (
        <div className="space-y-1">
          {d.impact.blocking.map((b, i) => (
            <div key={i} className="rounded-lg border border-red-500/40 bg-red-500/5 px-3 py-1.5 text-xs text-dan">
              ⛔ {b.detail}
              {b.sample_items?.map((s) => (
                <span key={s.id} className="ml-2 font-mono text-[10px] text-mut">{s.title}</span>
              ))}
            </div>
          ))}
        </div>
      )}
      {d.impact.warnings.length > 0 && (
        <div className="rounded-lg border border-dashed border-line px-3 py-1.5 text-[11px] text-mut">
          {d.impact.warnings.map((w, i) => <div key={i}>· {w.detail}</div>)}
        </div>
      )}
      {d.to_validation_errors.length > 0 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-1.5 text-[11px] text-amber-600">
          当前文件校验问题：{d.to_validation_errors.join("；")}
        </div>
      )}
    </div>
  );
}

const RULE_META: Record<string, { label: string; tone: string }> = {
  "L1-add-field": { label: "字段显式化", tone: "indigo" },
  "L2-register-relation": { label: "关系补注册", tone: "amber" },
  "L3-wire-deposit": { label: "沉淀链接补全", tone: "violet" },
  "L4-add-role": { label: "角色覆盖", tone: "green" },
  "LLM-curate": { label: "LLM 建议", tone: "violet" },
};

/** Ontology-learning panel (semantica 模式)：pattern 扫描 / LLM 建议 → review → apply. */
function LearnPanel({
  scan, scanning, applying, selected, onLearn, onLearnLlm, onApply, onToggle,
}: {
  scan: OntologyLearnResult | null; scanning: boolean; applying: boolean;
  selected: Set<string>;
  onLearn: () => void; onLearnLlm: () => void; onApply: () => void; onToggle: (id: string) => void;
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
          <Button size="sm" variant="outline" disabled={scanning || applying} onClick={onLearnLlm}>
            ✨ LLM 建议
          </Button>
          {scan && scan.candidates.length > 0 && (
            <Button size="sm" variant="primary" disabled={applying || !selected.size} onClick={onApply}>
              {applying ? "应用中…" : `应用选中（${selected.size}）`}
            </Button>
          )}
        </span>
      </div>
      {scan?.llm && (
        <div className="mt-2 font-mono text-[10px] text-mut">
          LLM 层（{scan.llm.provider_mode}）：原始 {scan.llm.raw} · 接受 {scan.llm.accepted} · 与 pattern 层合并 {scan.llm.merged} · 低置信丢弃 {scan.llm.dropped_low_confidence}
          {scan.llm.error ? ` · 降级：${scan.llm.error}` : ""}
        </div>
      )}
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
                    {c.provenance.channels?.includes("llm") && (
                      <Badge tone="violet">LLM{c.provenance.confidence != null ? ` · ${c.provenance.confidence}` : ""}</Badge>
                    )}
                    <span className="text-xs text-ink">{c.summary}</span>
                  </span>
                  <span className="mt-1 block font-mono text-[10px] text-mut">
                    {c.provenance.rule} · support {c.provenance.support}
                    {c.provenance.channels?.length ? ` · 通道 ${c.provenance.channels.join("+")}` : ""}
                    {c.provenance.sample_item_ids?.length ? ` · 样本 ${c.provenance.sample_item_ids.join(", ")}` : ""}
                    {c.provenance.sample_run_ids?.length ? ` · runs ${c.provenance.sample_run_ids.join(", ")}` : ""}
                    {c.provenance.sample_asset_ids?.length ? ` · assets ${c.provenance.sample_asset_ids.join(", ")}` : ""}
                  </span>
                  {c.provenance.llm_rationale && (
                    <span className="mt-0.5 block text-[10px] text-mut">💬 {c.provenance.llm_rationale}</span>
                  )}
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
