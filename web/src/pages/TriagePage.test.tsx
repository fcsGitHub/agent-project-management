/** M117-I358（docs/01 §DH）：TriagePage 回归锁——①队列渲染（triage 项+
 * 暂缓徽标默认隐藏）②接受动作调 api 并失效重取③暂缓项显隐开关。 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
import { TriagePage } from "./TriagePage";

const future = new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10);

const QUEUE = {
  items: [
    { id: "i_t1", project_id: "p1", concept_id: "task", title: "登录页反馈", status: "triage",
      status_group: "backlog", priority: "high", created_at: "2026-10-06T09:00:00Z",
      updated_at: "2026-10-06T09:00:00Z", snoozed_until: null,
      reporter_id: "intake", reporter_name: "intake" },
    { id: "i_t2", project_id: "p1", concept_id: "bug", title: "旧报表报错", status: "triage",
      status_group: "backlog", priority: "low", created_at: "2026-10-05T09:00:00Z",
      updated_at: "2026-10-05T09:00:00Z", snoozed_until: future,
      reporter_id: "u_rep", reporter_name: "小张" },
  ], total: 2,
};

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/triage"]}>
        <Routes>
          <Route path="/p/:pid/triage" element={<TriagePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  (api.listItems as ReturnType<typeof vi.fn>).mockResolvedValue(QUEUE);
  (api.listMembers as ReturnType<typeof vi.fn>).mockResolvedValue({
    members: [{ user_id: "u_w", role: "contributor", name: "工人", created_at: "2026-10-01" }],
  });
});

afterEach(cleanup);

describe("TriagePage（M117）", () => {
  it("渲染队列——triage 项上卡、暂缓项默认隐藏", async () => {
    mount();
    expect(await screen.findByText("登录页反馈")).toBeTruthy();
    expect(screen.queryByText("旧报表报错")).toBeNull();  // 暂缓中，默认隐藏
    expect(screen.getByText(/另有 1 项暂缓中/)).toBeTruthy();
    expect((api.listItems as ReturnType<typeof vi.fn>).mock.calls[0][1]).toEqual(
      expect.objectContaining({ status: "triage" }));
  });

  it("接受动作调 triageItem 并在失效后重取", async () => {
    // 状态驱动 mock：决定发生后队列转空——避免「失效重取早于 mock 重设」的竞态
    let accepted = false;
    (api.triageItem as ReturnType<typeof vi.fn>).mockImplementation(async () => {
      accepted = true;
      return { item_id: "i_t1", action: "accept", status: "open" };
    });
    (api.listItems as ReturnType<typeof vi.fn>).mockImplementation(async () =>
      accepted ? { items: [], total: 0 } : QUEUE);
    mount();
    const btn = await screen.findByRole("button", { name: "✅ 接受" });
    fireEvent.click(btn);
    await waitFor(() => expect(api.triageItem).toHaveBeenCalledWith("i_t1", "accept", undefined));
    await waitFor(() => expect(screen.getByText("分诊队列为空")).toBeTruthy(), { timeout: 4000 });
  });

  it("「显示已暂缓」开关露出暂缓项与回队天数徽标", async () => {
    mount();
    await screen.findByText("登录页反馈");
    fireEvent.click(screen.getByLabelText("显示已暂缓"));
    expect(await screen.findByText("旧报表报错")).toBeTruthy();
    expect(screen.getByText(/天后回队/)).toBeTruthy();
  });

  it("报告人显示真源（intake→外部，用户→显示名）且标题深链看板抽屉", async () => {
    // M118-I363: 此前拿 assignee 冒充报告人（接受并指派后会变成被指派者）
    mount();
    await screen.findByText("登录页反馈");
    expect(screen.getByText(/报告人 外部/)).toBeTruthy();
    const link = screen.getByRole("link", { name: "登录页反馈" });
    expect(link.getAttribute("href")).toBe("/p/p1/board?item=i_t1");
    fireEvent.click(screen.getByLabelText("显示已暂缓"));
    expect(await screen.findByText(/报告人 小张/)).toBeTruthy();
  });
});
