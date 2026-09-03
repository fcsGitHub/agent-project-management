/** Template center (M7-I24): browse packs, preview graph + CQs, one-click project. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Badge, Button, Card, Drawer, Empty, Input, Modal, Textarea } from "../components/ui";

const SOURCE_BADGE: Record<string, { label: string; tone: "neutral" | "green" | "violet" }> = {
  builtin: { label: "内置", tone: "neutral" },
  imported: { label: "导入", tone: "violet" },
  asset: { label: "资产沉淀", tone: "green" },
};

const sourceBadge = (s: string) => SOURCE_BADGE[s] ?? { label: s, tone: "neutral" as const };

export function TemplatesPage() {
  const packs = useQuery({ queryKey: ["template-packs"], queryFn: api.listTemplatePacks });
  const [preview, setPreview] = useState<string | null>(null);
  const [instantiate, setInstantiate] = useState<string | null>(null);
  const list = packs.data?.packs ?? [];

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-sm font-semibold">🧩 模板中心</span>
        <span className="text-xs text-mut">一套模板 = 本体 + 角色 + 提示词；选一个直接开项目</span>
        <span className="ml-auto text-xs text-mut">{list.length} 个模板</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          {list.map((p) => {
            const sb = sourceBadge(p.source);
            return (
              <Card key={p.name} className="flex flex-col p-4 text-xs">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-semibold">{p.display_name}</span>
                  <Badge tone={sb.tone}>{sb.label}</Badge>
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-mut">{p.name} · v{p.version}</div>
                <div className="mt-2 flex flex-wrap gap-1 text-[11px] text-mut">
                  <Badge tone="neutral">📦 {p.concepts} 概念</Badge>
                  <Badge tone="neutral">🗺️ {p.phases} 阶段</Badge>
                  <Badge tone="neutral">❓ {p.competency_questions} CQ</Badge>
                </div>
                <div className="mt-3 flex gap-1.5">
                  <Button size="sm" variant="outline" onClick={() => setPreview(p.name)}>预览</Button>
                  <Button size="sm" variant="primary" disabled={!p.valid}
                    onClick={() => setInstantiate(p.name)}>用此模板建项目</Button>
                </div>
              </Card>
            );
          })}
        </div>
        {!list.length && <Empty icon="🧩" title="暂无模板" hint="内置本体即模板；也可从本体页导出/导入模板包" />}
      </div>
      <PackDrawer name={preview} onClose={() => setPreview(null)} onInstantiate={(n) => { setPreview(null); setInstantiate(n); }} />
      <InstantiateModal name={instantiate} onClose={() => setInstantiate(null)} />
    </div>
  );
}

function PackDrawer({ name, onClose, onInstantiate }: {
  name: string | null; onClose: () => void; onInstantiate: (name: string) => void;
}) {
  const prev = useQuery({
    queryKey: ["template-pack", name],
    queryFn: () => api.previewTemplatePack(name!),
    enabled: !!name,
  });
  const d = prev.data;
  return (
    <Drawer open={!!name} onClose={onClose} title={d ? `模板预览 · ${d.display_name}` : "模板预览"} width="46%">
      {d && (
        <div className="space-y-4 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="indigo">v{d.version}</Badge>
            <Badge tone={sourceBadge(d.source).tone}>{sourceBadge(d.source).label}</Badge>
            <Badge tone="neutral">📦 {d.summary.concepts} 概念</Badge>
            <Badge tone="neutral">🗺️ {d.summary.phases} 阶段</Badge>
            <Badge tone="neutral">❓ {d.summary.competency_questions} CQ</Badge>
          </div>

          <section>
            <div className="mb-1 font-semibold">阶段流程</div>
            <div className="flex flex-wrap items-center gap-1">
              {d.phases.map((p, i) => (
                <span key={p.id} className="flex items-center gap-1">
                  {i > 0 && <span className="text-mut">→</span>}
                  <span className="rounded-md border border-line px-1.5 py-0.5">
                    {p.name}{p.gate && <span className="ml-1 text-acc">⚑{p.gate}</span>}
                  </span>
                </span>
              ))}
            </div>
          </section>

          <section>
            <div className="mb-1 font-semibold">概念表</div>
            <div className="grid grid-cols-2 gap-2">
              {d.concepts.map((c) => (
                <div key={c.id} className="rounded-lg border border-line p-2">
                  <div className="font-medium">{c.icon} {c.name} <span className="font-mono text-[10px] text-mut">{c.id}</span></div>
                  <div className="mt-1 text-[11px] text-mut">
                    状态：{c.states.map((s) => s.name).join(" → ")}
                  </div>
                  {!!c.fields.length && (
                    <div className="mt-0.5 text-[11px] text-mut">
                      字段：{c.fields.map((f) => f.name).join("、")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section>
            <div className="mb-1 font-semibold">能力问题（CQ）</div>
            <ul className="list-disc space-y-1 pl-5 text-mut">
              {d.competency_questions.map((q) => <li key={q}>{q}</li>)}
            </ul>
          </section>

          <div className="flex justify-end">
            <Button variant="primary" onClick={() => onInstantiate(d.name)}>用此模板建项目 →</Button>
          </div>
        </div>
      )}
    </Drawer>
  );
}

function InstantiateModal({ name, onClose }: { name: string | null; onClose: () => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [projectName, setProjectName] = useState("");
  const [requirement, setRequirement] = useState("");
  const [busy, setBusy] = useState(false);
  const meta = useQuery({
    queryKey: ["template-pack", name],
    queryFn: () => api.previewTemplatePack(name!),
    enabled: !!name,
  });
  return (
    <Modal open={!!name} onClose={onClose} title={meta.data ? `用「${meta.data.display_name}」建项目` : "用模板建项目"}>
      <div className="space-y-3">
        <Input placeholder="项目名称（如：周报工具）" value={projectName} onChange={(e) => setProjectName(e.target.value)} />
        <Textarea rows={3} placeholder="一句话需求（PM-Agent 将据此起草 PRD，可留空）"
          value={requirement} onChange={(e) => setRequirement(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!projectName.trim() || busy} onClick={async () => {
            setBusy(true);
            try {
              const p = await api.instantiateTemplatePack(name!, {
                project_name: projectName, requirement: requirement || undefined,
              });
              await qc.invalidateQueries({ queryKey: ["projects"] });
              toast.success("项目已从模板创建", { description: p.name });
              onClose();
              navigate(`/p/${p.id}/board`);
            } catch (e) {
              toast.error("创建失败", { description: String(e) });
            } finally {
              setBusy(false);
            }
          }}>创建并打开看板</Button>
        </div>
      </div>
    </Modal>
  );
}
