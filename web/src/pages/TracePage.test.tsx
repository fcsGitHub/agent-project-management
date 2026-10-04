/** 验收考官 Round 1（docs/13）：TracePage 两个集成缺陷的回归锁——
 * ①登记追溯链接后 trace-impact 查询缓存未被失效，影响分析面板停留在登记前的
 *   旧图（同一屏两个面板自相矛盾）；②影响分析的对象下拉只要有需求就只剩需求，
 *   docs/10 §M108 的「从任务侧进入则反查需求」在 UI 上不可达。 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
import { TracePage } from "./TracePage";
import { toast } from "sonner";

const coverage = {
  requirements: [{ id: "i_req", title: "登录鉴权", status: "open", updated_at: "2026-10-04",
    has_decision: false, has_implementation: false, has_test: false, has_deliverable: false,
    has_document: false, links: 0, first_evidence_at: null, needs_review: false, closed: false }],
  gaps: { requirements_without_evidence: [], requirements_without_tests: [],
    requirements_without_implementation: [], orphan_items: [], stale_links: [],
    changed_after_evidence: [] },
  summary: { requirements: 1, with_implementation: 0, with_tests: 0, closed: 0,
    closed_rate: 0, orphan_items: 0, stale_links: 0, needs_review: 0 },
};
const items = {
  items: [
    { id: "i_req", project_id: "p1", concept_id: "requirement", title: "登录鉴权", status: "open" },
    { id: "i_task", project_id: "p1", concept_id: "task", title: "实现登录模块", status: "doing" },
  ],
};
const impact = {
  node: { type: "item", ref: "i_req", title: "登录鉴权", missing: false, requirement_like: true },
  depth: 2,
  groups: { requirements: [], decisions: [], implementation: [], tests: [], deliverables: [], documents: [], related: [] },
  summary: { needs_review: 0 },
};

function mountTrace() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/trace"]}>
        <Routes>
          <Route path="/p/:pid/trace" element={<TracePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { qc, spy };
}

describe("TracePage 集成回归（考官 Round 1）", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    apiStub.traceCoverage = vi.fn().mockResolvedValue(coverage);
    apiStub.listTraceLinks = vi.fn().mockResolvedValue({ links: [] });
    apiStub.listItems = vi.fn().mockResolvedValue(items);
    apiStub.listArtifacts = vi.fn().mockResolvedValue({ artifacts: [] });
    apiStub.listMilestones = vi.fn().mockResolvedValue({ milestones: [] });
    apiStub.traceImpact = vi.fn().mockResolvedValue(impact);
    apiStub.createTraceLink = vi.fn().mockResolvedValue({ id: "tl_1" });
  });

  it("登记链接后失效 trace-impact 缓存（F2：影响面板不得停留在旧图）", async () => {
    const { spy } = mountTrace();
    await screen.findByText("覆盖概览");
    // 来源=工作项 i_task，目标类型=工件（空列表→自由输入框）
    fireEvent.change(screen.getByLabelText("来源节点"), { target: { value: "i_task" } });
    fireEvent.change(screen.getByLabelText("目标节点"), { target: { value: "docs/prd.md" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "登记" })); });
    await waitFor(() => expect(api.createTraceLink).toHaveBeenCalled());
    await waitFor(() => expect(spy).toHaveBeenCalledWith({ queryKey: ["trace-impact", "p1"] }));
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("存在需求时影响分析下拉仍提供任务选项（F3：反查入口可达）", async () => {
    mountTrace();
    await screen.findByText("覆盖概览");
    const select = screen.getByLabelText("分析对象") as HTMLSelectElement;
    await waitFor(() => expect(select.options.length).toBeGreaterThan(1));
    const labels = Array.from(select.options).map((o) => o.textContent);
    expect(labels).toContain("[需求] 登录鉴权");
    expect(labels).toContain("[doing] 实现登录模块");
  });
});
