/** I95: `?` shortcuts help overlay (Linear-style, searchable). Renders SHORTCUTS
 *  from lib/shortcuts — the same table the window key handlers implement. */
import { useState } from "react";
import { SHORTCUTS } from "../lib/shortcuts";

export function ShortcutsOverlay({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState("");
  const kw = q.trim().toLowerCase();
  const rows = SHORTCUTS.filter(
    (s) =>
      !kw ||
      s.desc.toLowerCase().includes(kw) ||
      s.scope.includes(kw) ||
      s.keys.some((k) => k.toLowerCase().includes(kw)),
  );
  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 p-6" onClick={onClose}>
      <div
        className="mt-24 w-full max-w-lg rounded-xl border border-line bg-surface p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center gap-2">
          <span className="text-sm font-semibold">⌨️ 键盘快捷键</span>
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && onClose()}
            placeholder="搜索快捷键…"
            className="ml-auto w-44 rounded-lg border border-line bg-bg px-2.5 py-1.5 text-xs"
          />
        </div>
        <div className="divide-y divide-line">
          {rows.map((s) => (
            <div key={s.keys.join("+") + s.desc} className="flex items-center gap-3 py-2 text-xs">
              <span className="w-8 shrink-0 text-[10px] text-mut">{s.scope}</span>
              <span>{s.desc}</span>
              <span className="ml-auto flex shrink-0 gap-1">
                {s.keys.map((k) => (
                  <kbd key={k} className="rounded border border-line bg-bg px-1.5 py-0.5 font-mono text-[10px] text-ink">
                    {k}
                  </kbd>
                ))}
              </span>
            </div>
          ))}
          {!rows.length && <div className="py-6 text-center text-xs text-mut">没有匹配的快捷键</div>}
        </div>
        <div className="mt-3 border-t border-line pt-2 text-[10px] text-mut">
          单键快捷键在输入框聚焦时不生效；Esc 关闭本浮层。
        </div>
      </div>
    </div>
  );
}
