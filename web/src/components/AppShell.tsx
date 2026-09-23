/** App shell: dark icon rail + feature column + topbar (mirrors demo.html layout). */
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, BarChart3, CalendarClock, CalendarRange, GitBranch, Library, LayoutDashboard, KanbanSquare, ListTodo, Map as MapIcon, Menu, MessagesSquare, Newspaper, ScrollText,
  Settings as SettingsIcon, Shapes, ShieldAlert, Users, Workflow, Plus, Bell, BellRing, Command,
} from "lucide-react";
import { api } from "../lib/api";
import { connectStream } from "../lib/sse";
import { isTypingTarget } from "../lib/shortcuts";
import { Badge, Button, Modal, Input, Textarea, cx } from "./ui";
import { CommandBar } from "./CommandBar";
import { ShortcutsOverlay } from "./ShortcutsOverlay";
import { toast } from "sonner";

const RAIL = [
  { to: "", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/board", label: "Board", icon: KanbanSquare },
  { to: "/timeline", label: "时间线", icon: CalendarRange },
  { to: "/deps", label: "依赖图", icon: GitBranch },
  { to: "/risks", label: "风险", icon: ShieldAlert },
  { to: "/graph", label: "Graph", icon: Workflow },
  { to: "/reports", label: "报表", icon: BarChart3 },
  { to: "/conversations", label: "Conversations", icon: MessagesSquare, page: true },
  { to: "/runs", label: "Runs", icon: Activity },
  { to: "/my/work", label: "我的工作", icon: ListTodo, global: true },
  { to: "/my/time", label: "我的工时", icon: CalendarClock, global: true },
  { to: "/my/schedule", label: "我的日程", icon: CalendarRange, global: true },
  { to: "/roadmap", label: "路线图", icon: MapIcon, global: true },
  { to: "/activity", label: "项目动态", icon: Newspaper, global: true },
  { to: "/workload", label: "负载", icon: Users, global: true },
  { to: "/assets", label: "Assets", icon: Library, global: true },
  { to: "/templates", label: "模板", icon: Shapes, global: true },
  { to: "/audit", label: "Audit", icon: ScrollText },
  { to: "/ontology", label: "本体", icon: SettingsIcon, page: true },
];

export function AppShell() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const featureId = params.get("feature") ?? undefined;

  const projects = useQuery({ queryKey: ["projects", false], queryFn: () => api.listProjects(false) });
  const features = useQuery({
    queryKey: ["features", pid],
    queryFn: () => api.listFeatures(pid!),
    enabled: !!pid,
  });
  const approvals = useQuery({
    queryKey: ["approvals", pid, "pending"],
    queryFn: () => api.listApprovals({ status: "pending", project_id: pid }),
    enabled: !!pid,
    refetchInterval: 10_000,
  });
  // M44: real-LLM chip — shows the wired model; click pings the provider live
  const llm = useQuery({ queryKey: ["llm-status"], queryFn: api.llmStatus, staleTime: 60_000 });
  const [pinging, setPinging] = useState(false);
  const pingLlm = async () => {
    setPinging(true);
    toast.promise(api.llmPing(), {
      loading: "正在 ping 真实模型…",
      success: (r) => r.ok
        ? `${r.model} 在线 · ${r.latency_ms}ms · tokens ${r.usage?.input}/${r.usage?.output}`
        : `未联通：${r.error ?? "未知错误"}`,
      error: (e) => `ping 失败：${String(e)}`,
      finally: () => setPinging(false),
    });
  };

  useEffect(() => {
    if (!pid) return;
    const es = connectStream(qc, pid);
    return () => es.close();
  }, [pid, qc]);

  const [newFeature, setNewFeature] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
        return;
      }
      // I95: "?" opens the searchable shortcuts overlay (never while typing)
      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey && !isTypingTarget(e.target)) {
        e.preventDefault();
        setHelpOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const pendingCount = approvals.data?.approvals.length ?? 0;
  const active = projects.data?.projects.find((p) => p.id === pid);

  return (
    <div className="flex h-full">
      {/* icon rail (desktop; <md collapses into hamburger drawer below) */}
      <nav className="hidden w-16 shrink-0 flex-col items-center gap-1 bg-rail py-3 text-zinc-400 md:flex">
        {RAIL.map((r) => {
          const to = r.global ? r.to : `/p/${pid}${r.to}`;
          return (
            <NavLink
              key={r.label}
              to={to}
              end={r.end}
              title={r.label}
              className={({ isActive }) =>
                cx(
                  "flex h-11 w-11 items-center justify-center rounded-xl transition-colors",
                  isActive ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-zinc-200",
                )
              }
            >
              <r.icon size={19} strokeWidth={1.8} />
            </NavLink>
          );
        })}
        <div className="mt-auto flex flex-col items-center gap-2 pb-1">
          <ThemeToggle />
          <button
            onClick={pingLlm}
            disabled={pinging}
            title={
              llm.data
                ? `LLM：${llm.data.provider_mode} · ${llm.data.model}\n${llm.data.api_base}\n点击 ping 真实连通`
                : "LLM 状态加载中…"
            }
            className={cx(
              "flex h-11 w-11 flex-col items-center justify-center rounded-xl text-[10px] leading-none",
              llm.data?.provider_mode === "replay"
                ? "text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
                : "text-emerald-400 hover:bg-white/5",
            )}
          >
            <span>{llm.data?.provider_mode === "replay" ? "↻" : "⚙"}</span>
            <span className="mt-0.5 max-w-full truncate px-1">
              {llm.data?.provider_mode === "replay" ? "replay" : (llm.data?.model ?? "…").replace(/^glm-/, "")}
            </span>
          </button>
          <Link to="/" title="项目列表" className="flex h-11 w-11 items-center justify-center rounded-xl hover:bg-white/5 hover:text-zinc-200">
            <Library size={19} strokeWidth={1.8} />
          </Link>
        </div>
      </nav>

      {/* feature column (desktop; features also listed inside the mobile drawer) */}
      <aside className="hidden w-44 shrink-0 flex-col border-r border-line bg-surface/60 md:flex">
        <div className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wide text-mut">
          功能
        </div>
        <div className="flex-1 overflow-y-auto px-2">
          {(features.data?.features ?? []).map((f) => (
            <Link
              key={f.id}
              to={`/p/${pid}/f/${f.id}`}
              className={cx(
                "mb-0.5 block truncate rounded-lg px-2.5 py-1.5 text-[13px]",
                featureId === f.id ? "bg-accbg font-medium text-acc" : "text-ink hover:bg-bg",
              )}
              title={f.title}
            >
              {f.title}
            </Link>
          ))}
          {!features.data?.features.length && (
            <div className="px-2.5 py-2 text-xs text-mut">暂无功能</div>
          )}
        </div>
        <div className="p-2">
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => setNewFeature(true)}>
            <Plus size={14} /> 新功能
          </Button>
        </div>
      </aside>

      {/* main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print flex h-12 shrink-0 items-center gap-1.5 border-b border-line bg-surface px-3 sm:gap-3 sm:px-4">
          <button
            onClick={() => setNavOpen(true)}
            className="-ml-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-mut hover:bg-white/5 hover:text-ink md:hidden"
            title="导航"
          >
            <Menu size={20} />
          </button>
          <span className="truncate text-sm font-semibold">{active?.name ?? "AgentPM"}</span>
          {active && <Badge tone="violet">{active.ontology}</Badge>}
          <button
            onClick={() => setCmdOpen(true)}
            className="ml-auto flex h-9 shrink-0 items-center gap-2 rounded-lg border border-line px-2.5 text-xs text-mut hover:border-acc hover:text-acc"
          >
            <Command size={13} /> <span className="hidden sm:inline">⌘K 命令 / 自然语言</span>
          </button>
          <Link to={`/p/${pid}/approvals`} aria-label="审批中心" className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-mut hover:text-acc" title="审批中心">
            <Bell size={17} />
            {pendingCount > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-dan px-1 text-[10px] font-bold text-white">
                {pendingCount}
              </span>
            )}
          </Link>
          <NotificationsBell />
          <IdentitySwitcher />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      <CommandBar open={cmdOpen} onClose={() => setCmdOpen(false)} />
      {helpOpen && <ShortcutsOverlay onClose={() => setHelpOpen(false)} />}

      {/* mobile navigation drawer (I47): rail + features collapse into one slide-over <768px */}
      {navOpen && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-label="导航抽屉">
          <div className="absolute inset-0 bg-black/50" onClick={() => setNavOpen(false)} />
          <nav className="absolute inset-y-0 left-0 flex w-64 flex-col overflow-y-auto bg-rail pb-3 text-zinc-300 shadow-xl">
            <div className="flex items-center justify-between px-4 pb-1 pt-3">
              <span className="truncate text-sm font-semibold text-white">{active?.name ?? "AgentPM"}</span>
              <button
                onClick={() => setNavOpen(false)}
                className="flex h-9 w-9 items-center justify-center rounded-lg text-zinc-400 hover:bg-white/5 hover:text-white"
                title="关闭"
              >
                ✕
              </button>
            </div>
            {RAIL.map((r) => {
              const to = r.global ? r.to : `/p/${pid}${r.to}`;
              return (
                <NavLink
                  key={r.label}
                  to={to}
                  end={r.end}
                  onClick={() => setNavOpen(false)}
                  className={({ isActive }) =>
                    cx("flex items-center gap-3 px-4 py-2.5 text-sm", isActive ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-zinc-100")
                  }
                >
                  <r.icon size={18} strokeWidth={1.8} /> {r.label}
                </NavLink>
              );
            })}
            {pid && (
              <>
                <div className="mt-2 border-t border-white/10 px-4 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                  功能
                </div>
                {(features.data?.features ?? []).map((f) => (
                  <Link
                    key={f.id}
                    to={`/p/${pid}/f/${f.id}`}
                    onClick={() => setNavOpen(false)}
                    className={cx(
                      "truncate px-4 py-2.5 text-sm",
                      featureId === f.id ? "bg-accbg font-medium text-acc" : "hover:bg-white/5 hover:text-zinc-100",
                    )}
                    title={f.title}
                  >
                    {f.title}
                  </Link>
                ))}
              </>
            )}
          </nav>
        </div>
      )}

      <NewFeatureModal
        open={newFeature}
        onClose={() => setNewFeature(false)}
        pid={pid}
        onCreated={() => setNewFeature(false)}
      />
    </div>
  );
}

const KIND_ICON: Record<string, string> = { assigned: "👤", approval: "◆", rule_notify: "⚡", notify: "🔔" };

/** M54-I163: watch rules management (GitHub custom watch semantics) —
 * 「人×项目×事件类型」 self-built rules; the per-kind pref matrix above still
 * governs delivery per channel. */
const WATCHABLE: { type: string; label: string }[] = [
  { type: "item.created", label: "新建工作项" },
  { type: "item.updated", label: "工作项更新" },
  { type: "item.status_changed", label: "状态变更" },
  { type: "item.assigned", label: "新指派" },
  { type: "comment.created", label: "新评论" },
  { type: "approval.requested", label: "审批请求" },
  { type: "approval.decided", label: "审批决定" },
  { type: "risk.created", label: "新风险" },
  { type: "risk.closed", label: "风险关闭" },
  { type: "expense.recorded", label: "费用登记" },
  { type: "attachment.created", label: "新附件" },
  { type: "artifact.report_generated", label: "报告生成" },
];

function WatchRulesSection() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["watch-rules"], queryFn: api.listWatchRules });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api.listProjects() });
  const [newType, setNewType] = useState(WATCHABLE[2].type);
  const [newPid, setNewPid] = useState("");
  const [condKey, setCondKey] = useState("");
  const [condVal, setCondVal] = useState("");
  useEffect(() => {
    if (!newPid && projects.data?.projects.length) setNewPid(projects.data.projects[0].id);
  }, [projects.data, newPid]);

  const add = async () => {
    if (!newPid) return;
    try {
      const condition: Record<string, string> = {};
      if (condKey.trim() && condVal.trim()) condition[condKey.trim()] = condVal.trim();
      await api.addWatchRule(newPid, newType, condition);
      toast.success("已添加关注");
      setCondKey("");
      setCondVal("");
      await qc.invalidateQueries({ queryKey: ["watch-rules"] });
    } catch (e) {
      toast.error(`添加失败：${e instanceof Error ? e.message : e}`);
    }
  };
  const remove = async (pid: string, type: string) => {
    try {
      await api.removeWatchRule(pid, type);
      await qc.invalidateQueries({ queryKey: ["watch-rules"] });
    } catch (e) {
      toast.error(`删除失败：${e instanceof Error ? e.message : e}`);
    }
  };
  const labelOf = (t: string) => WATCHABLE.find((w) => w.type === t)?.label ?? t;
  return (
    <div className="space-y-1 border-t border-line pt-2">
      <div className="text-[10px] text-mut">👁 项目关注规则（别人动了我关注的项目就提醒我）</div>
      {(rules.data?.rules ?? []).map((r) => (
        <div key={`${r.project_id}/${r.event_type}`} className="flex items-center gap-1.5 text-xs">
          <span className="flex-1 truncate" title={`${r.project_name} · ${r.event_type}${r.condition ? ` · 仅当 ${r.condition}` : ""}`}>
            {r.project_name} · {labelOf(r.event_type)}
            {r.condition && (
              <span className="ml-1 rounded bg-acc/10 px-1 text-[10px] text-acc">仅当 {r.condition}</span>
            )}
          </span>
          <button onClick={() => remove(r.project_id, r.event_type)}
            className="text-mut hover:text-dan" title="删除该关注">✕</button>
        </div>
      ))}
      {rules.data && !rules.data.rules.length && (
        <div className="text-[11px] text-mut">暂无关注——添加一条，命中时通过上面的「自定义关注」通道提醒你</div>
      )}
      <div className="flex items-center gap-1">
        <select value={newPid} onChange={(e) => setNewPid(e.target.value)}
          className="w-0 flex-1 rounded border border-line bg-surface px-1 py-0.5 text-[11px]" title="选择项目">
          {(projects.data?.projects ?? []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <select value={newType} onChange={(e) => setNewType(e.target.value)}
          className="w-0 flex-1 rounded border border-line bg-surface px-1 py-0.5 text-[11px]" title="选择事件类型">
          {WATCHABLE.map((w) => (
            <option key={w.type} value={w.type}>{w.label}</option>
          ))}
        </select>
        <button onClick={add} className="shrink-0 rounded border border-line px-1.5 py-0.5 text-[11px] text-acc hover:border-acc">
          + 关注
        </button>
      </div>
      <div className="flex items-center gap-1 text-[10px] text-mut" title="可选：对事件载荷的精确匹配，如 status_group=done 表示只关注完成">
        <span>仅当</span>
        <input value={condKey} onChange={(e) => setCondKey(e.target.value)} placeholder="字段"
          className="w-0 flex-1 rounded border border-line bg-surface px-1 py-0.5" />
        <span>=</span>
        <input value={condVal} onChange={(e) => setCondVal(e.target.value)} placeholder="值"
          className="w-0 flex-1 rounded border border-line bg-surface px-1 py-0.5" />
      </div>
    </div>
  );
}

/** I96: per-kind × channel preference matrix (GitLab Custom level). mention is
 *  checked and disabled — the API refuses to turn it off anyway (fail-closed). */
function KindPrefMatrix() {
  const qc = useQueryClient();
  const prefs = useQuery({ queryKey: ["notif-prefs"], queryFn: api.getNotificationPrefs });
  const put = async (kind: string, inapp: boolean, email: boolean) => {
    try {
      await api.putNotificationPrefs({ prefs: [{ kind, inapp, email }] });
      await qc.invalidateQueries({ queryKey: ["notif-prefs"] });
    } catch (e) {
      toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
    }
  };
  if (!prefs.data) return null;
  return (
    <div className="space-y-1 pt-1">
      <div className="flex items-center gap-2 text-[10px] text-mut">
        <span className="flex-1">按事件类型</span>
        <span className="w-6 text-center">站内</span>
        <span className="w-6 text-center">邮件</span>
      </div>
      {prefs.data.kinds.map((k) => (
        <div key={k.kind} className="flex items-center gap-2 text-xs">
          <span className="flex-1 truncate" title={k.kind}>{k.label}</span>
          <input type="checkbox" checked={k.inapp} disabled={k.kind === "mention"}
            title={k.kind === "mention" ? "@提及永远送达" : undefined}
            onChange={(e) => put(k.kind, e.target.checked, k.email)} />
          <input type="checkbox" checked={k.email} disabled={k.kind === "mention"}
            onChange={(e) => put(k.kind, k.inapp, e.target.checked)} />
        </div>
      ))}
    </div>
  );
}

/** M46-I140 主题三态切换（亮 → 暗 → 跟随系统循环）。类名与 localStorage
 * 键必须与 index.html 的引导脚本一致（theme-dark / theme-light / apm-theme）。 */
function ThemeToggle() {
  const [theme, setTheme] = useState<"system" | "light" | "dark">(() => {
    try {
      const t = localStorage.getItem("apm-theme");
      return t === "dark" || t === "light" ? t : "system";
    } catch { return "system"; }
  });

  const apply = (next: "system" | "light" | "dark") => {
    setTheme(next);
    const el = document.documentElement;
    el.classList.remove("theme-light", "theme-dark");
    if (next !== "system") el.classList.add(`theme-${next}`);
    try { localStorage.setItem("apm-theme", next); } catch { /* private mode */ }
    toast.info(
      next === "dark" ? "已切换暗色主题" : next === "light" ? "已切换亮色主题" : "跟随系统主题",
      { duration: 1500 },
    );
  };

  const META = {
    system: { icon: "◐", label: "主题：跟随系统（点击切换亮色）" },
    light: { icon: "☀", label: "主题：亮色（点击切换暗色）" },
    dark: { icon: "☾", label: "主题：暗色（点击恢复跟随系统）" },
  } as const;
  const m = META[theme];

  return (
    <button
      onClick={() => apply(theme === "system" ? "light" : theme === "light" ? "dark" : "system")}
      title={m.label}
      aria-label={m.label}
      className="flex h-11 w-11 flex-col items-center justify-center rounded-xl text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
    >
      <span className="text-[15px] leading-none">{m.icon}</span>
      <span className="mt-0.5 text-[10px] leading-none">
        {theme === "system" ? "自动" : theme === "light" ? "亮" : "暗"}
      </span>
    </button>
  );
}

/** In-app notification center (M10-I34): unread badge + latest list + mark-read.
 *  Footer doubles as notification preferences (M11-I37): email switch + feed key. */
function NotificationsBell() {
  const qc = useQueryClient();
  const { pid } = useParams();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [showKey, setShowKey] = useState<string | null>(null);
  const notes = useQuery({
    queryKey: ["notifications"],
    queryFn: api.listNotifications,
    refetchInterval: 15_000,
  });
  const unread = notes.data?.unread ?? 0;

  const invalidate = () => qc.invalidateQueries({ queryKey: ["notifications"] });

  const markAll = async () => {
    try {
      await api.markNotificationsRead({ all: true });
      await invalidate();
    } catch (e) {
      toast.error("标记已读失败", { description: String(e) });
    }
  };

  const toggleEmail = async () => {
    const next = !(notes.data?.email_enabled ?? true);
    try {
      await api.setNotificationPrefs({ email_enabled: next });
      await invalidate();
      toast.info(next ? "邮件通知已开启" : "邮件通知已关闭（站内通知照常）");
    } catch (e) {
      toast.error("通知偏好保存失败", { description: String(e) });
    }
  };

  const loadFeedKey = async () => {
    if (showKey) { setShowKey(null); return; }
    try {
      setShowKey((await api.getFeedKey()).feed_key);
    } catch (e) {
      toast.error("获取订阅密钥失败", { description: String(e) });
    }
  };

  const rotateKey = async () => {
    try {
      const r = await api.rotateFeedKey();
      setShowKey(r.feed_key);
      toast.success("feed key 已换发，旧 key 立即失效");
    } catch (e) {
      toast.error("换发失败", { description: String(e) });
    }
  };

  const copyLink = async () => {
    if (!showKey || !pid) return;
    await navigator.clipboard.writeText(
      `${location.origin}/api/projects/${pid}/feed.atom?key=${showKey}`,
    );
    toast.success("订阅链接已复制");
  };

  return (
    <div className="relative">
      <button onClick={() => setOpen((v) => !v)} aria-label="通知中心" className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-mut hover:text-acc" title="通知中心">
        <BellRing size={17} />
        {unread > 0 && (
          <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-dan px-1 text-[10px] font-bold text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="fixed inset-x-2 top-14 z-40 rounded-xl border border-line bg-surface p-2 shadow-lg sm:absolute sm:inset-x-auto sm:right-0 sm:top-9 sm:w-80">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-xs font-semibold">通知</span>
            <button disabled={!unread} onClick={markAll}
              className={cx("text-[11px]", unread ? "text-acc hover:underline" : "text-mut")}>
              全部已读
            </button>
          </div>
          <div className="max-h-64 space-y-0.5 overflow-y-auto">
            {(notes.data?.notifications ?? []).map((n) => (
              <div key={n.id}
                onClick={async () => {
                  // M18-I57: mention notifications deep-link to the commented item;
                  // following the link also reads the notification
                  if (n.kind === "mention" && (n as { item_id?: string }).item_id && pid) {
                    setOpen(false);
                    if (!n.read) {
                      await api.markNotificationsRead({ ids: [n.id] });
                      invalidate();
                    }
                    navigate(`/p/${pid}/board?item=${(n as { item_id?: string }).item_id}`);
                  }
                }}
                className={cx("flex items-start gap-2 rounded-lg px-2 py-1.5 text-xs",
                  !n.read && "bg-accbg/50",
                  n.kind === "mention" && (n as { item_id?: string }).item_id && "cursor-pointer hover:bg-bg")}>
                <span>{KIND_ICON[n.kind] ?? "🔔"}</span>
                <div className="min-w-0">
                  <div className={cx("truncate", !n.read && "font-medium")}>{n.summary}</div>
                  <div className="text-[10px] text-mut">{n.kind} · {new Date(n.created_at).toLocaleString()}</div>
                </div>
                {!n.read && <span className="ml-auto mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-acc" />}
              </div>
            ))}
            {!notes.data?.notifications.length && (
              <div className="px-2 py-3 text-xs text-mut">暂无通知——指派、审批请求与自动化提醒会出现在这里</div>
            )}
          </div>
          <div className="mt-1 space-y-1 border-t border-line px-2 pt-2 text-xs">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={notes.data?.email_enabled ?? true} onChange={toggleEmail} />
              <span>邮件通知{notes.data?.email_enabled ? "（开启）" : "（已关，站内照常）"}</span>
            </label>
            <KindPrefMatrix />
            <WatchRulesSection />
            <div className="flex items-center gap-2">
              <button onClick={loadFeedKey} className="text-[11px] text-acc hover:underline">
                {showKey ? "隐藏 feed key" : "Atom 订阅 key"}
              </button>
              {showKey && pid && (
                <button onClick={copyLink} className="text-[11px] text-acc hover:underline">复制订阅链接</button>
              )}
              {showKey && (
                <button onClick={rotateKey} className="text-[11px] text-mut hover:text-dan">换发</button>
              )}
            </div>
            {showKey && (
              <pre className="max-h-16 overflow-auto rounded-lg border border-line bg-bg px-2 py-1 font-mono text-[10px]">
                {showKey}{pid ? `\n${location.origin}/api/projects/${pid}/feed.atom?key=${showKey}` : ""}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function NewFeatureModal({ open, onClose, pid, onCreated }: {
  open: boolean; onClose: () => void; pid?: string;  onCreated: (f: { id: string }) => void;
}) {
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const qc = useQueryClient();
  const [error, setError] = useState("");
  useEffect(() => { if (open) { setTitle(""); setBrief(""); setError(""); } }, [open]);
  if (!pid) return null;
  return (
    <Modal open={open} onClose={onClose} title="新功能">
      <div className="space-y-3">
        <Input placeholder="功能名称（如：导入解析）" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Textarea rows={3} placeholder="一句话描述（将作为功能简报 L2 初稿）" value={brief} onChange={(e) => setBrief(e.target.value)} />
        {error && <div className="text-xs text-dan">{error}</div>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button
            variant="primary"
            disabled={!title.trim()}
            onClick={async () => {
              try {
                const f = await api.createFeature(pid, { title, brief: brief || undefined });
                await qc.invalidateQueries({ queryKey: ["features", pid] });
                onCreated(f);
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            创建
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/** Identity chip (M5-I19 local switching / M8-I28 session identity). */
function IdentitySwitcher() {
  const me = useQuery({ queryKey: ["auth-me"], queryFn: api.authMe });
  const navigate = useNavigate();
  const qc = useQueryClient();
  if (me.data?.source === "session") {
    // network 模式：身份 = 登录人，切换 = 登出重登。
    return (
      <div className="flex items-center gap-1.5">
        <span className="shrink-0 whitespace-nowrap rounded-lg border border-line px-2.5 py-1.5 text-xs text-mut"
          title="网络模式 · 以登录身份归账">
          {me.data.is_admin ? "⭐" : "👤"} {me.data.name}
        </span>
        <button onClick={async () => {
          await api.logout();
          await qc.invalidateQueries();
          navigate("/login");
        }} className="rounded-lg border border-line px-2 py-1.5 text-xs text-mut hover:text-ink">登出</button>
      </div>
    );
  }
  return <LocalSwitcher />;
}

/** Local-mode identity switcher (M5-I19): 单机多身份——切换后所有操作归到该身份的审计流。 */
function LocalSwitcher() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });

  const switchTo = async (uid: string) => {
    try {
      const r = await api.switchIdentity(uid);
      toast.success(`已切换身份：${r.name}（${r.current}）`);
      setOpen(false);
      await qc.invalidateQueries();
    } catch (e) {
      toast.error(`切换失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const register = async () => {
    if (!newName.trim()) return;
    try {
      const u = await api.registerUser(newName.trim());
      setNewName("");
      await qc.invalidateQueries({ queryKey: ["users"] });
      await switchTo(u.id);
    } catch (e) {
      toast.error(`注册失败：${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border border-line px-2.5 py-1.5 text-xs text-mut hover:border-acc hover:text-acc"
        title="切换身份（单机多身份）"
      >
        👤 {users.data?.current_name ?? "…"}
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-40 w-60 rounded-xl border border-line bg-surface p-2 shadow-lg">
          <div className="space-y-0.5">
            {users.data?.users.map((u) => (
              <button
                key={u.id}
                onClick={() => switchTo(u.id)}
                className={cx(
                  "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-bg",
                  u.id === users.data?.current && "text-acc",
                )}
              >
                <span>{u.id === users.data?.current ? "●" : "○"}</span>
                <span className="font-medium">{u.name}</span>
                <span className="ml-auto font-mono text-[10px] text-mut">{u.id}</span>
              </button>
            ))}
          </div>
          <div className="mt-2 flex items-center gap-1.5 border-t border-line pt-2">
            <input
              className="min-w-0 flex-1 rounded-lg border border-line bg-bg px-2 py-1 text-xs"
              placeholder="新身份姓名"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && register()}
            />
            <Button size="sm" variant="outline" onClick={register} disabled={!newName.trim()}>
              注册
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
