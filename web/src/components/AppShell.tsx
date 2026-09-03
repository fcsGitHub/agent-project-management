/** App shell: dark icon rail + feature column + topbar (mirrors demo.html layout). */
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, Library, LayoutDashboard, KanbanSquare, MessagesSquare, ScrollText,
  Settings as SettingsIcon, Shapes, Workflow, Plus, Bell, BellRing, Command,
} from "lucide-react";
import { api } from "../lib/api";
import { connectStream } from "../lib/sse";
import { Badge, Button, Modal, Input, Textarea, cx } from "./ui";
import { CommandBar } from "./CommandBar";
import { toast } from "sonner";

const RAIL = [
  { to: "", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/board", label: "Board", icon: KanbanSquare },
  { to: "/graph", label: "Graph", icon: Workflow },
  { to: "/conversations", label: "Conversations", icon: MessagesSquare, page: true },
  { to: "/runs", label: "Runs", icon: Activity },
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

  const projects = useQuery({ queryKey: ["projects"], queryFn: api.listProjects });
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

  useEffect(() => {
    if (!pid) return;
    const es = connectStream(qc, pid);
    return () => es.close();
  }, [pid, qc]);

  const [newFeature, setNewFeature] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const pendingCount = approvals.data?.approvals.length ?? 0;
  const active = projects.data?.projects.find((p) => p.id === pid);

  return (
    <div className="flex h-full">
      {/* icon rail */}
      <nav className="flex w-16 shrink-0 flex-col items-center gap-1 bg-rail py-3 text-zinc-400">
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
          <Link to="/" title="项目列表" className="flex h-11 w-11 items-center justify-center rounded-xl hover:bg-white/5 hover:text-zinc-200">
            <Library size={19} strokeWidth={1.8} />
          </Link>
        </div>
      </nav>

      {/* feature column */}
      <aside className="flex w-44 shrink-0 flex-col border-r border-line bg-surface/60">
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
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-surface px-4">
          <span className="truncate text-sm font-semibold">{active?.name ?? "AgentPM"}</span>
          {active && <Badge tone="violet">{active.ontology}</Badge>}
          <button
            onClick={() => setCmdOpen(true)}
            className="ml-auto flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-xs text-mut hover:border-acc hover:text-acc"
          >
            <Command size={13} /> ⌘K 命令 / 自然语言
          </button>
          <Link to={`/p/${pid}/approvals`} className="relative text-mut hover:text-acc" title="审批中心">
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

/** In-app notification center (M10-I34): unread badge + latest list + mark-read.
 *  Footer doubles as notification preferences (M11-I37): email switch + feed key. */
function NotificationsBell() {
  const qc = useQueryClient();
  const { pid } = useParams();
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
    await api.markNotificationsRead({ all: true });
    await invalidate();
  };

  const toggleEmail = async () => {
    const next = !(notes.data?.email_enabled ?? true);
    await api.setNotificationPrefs({ email_enabled: next });
    await invalidate();
    toast.info(next ? "邮件通知已开启" : "邮件通知已关闭（站内通知照常）");
  };

  const loadFeedKey = async () => {
    const k = showKey ? null : (await api.getFeedKey()).feed_key;
    setShowKey(k);
  };

  const rotateKey = async () => {
    const r = await api.rotateFeedKey();
    setShowKey(r.feed_key);
    toast.success("feed key 已换发，旧 key 立即失效");
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
      <button onClick={() => setOpen((v) => !v)} className="relative text-mut hover:text-acc" title="通知中心">
        <BellRing size={17} />
        {unread > 0 && (
          <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-dan px-1 text-[10px] font-bold text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-40 w-80 rounded-xl border border-line bg-surface p-2 shadow-lg">
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
                className={cx("flex items-start gap-2 rounded-lg px-2 py-1.5 text-xs",
                  !n.read && "bg-accbg/50")}>
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
        <span className="rounded-lg border border-line px-2.5 py-1.5 text-xs text-mut"
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
        className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs text-mut hover:border-acc hover:text-acc"
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
