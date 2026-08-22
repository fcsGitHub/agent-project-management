/** Ontology page: read-only browsing of the project's type system + validation. */
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Card } from "../components/ui";

export function OntologyPage() {
  const { pid } = useParams();
  const onto = useQuery({
    queryKey: ["ontology", pid],
    queryFn: () => api.getOntology(pid!, true),
    enabled: !!pid,
  });
  const o = onto.data;
  if (!o) return <div className="p-6 text-sm text-mut">加载本体…</div>;

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
