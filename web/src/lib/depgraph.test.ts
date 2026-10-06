/** M119-I367（docs/01 §DK）：依赖图方向契约锁——本库 depends_on 语义是
 *  from=依赖方（后继）、to=前置，与后端自动排程/blocked 旗标/CPM（M119-I366
 *  修正）同向。页面旧实现把 e.from 一律当上游：依赖图层级倒挂（前置被排到
 *  依赖方下方）、被阻塞旗标标到前置头上。红→绿：先移植旧逻辑跑红，再修正。 */
import { describe, expect, it } from "vitest";
import { computeBlocked, computeLevels, upstreamMap } from "./depgraph";

const state = (g: string) => ({ status_group: g });

describe("depends_on 方向（from=依赖方, to=前置）", () => {
  const edges = [{ from: "A", to: "B", kind: "depends_on" as const }];
  const nodes = new Map([["A", state("in_progress")], ["B", state("todo")]]);

  it("前置 B 是依赖方 A 的上游（层级：B 在上）", () => {
    const lv = computeLevels(["A", "B"], edges);
    expect(lv.get("B")).toBe(0);
    expect(lv.get("A")).toBe(1);
    expect(upstreamMap(edges).get("A")).toEqual(["B"]);
  });

  it("前置未完成 → 依赖方被阻塞，前置自身不背旗", () => {
    expect(computeBlocked(nodes, edges)).toEqual(new Set(["A"]));
  });

  it("前置完成/取消 → 无人被阻塞", () => {
    const done = new Map([["A", state("in_progress")], ["B", state("done")]]);
    expect(computeBlocked(done, edges).size).toBe(0);
    const cancelled = new Map([["A", state("cancelled")], ["B", state("todo")]]);
    expect(computeBlocked(cancelled, edges).size).toBe(0);
  });

  it("依赖方自己已完成 → 不再被阻塞", () => {
    const done = new Map([["A", state("done")], ["B", state("todo")]]);
    expect(computeBlocked(done, edges).size).toBe(0);
  });

  it("未知状态（🔒 外部占位）前置不假红", () => {
    const ext = new Map([["A", state("in_progress")], ["B", state("external-unknown")]]);
    expect(computeBlocked(ext, edges).size).toBe(0);
  });
});

describe("blocks 方向（from=阻塞者, to=被阻塞）", () => {
  const edges = [{ from: "C", to: "D", kind: "blocks" as const }];

  it("阻塞者 C 在被阻塞者 D 之上", () => {
    const lv = computeLevels(["C", "D"], edges);
    expect(lv.get("C")).toBe(0);
    expect(lv.get("D")).toBe(1);
  });

  it("阻塞者未完成 → 被阻塞者背旗", () => {
    const nodes = new Map([["C", state("in_progress")], ["D", state("todo")]]);
    expect(computeBlocked(nodes, edges)).toEqual(new Set(["D"]));
  });
});

describe("混合与环", () => {
  it("菱形链层级取最长路", () => {
    const edges = [
      { from: "M", to: "F", kind: "depends_on" as const },
      { from: "T", to: "M", kind: "depends_on" as const },
      { from: "T", to: "DOC", kind: "depends_on" as const },
    ];
    const lv = computeLevels(["F", "M", "T", "DOC"], edges);
    expect(lv.get("F")).toBe(0);
    expect(lv.get("M")).toBe(1);
    expect(lv.get("DOC")).toBe(0);
    expect(lv.get("T")).toBe(2);
  });

  it("成环不炸：环上节点落在保底层级", () => {
    const edges = [
      { from: "A", to: "B", kind: "depends_on" as const },
      { from: "B", to: "A", kind: "depends_on" as const },
    ];
    expect(() => computeLevels(["A", "B"], edges)).not.toThrow();
  });
});
