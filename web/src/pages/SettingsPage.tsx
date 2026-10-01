/** Settings hub (I211, docs/01 §BO.2): hybrid IA — low-frequency,
 * high-consequence settings get one findable place; complex panels stay in
 * their working context and the hub deep-links to them (single source of
 * truth preserved, zero backend changes, zero regression on the source
 * pages). Simple toggles (auto-deposit, cost budget) are editable inline. */
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Badge, Button, Card, cx } from "../components/ui";
import { SETTINGS_SECTIONS, budgetOk } from "../lib/settings";

export function SettingsPage() {
  const { pid } = useParams();
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const project = useQuery({
    queryKey: ["project", pid],
    queryFn: () => api.getProject(pid!),
    enabled: !!pid,
  });
  const tokens = useQuery({
    queryKey: ["tokens"],
    queryFn: () => api.listTokens(),
  });
  const push = useQuery({
    queryKey: ["push-config"],
    queryFn: () => api.getPushConfig(),
  });
  // ?section= 深链 → 滚动定位 + 高亮
  const section = params.get("section") ?? "";
  useEffect(() => {
    if (!section) return;
    document.getElementById(`sec-${section}`)?.scrollIntoView({ block: "start" });
  }, [section]);

  const [budget, setBudget] = useState<string | null>(null);
  const p = project.data;
  useEffect(() => {
    if (p && budget === null) setBudget(p.cost_budget_usd != null ? String(p.cost_budget_usd) : "");
  }, [p, budget]);

  if (!p) return <div className="p-8 text-sm text-mut">加载设置…</div>;

  const patch = async (body: Record<string, unknown>, ok: string) => {
    try {
      await api.patchProject(pid!, body);
      toast.success(ok);
      qc.invalidateQueries({ queryKey: ["project", pid] });
    } catch (e) {
      toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const autoDeposit = !!p.auto_deposit;
  const restricted = Object.entries(p.concept_visibility ?? {}).filter(([, v]) => v === "owner");
  const tpl = p.report_template?.sections ?? [];
  return (
    <div className="flex h-full overflow-y-auto">
      {/* 左栏分区导航（I232：375px 下收窄避挤压） */}
      <div className="w-32 shrink-0 border-r border-line p-3 sm:w-52">
        <div className="mb-2 px-2 text-sm font-semibold">⚙ 项目设置</div>
        <div className="space-y-0.5">
          {SETTINGS_SECTIONS.map((s) => (
            <a key={s.id} href={`#/p/${pid}/settings?section=${s.id}`}
              className={cx("block rounded-lg px-2 py-1.5 text-xs hover:bg-bg", section === s.id && "bg-accbg text-acc")}>
              <span className="whitespace-nowrap">{s.icon} {s.label}</span>
              <div className="text-[10px] text-mut">{s.hint}</div>
            </a>
          ))}
        </div>
      </div>
      <div className="min-w-0 flex-1 space-y-4 p-4">
        {/* ⚙ 项目配置 */}
        <section id="sec-project" className="space-y-3">
          <h2 className="text-sm font-semibold">⚙ 项目配置</h2>
          <Card className="space-y-3 p-3 text-xs">
            <label className="flex flex-wrap items-start gap-2">
              <input type="checkbox" className="mt-0.5" checked={autoDeposit}
                onChange={(e) => patch({ auto_deposit: e.target.checked }, e.target.checked ? "产物自动沉淀已开启" : "产物自动沉淀已关闭")} />
              <span className="whitespace-nowrap font-medium">产物自动沉淀</span>
              <span className="text-mut">run 成功且产出工件时自动存入资产库（draft，评审门不绕过）</span>
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <span className="whitespace-nowrap font-medium">LLM 月度成本预算（USD）</span>
              <input value={budget ?? ""} onChange={(e) => setBudget(e.target.value)}
                placeholder="空 = 不设预算"
                className={cx("w-28 rounded-lg border bg-bg px-2 py-1", budget && !budgetOk(budget) ? "border-dan" : "border-line")} />
              <Button size="sm" variant="outline" disabled={budget === null || !budgetOk(budget)}
                onClick={() => patch({ cost_budget_usd: budget!.trim() === "" ? null : Number(budget) }, "成本预算已保存")}>
                保存
              </Button>
              <span className="text-mut">达 80% 警告（软阈），100% 拦截新 run（硬顶 402）</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="whitespace-nowrap font-medium">报告模板</span>
              {tpl.length
                ? <span className="text-mut">{tpl.filter((s) => s.enabled).length}/{tpl.length} 段启用{tpl.some((s) => s.heading) ? " · 含自定义标题" : ""}</span>
                : <Badge tone="neutral">默认骨架</Badge>}
              <Link className="text-acc hover:underline" to={`/p/${pid}/reports`}>去报告页配置 →</Link>
            </div>
          </Card>
        </section>

        {/* 🔒 权限与可见性 */}
        <section id="sec-access" className="space-y-3">
          <h2 className="text-sm font-semibold">🔒 权限与可见性</h2>
          <Card className="space-y-2 p-3 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="whitespace-nowrap font-medium">概念级可见性</span>
              {restricted.length
                ? <Badge tone="amber">🔒 {restricted.length} 个概念仅 owner 可见</Badge>
                : <Badge tone="green">全部概念成员可见</Badge>}
              <Link className="text-acc hover:underline" to={`/p/${pid}/ontology?section=visibility`}>去本体页配置 →</Link>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="whitespace-nowrap font-medium">项目角色指令（L1.5）</span>
              <span className="text-mut">按 project×role 细化全局角色提示词（深层优先）</span>
              <Link className="text-acc hover:underline" to={`/p/${pid}/ontology?section=roles`}>去本体页配置 →</Link>
            </div>
          </Card>
        </section>

        {/* 🔔 通知与接入 */}
        <section id="sec-notify" className="space-y-3">
          <h2 className="text-sm font-semibold">🔔 通知与接入</h2>
          <Card className="space-y-2 p-3 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="whitespace-nowrap font-medium">推送通道（ntfy）</span>
              {push.data?.push_url
                ? <Badge tone="green">已配置 {new URL(push.data.push_url).host}</Badge>
                : <Badge tone="neutral">未配置</Badge>}
              <Link className="text-acc hover:underline" to="/my/work">去我的工作台配置 →</Link>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="whitespace-nowrap font-medium">机器接入令牌（PAT）</span>
              <Badge tone="indigo">{tokens.data?.tokens?.length ?? 0} 个有效</Badge>
              <Link className="text-acc hover:underline" to="/my/work">去我的工作台管理 →</Link>
            </div>
          </Card>
        </section>

        {/* 👁 看板偏好 */}
        <section id="sec-board" className="space-y-3">
          <h2 className="text-sm font-semibold">👁 看板偏好</h2>
          <Card className="p-3 text-xs">
            <div className="text-mut">
              WIP 上限、泳道与保存的视图是看板的现场控制（使用即配）——
              <Link className="text-acc underline hover:no-underline" to={`/p/${pid}/board`}>去看板 →</Link>
            </div>
          </Card>
        </section>
      </div>
    </div>
  );
}
