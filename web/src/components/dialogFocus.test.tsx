/** Dialog 焦点管理测试（M85-I257）：初始焦点、Tab 循环陷阱、关闭还原、ARIA 语义。 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { Modal } from "./ui";

afterEach(cleanup);

function Harness({ startOpen = false }: { startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen);
  return (
    <>
      <button onClick={() => setOpen(true)}>打开弹窗</button>
      <Modal open={open} onClose={() => setOpen(false)} title="测试弹窗">
        <button>第一个按钮</button>
        <button>第二个按钮</button>
      </Modal>
    </>
  );
}

describe("Dialog 焦点管理（M85-I257）", () => {
  it("语义与初始焦点：role=dialog + aria-modal + 首个可聚焦元素", () => {
    const dlg = render(<Harness startOpen />);
    const dialog = dlg.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBeTruthy();
    expect(document.activeElement?.textContent).toBe("第一个按钮");
  });

  it("Tab 陷阱：末尾元素前向 Tab 循回首、首元素反向 Tab 循环至末尾", () => {
    render(<Harness startOpen />);
    const first = screen.getByText("第一个按钮");
    const last = screen.getByText("第二个按钮");
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement?.textContent).toBe("第一个按钮");
    first.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement?.textContent).toBe("第二个按钮");
  });

  it("关闭还原焦点到触发元素（Esc 关闭同一路径——open 翻 false 触发清理）", () => {
    const h = render(<Harness />);
    const trigger = h.getByText("打开弹窗");
    trigger.focus();
    expect(document.activeElement?.textContent).toBe("打开弹窗");
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeTruthy();
    // 通过 Esc 关闭（window keydown 契约——I95）
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement?.textContent).toBe("打开弹窗");
  });
});
