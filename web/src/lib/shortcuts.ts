/** I95: keyboard-first layer (docs/01 §AD.1, Linear/Dynatrace ⌘K·?·jk convention).
 *  SHORTCUTS is the single source of truth — the `?` overlay renders it and the
 *  window key handlers in AppShell/Board implement it; add new bindings here. */

export type Shortcut = { keys: string[]; desc: string; scope: "全局" | "看板" };

export const SHORTCUTS: Shortcut[] = [
  { keys: ["⌘K", "Ctrl K"], desc: "命令面板 / 自然语言", scope: "全局" },
  { keys: ["?"], desc: "快捷键帮助（本浮层）", scope: "全局" },
  { keys: ["Esc"], desc: "关闭弹窗 / 取消拖拽", scope: "全局" },
  { keys: ["C"], desc: "新建任务（当前项目，自动指派给你）", scope: "看板" },
  { keys: ["J"], desc: "选中下一张卡片", scope: "看板" },
  { keys: ["K"], desc: "选中上一张卡片", scope: "看板" },
  { keys: ["Enter"], desc: "打开选中卡片的评论区", scope: "看板" },
];

/** True when the event target is a text-entry surface — single-key shortcuts must
 *  yield to typing (vim j/k convention: never hijack while an input has focus). */
export function isTypingTarget(target: EventTarget | null): boolean {
  const t = target as { tagName?: string; isContentEditable?: boolean } | null;
  if (!t) return false;
  const tag = (t.tagName ?? "").toUpperCase();
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || !!t.isContentEditable;
}
