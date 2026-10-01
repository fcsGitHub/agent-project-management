/** ErrorBoundary 组件测试（M82-I246）：渲染崩溃→fallback、重试复位、chunk 失败→刷新引导。 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Component, type ReactNode } from "react";
import { ErrorBoundary, isChunkLoadError } from "./ErrorBoundary";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** 受控炸弹：thrower.always=true 时每次渲染都抛（各用例显式置位，无跨用例序依赖）。 */
let thrower = { always: true };
class Bomb extends Component<{ children?: ReactNode }> {
  render(): ReactNode {
    if (thrower.always) throw new Error("boom");
    return <div>恢复正常</div>;
  }
}

describe("isChunkLoadError", () => {
  it("识别动态 import chunk 加载失败的各种措辞", () => {
    expect(isChunkLoadError(new Error("Failed to fetch dynamically imported module: /a.js"))).toBe(true);
    expect(isChunkLoadError(new Error("Importing a module script failed."))).toBe(true);
    expect(isChunkLoadError(new Error("Loading chunk 5 failed."))).toBe(true);
    expect(isChunkLoadError(new TypeError("Cannot read properties of undefined"))).toBe(false);
    expect(isChunkLoadError(new Error("boom"))).toBe(false);
  });
});

describe("ErrorBoundary", () => {
  it("子树渲染崩溃→页级 fallback（错误卡+错误摘要），不白屏", () => {
    thrower.always = true;
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary level="page">
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByText("这个页面出了问题", { exact: false })).toBeTruthy();
    expect(screen.getByText("boom")).toBeTruthy();
    expect(screen.getByText("↻ 重试")).toBeTruthy();
  });

  it("app 级 fallback 给重载动作（rail 外整树兜底）", () => {
    thrower.always = true;
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary level="app">
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByText("应用出了问题", { exact: false })).toBeTruthy();
    expect(screen.getByText("🔄 重载")).toBeTruthy();
  });

  it("重试复位错误态：崩溃源解除后子树恢复渲染", () => {
    thrower.always = true;
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary level="page">
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByText("这个页面出了问题", { exact: false })).toBeTruthy();
    thrower.always = false;
    fireEvent.click(screen.getByText("↻ 重试"));
    expect(screen.getByText("恢复正常")).toBeTruthy();
  });

  it("chunk 加载失败→「新版本已发布」刷新引导而非笼统报错", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    class ChunkBomb extends Component {
      render(): ReactNode {
        throw new Error("Failed to fetch dynamically imported module: /assets/x.js");
      }
    }
    render(
      <ErrorBoundary level="page">
        <ChunkBomb />
      </ErrorBoundary>,
    );
    expect(screen.getByText("🆙 新版本已发布")).toBeTruthy();
    expect(screen.getByText("🔄 立即刷新")).toBeTruthy();
  });
});
