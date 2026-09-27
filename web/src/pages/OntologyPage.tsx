/** Ontology page: read-only browsing of the project's type system + validation
 *  + the ontology-learning flywheel (M4-I14, docs/08 §8: scan → review → apply)
 *  + versioning with semantic diff & impact analysis (M4-I15). */
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useEffect, useState } from "react";
import { api, type AutomationRule, type DeliveryRecord, type OntologyDiff, type OntologyLearnResult } from "../lib/api";
import { Badge, Button, Card, Input, Modal, cx } from "../components/ui";

export function OntologyPage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.authMe });
  const members = useQuery({ queryKey: ["members", pid], queryFn: () => api.listMembers(pid!), enabled: !!pid });
  const myRole = (members.data?.members ?? []).find((m) => m.user_id === me.data?.user_id)?.role;
  const isAdmin = !!me.data?.is_admin;
  const onto = useQuery({
    queryKey: ["ontology", pid],
    queryFn: () => api.getOntology(pid!, true),
    enabled: !!pid,
  });
  const o = onto.data;
  const [scan, setScan] = useState<OntologyLearnResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [diff, setDiff] = useState<OntologyDiff | null>(null);
  const [diffing, setDiffing] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importName, setImportName] = useState("");
  const [importing, setImporting] = useState(false);

  const history = useQuery({
    queryKey: ["ontology-history", pid],
    queryFn: () => api.getOntologyHistory(o?.name ?? ""),
    enabled: !!o,
  });
  const project = useQuery({
    queryKey: ["project", pid],
    queryFn: () => api.getProject(pid!),
    enabled: !!pid,
  });
  const disabledFields = project.data?.disabled_fields ?? [];
  const cq = useQuery({
    queryKey: ["ontology-cq", pid],
    queryFn: () => api.cqCheck(o!.name),
    enabled: !!o,
  });

  if (!o) return <div className="p-6 text-sm text-mut">加载本体…</div>;

  const runLearn = async () => {
    setScanning(true);
    try {
      const r = await api.learnOntology(o.name);
      setScan(r);
      setSelected(new Set());
      if (!r.candidates.length) toast.info("数据与本体一致，暂无可归纳的变更候选");
    } catch (e) {
      toast.error(`扫描失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setScanning(false);
    }
  };

  const runLearnLlm = async () => {
    setScanning(true);
    try {
      const r = await api.learnOntologyLlm(o.name);
      setScan(r);
      setSelected(new Set());
      if (r.llm?.error) toast.warning(`LLM 层降级：${r.llm.error}（pattern 层结果不受影响）`);
      else if (!r.candidates.length) toast.info("LLM 层与数据面均无可归纳的变更候选");
      else toast.success(`LLM 层：接受 ${r.llm?.accepted ?? 0} 条（合并 ${r.llm?.merged ?? 0} 条）`);
    } catch (e) {
      toast.error(`LLM 扫描失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setScanning(false);
    }
  };

  const runApply = async () => {
    if (!selected.size) return;
    setApplying(true);
    try {
      const r = await api.applyOntology(o.name, [...selected]);
      toast.success(`已应用 ${r.applied.length} 项候选，本体升级到 v${r.version}`);
      setScan(null);
      setSelected(new Set());
      await qc.invalidateQueries({ queryKey: ["ontology", pid] });
      await qc.invalidateQueries({ queryKey: ["ontology-history", pid] });
      await qc.invalidateQueries({ queryKey: ["ontology-cq", pid] });
    } catch (e) {
      toast.error(`应用失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setApplying(false);
    }
  };

  const runDiff = async (fromV: number, toV?: number) => {
    setDiffing(true);
    try {
      setDiff(await api.getOntologyDiff(o!.name, fromV, toV));
    } catch (e) {
      toast.error(`diff 失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setDiffing(false);
    }
  };

  const exportPack = async () => {
    try {
      const pack = await api.exportOntology(o!.name);
      const blob = new Blob([JSON.stringify(pack, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${o!.name}-pack.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast.success("模板包已导出（本体 + 角色 + 提示词模板）");
    } catch (e) {
      toast.error(`导出失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const doImport = async () => {
    setImporting(true);
    try {
      const pack = JSON.parse(importText);
      const r = await api.importOntology(pack, importName.trim());
      toast.success(`已导入为 ${r.name} v${r.version}（角色：${r.roles.map((x) => `${x.id}:${x.action}`).join("、") || "无"}）`);
      setImportOpen(false);
      setImportText("");
      setImportName("");
    } catch (e) {
      toast.error(`导入失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setImporting(false);
    }
  };

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="space-y-4 p-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{o.display_name}</span>
          <Badge tone="violet">{o.name} · v{o.version}</Badge>
          <Badge tone={o.errors.length ? "red" : "green"}>
            {o.errors.length ? `校验失败（${o.errors.length}）` : "校验通过 ✓"}
          </Badge>
          <span className="ml-auto flex items-center gap-2">
            <span className="font-mono text-xs text-mut">ontology/ontology.yaml</span>
            <Button size="sm" variant="ghost" onClick={exportPack}>⬇ 导出模板包</Button>
            <Button size="sm" variant="ghost" onClick={() => setImportOpen((v) => !v)}>⬆ 导入</Button>
          </span>
        </div>
        {importOpen && (
          <div className="mt-3 space-y-2 rounded-lg border border-line bg-bg p-3">
            <div className="flex items-center gap-2">
              <input
                className="w-56 rounded-lg border border-line bg-surface px-2 py-1 text-xs"
                placeholder="导入为本体名（如 software-dev-lite）"
                value={importName} onChange={(e) => setImportName(e.target.value)}
              />
              <Button size="sm" variant="primary" disabled={importing || !importName.trim() || !importText.trim()} onClick={doImport}>
                {importing ? "导入中…" : "导入"}
              </Button>
              <span className="text-[10px] text-mut">同名本体拒绝导入（409）；已存在的角色复用不覆盖。</span>
            </div>
            <textarea
              className="h-32 w-full rounded-lg border border-line bg-surface p-2 font-mono text-[10px]"
              placeholder="粘贴模板包 JSON（本体页「导出模板包」所得）"
              value={importText} onChange={(e) => setImportText(e.target.value)}
            />
          </div>
        )}
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

      <FieldActivationPanel pid={pid!} concepts={o.concepts} disabled={disabledFields} />

      {(myRole === "owner" || isAdmin) && <ConceptVisibilityPanel pid={pid!} concepts={o.concepts} />}

      <MembersPanel pid={pid!} />

      {(myRole === "owner" || isAdmin) && <IntakePanel pid={pid!} />}

      <CalendarPanel />

      <RatePanel />

      <TimeOffPanel />

      <OidcPanel />

      <AutomationsPanel pid={pid!} concepts={o.concepts}
        agentRoles={[...new Set(o.concepts.flatMap((c) => c.agent_roles))]} />

      <WebhooksPanel pid={pid!} />

      <LearnPanel
        scan={scan} scanning={scanning} applying={applying} selected={selected}
        onLearn={runLearn} onLearnLlm={runLearnLlm} onApply={runApply} onToggle={toggle}
      />

      <VersionPanel
        currentVersion={o.version}
        history={history.data}
        diff={diff} diffing={diffing}
        onDiff={runDiff}
      />

      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-mut">
          Competency Questions（验收锚点 · I16 可回答性检查）
          {cq.data && <Badge tone={allAnswerable(cq.data) ? "green" : "amber"}>{cq.data.summary}</Badge>}
        </div>
        <Card className="divide-y divide-line">
          {cq.data?.questions.map((q) => (
            <div key={q.question} className="px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs">❓ {q.question}</span>
                <CqStatusBadge status={q.status} />
              </div>
              {q.evidence.length > 0 && (
                <div className="mt-1 space-y-0.5 pl-4">
                  {q.evidence.map((e) => (
                    <div key={e.source} className="font-mono text-[10px] text-mut">
                      {SOURCE_LABEL[e.source] ?? e.source}：{e.count > 0 ? `✓ ${e.count}` : "× 0"} — {e.summary}
                    </div>
                  ))}
                </div>
              )}
              {q.status === "unmapped" && (
                <div className="mt-1 pl-4 text-[10px] text-mut">
                  未声明支撑数据面——在 ontology.yaml 的 cq_mappings 中为该问题补充 supports。
                </div>
              )}
            </div>
          ))}
          {!cq.data && <div className="px-3 py-2 text-xs text-mut">检查中…</div>}
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

/** Per-project custom-field activation (M7-I25): the ontology declares fields,
 *  the project activates/deactivates them — writes and board grouping follow. */
function FieldActivationPanel({ pid, concepts, disabled }: {
  pid: string;
  disabled: string[];
  concepts: { id: string; name: string; fields?: { id: string; name: string; type: string }[] }[];
}) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const fields = new Map<string, { name: string; type: string; conceptNames: string[] }>();
  for (const c of concepts)
    for (const f of c.fields ?? []) {
      const cur = fields.get(f.id) ?? { name: f.name, type: f.type, conceptNames: [] };
      cur.conceptNames.push(c.name);
      fields.set(f.id, cur);
    }
  if (!fields.size) return null;

  const flip = async (fieldId: string, active: boolean) => {
    setBusy(fieldId);
    try {
      await api.patchProjectFields(pid, { field_id: fieldId, active });
      await qc.invalidateQueries({ queryKey: ["project", pid] });
      await qc.invalidateQueries({ queryKey: ["board", pid] });
      toast.success(active ? `字段「${fields.get(fieldId)?.name}」已启用` : `字段「${fields.get(fieldId)?.name}」已停用（写入与看板分组将拒绝）`);
    } catch (e) {
      toast.error(`操作失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">字段激活（本项目）</span>
        <span className="text-xs text-mut">停用后该项目拒绝写入此字段，看板分组也不再提供该维度</span>
      </div>
      <div className="mt-3 space-y-1.5">
        {[...fields.entries()].map(([fid, f]) => {
          const off = disabled.includes(fid);
          return (
            <div key={fid} className="flex items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-xs">
              <span className="font-medium">{f.name}</span>
              <span className="font-mono text-[10px] text-mut">{fid} · {f.type}</span>
              <span className="text-[11px] text-mut">用于 {f.conceptNames.join("、")}</span>
              <button
                disabled={busy === fid}
                onClick={() => flip(fid, off)}
                className={cx("ml-auto rounded-md border px-2 py-0.5",
                  off ? "border-line text-mut hover:text-ink" : "border-acc bg-accbg text-acc")}
              >
                {off ? "已停用 · 点击启用" : "已启用 · 点击停用"}
              </button>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

const MEMBER_ROLE: Record<string, { label: string; tone: "green" | "violet" | "neutral" }> = {
  owner: { label: "Owner", tone: "green" },
  contributor: { label: "Contributor", tone: "violet" },
  viewer: { label: "Viewer", tone: "neutral" },
};/** OIDC SSO diagnostics (M17-I54): read-only env-derived config; secret never echoed. */
function OidcPanel() {
  const st = useQuery({ queryKey: ["oidc-status"], queryFn: api.oidcStatus });
  const d = st.data;
  if (!d) return null;
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold">OIDC 单点登录</span>
        {d.enabled
          ? <Badge tone="ok">已启用</Badge>
          : <Badge tone="neutral">未配置</Badge>}
      </div>
      {d.enabled ? (
        <div className="space-y-1 text-xs text-mut">
          <div>Issuer：<span className="font-mono text-ink">{d.issuer}</span></div>
          <div>Client ID：<span className="font-mono text-ink">{d.client_id}</span></div>
          <div>回调地址：<span className="font-mono text-ink">{d.redirect_uri}</span></div>
          <div>组白名单：{d.allowed_groups.length
            ? d.allowed_groups.map((g) => <Badge key={g} tone="indigo">{g}</Badge>)
            : <span>未设（任何已验证 IdP 用户可注册）</span>}</div>
          <div className="pt-1 text-[11px]">JIT 注册角色 = viewer 缺省；配置项走 APM_OIDC_* 环境变量，client secret 不回显。</div>
        </div>
      ) : (
        <div className="text-xs text-mut">设置 APM_OIDC_ISSUER / APM_OIDC_CLIENT_ID / APM_OIDC_CLIENT_SECRET 后启用；当前登录页不显示 SSO 入口。</div>
      )}
    </Card>
  );
}

/** Project members & roles (M8-I27): owner / contributor / viewer management. */
/** I99: external intake (Trello board-email semantics) — owner mints one
 *  token per project; the public form lands first-class items via it. */
function IntakePanel({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const tok = useQuery({ queryKey: ["intake-token", pid], queryFn: () => api.getIntakeToken(pid) });
  const [busy, setBusy] = useState(false);
  const [justCopied, setJustCopied] = useState(false);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["intake-token", pid] });

  const issue = async () => {
    setBusy(true);
    try {
      await api.issueIntakeToken(pid);
      await invalidate();
      toast.success("收件令牌已生成");
    } catch (e) {
      toast.error(`生成失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    setBusy(true);
    try {
      await api.revokeIntakeToken(pid);
      await invalidate();
      toast.info("收件令牌已吊销——旧链接立即失效");
    } catch (e) {
      toast.error(`吊销失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const link = tok.data?.issued && tok.data.token
    ? `${location.origin}/#/intake/${tok.data.token}` : null;

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">📮 外部收件</span>
        <span className="text-xs text-mut">免登录表单直达看板 · 令牌即凭证</span>
        <span className="ml-auto flex items-center gap-1">
          {tok.data?.issued && (
            <>
              <button onClick={async () => {
                if (link) { await navigator.clipboard.writeText(link); setJustCopied(true); setTimeout(() => setJustCopied(false), 1500); }
              }} className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-ink">
                {justCopied ? "已复制 ✓" : "复制链接"}
              </button>
              <button disabled={busy} onClick={revoke}
                className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-dan">吊销</button>
            </>
          )}
          <Button size="sm" variant="outline" disabled={busy} onClick={issue}>
            {tok.data?.issued ? "重发令牌" : "生成令牌"}
          </Button>
        </span>
      </div>
      {tok.data?.issued && link && (
        <div className="mt-2 truncate rounded-lg border border-line bg-bg px-2.5 py-1.5 font-mono text-[11px] text-ink" title={link}>
          {link}
        </div>
      )}
      <div className="mt-1 text-[10px] text-mut">
        任何人用此链接无需账号即可提交工作项（标题必填、优先级可选），提交按「intake」身份归账；吊销或重发后旧链接立即失效。邮件通道可用「[项目名] 主题」前缀定向到成员项目（I113）。
      </div>
    </Card>
  );
}

/** I111: personal time-off (Taiga capacity-pain / Jira PTO semantics) —
 *  own-data stretches; workload flags 🏖 and my-schedule overlays the bar. */
function RatePanel() {
  const qc = useQueryClient();
  const cur = useQuery({ queryKey: ["hourly-rate"], queryFn: api.getHourlyRate });
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (cur.data?.rate != null) setRate(String(cur.data.rate)); }, [cur.data]);

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">💰 我的时薪</span>
        <span className="text-xs text-mut">成本报表用它把你的工时换算成成本（仅自己可见可改）</span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input type="number" min="0" step="0.5" value={rate} onChange={(e) => setRate(e.target.value)}
          placeholder="如：120" className="w-28 rounded-md border border-line bg-bg px-2 py-1 text-xs text-ink" />
        <Button size="sm" variant="outline" disabled={busy || rate === ""}
          onClick={async () => {
            setBusy(true);
            try {
              await api.setHourlyRate(Number(rate));
              toast.success("时薪已保存");
              await qc.invalidateQueries({ queryKey: ["hourly-rate"] });
            } catch (e) {
              toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
            } finally { setBusy(false); }
          }}>保存</Button>
        {cur.data?.rate == null && <span className="text-[10px] text-mut">未设置——成本报表里你的工时按 0 成本计</span>}
      </div>
    </Card>
  );
}

function TimeOffPanel() {
  const qc = useQueryClient();
  const offs = useQuery({ queryKey: ["time-off"], queryFn: api.listTimeOff });
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [delegate, setDelegate] = useState("");
  const [busy, setBusy] = useState(false);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["time-off"] });

  const add = async () => {
    if (!start || !end) return;
    setBusy(true);
    try {
      await api.addTimeOff(start, end, reason, delegate || undefined);
      toast.success("休假已登记");
      setStart(""); setEnd(""); setReason(""); setDelegate("");
      await invalidate();
    } catch (e) {
      toast.error(`登记失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (id: string) => {
    setBusy(true);
    try {
      await api.cancelTimeOff(id);
      toast.info("休假已取消");
      await invalidate();
    } catch (e) {
      toast.error(`取消失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const list = (offs.data?.time_off ?? []).filter((o) => !o.cancelled_at);

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">🏖 我的休假</span>
        <span className="text-xs text-mut">日期段登记 · 负载页与我的日程自动消费</span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
          className="rounded-md border border-line bg-bg px-2 py-1 text-xs text-ink" />
        <span className="text-xs text-mut">至</span>
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
          className="rounded-md border border-line bg-bg px-2 py-1 text-xs text-ink" />
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="原因（如：年假）"
          className="w-32 rounded-md border border-line bg-bg px-2 py-1 text-xs text-ink" />
        <input value={delegate} onChange={(e) => setDelegate(e.target.value)} placeholder="代理人（可选，用户 ID）"
          title="休假期间活跃任务将临时转给该同项目成员，结束后自动转回"
          className="w-40 rounded-md border border-line bg-bg px-2 py-1 text-xs text-ink" />
        <Button size="sm" variant="outline" disabled={busy || !start || !end} onClick={add}>登记休假</Button>
      </div>
      {list.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {list.map((o) => (
            <span key={o.id}
              className="inline-flex items-center gap-1 rounded-full border border-line bg-bg px-2 py-0.5 text-[10px] text-ink">
              🏖 {o.start_date} ~ {o.end_date}{o.reason ? ` · ${o.reason}` : ""}{o.delegate ? ` · 代理：${o.delegate}` : ""}
              <button disabled={busy} onClick={() => cancel(o.id)}
                className="text-mut hover:text-dan" title="取消">✕</button>
            </span>
          ))}
        </div>
      )}
      <div className="mt-1 text-[10px] text-mut">
        登记后负载页会在休假期间给你标「🏖 休假中」，「我的日程」月历也会叠加休假条；日期段重叠会被拒绝。
        填了代理人时，休假首日的每日扫描会把你的活跃任务临时转给TA（须与你同项目）、末日自动转回，全程留 item.assigned 审计。
      </div>
    </Card>
  );
}

/** I104: working calendar (OpenProject 12.3 semantics) — admin maintains
 *  global non-working days; auto-scheduled items skip them on landing. */
function CalendarPanel() {
  const qc = useQueryClient();
  const days = useQuery({ queryKey: ["holidays"], queryFn: api.listHolidays });
  const [day, setDay] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["holidays"] });

  const add = async () => {
    if (!day) return;
    setBusy(true);
    try {
      await api.addHoliday(day, note);
      toast.success(`已加入非工作日：${day}`);
      setDay(""); setNote("");
      await invalidate();
    } catch (e) {
      toast.error(`添加失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (d: string) => {
    setBusy(true);
    try {
      await api.removeHoliday(d);
      toast.info(`已移除非工作日：${d}`);
      await invalidate();
    } catch (e) {
      toast.error(`移除失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const list = days.data?.holidays ?? [];

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">📅 工作日历</span>
        <span className="text-xs text-mut">非工作日 · 自动排期落点顺延 · 手排期不受影响</span>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)}
          className="rounded-md border border-line bg-bg px-2 py-1 text-xs text-ink" />
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="备注（如：国庆节）"
          className="w-40 rounded-md border border-line bg-bg px-2 py-1 text-xs text-ink" />
        <Button size="sm" variant="outline" disabled={busy || !day} onClick={add}>加入非工作日</Button>
      </div>
      {list.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {list.map((h) => (
            <span key={h.date}
              className="inline-flex items-center gap-1 rounded-full border border-line bg-bg px-2 py-0.5 text-[10px] text-ink">
              {h.date}{h.note ? ` · ${h.note}` : ""}
              <button disabled={busy} onClick={() => remove(h.date)}
                className="text-mut hover:text-dan" title="移除">✕</button>
            </span>
          ))}
        </div>
      )}
      <div className="mt-1 text-[10px] text-mut">
        仅管理员可维护；auto_scheduled 任务的 start/due 落在周末或非工作日时顺延至下一个工作日，手动排期的任务完全不受影响。
      </div>
    </Card>
  );
}

function MembersPanel({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const [addId, setAddId] = useState("");
  const [addRole, setAddRole] = useState("contributor");
  const members = useQuery({
    queryKey: ["members", pid],
    queryFn: () => api.listMembers(pid),
  });
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const candidates = (users.data?.users ?? []).filter(
    (u) => !(members.data?.members ?? []).some((m) => m.user_id === u.id),
  );

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["members", pid] });
    qc.invalidateQueries({ queryKey: ["users"] });
  };

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">项目成员</span>
        <span className="text-xs text-mut">Owner 全权 · Contributor 读写 · Viewer 只读</span>
      </div>
      <div className="mt-3 space-y-1.5">
        {(members.data?.members ?? []).map((m) => {
          const rb = MEMBER_ROLE[m.role] ?? { label: m.role, tone: "neutral" as const };
          const muted = m.notify_level === "mentions_only";
          return (
            <div key={m.user_id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-xs">
              <span className="font-medium">{m.name || m.user_id}</span>
              <span className="font-mono text-[10px] text-mut">{m.user_id}</span>
              <Badge tone={rb.tone}>{rb.label}</Badge>
              <button
                title={muted ? "参与类通知已静音（提及/指派/审批/到期/关注规则照常）——点击恢复默认" : "将该成员在本项目的参与类通知静音（提及与审批照达）"}
                onClick={async () => {
                  await api.setMemberNotifyLevel(pid, m.user_id, muted ? null : "mentions_only");
                  invalidate();
                }}
                className={cx("rounded-md border px-1.5 py-0.5 text-[10px]",
                  muted ? "border-warn bg-warn/10 text-warn" : "border-line text-mut hover:text-ink")}>
                {muted ? "🔕 仅提及" : "🔔 默认"}
              </button>
              {m.role !== "owner" && (
                <span className="ml-auto flex gap-1">
                  {Object.entries(MEMBER_ROLE).filter(([r]) => r !== m.role).map(([r, def]) => (
                    <button key={r} onClick={async () => {
                      await api.changeMemberRole(pid, { user_id: m.user_id, role: r });
                      invalidate();
                    }} className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-ink">
                      → {def.label}
                    </button>
                  ))}
                  <button onClick={async () => {
                    await api.removeMember(pid, m.user_id);
                    invalidate();
                  }} className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-dan">移除</button>
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex items-center gap-1.5">
        <select value={addId} onChange={(e) => setAddId(e.target.value)}
          className="rounded-lg border border-line bg-surface px-2 py-1.5 text-xs">
          <option value="">添加用户…</option>
          {candidates.map((u) => (
            <option key={u.id} value={u.id}>{u.name}（{u.id}）</option>
          ))}
        </select>
        <select value={addRole} onChange={(e) => setAddRole(e.target.value)}
          className="rounded-lg border border-line bg-surface px-2 py-1.5 text-xs">
          {Object.entries(MEMBER_ROLE).map(([r, def]) => (
            <option key={r} value={r}>{def.label}</option>
          ))}
        </select>
        <Button size="sm" variant="outline" disabled={!addId} onClick={async () => {
          await api.addMember(pid, { user_id: addId, role: addRole });
          setAddId("");
          invalidate();
        }}>＋ 添加</Button>
      </div>
    </Card>
  );
}

const TRIGGER_LABEL: Record<string, string> = {
  "item.created": "创建工作项",
  "item.updated": "更新字段",
  "item.status_changed": "状态变更",
  "item.assigned": "指派变更",
  "schedule:daily": "每日扫描",
};
const PRIORITY_LABEL: Record<string, string> = { high: "高", medium: "中", low: "低" };
const ACTION_LABEL: Record<string, string> = {
  assign: "指派给", set_priority: "置优先级", set_field: "设自定义字段", set_status: "改状态",
  create_recurring: "每日建卡", run_agent: "🤖 让 Agent 执行",
};

function condSummary(r: { condition: { concept_id?: string; fields?: Record<string, unknown> } }): string {
  const parts: string[] = [];
  if (r.condition.concept_id) parts.push(r.condition.concept_id);
  for (const [k, v] of Object.entries(r.condition.fields ?? {})) parts.push(`${k}=${String(v)}`);
  return parts.length ? parts.join(" · ") : "无条件";
}

function actionSummary(a: AutomationRule["action"]): string {
  if (a.type === "assign") return `指派 → ${a.user_id}`;
  if (a.type === "set_priority") {
    const v = String(a.value ?? "");
    return `优先级 → ${PRIORITY_LABEL[v] ?? v}`;
  }
  if (a.type === "set_field") return `${a.field_id} → ${Array.isArray(a.value) ? a.value.join("、") : String(a.value)}`;
  if (a.type === "set_status") return `状态 → ${a.status}`;
  if (a.type === "create_recurring") return `每日建卡「${a.title}」`;
  if (a.type === "run_agent") return `🤖 ${a.agent_role} 执行`;
  return a.type;
}

/** Automation rules (M9-I30): trigger → condition → action, managed per project.
 *  Backend executes on the event stream (Kanboard bindings × n8n 三段式). */
function AutomationsPanel({ pid, concepts, agentRoles }: {
  pid: string;
  concepts: { id: string; name: string; states: { id: string; name: string; group: string }[]; fields?: { id: string; name: string; type: string; values?: (string | number)[] }[] }[];
  agentRoles: string[];
}) {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["automations", pid], queryFn: () => api.listAutomations(pid) });
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("item.created");
  const [conceptId, setConceptId] = useState("");
  const [condField, setCondField] = useState("");
  const [condValue, setCondValue] = useState("");
  const [actionType, setActionType] = useState("assign");
  const [actUserId, setActUserId] = useState("");
  const [actPriority, setActPriority] = useState("high");
  const [actFieldId, setActFieldId] = useState("");
  const [actFieldValue, setActFieldValue] = useState("");
  const [actStatus, setActStatus] = useState("");
  const [recTitle, setRecTitle] = useState("");
  // M63-I189: run_agent action inputs
  const [actRole, setActRole] = useState("");
  const [actInstruction, setActInstruction] = useState("");
  const [historyOf, setHistoryOf] = useState<string | null>(null);

  const declaredFields = new Map<string, { name: string; type: string; values?: (string | number)[] }>();
  for (const c of concepts)
    for (const f of c.fields ?? []) declaredFields.set(f.id, { name: f.name, type: f.type, values: f.values });
  const statusPool = conceptId
    ? (concepts.find((c) => c.id === conceptId)?.states ?? []).map((s) => s.id)
    : [...new Set(concepts.flatMap((c) => c.states.map((s) => s.id)))];
  const actField = declaredFields.get(actFieldId);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["automations", pid] });

  const buildPayload = () => {
    const condition: { concept_id?: string; fields?: Record<string, string> } = {};
    if (conceptId) condition.concept_id = conceptId;
    if (condField && condValue) condition.fields = { [condField]: condValue };
    let action: AutomationRule["action"] = { type: actionType };
    if (actionType === "assign") action.user_id = actUserId;
    if (actionType === "set_priority") action.value = actPriority;
    if (actionType === "set_field") {
      action.field_id = actFieldId;
      action.value = actField?.type === "multiselect"
        ? actFieldValue.split(/[,，]/).map((s) => s.trim()).filter(Boolean)  // 逗号分隔 → 字符串数组
        : actFieldValue;
    }
    if (actionType === "set_status") action.status = actStatus;
    if (actionType === "create_recurring") {
      action.concept_id = conceptId;
      action.title = recTitle;
    }
    if (actionType === "run_agent") {
      action.agent_role = actRole;
      action.instruction = actInstruction.trim();
    }
    return { name: name.trim(), trigger_event: trigger, condition, action };
  };

  const create = async () => {
    try {
      await api.createAutomation(pid, buildPayload());
      toast.success("规则已创建（事件溯源，可 rebuild）");
      setOpen(false);
      setName(""); setCondField(""); setCondValue(""); setActFieldValue("");
      await invalidate();
    } catch (e) {
      toast.error(`创建失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const runTest = async (ruleId: string) => {
    try {
      const r = await api.testAutomation(pid, ruleId);
      if (r.matched) toast.success(`命中「${r.item_title}」→ ${actionSummary(r.action!)}`);
      else toast.info(`未命中：${r.reason}`);
    } catch (e) {
      toast.error(`测试失败：${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">自动化规则</span>
        <span className="text-xs text-mut">触发 → 条件 → 动作 · 事件溯源 · 动作按 automation 归账</span>
        <Button size="sm" variant="ghost" className="ml-auto" title="立即强制运行每日扫描（转派/提醒即时生效）"
          onClick={async () => {
            try {
              const r = await api.sweepAutomations(true);
              if (r.swept) toast.success(`扫描完成：动作 ${r.fired} 次 · 建卡 ${r.created} 张 · 转派 ${r.delegated} 项`);
              else toast.info(`今日（${r.date}）已扫描过——心跳幂等`);
            } catch (e) {
              toast.error(`扫描失败：${e instanceof Error ? e.message : e}`);
            }
          }}>⟳ 手动扫描</Button>
        <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}>＋ 新建规则</Button>
      </div>

      <div className="mt-3 space-y-1.5">
        {(rules.data?.rules ?? []).map((r) => (
          <div key={r.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-xs">
            <span className={cx("font-medium", !r.enabled && "text-mut line-through")}>{r.name}</span>
            <Badge tone="violet">{TRIGGER_LABEL[r.trigger_event] ?? r.trigger_event}</Badge>
            <span className="text-[11px] text-mut">{condSummary(r)}</span>
            <span className="text-[11px] text-ink">→ {actionSummary(r.action)}</span>
            <span className="ml-auto flex items-center gap-1">
              <button onClick={() => runTest(r.id)}
                className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-ink">测试运行</button>
              <button onClick={() => setHistoryOf(r.id)}
                className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-ink">历史</button>
              <button onClick={async () => { await api.patchAutomation(pid, r.id, { enabled: !r.enabled }); invalidate(); }}
                className={cx("rounded-md border px-1.5 py-0.5 text-[10px]",
                  r.enabled ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink")}>
                {r.enabled ? "已启用" : "已停用"}
              </button>
              <button onClick={async () => { await api.deleteAutomation(pid, r.id); invalidate(); }}
                className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-dan">删除</button>
            </span>
          </div>
        ))}
        {!rules.data?.rules.length && <div className="px-1 py-1 text-xs text-mut">暂无规则——建一条，让 Agent 之外的生产线也自动转起来</div>}
      </div>

      {open && (
        <div className="mt-3 space-y-2 rounded-xl border border-line bg-bg p-3 text-xs">
          <div className="flex items-center gap-1.5">
            <Input className="flex-1" placeholder="规则名称（如：缺陷建卡即指派 QA）" value={name} onChange={(e) => setName(e.target.value)} />
            <select value={trigger} onChange={(e) => setTrigger(e.target.value)}
              className="rounded-lg border border-line bg-surface px-2 py-1.5">
              {Object.entries(TRIGGER_LABEL).map(([v, l]) => <option key={v} value={v}>当{l}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-1.5 text-mut">
            <span>满足</span>
            <select value={conceptId} onChange={(e) => { setConceptId(e.target.value); setActStatus(""); }}
              className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
              <option value="">任意概念</option>
              {concepts.map((c) => <option key={c.id} value={c.id}>{c.name}（{c.id}）</option>)}
            </select>
            <select value={condField} onChange={(e) => setCondField(e.target.value)}
              className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
              <option value="">无条件</option>
              {["priority", "status", "assignee_id", "overdue"].map((f) => <option key={f} value={f}>{f}</option>)}
              {[...declaredFields.keys()].map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            {condField && <Input className="w-28" placeholder="值" value={condValue} onChange={(e) => setCondValue(e.target.value)} />}
          </div>
          <div className="flex items-center gap-1.5 text-mut">
            <span>则</span>
            <select value={actionType} onChange={(e) => { setActionType(e.target.value); setActFieldValue(""); }}
              className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
              {Object.entries(ACTION_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            {actionType === "assign" && (
              <select value={actUserId} onChange={(e) => setActUserId(e.target.value)}
                className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
                <option value="">选择用户…</option>
                {(users.data?.users ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}（{u.id}）</option>)}
              </select>
            )}
            {actionType === "set_priority" && (
              <select value={actPriority} onChange={(e) => setActPriority(e.target.value)}
                className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
                {Object.entries(PRIORITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            )}
            {actionType === "set_field" && (
              <>
                <select value={actFieldId} onChange={(e) => { setActFieldId(e.target.value); setActFieldValue(""); }}
                  className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
                  <option value="">选择字段…</option>
                  {[...declaredFields.entries()].map(([f, spec]) => <option key={f} value={f}>{spec.name}（{f}）</option>)}
                </select>
                {actField?.type === "enum" && (
                  <select value={actFieldValue} onChange={(e) => setActFieldValue(e.target.value)}
                    className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
                    <option value="">值…</option>
                    {(actField.values ?? []).map((v) => <option key={String(v)} value={String(v)}>{String(v)}</option>)}
                  </select>
                )}
                {actField && actField.type !== "enum" && (
                  <Input className="w-28" placeholder={actField.type === "multiselect" ? "逗号分隔多值" : "值"}
                    value={actFieldValue} onChange={(e) => setActFieldValue(e.target.value)} />
                )}
              </>
            )}
            {actionType === "set_status" && (
              <select value={actStatus} onChange={(e) => setActStatus(e.target.value)}
                className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
                <option value="">状态…</option>
                {statusPool.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            )}
            {actionType === "create_recurring" && (
              <>
                <select value={conceptId} onChange={(e) => setConceptId(e.target.value)}
                  className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
                  <option value="">概念…</option>
                  {concepts.map((c) => <option key={c.id} value={c.id}>{c.name}（{c.id}）</option>)}
                </select>
                <Input className="w-36" placeholder="每日卡片标题" value={recTitle} onChange={(e) => setRecTitle(e.target.value)} />
              </>
            )}
            {actionType === "run_agent" && (
              <>
                <select value={actRole} onChange={(e) => setActRole(e.target.value)}
                  className="rounded-lg border border-line bg-surface px-2 py-1.5 text-ink">
                  <option value="">角色…</option>
                  {agentRoles.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
                <Input className="w-64" placeholder="给 Agent 的指令（≤200 字）" maxLength={200}
                  value={actInstruction} onChange={(e) => setActInstruction(e.target.value)} />
                <span className="text-[10px] text-mut" title="触发时对命中工作项起真实 run；Gate/审批照走；每规则每日 ≤3 次防失控">
                  触发即起 run · Gate 照走 · 日上限 3
                </span>
              </>
            )}
            <Button size="sm" className="ml-auto" disabled={!name.trim() || (actionType === "assign" && !actUserId) || (actionType === "set_field" && (!actFieldId || !actFieldValue)) || (actionType === "set_status" && !actStatus) || (actionType === "create_recurring" && (!conceptId || !recTitle.trim())) || (actionType === "run_agent" && (!actRole || !actInstruction.trim()))} onClick={create}>
              创建规则
            </Button>
          </div>
        </div>
      )}

      <Modal open={!!historyOf} onClose={() => setHistoryOf(null)} title="规则触发历史">
        <RuleHistory pid={pid} ruleId={historyOf!} />
      </Modal>
    </Card>
  );
}

function RuleHistory({ pid, ruleId }: { pid: string; ruleId: string }) {
  const runs = useQuery({
    queryKey: ["automation-runs", pid, ruleId],
    queryFn: () => api.automationHistory(pid, ruleId),
  });
  const list = runs.data?.runs ?? [];
  if (!list.length) return <div className="p-2 text-xs text-mut">还没有触发记录——命中条件的事件发生时会在这里留痕</div>;
  return (
    <div className="space-y-1.5 text-xs">
      {list.map((r) => (
        <div key={r.event_id} className="rounded-lg border border-line px-3 py-1.5">
          <div className="flex items-center gap-2">
            <span className={cx("font-medium", r.result.ok ? "text-acc" : "text-dan")}>#{r.event_id}</span>
            <span className="text-mut">{new Date(r.ts).toLocaleString()}</span>
            <Badge tone={r.result.ok ? "green" : "red"}>{r.result.ok ? "已执行" : "被拒绝"}</Badge>
          </div>
          <div className="mt-0.5 text-mut">
            「{r.item_title}」{TRIGGER_LABEL[r.trigger_event] ?? r.trigger_event} → {r.result.detail}
          </div>
        </div>
      ))}
    </div>
  );
}

const WEBHOOK_EVENTS = [
  "item.created", "item.updated", "item.status_changed", "item.assigned",
  "approval.requested", "approval.granted", "approval.rejected",
  "feature.created", "automation.rule_fired",
];

/** Outbound webhooks (M10-I33): signed event push — config, secret rotation,
 *  delivery history, manual replay, test ping. */
function WebhooksPanel({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const hooks = useQuery({ queryKey: ["webhooks", pid], queryFn: () => api.listWebhooks(pid) });
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [evs, setEvs] = useState<Set<string>>(new Set());
  const [secretOnce, setSecretOnce] = useState<string | null>(null);
  const [historyOf, setHistoryOf] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["webhooks", pid] });

  const create = async () => {
    try {
      const wh = await api.createWebhook(pid, { url: url.trim(), events: [...evs] });
      setSecretOnce(wh.secret ?? null);
      setUrl("");
      setEvs(new Set());
      setOpen(false);
      await invalidate();
      toast.success("Webhook 已创建——secret 仅此一次展示，请立即保存");
    } catch (e) {
      toast.error(`创建失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const rotate = async (id: string) => {
    try {
      const r = await api.rotateWebhookSecret(pid, id);
      setSecretOnce(r.secret);
      await invalidate();
    } catch (e) {
      toast.error(`换发失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const ping = async (id: string) => {
    try {
      const r = await api.pingWebhook(pid, id);
      r.status_code && r.status_code < 300
        ? toast.success(`Ping 成功（HTTP ${r.status_code}，${r.duration_ms}ms）`)
        : toast.error(`Ping 失败：${r.error ?? `HTTP ${r.status_code}`}`);
      await qc.invalidateQueries({ queryKey: ["webhook-deliveries", pid, id] });
    } catch (e) {
      toast.error(`Ping 失败：${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">Webhooks 出站</span>
        <span className="text-xs text-mut">事件推送 · HMAC-SHA256 签名 · 投递留痕可重发</span>
        <Button size="sm" variant="outline" className="ml-auto" onClick={() => setOpen((v) => !v)}>＋ 新建 Webhook</Button>
      </div>

      <div className="mt-3 space-y-1.5">
        {(hooks.data?.webhooks ?? []).map((w) => (
          <div key={w.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-xs">
            <span className={cx("font-mono", !w.enabled && "text-mut line-through")}>{w.url}</span>
            <span className="text-[10px] text-mut">{w.events.length} 类事件</span>
            {!w.has_secret && <Badge tone="amber">secret 已失效（rebuild 后需 rotate）</Badge>}
            <span className="ml-auto flex items-center gap-1">
              <button onClick={() => ping(w.id)}
                className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-ink">Ping</button>
              <button onClick={() => setHistoryOf(w.id)}
                className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-ink">投递历史</button>
              <button onClick={() => rotate(w.id)}
                className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-ink">换发 secret</button>
              <button onClick={async () => { await api.patchWebhook(pid, w.id, { enabled: !w.enabled }); invalidate(); }}
                className={cx("rounded-md border px-1.5 py-0.5 text-[10px]",
                  w.enabled ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink")}>
                {w.enabled ? "已启用" : "已停用"}
              </button>
              <button onClick={async () => { await api.deleteWebhook(pid, w.id); invalidate(); }}
                className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-dan">删除</button>
            </span>
          </div>
        ))}
        {!hooks.data?.webhooks.length && <div className="px-1 py-1 text-xs text-mut">还没有出站 webhook——把项目事件推给 IM 机器人、CI 或任意接收端</div>}
      </div>

      {open && (
        <div className="mt-3 space-y-2 rounded-xl border border-line bg-bg p-3 text-xs">
          <Input placeholder="接收端 URL（http/https）" value={url} onChange={(e) => setUrl(e.target.value)} />
          <div className="flex flex-wrap gap-1">
            {WEBHOOK_EVENTS.map((ev) => {
              const on = evs.has(ev);
              return (
                <button key={ev} onClick={() => {
                  const next = new Set(evs);
                  on ? next.delete(ev) : next.add(ev);
                  setEvs(next);
                }}
                  className={cx("rounded-full border px-2 py-0.5 text-[11px]",
                    on ? "border-acc bg-accbg text-acc" : "border-line text-mut hover:text-ink")}>
                  {ev}
                </button>
              );
            })}
          </div>
          <div className="flex justify-end">
            <Button size="sm" disabled={!url.trim() || !evs.size} onClick={create}>创建 Webhook</Button>
          </div>
        </div>
      )}

      <Modal open={!!secretOnce} onClose={() => setSecretOnce(null)} title="Webhook secret（仅此一次展示）">
        <div className="space-y-2 text-xs">
          <p className="text-mut">接收方以此 secret 对原始请求体做 HMAC-SHA256 验签（X-APM-Signature）。关闭后无法再查看，只能换发新的。</p>
          <pre className="overflow-auto rounded-lg border border-line bg-bg px-3 py-2 font-mono">{secretOnce}</pre>
        </div>
      </Modal>

      <Modal open={!!historyOf} onClose={() => setHistoryOf(null)} title="投递历史">
        <DeliveryHistory pid={pid} hookId={historyOf!} />
      </Modal>
    </Card>
  );
}

function DeliveryHistory({ pid, hookId }: { pid: string; hookId: string }) {
  const qc = useQueryClient();
  const deliveries = useQuery({
    queryKey: ["webhook-deliveries", pid, hookId],
    queryFn: () => api.listEvents({ project_id: pid, agg_type: "webhook", agg_id: hookId, limit: 50 }),
  });
  const rows = (deliveries.data?.events ?? [])
    .filter((e) => e.event_type === "webhook.delivered" || e.event_type === "webhook.delivery_failed");
  const [busy, setBusy] = useState<string | null>(null);

  const replay = async (deliveryId: string) => {
    setBusy(deliveryId);
    try {
      const r = await api.replayWebhookDelivery(pid, hookId, deliveryId);
      r.status_code && r.status_code < 300
        ? toast.success(`重发成功（HTTP ${r.status_code}）`)
        : toast.error(`重发失败：${r.error ?? `HTTP ${r.status_code}`}`);
      await qc.invalidateQueries({ queryKey: ["webhook-deliveries", pid, hookId] });
    } catch (e) {
      toast.error(`重发失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(null);
    }
  };

  if (!rows.length) return <div className="p-2 text-xs text-mut">还没有投递记录——命中订阅事件后这里会留痕</div>;
  return (
    <div className="space-y-1.5 text-xs">
      {rows.map((e) => {
        const p = e.payload as unknown as DeliveryRecord;
        const ok = e.event_type === "webhook.delivered";
        return (
          <div key={e.id} className="rounded-lg border border-line px-3 py-1.5">
            <div className="flex items-center gap-2">
              <Badge tone={ok ? "green" : "red"}>{ok ? "已送达" : "失败"}</Badge>
              <span className="font-mono text-[10px] text-mut">{p.delivery_id}</span>
              <span className="text-mut">{p.event_type}{p.event_type === "ping" ? "" : ` → #${p.event_id}`}</span>
              <span className="ml-auto text-mut">
                {p.status_code != null ? `HTTP ${p.status_code} · ` : ""}{p.attempts} 次{p.duration_ms != null ? ` · ${p.duration_ms}ms` : ""}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              {!ok && p.error && <span className="text-[11px] text-dan">{p.error}</span>}
              <button disabled={busy === p.delivery_id} onClick={() => replay(p.delivery_id)}
                className="ml-auto rounded-md border border-line px-1.5 py-0.5 text-[10px] text-mut hover:text-ink">
                重发
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function libIcon(id: string) {
  return { product: "📦", test: "🧪", doc: "📚" }[id] ?? "🗃️";
}

const KIND_TONE: Record<string, string> = {
  add_field: "indigo", add_relation: "amber", wire_deposit: "violet", add_role: "green",
};

const SOURCE_LABEL: Record<string, string> = {
  items: "工作项", relations: "关系", approvals: "审批", assets: "资产",
  runs: "Agent 运行", events: "事件流", artifacts: "内容仓工件",
};

const CQ_STATUS: Record<string, { label: string; tone: string }> = {
  answerable: { label: "可回答", tone: "green" },
  no_data: { label: "缺数据", tone: "amber" },
  unmapped: { label: "缺映射", tone: "neutral" },
};

const allAnswerable = (c: { questions: { status: string }[] }) =>
  c.questions.every((q) => q.status === "answerable");

function CqStatusBadge({ status }: { status: string }) {
  const s = CQ_STATUS[status] ?? { label: status, tone: "neutral" };
  return <Badge tone={s.tone as never}>{s.label}</Badge>;
}

/** Version timeline + semantic diff with data impact analysis (M4-I15). */
function VersionPanel({
  currentVersion, history, diff, diffing, onDiff,
}: {
  currentVersion: number;
  history?: { current_version: number; snapshots: number[]; history: { event_id: number; ts: string; previous_version: number; version: number; applied_count: number; applied: { id: string; kind: string; summary: string }[]; summary: string }[] };
  diff: OntologyDiff | null; diffing: boolean;
  onDiff: (fromV: number, toV?: number) => void;
}) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">◷ 版本与影响分析</span>
        <Badge tone="neutral">v{currentVersion} · 快照 {history?.snapshots.length ?? 0} 份</Badge>
        <span className="ml-auto text-[11px] text-mut">semantica VersionManager 轻量版（docs/08 §8.1）</span>
      </div>
      {history && history.history.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {history.history.map((h) => (
            <div key={h.event_id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-bg px-3 py-1.5">
              <span className="font-mono text-[11px] text-mut">v{h.previous_version} → v{h.version}</span>
              <span className="text-xs text-ink">{h.summary}</span>
              {h.applied.slice(0, 3).map((a) => (
                <Badge key={a.id} tone={(KIND_TONE[a.kind] ?? "neutral") as never}>
                  {a.kind}
                </Badge>
              ))}
              {h.applied.length > 3 && <span className="text-[10px] text-mut">+{h.applied.length - 3}</span>}
              <Button size="sm" variant="ghost" className="ml-auto" disabled={diffing}
                      onClick={() => onDiff(h.previous_version, h.version)}>
                对比
              </Button>
            </div>
          ))}
        </div>
      )}
      {history && history.history.length === 0 && (
        <p className="mt-2 text-xs text-mut">
          尚无版本事件——在本体学习中应用候选后，这里会出现版本时间线；也可对磁盘上的手工改动做影响分析。
        </p>
      )}
      {diff && <DiffView d={diff} />}
    </Card>
  );
}

function DiffView({ d }: { d: OntologyDiff }) {
  const g = d.diff;
  const chip = (label: string, removed = false) => (
    <span key={label}
          className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${removed ? "bg-danbg text-dan" : "bg-okbg text-ok"}`}>
      {removed ? "−" : "+"}{label}
    </span>
  );
  return (
    <div className="mt-3 space-y-2 border-t border-line pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold">v{d.from_version} → v{d.to_version} 语义 diff</span>
        <span className="text-[11px] text-mut">{d.summary}</span>
      </div>
      {(g.concepts.added.length > 0 || g.concepts.removed.length > 0) && (
        <div className="flex flex-wrap items-center gap-1 text-xs">
          <span className="text-mut">概念：</span>
          {g.concepts.added.map((c) => chip(c.name || c.id))}
          {g.concepts.removed.map((c) => chip(c.name || c.id, true))}
        </div>
      )}
      {g.concepts.modified.map((m) => (
        <div key={m.id} className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-1.5 text-xs">
          <span className="font-medium">~ {m.name}</span>
          {m.changes.map((c, i) => (
            <span key={i} className="ml-2 font-mono text-[10px] text-warn">{c.type}:{c.detail}</span>
          ))}
        </div>
      ))}
      {(["relations", "phases", "asset_kinds"] as const).map((k) => {
        const label = { relations: "关系", phases: "阶段", asset_kinds: "资产类型" }[k];
        return (g[k].added.length > 0 || g[k].removed.length > 0) ? (
          <div key={k} className="flex flex-wrap items-center gap-1 text-xs">
            <span className="text-mut">{label}：</span>
            {g[k].added.map((c) => chip(c.name || c.id))}
            {g[k].removed.map((c) => chip(c.name || c.id, true))}
          </div>
        ) : null;
      })}
      {d.impact.blocking.length > 0 && (
        <div className="space-y-1">
          {d.impact.blocking.map((b, i) => (
            <div key={i} className="rounded-lg border border-dan/40 bg-danbg px-3 py-1.5 text-xs text-dan">
              ⛔ {b.detail}
              {b.sample_items?.map((s) => (
                <span key={s.id} className="ml-2 font-mono text-[10px] text-mut">{s.title}</span>
              ))}
            </div>
          ))}
        </div>
      )}
      {d.impact.warnings.length > 0 && (
        <div className="rounded-lg border border-dashed border-line px-3 py-1.5 text-[11px] text-mut">
          {d.impact.warnings.map((w, i) => <div key={i}>· {w.detail}</div>)}
        </div>
      )}
      {d.to_validation_errors.length > 0 && (
        <div className="rounded-lg border border-warn/40 bg-warnbg px-3 py-1.5 text-[11px] text-warn">
          当前文件校验问题：{d.to_validation_errors.join("；")}
        </div>
      )}
    </div>
  );
}

const RULE_META: Record<string, { label: string; tone: string }> = {
  "L1-add-field": { label: "字段显式化", tone: "indigo" },
  "L2-register-relation": { label: "关系补注册", tone: "amber" },
  "L3-wire-deposit": { label: "沉淀链接补全", tone: "violet" },
  "L4-add-role": { label: "角色覆盖", tone: "green" },
  "LLM-curate": { label: "LLM 建议", tone: "violet" },
};

/** Ontology-learning panel (semantica 模式)：pattern 扫描 / LLM 建议 → review → apply. */
function LearnPanel({
  scan, scanning, applying, selected, onLearn, onLearnLlm, onApply, onToggle,
}: {
  scan: OntologyLearnResult | null; scanning: boolean; applying: boolean;
  selected: Set<string>;
  onLearn: () => void; onLearnLlm: () => void; onApply: () => void; onToggle: (id: string) => void;
}) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">🔬 本体学习</span>
        <Badge tone="neutral">semantica 模式 · 从数据归纳</Badge>
        <span className="ml-auto flex items-center gap-2">
          {scan && (
            <span className="font-mono text-[11px] text-mut">
              扫描 {scan.scanned.projects} 项目 · {scan.scanned.items} 工作项 · {scan.scanned.relations} 关系 · {scan.scanned.artifact_links} 资产链接
            </span>
          )}
          <Button size="sm" variant="outline" disabled={scanning || applying} onClick={onLearn}>
            {scanning ? "扫描中…" : scan ? "重新扫描" : "扫描项目数据"}
          </Button>
          <Button size="sm" variant="outline" disabled={scanning || applying} onClick={onLearnLlm}>
            ✨ LLM 建议
          </Button>
          {scan && scan.candidates.length > 0 && (
            <Button size="sm" variant="primary" disabled={applying || !selected.size} onClick={onApply}>
              {applying ? "应用中…" : `应用选中（${selected.size}）`}
            </Button>
          )}
        </span>
      </div>
      {scan?.llm && (
        <div className="mt-2 font-mono text-[10px] text-mut">
          LLM 层（{scan.llm.provider_mode}）：原始 {scan.llm.raw} · 接受 {scan.llm.accepted} · 与 pattern 层合并 {scan.llm.merged} · 低置信丢弃 {scan.llm.dropped_low_confidence}
          {scan.llm.error ? ` · 降级：${scan.llm.error}` : ""}
        </div>
      )}
      {scan && (
        <div className="mt-3 space-y-2">
          {scan.candidates.map((c) => {
            const rule = RULE_META[c.provenance.rule] ?? { label: c.provenance.rule, tone: "neutral" };
            return (
              <label key={c.id} className="flex cursor-pointer items-start gap-2 rounded-lg border border-line bg-bg px-3 py-2">
                <input
                  type="checkbox" className="mt-1 accent-indigo-500"
                  checked={selected.has(c.id)} onChange={() => onToggle(c.id)}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={rule.tone as never}>{rule.label}</Badge>
                    {c.provenance.channels?.includes("llm") && (
                      <Badge tone="violet">LLM{c.provenance.confidence != null ? ` · ${c.provenance.confidence}` : ""}</Badge>
                    )}
                    <span className="text-xs text-ink">{c.summary}</span>
                  </span>
                  <span className="mt-1 block font-mono text-[10px] text-mut">
                    {c.provenance.rule} · support {c.provenance.support}
                    {c.provenance.channels?.length ? ` · 通道 ${c.provenance.channels.join("+")}` : ""}
                    {c.provenance.sample_item_ids?.length ? ` · 样本 ${c.provenance.sample_item_ids.join(", ")}` : ""}
                    {c.provenance.sample_run_ids?.length ? ` · runs ${c.provenance.sample_run_ids.join(", ")}` : ""}
                    {c.provenance.sample_asset_ids?.length ? ` · assets ${c.provenance.sample_asset_ids.join(", ")}` : ""}
                  </span>
                  {c.provenance.llm_rationale && (
                    <span className="mt-0.5 block text-[10px] text-mut">💬 {c.provenance.llm_rationale}</span>
                  )}
                </span>
              </label>
            );
          })}
          {!scan.candidates.length && (
            <div className="rounded-lg border border-line bg-bg px-3 py-2 text-xs text-mut">
              未发现可执行的变更候选。
            </div>
          )}
          {scan.observations.unused_concepts.length > 0 && (
            <div className="rounded-lg border border-dashed border-line px-3 py-2 text-[11px] text-mut">
              观察（不参与应用）：以下概念在本体覆盖的所有项目中零使用，可考虑精简 —— {scan.observations.unused_concepts.join("、")}
            </div>
          )}
        </div>
      )}
      {!scan && (
        <p className="mt-2 text-xs text-mut">
          扫描该本体下所有项目的实际数据（字段使用、遗留关系、资产沉淀、角色执行），
          生成带 provenance 的变更候选；勾选并应用后本体 YAML 版本 +1 并落审计事件。
        </p>
      )}
    </Card>
  );
}

/** M67-I201 (docs/01 §BL.1): two-level concept visibility — toggling a concept
 * to owner-only hides that work-item type from non-owner members across the
 * board/list/search/write faces; undeclared concepts stay fully visible. */
function ConceptVisibilityPanel({ pid, concepts }: {
  pid: string;
  concepts: { id: string; name: string; icon: string }[];
}) {
  const qc = useQueryClient();
  const project = useQuery({ queryKey: ["project", pid], queryFn: () => api.getProject(pid) });
  const cv: Record<string, string> = project.data?.concept_visibility ?? {};
  const toggle = async (conceptId: string) => {
    const next = { ...cv };
    if (next[conceptId]) delete next[conceptId];
    else next[conceptId] = "owner";
    try {
      await api.patchProject(pid, { concept_visibility: next });
      toast.success(next[conceptId] ? "已设为仅 Owner 可见" : "已恢复全员可见");
      qc.invalidateQueries();
    } catch (e) {
      toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
    }
  };
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-semibold">🙈 概念可见性</span>
        <span className="text-xs text-mut">
          声明为「仅 Owner」的概念：非 Owner 成员在看板/列表/搜索/导出中不可见、写入 403、参与通知静默（mention/审批/watch 仍送达）
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {concepts.map((c) => {
          const restricted = !!cv[c.id];
          return (
            <button key={c.id} onClick={() => toggle(c.id)}
              title={restricted ? "点击恢复全员可见" : "点击设为仅 Owner 可见"}
              className={cx(
                "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs",
                restricted ? "border-dan bg-danbg font-medium text-dan" : "border-line text-mut hover:text-ink",
              )}>
              <span>{c.icon}</span> {c.name}
              {restricted && <span>🔒 仅 Owner</span>}
            </button>
          );
        })}
      </div>
    </Card>
  );
}
