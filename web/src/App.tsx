import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import { AppShell } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";

// 路由级代码分割（M82-I246）：页面组件全量 React.lazy 按路由拆 chunk（vite 动态 import
// 自动分包），AppShell/内联 ProjectPicker 保持 eager 保首屏骨架。页面命名导出经 .then
// 归一成 lazy 要求的 default 形态。
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const Board = lazy(() => import("./pages/Board").then((m) => ({ default: m.Board })));
const FeaturePage = lazy(() => import("./pages/FeaturePage").then((m) => ({ default: m.FeaturePage })));
const ConversationView = lazy(() => import("./pages/ConversationView").then((m) => ({ default: m.ConversationView })));
const ConversationsPage = lazy(() => import("./pages/ConversationsPage").then((m) => ({ default: m.ConversationsPage })));
const RunsPage = lazy(() => import("./pages/RunsPage").then((m) => ({ default: m.RunsPage })));
const GraphView = lazy(() => import("./pages/GraphView").then((m) => ({ default: m.GraphView })));
const ApprovalsPage = lazy(() => import("./pages/ApprovalsPage").then((m) => ({ default: m.ApprovalsPage })));
const AssetsPage = lazy(() => import("./pages/AssetsPage").then((m) => ({ default: m.AssetsPage })));
const LoginPage = lazy(() => import("./pages/LoginPage").then((m) => ({ default: m.LoginPage })));
const TemplatesPage = lazy(() => import("./pages/TemplatesPage").then((m) => ({ default: m.TemplatesPage })));
const AuditPage = lazy(() => import("./pages/AuditPage").then((m) => ({ default: m.AuditPage })));
const OntologyPage = lazy(() => import("./pages/OntologyPage").then((m) => ({ default: m.OntologyPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const ArtifactsPage = lazy(() => import("./pages/ArtifactsPage").then((m) => ({ default: m.ArtifactsPage })));
const ReportsPage = lazy(() => import("./pages/ReportsPage").then((m) => ({ default: m.ReportsPage })));
const TimelinePage = lazy(() => import("./pages/TimelinePage").then((m) => ({ default: m.TimelinePage })));
const MyWorkPage = lazy(() => import("./pages/MyWorkPage").then((m) => ({ default: m.MyWorkPage })));
const MyTimePage = lazy(() => import("./pages/MyTimePage").then((m) => ({ default: m.MyTimePage })));
const SearchPage = lazy(() => import("./pages/SearchPage").then((m) => ({ default: m.SearchPage })));
const RoadmapPage = lazy(() => import("./pages/RoadmapPage").then((m) => ({ default: m.RoadmapPage })));
const ActivityPage = lazy(() => import("./pages/ActivityPage").then((m) => ({ default: m.ActivityPage })));
const WorkloadPage = lazy(() => import("./pages/WorkloadPage").then((m) => ({ default: m.WorkloadPage })));
const SchedulePage = lazy(() => import("./pages/SchedulePage").then((m) => ({ default: m.SchedulePage })));
const IntakePage = lazy(() => import("./pages/IntakePage").then((m) => ({ default: m.IntakePage })));
const RisksPage = lazy(() => import("./pages/RisksPage").then((m) => ({ default: m.RisksPage })));
const DependencyGraphPage = lazy(() => import("./pages/DependencyGraphPage").then((m) => ({ default: m.DependencyGraphPage })));
const TracePage = lazy(() => import("./pages/TracePage").then((m) => ({ default: m.TracePage })));
const TeamPage = lazy(() => import("./pages/TeamPage").then((m) => ({ default: m.TeamPage })));

/** 页面级边界（M82-I246）：key=路由形态（非解析后的 pathname——同一路由参数变化不重挂，
 * 保持既有「f/a→f/b 不丢实例」行为；跨路由切换才复位边界错误态）。 */
function pg(rk: string, elem: ReactNode): ReactNode {
  return (
    <ErrorBoundary key={rk} level="page">
      <Suspense fallback={<div className="p-8 text-sm text-mut">加载中…</div>}>{elem}</Suspense>
    </ErrorBoundary>
  );
}

export default function App() {
  return (
    <HashRouter>
      {/* App 级兜底（rail/路由表/内联页崩溃→整窗错误卡+重载；页面级崩溃被 pg 拦在页内）。 */}
      <ErrorBoundary level="app">
        <RequireSession>
          <Routes>
            <Route path="/" element={<ProjectPicker />} />
            <Route path="/intake/:token" element={pg("intake", <IntakePage />)} />
            <Route path="/p/:pid" element={<AppShell />}>
              <Route index element={pg("dashboard", <Dashboard />)} />
              <Route path="board" element={pg("board", <Board />)} />
              <Route path="timeline" element={pg("timeline", <TimelinePage />)} />
              <Route path="deps" element={pg("deps", <DependencyGraphPage />)} />
              <Route path="risks" element={pg("risks", <RisksPage />)} />
              <Route path="trace" element={pg("trace", <TracePage />)} />
              <Route path="f/:fid" element={pg("feature", <FeaturePage />)} />
              <Route path="c/:cid" element={pg("conversation", <ConversationView />)} />
              <Route path="conversations" element={pg("conversations", <ConversationsPage />)} />
              <Route path="runs" element={pg("runs", <RunsPage />)} />
              <Route path="graph" element={pg("graph", <GraphView />)} />
              <Route path="approvals" element={pg("approvals", <ApprovalsPage />)} />
              <Route path="audit" element={pg("audit", <AuditPage />)} />
              <Route path="reports" element={pg("reports", <ReportsPage />)} />
              <Route path="ontology" element={pg("ontology", <OntologyPage />)} />
              <Route path="settings" element={pg("settings", <SettingsPage />)} />
              <Route path="artifacts" element={pg("artifacts", <ArtifactsPage />)} />
            </Route>
            <Route path="/assets" element={pg("assets", <AssetsPage />)} />
            <Route path="/templates" element={pg("templates", <TemplatesPage />)} />
            <Route path="/my/work" element={pg("my-work", <MyWorkPage />)} />
            <Route path="/my/time" element={pg("my-time", <MyTimePage />)} />
            <Route path="/roadmap" element={pg("roadmap", <RoadmapPage />)} />
            <Route path="/workload" element={pg("workload", <WorkloadPage />)} />
            <Route path="/activity" element={pg("activity", <ActivityPage />)} />
            <Route path="/team" element={pg("team", <TeamPage />)} />
            <Route path="/my/schedule" element={pg("my-schedule", <SchedulePage />)} />
            <Route path="/search" element={pg("search", <SearchPage />)} />
            <Route path="/login" element={pg("login", <LoginPage />)} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </RequireSession>
      </ErrorBoundary>
    </HashRouter>
  );
}

/** M95-I287: network 匿名首访主动引导登录——此前只有写请求吃了 401 才被
 * 重定向（api.ts 反应式），首屏渲染的是全功能界面+本地身份切换器（误导）。
 * local 模式零影响；/login 本身与公开的 /intake 提交面不拦。 */
function RequireSession({ children }: { children: ReactNode }) {
  const location = useLocation();
  const healthQ = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 60_000 });
  const meQ = useQuery({ queryKey: ["auth-me-boot"], queryFn: api.authMe, retry: false });
  if (!healthQ.data) return null; // 加载中/后端不可达：渲染空而非误导性界面
  if (healthQ.data.auth_mode !== "network") return children;
  const onPublicPage = location.pathname.startsWith("/login") || location.pathname.startsWith("/intake/");
  if (!onPublicPage && meQ.isError) {
    const dest = location.pathname + location.search;
    if (dest.startsWith("/") && !dest.startsWith("//")) {
      // 仅相对 hash 路径——防 open-redirect；登录成功后由 LoginPage 消费。
      sessionStorage.setItem("apm-returnTo", dest);
    }
    return <Navigate to="/login" replace />;
  }
  return children;
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

// M95-I287: 新建弹窗草稿跨登录/刷新保留（M94 journey 发现②——表单填一半
// 被登录重定向打断，回来全丢）。sessionStorage 生命周期=标签页，恰好够用。
const DRAFT_NAME = "apm-draft-new-project:name";
const DRAFT_REQ = "apm-draft-new-project:req";

function PickerInner({ projects, autoOpen = false, showArchived, onToggleArchived }: {
  projects: { id: string; name: string; ontology: string; status: string; item_counts?: Record<string, number>; gates_pending?: number }[];
  autoOpen?: boolean;
  showArchived: boolean;
  onToggleArchived: (v: boolean) => void;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(autoOpen);
  const [name, setName] = useState(() => sessionStorage.getItem(DRAFT_NAME) ?? "");
  const [req, setReq] = useState(() => sessionStorage.getItem(DRAFT_REQ) ?? "");
  const [ontology, setOntology] = useState("software-dev");
  const [busy, setBusy] = useState(false);
  const [restored] = useState(() => Boolean(sessionStorage.getItem(DRAFT_NAME) || sessionStorage.getItem(DRAFT_REQ)));

  useEffect(() => {
    if (restored && (name || req)) toast.info("已恢复上次填写的草稿");
    // 只在挂载时提示一次。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (name) sessionStorage.setItem(DRAFT_NAME, name); else sessionStorage.removeItem(DRAFT_NAME);
    if (req) sessionStorage.setItem(DRAFT_REQ, req); else sessionStorage.removeItem(DRAFT_REQ);
  }, [name, req]);

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
                  {p.status === "completed" && <Badge tone="green" title="收尾清单全绿后交付">✅ 已交付</Badge>}
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
          <Input aria-label="项目名称" placeholder="项目名称" value={name} onChange={(e) => setName(e.target.value)} />
          <Textarea aria-label="一句话需求" rows={3} placeholder="一句话需求（PM-Agent 将据此起草 PRD）" value={req} onChange={(e) => setReq(e.target.value)} />
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
                  sessionStorage.removeItem(DRAFT_NAME);
                  sessionStorage.removeItem(DRAFT_REQ);
                  await qc.invalidateQueries({ queryKey: ["projects"] });
                  navigate(`/p/${p.id}`);
                } catch (e) {
                  toast.error("创建失败", { description: String(e) });
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
