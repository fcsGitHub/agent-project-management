/** M116-I353/I354（docs/01 §DG）：TeamPage 回归锁——①目录渲染（三源合并的
 * 声明面+治理面+统计面都上卡）②治理动作（暂停按钮调 api 并在失效后显示
 * 已暂停态）③非管理员只读（无治理按钮）。 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiStub } = vi.hoisted(() => ({ apiStub: {} as Record<string, ReturnType<typeof vi.fn>> }));

vi.mock("../lib/api", () => ({
  API_BASE: "http://test",
  api: new Proxy(apiStub, {
    get: (t, k) => t[k as string] ?? (t[k as string] = vi.fn().mockResolvedValue(undefined)),
  }),
}));
vi.mock("sonner", () => ({
  toast: Object.fromEntries(["success", "error", "info", "promise"].map((m) => [m, vi.fn()])),
}));

import { api } from "../lib/api";
import { TeamPage } from "./TeamPage";

const AGENTS = {
  agents: [
    { id: "dev-agent", display_name: "开发 Agent", tier: "standard", model: "m",
      concepts: ["task", "bug"], tools: ["read_artifact"],
      status: "active", budget_usd: null,
      stats: { total_runs: 4, succeeded: 3, failed: 1, active_runs: 2,
        last_started_at: "2026-10-06T09:00:00Z", total_tokens: 1200,
        estimated_cost_usd: 0.42, month_cost_usd: 0.12 } },
    { id: "qa-agent", display_name: "测试 Agent", tier: "cheap", model: "m2",
      concepts: [], tools: [],
      status: "paused", budget_usd: 5,
      stats: { total_runs: 0, succeeded: 0, failed: 0, active_runs: 0,
        last_started_at: null, total_tokens: 0,
        estimated_cost_usd: 0, month_cost_usd: 0 } },
  ],
};

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TeamPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  (api.listAgents as ReturnType<typeof vi.fn>).mockResolvedValue(AGENTS);
  (api.authMe as ReturnType<typeof vi.fn>).mockResolvedValue({ user_id: "u_admin", is_admin: true });
});

afterEach(cleanup);

describe("TeamPage（M116）", () => {
  it("渲染三源合并的团队目录卡（声明面+统计面+治理态）", async () => {
    mount();
    expect(await screen.findByText("开发 Agent")).toBeTruthy();
    expect(screen.getByText("qa-agent")).toBeTruthy();
    // 运行态徽标 ×2 与 已暂停
    expect(screen.getByText("▶ 运行中 ×2")).toBeTruthy();
    expect(screen.getByText("⏸ 已暂停")).toBeTruthy();
    // 统计面：成功率（3/4=75%）与累计成本
    expect(screen.getByText("75%")).toBeTruthy();
    expect(screen.getByText("$0.42")).toBeTruthy();
  });

  it("管理员暂停动作调 api 并在失效后翻转为已暂停", async () => {
    (api.pauseAgent as ReturnType<typeof vi.fn>).mockResolvedValue({ role_id: "dev-agent", status: "paused" });
    mount();
    const btn = await screen.findByRole("button", { name: "⏸ 暂停" });
    fireEvent.click(btn);
    await waitFor(() => expect(api.pauseAgent).toHaveBeenCalledWith("dev-agent"));
    // 失效后重取 → 治理态翻转
    (api.listAgents as ReturnType<typeof vi.fn>).mockResolvedValue({
      agents: [{ ...AGENTS.agents[0], status: "paused", stats: { ...AGENTS.agents[0].stats, active_runs: 0 } }],
    });
    await waitFor(() => expect(screen.getByText("⏸ 已暂停")).toBeTruthy());
  });

  it("非管理员只读——无治理按钮、无设预算入口", async () => {
    (api.authMe as ReturnType<typeof vi.fn>).mockResolvedValue({ user_id: "u_x", is_admin: false });
    mount();
    await screen.findByText("开发 Agent");
    expect(screen.queryByRole("button", { name: "⏸ 暂停" })).toBeNull();
    expect(screen.queryByText("设预算")).toBeNull();
    // 预算读面仍在（qa 卡：本月 $0.00 / 预算 $5.00）
    expect(screen.getByText("$5.00")).toBeTruthy();
  });
});
