/** Audit page: event stream with filters, payload expansion, CSV export. */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import { Button, Card, Empty, Input, cx } from "../components/ui";

const ICON: Record<string, string> = { human: "👤", agent: "🤖", system: "⚙️", ui_agent: "⌨️", automation: "⚡" };
const DOMAINS = ["全部", "approval", "item", "automation", "run", "message", "artifact", "asset", "ui_command", "prompt"];

export function AuditPage() {
  const { pid } = useParams();
  const [domain, setDomain] = useState("全部");
  const [actor, setActor] = useState("");
  const [q, setQ] = useState("");
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const events = useQuery({
    queryKey: ["events", pid, domain, actor, page],
    queryFn: () => api.listEvents({ project_id: pid, actor_type: actor || undefined, limit: 50, offset: page * 50 }),
    enabled: !!pid,
  });

  const filtered = (events.data?.events ?? []).filter((e) => {
    if (domain !== "全部" && !e.event_type.startsWith(domain === "message" ? "message" : domain)) return false;
    if (q && !`${e.event_type} ${e.agg_id} ${JSON.stringify(e.payload)}`.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  const exportCsv = () => {
    const rows = [["id", "ts", "actor_type", "actor_id", "event_type", "agg_type", "agg_id", "payload"]];
    for (const e of filtered) {
      rows.push([String(e.id), e.ts, e.actor_type, e.actor_id, e.event_type, e.agg_type, e.agg_id, JSON.stringify(e.payload)]);
    }
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `audit-${pid}.csv`;
    a.click();
    // audit.exported is recorded server-side on next reload; MVP keeps client export simple
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2">
        <span className="text-sm font-semibold">审计 · 不可变事件流</span>
        <div className="flex flex-wrap gap-1">
          {DOMAINS.map((d) => (
            <button key={d} onClick={() => setDomain(d)}
              className={cx("rounded-full border px-2 py-0.5 text-[11px]",
                domain === d ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink")}>
              {d}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <select value={actor} onChange={(e) => setActor(e.target.value)}
            className="rounded-lg border border-line bg-surface px-2 py-1.5 text-xs">
            <option value="">发起者（全部）</option>
            <option value="human">👤 人</option>
            <option value="agent">🤖 Agent</option>
            <option value="automation">⚡ 自动化</option>
            <option value="system">⚙️ 系统</option>
            <option value="ui_agent">⌨️ UI-Agent</option>
          </select>
          <Input className="w-40" placeholder="搜索 payload…" value={q} onChange={(e) => setQ(e.target.value)} />
          <Button size="sm" variant="outline" onClick={exportCsv}>导出 CSV</Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <Card className="divide-y divide-line">
          {filtered.map((e) => (
            <div key={e.id}>
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-bg"
                onClick={() => setOpenRow(openRow === String(e.id) ? null : String(e.id))}
              >
                <span className={`w-16 shrink-0 font-mono text-mut${openRow === String(e.id) ? " hidden" : ""}`}>#{e.id}</span>
                <span className="w-20 shrink-0 text-mut">{timeAgo(e.ts)}</span>
                <span>{ICON[e.actor_type] ?? "•"}</span>
                <span className="w-32 shrink-0 truncate text-mut">{e.actor_id.split(":")[0]}</span>
                <span className="font-mono font-medium">{e.event_type}</span>
                <span className="truncate text-mut">{String(e.payload.title ?? e.payload.status ?? e.payload.path ?? "")}</span>
              </button>
              {openRow === String(e.id) && (
                <pre className="max-h-64 overflow-auto border-t border-line bg-bg/50 px-4 py-2 text-[11px]">
                  {JSON.stringify(e, null, 2)}
                </pre>
              )}
            </div>
          ))}
          {!filtered.length && <Empty title="无匹配事件" hint="调整过滤条件" />}
        </Card>
        <div className="mt-3 flex items-center justify-center gap-2 text-xs text-mut">
          <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>← 上一页</Button>
          <span>第 {page + 1} 页 · 共 {events.data?.total ?? 0} 条</span>
          <Button size="sm" variant="ghost" disabled={(events.data?.events.length ?? 0) < 50} onClick={() => setPage(page + 1)}>下一页 →</Button>
        </div>
      </div>
    </div>
  );
}
