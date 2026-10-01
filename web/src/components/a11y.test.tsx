/** a11y 机械锁（M85-I258，机械防腐第七件）：ui.tsx 两原语（Modal/Drawer）的
 * 代表性内容经 axe-core（dequelabs 官方引擎）断言零 serious/critical 违规；
 * 故意红自证证明引擎在岗（无名图标按钮必被 button-name 规则点名）。
 * 规则裁剪仅限页面级 region/landmark/heading（组件测试无页面语境）——
 * 色彩对比在 jsdom 无布局属 incomplete 不误伤。 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import axe from "axe-core";
import { Modal, Drawer } from "./ui";

afterEach(cleanup);

const PAGE_LEVEL_RULES = ["region", "landmark-one-main", "page-has-heading-one"];

async function seriousViolations(container: HTMLElement) {
  const results = await axe.run(container, {
    rules: Object.fromEntries(PAGE_LEVEL_RULES.map((r) => [r, { enabled: false }])),
  });
  return results.violations.filter((v) =>
    (["critical", "serious"] as string[]).includes(v.impact ?? ""),
  );
}

describe("a11y 机械锁（M85-I258）", () => {
  it("Modal 代表性表单内容零 serious/critical 违规", async () => {
    const { container } = render(
      <Modal open onClose={() => {}} title="新建项目">
        <input aria-label="项目名称" placeholder="项目名称" />
        <textarea aria-label="一句话需求" rows={3} />
        <button>取消</button>
        <button>创建</button>
      </Modal>,
    );
    expect((await seriousViolations(container)).map((v) => v.id)).toEqual([]);
  });

  it("Drawer 代表性内容零 serious/critical 违规", async () => {
    const { container } = render(
      <Drawer open onClose={() => {}} title="任务详情">
        <p>正文内容——抽屉消费面 8+ 文件的代表形态。</p>
        <button>编辑</button>
      </Drawer>,
    );
    expect((await seriousViolations(container)).map((v) => v.id)).toEqual([]);
  });

  it("故意红自证：空文本按钮必被 button-name 规则点名", async () => {
    const { container } = render(<button aria-label="" />);
    const results = await axe.run(container, {
      rules: Object.fromEntries(PAGE_LEVEL_RULES.map((r) => [r, { enabled: false }])),
    });
    expect(results.violations.some((v) => v.id === "button-name")).toBe(true);
  });
});
