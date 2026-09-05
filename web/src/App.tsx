import { useState } from "react";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import { AppShell } from "./components/AppShell";
import { Dashboard } from "./pages/Dashboard";
import { Board } from "./pages/Board";
import { FeaturePage } from "./pages/FeaturePage";
import { ConversationView } from "./pages/ConversationView";
import { ConversationsPage } from "./pages/ConversationsPage";
import { RunsPage } from "./pages/RunsPage";
import { GraphView } from "./pages/GraphView";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AssetsPage } from "./pages/AssetsPage";
import { LoginPage } from "./pages/LoginPage";
import { TemplatesPage } from "./pages/TemplatesPage";
import { AuditPage } from "./pages/AuditPage";
import { OntologyPage } from "./pages/OntologyPage";
import { ReportsPage } from "./pages/ReportsPage";
import { TimelinePage } from "./pages/TimelinePage";
import { MyWorkPage } from "./pages/MyWorkPage";
import { MyTimePage } from "./pages/MyTimePage";
import { SearchPage } from "./pages/SearchPage";
import { RoadmapPage } from "./pages/RoadmapPage";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<ProjectPicker />} />
        <Route path="/p/:pid" element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="board" element={<Board />} />
          <Route path="timeline" element={<TimelinePage />} />
          <Route path="f/:fid" element={<FeaturePage />} />
          <Route path="c/:cid" element={<ConversationView />} />
          <Route path="conversations" element={<ConversationsPage />} />
          <Route path="runs" element={<RunsPage />} />
          <Route path="graph" element={<GraphView />} />
          <Route path="approvals" element={<ApprovalsPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="ontology" element={<OntologyPage />} />
        </Route>
        <Route path="/assets" element={<AssetsPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/my/work" element={<MyWorkPage />} />
        <Route path="/my/time" element={<MyTimePage />} />
        <Route path="/roadmap" element={<RoadmapPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  );
}

/** Redirect to the first project when one exists, else show the picker. */
function ProjectPicker() {
  const [showArchived, setShowArchived] = useState(false);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["projects", showArchived],
    queryFn: () => api.listProjects(showArchived),
  });
  if (isLoading) return <div className="p-8 text-sm text-mut">加载中…</div>;
  // 空库引导自动弹「新建项目」；后端不可达（离线/故障）时不弹——创建必失败，误导。
  return <PickerInner projects={data?.projects ?? []} autoOpen={!isError && !(data?.projects.length ?? 0)} showArchived={showArchived} onToggleArchived={setShowArchived} />;
}

import { Button, Card, Input, Textarea, Modal, Badge } from "./components/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

function PickerInner({ projects, autoOpen = false, showArchived, onToggleArchived }: {
  projects: { id: string; name: string; ontology: string; status: string; item_counts?: Record<string, number>; gates_pending?: number }[];
  autoOpen?: boolean;
  showArchived: boolean;
  onToggleArchived: (v: boolean) => void;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(autoOpen);
  const [name, setName] = useState("");
  const [req, setReq] = useState("");
  const [ontology, setOntology] = useState("software-dev");
  const [busy, setBusy] = useState(false);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast.success(ok); qc.invalidateQueries(); }
    catch (e) { toast.error(`操作失败：${e instanceof Error ? e.message : e}`); }
  };

  return (
    <div className="flex h-full items-center justify-center bg-bg p-6">
      <div className="w-full max-w-xl space-y-4">
        <div className="text-center">
          <div className="text-xl font-bold">AgentPM</div>
          <p className="mt-1 text-sm text-mut">人指挥 · Agent 执行 —— 以对话为中心的项目管理</p>
        </div>
        <Card className="divide-y divide-line">
          {projects.map((p) => {
            const c = p.item_counts ?? {};
            const gates = p.gates_pending ?? 0;
            const archived = p.status === "archived";
            return (
              <div key={p.id} className={`flex items-center gap-2 px-3 py-2.5 ${archived ? "opacity-60" : ""}`}>
                <button
                  onClick={() => navigate(`/p/${p.id}`)}
                  className="flex flex-1 items-center gap-3 text-left"
                >
                  <span className="flex-1 text-sm font-medium">{p.name}</span>
                  <span className="text-[11px] text-mut">
                    待办 {c.backlog ?? 0} · 进行 {c.in_progress ?? 0} · 完成 {c.done ?? 0}
                  </span>
                  {gates > 0 && <Badge tone="amber">◆ {gates} 待审</Badge>}
                  {archived && <Badge tone="neutral">已归档</Badge>}
                  <Badge tone="violet">{p.ontology}</Badge>
                </button>
                <button title="克隆项目（复制结构与工作项，成员不复制）"
                  onClick={() => {
                    const newName = window.prompt("克隆为新项目名", `${p.name}·克隆`);
                    if (!newName) return;
                    act(() => api.cloneProject(p.id, { name: newName }), "已克隆");
                  }}
                  className="rounded border border-line px-1.5 py-0.5 text-[10px] text-mut hover:border-acc hover:text-acc">克隆</button>
                {archived ? (
                  <button title="恢复为活跃项目"
                    onClick={() => act(() => api.reopenProject(p.id), "已恢复")}
                    className="rounded border border-line px-1.5 py-0.5 text-[10px] text-mut hover:border-acc hover:text-acc">恢复</button>
              ) : (
                  <button title="归档（只读，可随时恢复）"
                    onClick={() => act(() => api.archiveProject(p.id), "已归档（只读）")}
                    className="rounded border border-line px-1.5 py-0.5 text-[10px] text-mut hover:border-acc hover:text-acc">归档</button>
                )}
              </div>
            );
          })}
          {!projects.length && (
            <div className="px-4 py-10 text-center text-sm text-mut">
              还没有项目——从一句话需求开始，PM-Agent 会帮你拆任务
            </div>
          )}
        </Card>
        <div className="flex items-center justify-center gap-2">
          <Button variant="primary" onClick={() => setOpen(true)}>＋ 新建项目</Button>
          <Button variant="ghost" onClick={() => navigate("/templates")}>🧩 模板中心</Button>
          <button onClick={() => onToggleArchived(!showArchived)}
            className={`rounded-lg border px-2 py-1 text-xs ${showArchived ? "border-acc text-acc" : "border-line text-mut hover:border-acc"}`}>
            {showArchived ? "隐藏已归档" : "显示已归档"}
          </button>
        </div>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="新建项目">
        <div className="space-y-3">
          <Input placeholder="项目名称" value={name} onChange={(e) => setName(e.target.value)} />
          <Textarea rows={3} placeholder="一句话需求（PM-Agent 将据此起草 PRD）" value={req} onChange={(e) => setReq(e.target.value)} />
          <div className="flex gap-2">
            {[
              { id: "software-dev", label: "软件研发 · 完整七阶段" },
              { id: "generic", label: "通用轻流程 · 三阶段" },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setOntology(t.id)}
                className={`flex-1 rounded-lg border px-3 py-2 text-xs ${
                  ontology === t.id ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>取消</Button>
            <Button
              variant="primary"
              disabled={!name.trim() || busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const p = await api.createProject({ name, ontology, requirement: req });
                  await qc.invalidateQueries({ queryKey: ["projects"] });
                  navigate(`/p/${p.id}`);
                } finally {
                  setBusy(false);
                }
              }}
            >
              创建并初始化
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
