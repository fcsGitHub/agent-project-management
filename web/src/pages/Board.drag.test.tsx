/** M100-I303: board drag-to-column unit tests — the three states of the drag
 * handler (start / legal drop PATCH / 422 rollback) under jsdom with synthetic
 * pointer events. The whole Board page mounts against a stubbed api module so
 * the real handler wiring (two card render sites, column drop targets, click
 * suppression) is what gets exercised. */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

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
vi.mock("../lib/sse", () => ({ onStreamEvent: () => () => {} }));
vi.mock("../components/CommentsModal", () => ({ CommentsModal: () => null }));
vi.mock("../components/TimeLogModal", () => ({ TimeLogModal: () => null, fmtMinutes: (m: number) => `${m}m` }));

import { api, type BoardData } from "../lib/api";
import { Board } from "./Board";

const item = {
  id: "i1", project_id: "p1", concept_id: "task", title: "写 PRD",
  status: "todo", status_group: "todo", created_at: "2026-10-03", updated_at: "2026-10-03",
};

const boardData: BoardData = {
  project_id: "p1", group_by: "lifecycle",
  buckets: [
    { id: "todo", name: "待办", items: [item] },
    { id: "doing", name: "进行中", items: [] },
  ],
  columns: [
    { id: "task:todo", concept_id: "task", concept_name: "任务", status: "todo", name: "待办", group: "todo" },
    { id: "task:doing", concept_id: "task", concept_name: "任务", status: "doing", name: "进行中", group: "doing" },
  ],
};

function mountBoard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/board"]}>
        <Routes>
          <Route path="/p/:pid/board" element={<Board />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return qc;
}

const card = () => screen.getByText("写 PRD").closest("[data-kb]") as HTMLElement;
const dropCol = (group: string) => document.querySelector(`[data-drop-group="${group}"]`) as HTMLElement;

async function dragTo(target: HTMLElement | null) {
  // jsdom has no hit-testing: stub elementFromPoint to answer the drop target.
  const orig = document.elementFromPoint;
  document.elementFromPoint = () => (target ?? null);
  await act(async () => {
    fireEvent.pointerDown(card(), { clientX: 10, clientY: 10, pointerId: 1, pointerType: "mouse", button: 0 });
    fireEvent.pointerMove(window, { clientX: 60, clientY: 60, pointerId: 1 });
    fireEvent.pointerUp(window, { clientX: 60, clientY: 60, pointerId: 1 });
  });
  document.elementFromPoint = orig;
}

describe("Board drag-to-column (I302)", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    apiStub.getBoard = vi.fn().mockResolvedValue(boardData);
    apiStub.getOntology = vi.fn().mockResolvedValue({ concepts: [] });
    apiStub.listRuns = vi.fn().mockResolvedValue({ runs: [] });
    apiStub.listApprovals = vi.fn().mockResolvedValue({ approvals: [] });
    apiStub.listItems = vi.fn().mockResolvedValue({ items: [] });
    apiStub.listCycles = vi.fn().mockResolvedValue({ cycles: [] });
    apiStub.listViews = vi.fn().mockResolvedValue({ views: [] });
    apiStub.listUsers = vi.fn().mockResolvedValue({ users: [] });
    apiStub.patchItem = vi.fn().mockResolvedValue({ ok: true });
  });

  it("starts the drag only past the move threshold and dims the source card", async () => {
    mountBoard();
    await screen.findByText("写 PRD");
    const orig = document.elementFromPoint;
    document.elementFromPoint = () => dropCol("doing");
    await act(async () => {
      fireEvent.pointerDown(card(), { clientX: 10, clientY: 10, pointerId: 1, pointerType: "mouse", button: 0 });
      // below threshold — no drag state yet
      fireEvent.pointerMove(window, { clientX: 12, clientY: 12, pointerId: 1 });
    });
    expect(document.body.classList.contains("select-none")).toBe(false);
    await act(async () => {
      fireEvent.pointerMove(window, { clientX: 60, clientY: 60, pointerId: 1 });
    });
    expect(document.body.classList.contains("select-none")).toBe(true);
    expect(card().className).toContain("opacity-40");
    expect(dropCol("doing").className).toContain("ring-2");
    await act(async () => {
      fireEvent.pointerUp(window, { clientX: 60, clientY: 60, pointerId: 1 });
    });
    document.elementFromPoint = orig;
  });

  it("legal drop issues PATCH with the concept status of the target group", async () => {
    mountBoard();
    await screen.findByText("写 PRD");
    await dragTo(dropCol("doing"));
    await waitFor(() => expect(api.patchItem).toHaveBeenCalledWith("i1", { status: "doing" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("failed PATCH (422) surfaces the error toast instead of a success one", async () => {
    mountBoard();
    await screen.findByText("写 PRD");
    (api.patchItem as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("invalid transition"));
    await dragTo(dropCol("doing"));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(String((toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0])).toContain("invalid transition");
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("same-group drop is a no-op and plain clicks still toggle selection", async () => {
    mountBoard();
    await screen.findByText("写 PRD");
    await dragTo(dropCol("todo"));
    await waitFor(() => expect(document.body.classList.contains("select-none")).toBe(false));
    expect(api.patchItem).not.toHaveBeenCalled();
    // plain click (no drag movement) must not be swallowed by the suppress flag
    await act(async () => { fireEvent.click(card()); });
    expect(card().className).toContain("ring-2 ring-acc");
  });
});
