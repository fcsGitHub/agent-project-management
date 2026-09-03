/** Design-system primitives in the demo.html visual language (zinc + indigo). */
import React, { useEffect, useRef, useState } from "react";

export const cx = (...parts: (string | false | null | undefined)[]) =>
  parts.filter(Boolean).join(" ");

export function Button({
  variant = "default", size = "md", className, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "ghost" | "danger" | "outline";
  size?: "sm" | "md";
}) {
  return (
    <button
      className={cx(
        "inline-flex items-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-acc",
        size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm",
        variant === "default" && "bg-surface border border-line hover:bg-bg text-ink",
        variant === "primary" && "bg-acc text-white hover:bg-indigo-500 shadow-sm",
        variant === "ghost" && "hover:bg-bg text-mut hover:text-ink",
        variant === "danger" && "bg-dan text-white hover:bg-red-600",
        variant === "outline" && "border border-line text-ink hover:border-acc hover:text-acc",
        className,
      )}
      {...props}
    />
  );
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx("rounded-[12px] border border-line bg-surface shadow-sm", className)}
      {...props}
    />
  );
}

const TONES: Record<string, string> = {
  neutral: "bg-bg text-mut border-line",
  indigo: "bg-accbg text-acc border-indigo-100",
  violet: "bg-agbg text-ag border-violet-100",
  green: "bg-okbg text-ok border-okln",
  amber: "bg-warnbg text-warn border-warnln",
  red: "bg-danbg text-dan border-red-100",
};

export function Badge({
  tone = "neutral", className, ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof TONES | string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4",
        TONES[tone] ?? TONES.neutral,
        className,
      )}
      {...props}
    />
  );
}

export const GROUP_TONE: Record<string, string> = {
  backlog: "neutral", todo: "indigo", in_progress: "amber",
  done: "green", cancelled: "neutral",
};
export const GROUP_NAME: Record<string, string> = {
  backlog: "待办池", todo: "就绪", in_progress: "进行中", done: "已完成", cancelled: "已取消",
};
export const CONV_STATUS: Record<string, { label: string; tone: string }> = {
  active: { label: "活跃", tone: "neutral" },
  running: { label: "运行中", tone: "violet" },
  interrupted: { label: "已打断", tone: "amber" },
  awaiting_review: { label: "待评审", tone: "amber" },
  archived: { label: "已归档", tone: "neutral" },
};

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx(
        "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm placeholder:text-mut/60 focus:outline-none focus:border-acc",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(
        "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm placeholder:text-mut/60 focus:outline-none focus:border-acc",
        className,
      )}
      {...props}
    />
  );
}

export function Drawer({
  open, onClose, title, width = "40%", children,
}: {
  open: boolean; onClose: () => void; title: React.ReactNode; width?: string; children: React.ReactNode;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <aside
        className="relative z-10 flex h-full flex-col border-l border-line bg-surface shadow-xl"
        style={{ width: `min(${width}, 720px)` }}
      >
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="text-sm font-semibold">{title}</div>
          <Button variant="ghost" size="sm" onClick={onClose}>Esc ✕</Button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </aside>
    </div>
  );
}

export function Tabs({
  tabs, active, onChange,
}: {
  tabs: { id: string; label: string; count?: number }[];
  active: string; onChange: (id: string) => void;
}) {
  return (
    <div className="flex items-center gap-1 border-b border-line px-2">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
            active === t.id ? "border-acc text-acc" : "border-transparent text-mut hover:text-ink",
          )}
        >
          {t.label}
          {t.count !== undefined && <span className="ml-1.5 text-xs text-mut">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Empty({ icon, title, hint, action }: {
  icon?: React.ReactNode; title: string; hint?: string; action?: React.ReactNode;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 py-16 text-center">
      <div className="text-3xl opacity-40">{icon ?? "◌"}</div>
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="max-w-sm text-xs text-mut">{hint}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-2 py-1 text-xs">
      <span className="w-24 shrink-0 text-mut">{k}</span>
      <span className="min-w-0 break-all font-mono">{v}</span>
    </div>
  );
}

export function Collapse({ title, children, defaultOpen = false }: {
  title: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-line">
      <button
        className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-mut hover:text-ink"
        onClick={() => setOpen(!open)}
      >
        <span>{title}</span>
        <span className="text-[10px]">{open ? "收起 ▴" : "展开 ▾"}</span>
      </button>
      {open && <div className="border-t border-line p-3 text-xs">{children}</div>}
    </div>
  );
}

export function Modal({ open, onClose, title, children }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/25" onClick={onClose} />
      <div ref={ref} className="relative z-10 w-full max-w-lg rounded-[12px] border border-line bg-surface shadow-xl">
        <header className="border-b border-line px-4 py-3 text-sm font-semibold">{title}</header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
