/** Project graph: React Flow read-only DAG with status badges and node drawer. */
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Background, Controls, ReactFlow, type Edge, type Node, type NodeProps,
  Handle, Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "../lib/api";
import { Badge, Drawer, Empty, GROUP_TONE, cx } from "../components/ui";

type GraphNode = { id: string; kind: string; label: string; [k: string]: unknown };

function PhaseNode({ data }: NodeProps) {
  const d = data as { label: string; status: string };
  return (
    <div className={cx(
      "min-w-32 rounded-[12px] border-2 px-3 py-2 text-center text-xs font-medium shadow-sm",
      d.status === "passed" ? "border-ok bg-okbg" :
      d.status === "active" ? "border-warn bg-warnbg" :
      d.status === "skipped" ? "border-line bg-bg opacity-60" : "border-line bg-surface",
    )}>
      <Handle type="target" position={Position.Left} style={{ visibility: "hidden" }} />
      {d.label}
      <div className="text-[10px] font-normal text-mut">{d.status}</div>
      <Handle type="source" position={Position.Right} style={{ visibility: "hidden" }} />
    </div>
  );
}

function GateNode({ data }: NodeProps) {
  const d = data as { label: string; pending: number; passed: boolean };
  return (
    <div className={cx(
      "flex h-12 w-12 rotate-45 items-center justify-center rounded-md border-2 shadow-sm",
      d.pending > 0 ? "border-warn bg-warnbg" : d.passed ? "border-ok bg-okbg" : "border-line bg-surface",
    )} title={d.label}>
      <span className="-rotate-45 text-[10px] font-bold">{d.pending > 0 ? `🔔${d.pending}` : "◆"}</span>
    </div>
  );
}

function TaskNode({ data }: NodeProps) {
  const d = data as { label: string; status_group: string; status: string; assignee_type?: string; assignee_name?: string; conv?: string };
  return (
    <div className={cx(
      "min-w-36 rounded-lg border px-2.5 py-1.5 text-left text-[11px] shadow-sm",
      d.status_group === "done" ? "border-ok bg-okbg" :
      d.status_group === "in_progress" ? "border-acc bg-accbg" :
      "border-line bg-surface",
    )}>
      <Handle type="target" position={Position.Left} style={{ visibility: "hidden" }} />
      <div className="flex items-center gap-1 font-medium">
        <span>{d.assignee_type === "agent" ? "🤖" : "👤"}</span>
        <span className="truncate">{d.label}</span>
      </div>
      <div className="mt-0.5 flex items-center gap-1 text-[10px] text-mut">
        <span className="rounded bg-bg px-1">{d.status}</span>
        {d.conv && <span className="text-acc">▶</span>}
      </div>
      <Handle type="source" position={Position.Right} style={{ visibility: "hidden" }} />
    </div>
  );
}

const NODE_TYPES = { phase: PhaseNode, gate: GateNode, task: TaskNode };

export function GraphView() {
  const { pid } = useParams();
  const graph = useQuery({ queryKey: ["graph", pid], queryFn: () => api.getGraph(pid!), enabled: !!pid, refetchInterval: 5_000 });
  const phases = useQuery({ queryKey: ["phases", pid], queryFn: () => api.getPhases(pid!), enabled: !!pid });
  const runs = useQuery({ queryKey: ["runs", pid], queryFn: () => api.listRuns(pid!), enabled: !!pid });
  const approvals = useQuery({
    queryKey: ["approvals", pid, "pending"],
    queryFn: () => api.listApprovals({ status: "pending", project_id: pid }),
    enabled: !!pid,
    refetchInterval: 10_000,
  });
  const [selected, setSelected] = useState<GraphNode | null>(null);

  // 🔔 徽标数据源：挂在门上的待审批数（按门名聚合，与审批中心同口径）
  const pendingGateCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const a of approvals.data?.approvals ?? []) {
      if (a.kind !== "gate") continue;
      const g = String(a.payload_snapshot?.gate ?? "");
      if (g) m.set(g, (m.get(g) ?? 0) + 1);
    }
    return m;
  }, [approvals.data]);

  const { nodes, edges } = useMemo(() => {
    const phaseStatus = new Map((phases.data?.phases ?? []).map((p) => [p.id, p]));
    const itemRun = new Map<string, { conversation_id: string; status: string }>();
    for (const r of runs.data?.runs ?? []) {
      if (r.item_id) itemRun.set(r.item_id, { conversation_id: r.conversation_id, status: r.status });
    }
    const ns: Node[] = [];
    const es: Edge[] = [];
    let phaseIdx = 0;
    for (const n of graph.data?.nodes ?? []) {
      if (n.kind === "phase") {
        const st = phaseStatus.get(String(n.id.split(":")[1]));
        ns.push({
          id: n.id, type: "phase", position: { x: 60 + phaseIdx * 210, y: 40 },
          data: { label: String(n.label), status: st?.status ?? "pending" },
        });
        phaseIdx++;
      } else if (n.kind === "gate") {
        ns.push({
          id: n.id, type: "gate",
          position: { x: 60 + (phaseIdx - 1) * 210 + 130, y: 140 },
          data: {
            label: String(n.label),
            pending: pendingGateCounts.get(String(n.label)) ?? 0,
            passed: stOf(phaseStatus, String(n.phase)),
          },
        });
      } else {
        const idx = ns.filter((x) => x.type === "task").length;
        ns.push({
          id: n.id, type: "task",
          position: { x: 80 + (phaseIdx - 1) * 210, y: 210 + (idx % 6) * 64 },
          data: {
            label: String(n.label), status: String(n.status), status_group: String(n.status_group),
            assignee_type: n.assignee_type ? String(n.assignee_type) : undefined,
            assignee_name: n.assignee_name ? String(n.assignee_name) : undefined,
            conv: itemRun.get(n.id)?.conversation_id,
          },
        });
      }
    }
    for (const e of graph.data?.edges ?? []) {
      es.push({
        id: `${e.source}-${e.target}`,
        source: e.source, target: e.target,
        animated: e.kind === "sequence",
        style: e.kind === "depends_on"
          ? { stroke: "var(--color-dan, #dc2626)", strokeDasharray: "4 3" }
          : e.kind === "sequence" ? { stroke: "var(--color-mut, #a1a1aa)" } : { stroke: "var(--color-line, #d4d4d8)" },
      });
    }
    return { nodes: ns, edges: es };
  }, [graph.data, phases.data, runs.data, pendingGateCounts]);

  if (!pid) return null;

  return (
    <div className="relative h-full">
      {(graph.data?.nodes ?? []).length ? (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodeClick={(_, node) => {
            const raw = (graph.data?.nodes ?? []).find((n) => n.id === node.id);
            if (raw) setSelected(raw);
          }}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          {/* M119-I366: 背景点走语义 token——硬编码 #e7e7ea 在暗色主题下是
              贴在暗底上的亮色拼图（M114-I341 同族收口） */}
          <Background gap={20} color="var(--color-line, #e7e7ea)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      ) : (
        <Empty icon="latlong" title="项目图为空" hint="本体阶段图与工作项会在此渲染" />
      )}
      <NodeDrawer node={selected} onClose={() => setSelected(null)} pid={pid} runs={runs.data?.runs ?? []} />
    </div>
  );
}

function stOf(phases: Map<string, { status: string }>, phaseId: string): boolean {
  return phases.get(phaseId)?.status === "passed";
}

function NodeDrawer({ node, onClose, pid, runs }: {
  node: GraphNode | null; onClose: () => void; pid: string;
  runs: import("../lib/api").Run[];
}) {
  if (!node) return null;
  const related = node.kind === "task" ? runs.filter((r) => r.item_id === node.id) : [];
  return (
    <Drawer open onClose={onClose} title={`${node.kind === "gate" ? "◆" : node.kind === "phase" ? "▤" : "▪"} ${node.label}`}>
      <div className="space-y-3 text-sm">
        {node.kind === "task" && (
          <>
            <div className="flex gap-2">
              <Badge tone={GROUP_TONE[String(node.status_group)]}>{String(node.status ?? "")}</Badge>
              {node.assignee_id ? (
                <Badge tone="violet">
                  {node.assignee_type === "agent" ? "🤖" : "👤"}{" "}
                  {String(node.assignee_name ?? node.assignee_id)}
                </Badge>
              ) : null}
            </div>
            <div className="text-xs font-semibold text-mut">绑定对话与运行（{related.length}）</div>
            {related.slice(0, 6).map((r) => (
              <a key={r.id} href={`#/p/${pid}/c/${r.conversation_id}`} className="block rounded-lg border border-line px-3 py-2 text-xs hover:border-acc">
                🤖 {r.agent_role} · {r.status} · {r.started_at?.slice(11, 16)} →
              </a>
            ))}
            {!related.length && <div className="text-xs text-mut">尚无运行——在图/看板上「让 Agent 做」</div>}
          </>
        )}
        {node.kind === "gate" && (
          <div className="text-xs text-mut">
            阶段门：到达时挂起并生成审批（fail-closed · 单次授权）。在审批中心处理。
          </div>
        )}
        {node.kind === "phase" && (
          <div className="text-xs text-mut">阶段节点（{String(node.id).split(":")[1]}）</div>
        )}
      </div>
    </Drawer>
  );
}
