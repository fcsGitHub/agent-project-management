/** 追溯页（M108-I326，docs/01 §DA.1）：需求到证据的项目助手。三块能力：
 * ①覆盖与缺口——每轮收口前跑一遍，列出缺测试/缺实现/零证据的需求、孤儿
 *   工作项、失效链接、变更未复核（减少最后集中补文档的压力）；
 * ②影响分析——改一条需求前先看波及：设计决定/实现/测试/交付物/文档，
 *   默认两跳（任务上的测试也算需求的证据），从任务侧进入则反查需求；
 * ③链接登记——把证据挂到需求上（支持工作项/工件/资产/对话/功能五类节点）。 */
import { useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import type { TraceImpactEntry, TraceNodeType, TraceRelation } from "../lib/api";
import { Badge, Button, Card, Empty, Input, cx } from "../components/ui";

const RELATION_LABEL: Record<TraceRelation, string> = {
  implements: "实现", verifies: "验证", decides: "决策",
  delivers: "交付", documents: "记录", relates_to: "关联",
};
const GROUP_LABEL: Record<string, string> = {
  requirements: "需求", decisions: "设计决定", implementation: "实现 / 模块",
  tests: "测试", deliverables: "交付物", documents: "文档", related: "关联",
};
const NODE_TYPE_LABEL: Record<TraceNodeType, string> = {
  item: "工作项", artifact: "工件", asset: "资产", conversation: "对话", feature: "功能",
};

export function TracePage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const [milestoneId, setMilestoneId] = useState("");
  const [impactType, setImpactType] = useState<TraceNodeType>("item");
  const [impactRef, setImpactRef] = useState("");

  const coverage = useQuery({
    queryKey: ["trace-coverage", pid, milestoneId],
    queryFn: () => api.traceCoverage(pid!, milestoneId || undefined),
  });
  const links = useQuery({ queryKey: ["trace-links", pid], queryFn: () => api.listTraceLinks(pid!) });
  const items = useQuery({
    queryKey: ["items", pid],
    queryFn: () => api.listItems(pid!, { limit: 500 }),
  });
  const artifacts = useQuery({
    queryKey: ["artifacts", pid],
    queryFn: () => api.listArtifacts(pid!),
  });
  const milestones = useQuery({
    queryKey: ["milestones", pid],
    queryFn: () => api.listMilestones(pid!),
  });
  const impact = useQuery({
    queryKey: ["trace-impact", pid, impactType, impactRef],
    queryFn: () => api.traceImpact(pid!, impactType, impactRef),
    enabled: !!impactRef,
  });

  const unlink = async (id: string) => {
    try {
      await api.deleteTraceLink(id);
      toast.success("已解除关联");
      await qc.invalidateQueries({ queryKey: ["trace-links", pid] });
      await qc.invalidateQueries({ queryKey: ["trace-coverage", pid] });
      await qc.invalidateQueries({ queryKey: ["trace-impact", pid] });
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : e}`);
    }
  };

  const reqs = coverage.data?.requirements ?? [];
  const reqIds = new Set(reqs.map((r) => r.id));
  const gaps = coverage.data?.gaps;
  const sum = coverage.data?.summary;

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">🔗 需求到证据</h1>
          <p className="mt-0.5 text-xs text-mut">
            需求 · 设计决定 · 实现 · 测试 · 交付物的关联图谱——每轮找出遗漏和未闭环项
          </p>
        </div>
        <select
          value={milestoneId}
          onChange={(e) => setMilestoneId(e.target.value)}
          className="rounded-md border border-line bg-bg px-2 py-1.5 text-xs"
          aria-label="按里程碑切片"
        >
          <option value="">全部（不限轮次）</option>
          {(milestones.data?.milestones ?? []).map((m) => (
            <option key={m.id} value={m.id}>里程碑：{m.title}</option>
          ))}
        </select>      </div>

      {/* —— ① 覆盖与缺口（每轮收口清单）—— */}
      <Card className="p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">覆盖概览</span>
          {sum && (
            <span className="flex flex-wrap gap-1.5 text-[11px]">
              <Badge tone="indigo">需求 {sum.requirements}</Badge>
              <Badge tone={sum.closed === sum.requirements && sum.requirements > 0 ? "green" : "amber"}>
                已闭环 {sum.closed}（{sum.closed_rate != null ? `${Math.round(sum.closed_rate * 100)}%` : "—"}
                ，闭环=有实现+有测试）
              </Badge>
              <Badge tone={sum.orphan_items ? "amber" : "green"}>孤儿工作项 {sum.orphan_items}</Badge>
              <Badge tone={sum.stale_links ? "red" : "green"}>失效链接 {sum.stale_links}</Badge>
              <Badge tone={sum.needs_review ? "amber" : "green"}>变更待复核 {sum.needs_review}</Badge>
            </span>
          )}
        </div>
        {gaps && (
          <div className="space-y-2 text-xs">
            <GapRows
              title="缺测试的需求"
              hint="验证（verifies）边缺失——改动无法安全收口"
              rows={gaps.requirements_without_tests}
              render={(r) => <ReqChip key={r.id} r={r} pid={pid!} onJump={() => { setImpactType("item"); setImpactRef(r.id); }} />}
            />
            <GapRows
              title="缺实现的需求"              hint="实现（implements）边缺失——还没有任务/模块认领"
              rows={gaps.requirements_without_implementation}
              render={(r) => <ReqChip key={r.id} r={r} pid={pid!} onJump={() => { setImpactType("item"); setImpactRef(r.id); }} />}
            />
            <GapRows
              title="零证据的需求"
              hint="任何关联都没有——纯纸上需求"
              rows={gaps.requirements_without_evidence}
              render={(r) => <ReqChip key={r.id} r={r} pid={pid!} onJump={() => { setImpactType("item"); setImpactRef(r.id); }} />}
            />
            <GapRows
              title="孤儿工作项"
              hint="没挂到任何需求上的任务/缺陷——要么补链，要么说明为什么独立存在"
              rows={gaps.orphan_items.map((o) => ({ id: o.id, title: o.title }))}
              render={(o) => (
                <span key={o.id} className="rounded bg-bg px-1.5 py-0.5">
                  {o.title}
                </span>
              )}
            />
            <GapRows
              title="失效链接"
              hint="指向已删除的工件/工作项——清理或重挂"
              rows={gaps.stale_links.map((s) => ({ id: s.link_id, title: s.missing.join("、") }))}
              render={(s) => (
                <span key={s.id} className="flex items-center gap-1 rounded bg-red-50 px-1.5 py-0.5 text-red-700">
                  {s.title}
                  <button className="text-[10px] underline" onClick={() => unlink(s.id)}>删除链接</button>
                </span>
              )}
            />
            <GapRows
              title="需求变更未复核"
              hint="需求在证据登记之后又被修改——证据可能已过期"
              rows={gaps.changed_after_evidence.map((r) => ({ id: r.id, title: r.title }))}
              render={(r) => (
                <button key={r.id} className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800 hover:underline"
                  onClick={() => { setImpactType("item"); setImpactRef(r.id); }}>
                  {r.title} ↗
                </button>
              )}
            />
          </div>
        )}
      </Card>

      {/* —— ② 影响分析 —— */}
      <Card className="p-4">
        <div className="mb-2 text-sm font-semibold">影响分析</div>
        <p className="mb-2 text-[11px] text-mut">
          改一条需求前先看波及范围——默认两跳：任务上的测试也算这条需求的证据
        </p>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select value={impactType} onChange={(e) => { setImpactType(e.target.value as TraceNodeType); setImpactRef(""); }}
            className="rounded-md border border-line bg-bg px-2 py-1.5 text-xs" aria-label="节点类型">
            <option value="item">工作项</option>
            <option value="artifact">工件</option>
          </select>
          <select value={impactRef} onChange={(e) => setImpactRef(e.target.value)}
            className="min-w-56 rounded-md border border-line bg-bg px-2 py-1.5 text-xs" aria-label="分析对象">
            <option value="">选择{impactType === "item" ? "需求/工作项" : "工件"}…</option>
            {/* 考官 Round 1：任务也要可选（docs/10 §M108「从任务侧进入则反查需求」
                ——此前只要有需求，下拉就只剩需求，反查入口在 UI 上不可达） */}
            {impactType === "item"
              ? (items.data?.items ?? []).map((it) => (
                  <option key={it.id} value={it.id}>
                    {reqIds.has(it.id) ? "[需求] " : it.status ? `[${it.status}] ` : ""}{it.title}
                  </option>
                ))
              : (artifacts.data?.artifacts ?? []).map((a) => (
                  <option key={a.path} value={a.path}>{a.path}</option>
                ))}
          </select>
        </div>
        {impact.isFetching && <div className="mt-3 text-xs text-mut">分析中…</div>}
        {impact.data && (
          <div className="mt-3 space-y-2">
            <div className="text-xs text-mut">
              根节点：<span className="font-medium text-fg">{impact.data.node.title ?? impact.data.node.ref}</span>
              {impact.data.node.requirement_like && <Badge tone="indigo">需求</Badge>}
            </div>
            {Object.entries(impact.data.groups).map(([group, entries]) =>
              entries.length ? (
                <div key={group} className="rounded-lg border border-line p-2">
                  <div className="mb-1 text-[11px] font-semibold text-mut">
                    {GROUP_LABEL[group]} · {entries.length}
                  </div>
                  <div className="space-y-1">
                    {entries.map((e) => <ImpactRow key={e.key} e={e} onJump={(ref) => { setImpactType("item"); setImpactRef(ref); }} />)}
                  </div>
                </div>
              ) : null,
            )}
            {impact.data.summary.needs_review > 0 && (
              <div className="text-[11px] text-amber-700">
                ⚠ {impact.data.summary.needs_review} 条证据登记于需求最近一次变更之前——变更后未复核
              </div>
            )}
          </div>
        )}
        {!impact.isFetching && !impact.data && impactRef && (
          <div className="mt-3 text-xs text-mut">该节点没有任何关联证据</div>
        )}
      </Card>

      {/* —— ③ 链接登记 —— */}
      <LinkEditor pid={pid!} items={items.data?.items ?? []}
        artifactPaths={(artifacts.data?.artifacts ?? []).map((a) => a.path)} />

      {links.data && links.data.links.length > 0 && (
        <Card className="divide-y divide-line">
          <div className="px-3 py-2 text-xs font-semibold text-mut">已登记链接 · {links.data.links.length}</div>
          {links.data.links.map((ln) => (
            <div key={ln.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs">
              <Badge tone="indigo">{RELATION_LABEL[ln.relation]}</Badge>
              <NodeChip node={ln.source} />
              <span className="text-mut">→</span>
              <NodeChip node={ln.target} />
              {ln.note && <span className="text-mut">· {ln.note}</span>}
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => unlink(ln.id)}>解除</Button>
            </div>
          ))}
        </Card>
      )}
      {links.data && !links.data.links.length && (
        <Empty title="还没有任何追溯链接" hint="在上方把设计决定、任务、测试或交付物挂到需求上" />
      )}
    </div>
  );
}

function GapRows({ title, hint, rows, render }: {
  title: string; hint: string; rows: { id: string; title: string }[];
  render: (row: { id: string; title: string }) => ReactNode;
}) {
  if (!rows.length) return null;
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="font-semibold">{title}</span>
        <Badge tone="amber">{rows.length}</Badge>
        <span className="text-[10px] text-mut">{hint}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-1.5">{rows.map(render)}</div>
    </div>
  );
}

function ReqChip({ r, onJump }: {
  pid: string; r: { id: string; title: string; needs_review?: boolean }; onJump: () => void;
}) {
  return (
    <button className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-800 hover:underline"
      title={r.id}
      onClick={onJump}>
      {r.title}{r.needs_review ? " ⚠" : ""}
    </button>
  );
}

function NodeChip({ node }: { node: { type: string; ref: string; title?: string; missing: boolean } }) {
  return (
    <span className={cx("rounded px-1.5 py-0.5", node.missing ? "bg-red-50 text-red-700" : "bg-bg")}>
      {node.title ?? node.ref}
      {node.missing && "（已失效）"}
    </span>
  );
}

function ImpactRow({ e, onJump }: { e: TraceImpactEntry; onJump: (ref: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      {e.depth > 1 && <Badge tone="neutral">+{e.depth - 1}跳</Badge>}
      <span className="font-medium">{e.title ?? e.ref}</span>
      {e.status && <Badge tone="neutral">{e.status}</Badge>}
      {e.missing && <Badge tone="red">已失效</Badge>}
      {e.needs_review && <Badge tone="amber">变更后未复核</Badge>}
      <span className="text-[10px] text-mut">
        经 {e.via.map((v) => RELATION_LABEL[v.relation]).join(" → ")}
      </span>
      {e.type === "item" && (
        <button className="text-[10px] text-acc hover:underline" onClick={() => onJump(e.ref)}>
          以此为根分析
        </button>
      )}
    </div>
  );
}

const REF_RELATIONS: TraceRelation[] = ["implements", "verifies", "decides", "delivers", "documents", "relates_to"];

function LinkEditor({ pid, items, artifactPaths }: {
  pid: string; items: { id: string; title: string; concept_id: string }[]; artifactPaths: string[];
}) {
  const qc = useQueryClient();
  const [sourceType, setSourceType] = useState<TraceNodeType>("item");
  const [sourceRef, setSourceRef] = useState("");
  const [relation, setRelation] = useState<TraceRelation>("implements");
  const [targetType, setTargetType] = useState<TraceNodeType>("artifact");
  const [targetRef, setTargetRef] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const optionsFor = (t: TraceNodeType) =>
    t === "item" ? items.map((it) => ({ value: it.id, label: `${it.title}（${it.concept_id}）` }))
    : t === "artifact" ? artifactPaths.map((p) => ({ value: p, label: p }))
    : [];

  const add = async () => {
    if (!sourceRef || !targetRef) return;
    setBusy(true);
    try {
      await api.createTraceLink(pid, {
        source_type: sourceType, source_ref: sourceRef, relation,
        target_type: targetType, target_ref: targetRef, note: note.trim() || undefined,
      });
      toast.success("链接已登记");
      setSourceRef(""); setTargetRef(""); setNote("");
      await qc.invalidateQueries({ queryKey: ["trace-links", pid] });
      await qc.invalidateQueries({ queryKey: ["trace-coverage", pid] });
      // 考官 Round 1：登记边会改变影响面——不失效则影响分析面板停留在登记前的旧图
      await qc.invalidateQueries({ queryKey: ["trace-impact", pid] });
    } catch (e) {
      toast.error(`登记失败：${e instanceof Error ? e.message : e}`);
    } finally { setBusy(false); }
  };

  const picker = (t: TraceNodeType, value: string, onChange: (v: string) => void, ariaLabel: string) => {
    const opts = optionsFor(t);
    return opts.length ? (
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="max-w-64 rounded-md border border-line bg-bg px-2 py-1.5 text-xs" aria-label={ariaLabel}>
        <option value="">选择{NODE_TYPE_LABEL[t]}…</option>
        {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    ) : (
      <Input className="w-64" placeholder={`${NODE_TYPE_LABEL[t]} ID / 路径`} value={value}
        onChange={(e) => onChange(e.target.value)} aria-label={ariaLabel} />
    );
  };

  return (
    <Card className="p-4">
      <div className="mb-2 text-sm font-semibold">登记追溯链接</div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {picker(sourceType, sourceRef, setSourceRef, "来源节点")}
        <select value={sourceType} onChange={(e) => { setSourceType(e.target.value as TraceNodeType); setSourceRef(""); }}
          className="rounded-md border border-line bg-bg px-2 py-1.5 text-xs" aria-label="来源类型">
          {Object.entries(NODE_TYPE_LABEL).map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
        <span className="text-mut">—</span>
        <select value={relation} onChange={(e) => setRelation(e.target.value as TraceRelation)}
          className="rounded-md border border-line bg-bg px-2 py-1.5 text-xs" aria-label="关系">
          {REF_RELATIONS.map((r) => <option key={r} value={r}>{RELATION_LABEL[r]}（{r}）</option>)}
        </select>
        <span className="text-mut">→</span>
        {picker(targetType, targetRef, setTargetRef, "目标节点")}
        <select value={targetType} onChange={(e) => { setTargetType(e.target.value as TraceNodeType); setTargetRef(""); }}
          className="rounded-md border border-line bg-bg px-2 py-1.5 text-xs" aria-label="目标类型">
          {Object.entries(NODE_TYPE_LABEL).map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
        <Input className="w-40" placeholder="备注（可选）" value={note} onChange={(e) => setNote(e.target.value)} />
        <Button size="sm" variant="primary" disabled={busy || !sourceRef || !targetRef} onClick={add}>登记</Button>
      </div>
      <p className="mt-2 text-[10px] text-mut">
        惯例方向：证据 → 需求（任务实现需求、测试验证需求、决策支撑需求）；资产/对话/功能节点可手输 ID
      </p>
    </Card>
  );
}
