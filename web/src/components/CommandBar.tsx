/** ⌘K command bar: dual mode — fuzzy commands + natural language (UI-Agent L1). */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Badge, Button, cx } from "./ui";

type ParsedAction = { action: string; label?: string; description?: string; params: Record<string, unknown>; read_only: boolean; status?: string };

export function CommandBar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { pid } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [mode, setMode] = useState<"command" | "nl">("command");
  const [q, setQ] = useState("");
  const [nlResult, setNlResult] = useState<{ id: string; actions: ParsedAction[]; requires_confirmation: boolean; parser?: "rules" | "llm"; reply?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQ(""); setMode("command"); setNlResult(null);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const commands = useMemo(() => {
    if (!pid) return [];
    return [
      { id: "nav-dashboard", label: "打开 Dashboard", run: () => navigate(`/p/${pid}`) },
      { id: "nav-board", label: "打开看板 Board", run: () => navigate(`/p/${pid}/board`) },
      { id: "nav-graph", label: "打开项目图 Graph", run: () => navigate(`/p/${pid}/graph`) },
      { id: "nav-convs", label: "打开对话列表", run: () => navigate(`/p/${pid}/conversations`) },
      { id: "nav-runs", label: "打开 Runs 轨迹", run: () => navigate(`/p/${pid}/runs`) },
      { id: "nav-assets", label: "打开资产库", run: () => navigate(`/assets`) },
      { id: "nav-audit", label: "打开审计页", run: () => navigate(`/p/${pid}/audit`) },
      { id: "nav-ontology", label: "打开本体页", run: () => navigate(`/p/${pid}/ontology`) },
      { id: "nav-approvals", label: "打开审批中心", run: () => navigate(`/p/${pid}/approvals`) },
      { id: "new-feature", label: "新建功能", run: () => navigate(`/p/${pid}?new=feature`) },
      { id: "deliver", label: "生成交付（Release-Agent）", run: async () => {
        const r = await api.deliver(pid);
        toast.success("已启动 Release-Agent", { description: "发布说明起草中，请到审批中心查看" });
        navigate(`/p/${pid}/c/${r.conversation_id}`);
      } },
    ];
  }, [pid, navigate]);

  const filtered = commands.filter((c) => c.label.toLowerCase().includes(q.toLowerCase()));

  // M22-I68: with a query typed, offer the global search jump first
  const entries = q.trim()
    ? [{ id: "global-search", label: `🔍 搜索 '${q.trim()}'`, run: () => navigate(`/search?q=${encodeURIComponent(q.trim())}`) }, ...filtered]
    : filtered;

  if (!open) return null;

  const pageState = {
    route: location.pathname,
    feature: params.get("feature"),
  };

  const runNl = async () => {
    if (!q.trim()) return;
    setBusy(true);
    try {
      const r = await api.uiCommand(q, pageState);
      // read-only actions execute directly (navigate / filter via URL)
      const executed: ParsedAction[] = [];
      for (const a of r.actions as ParsedAction[]) {
        if (a.read_only) {
          applyReadonly(a);
          executed.push({ ...a, status: "executed" });
        }
      }
      setNlResult({ ...r, actions: [...executed, ...r.actions.filter((a) => !a.read_only)] });
    } catch (e) {
      toast.error("解析失败", { description: String(e) });
    } finally {
      setBusy(false);
    }
  };

  const confirmWrites = async () => {
    if (!nlResult) return;
    setBusy(true);
    try {
      await api.confirmUiCommand(nlResult.id);
      await qc.invalidateQueries();
      toast.success("已执行写操作");
      setNlResult(null);
      onClose();
    } catch (e) {
      toast.error("执行失败", { description: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]">
      <div className="absolute inset-0 bg-black/25" onClick={onClose} />
      <div className="relative z-10 w-full max-w-xl overflow-hidden rounded-[12px] border border-line bg-surface shadow-2xl">
        <div className="flex items-center gap-2 border-b border-line px-3">
          <div className="flex gap-1 py-2">
            {(["command", "nl"] as const).map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setNlResult(null); }}
                className={cx(
                  "rounded-md px-2 py-1 text-xs font-medium",
                  mode === m ? "bg-accbg text-acc" : "text-mut hover:text-ink",
                )}
              >
                {m === "command" ? "命令" : "自然语言"}
              </button>
            ))}
          </div>
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
              if (e.key === "Enter" && mode === "command" && entries[0]) { entries[0].run(); onClose(); }
              if (e.key === "Enter" && mode === "nl") runNl();
            }}
            placeholder={mode === "command" ? "搜索动作…（回车执行第一个）" : "试试：只看高优先级任务 / 打开审计页 / 批量批准"}
            className="flex-1 bg-transparent px-2 py-3 text-sm outline-none placeholder:text-mut/60"
          />
          <kbd className="rounded border border-line px-1.5 py-0.5 text-[10px] text-mut">ESC</kbd>
        </div>

        <div className="max-h-96 overflow-y-auto p-2">
          {mode === "command" &&
            entries.map((c) => (
              <button
                key={c.id}
                onClick={() => { c.run(); onClose(); }}
                className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-bg"
              >
                {c.label}
              </button>
            ))}
          {mode === "command" && !entries.length && (
            <div className="px-3 py-6 text-center text-xs text-mut">
              没有匹配动作——按 Tab 切到「自然语言」模式试试
            </div>
          )}

          {mode === "nl" && !nlResult && (
            <div className="px-3 py-4 text-xs text-mut">
              UI-Agent 将解析为页面动作：只读动作直接执行；写操作需确认。L1 规则解析优先；真实模型模式下规则未命中时自动回退 L2 模型解析。
            </div>
          )}

          {mode === "nl" && nlResult && (
            <div className="space-y-2 p-2">
              {nlResult.parser && (
                <div className="px-1 text-[11px] text-mut">
                  {nlResult.parser === "llm" ? "🤖 L2 模型解析（真实 LLM 调用）" : "📋 L1 规则解析"}
                  {nlResult.reply ? ` · ${nlResult.reply}` : ""}
                </div>
              )}
              {nlResult.actions.map((a, i) => (
                <div key={i} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                  <span className="flex items-center gap-2">
                    {a.status === "executed" ? "✅" : a.read_only ? "✓" : "▸"}
                    <span>{a.label ?? a.description ?? a.action}</span>
                  </span>
                  <Badge tone={a.read_only ? "green" : "amber"}>{a.read_only ? "只读·已执行" : "写操作"}</Badge>
                </div>
              ))}
              {nlResult.actions.some((a) => !a.read_only) && (
                <div className="flex justify-end gap-2 pt-1">
                  <Button variant="ghost" size="sm" onClick={() => setNlResult(null)}>取消</Button>
                  <Button variant="primary" size="sm" disabled={busy} onClick={confirmWrites}>
                    确认执行写操作
                  </Button>
                </div>
              )}
              {!nlResult.actions.some((a) => !a.read_only) && (
                <div className="text-right text-xs text-ok">只读操作已全部执行 ✓</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  function applyReadonly(a: ParsedAction) {
    const p = a.params as Record<string, string>;
    if (a.action === "navigate") navigate(p.path);
    if (a.action === "set_filter") {
      // hash routing: the real path lives in location.hash
      const [hashPath, hashQuery] = (location.hash.slice(1) || "/").split("?");
      const usp = new URLSearchParams(hashQuery ?? "");
      Object.entries(p).forEach(([k, v]) => usp.set(k, String(v)));
      navigate(`${hashPath}?${usp.toString()}`);
    }
  }
}
