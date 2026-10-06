/** M115-I344 活动流组件回归锁（docs/01 §DF）：item.updated 的 `_old` 渲染
 * 「从 A 改为 B」、item.assigned 的 from 侧、未知事件类型兜底不炸。 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiStub } = vi.hoisted(() => ({ apiStub: {} as Record<string, ReturnType<typeof vi.fn>> }));

vi.mock("../lib/api", () => ({
  API_BASE: "http://test",
  api: new Proxy(apiStub, {
    get: (t, k) => t[k as string] ?? (t[k as string] = vi.fn().mockResolvedValue(undefined)),
  }),
}));

import { api } from "../lib/api";
import { ItemActivity } from "./ItemActivity";

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemActivity itemId="i_x" resolvers={{
        statusName: (s) => (s === "ready" ? "就绪" : s),
        titleOf: (id) => (id === "i_parent" ? "父任务" : id),
        userName: (id) => (id === "u_admin" ? "管理员" : id),
      }} />
    </QueryClientProvider>,
  );
}

describe("ItemActivity", () => {
  beforeEach(() => {
    (api.listEvents as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [
        { id: 3, ts: "2026-10-06T09:30:00", actor_type: "user", actor_id: "u_admin",
          actor_name: "管理员", project_id: "p1", agg_type: "item", agg_id: "i_x",
          event_type: "item.updated",
          payload: { priority: "low", description: "新", _old: { priority: "high", description: "旧" } } },
        { id: 2, ts: "2026-10-06T09:20:00", actor_type: "user", actor_id: "u_admin",
          actor_name: "管理员", project_id: "p1", agg_type: "item", agg_id: "i_x",
          event_type: "item.status_changed",
          payload: { from: "open", status: "ready", status_group: "todo" } },
        { id: 1, ts: "2026-10-06T09:10:00", actor_type: "user", actor_id: "u_dev",
          project_id: "p1", agg_type: "item", agg_id: "i_x",
          event_type: "item.assigned",
          payload: { assignee_type: "human", assignee_id: "u_admin", from_assignee_id: "u_dev" } },
        { id: 0, ts: "2026-10-06T09:00:00", actor_type: "automation", actor_id: "scheduler",
          project_id: "p1", agg_type: "item", agg_id: "i_x",
          event_type: "item.rescheduled",
          payload: { start_date: "2026-10-07", due_date: "2026-10-08" } },
      ],
      total: 4,
    });
  });
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("renders humanized activity newest-first", async () => {
    mount();
    await waitFor(() => expect(screen.getByLabelText("工作项活动流")).toBeTruthy());
    const items = screen.getByLabelText("工作项活动流").querySelectorAll("li");
    expect(items.length).toBe(4);
    const text = screen.getByLabelText("工作项活动流").textContent ?? "";
    expect(text).toContain("优先级 高 → 低");
    expect(text).toContain("更新了描述");
    expect(text).toContain("状态由「open」改为「就绪」");
    expect(text).toContain("指派给 管理员（原：u_dev）");
    expect(text).toContain("自动顺期至 2026-10-08");
    expect(text).toContain("automation"); // 非 user actor 显示类型（不冒充人名）
  });

  it("shows empty state when no events", async () => {
    (api.listEvents as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [], total: 0 });
    mount();
    await waitFor(() => expect(screen.getByText("暂无活动记录")).toBeTruthy());
  });

  it("shows error state on fetch failure", async () => {
    (api.listEvents as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));
    mount();
    await waitFor(() => expect(screen.getByText("活动加载失败")).toBeTruthy());
  });
});
