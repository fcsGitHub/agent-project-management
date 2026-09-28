/** I211: settings-hub helpers — pure logic extracted so the hub page's
 * decisions are unit-testable without a component test environment. */

/** 左栏分区（混合 IA：hub 收纳 + 场景深链，复杂面板留在使用现场）。 */
export const SETTINGS_SECTIONS = [
  { id: "project", label: "项目配置", icon: "⚙", hint: "自动沉淀 / 成本预算 / 报告模板" },
  { id: "access", label: "权限与可见性", icon: "🔒", hint: "概念可见性 / 项目角色指令" },
  { id: "notify", label: "通知与接入", icon: "🔔", hint: "推送 / 机器接入令牌" },
  { id: "board", label: "看板偏好", icon: "👁", hint: "WIP / 泳道 / 保存的视图" },
] as const;

/** 成本预算输入校验：空 = 关闭预算（合法），否则须为非负有限数。 */
export function budgetOk(v: string): boolean {
  if (v.trim() === "") return true;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0;
}
