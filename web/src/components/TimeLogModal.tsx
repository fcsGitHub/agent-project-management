/** Work-item time log drawer (M19-I60): entries list (who/when/how long/note)
 * + log form. OpenProject-style explicit entry; totals exclude soft-deleted. */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Button, Modal } from "./ui";

const today = () => new Date().toISOString().slice(0, 10);

export const fmtMinutes = (m: number) => {
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60), mm = m % 60;
  return mm ? `${h}h${mm.toString().padStart(2, "0")}` : `${h}h`;
};

export function TimeLogModal({ itemId, title, onClose }: {
  itemId: string; title?: string; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [minutes, setMinutes] = useState("60");
  const [spentOn, setSpentOn] = useState(today());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const entries = useQuery({
    queryKey: ["time_entries", itemId],
    queryFn: () => api.listTimeEntries(itemId),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["time_entries", itemId] });
    // spent totals ride on board/list queries too
    qc.invalidateQueries();
  };

  const submit = async () => {
    const m = parseInt(minutes, 10);
    if (!m || m <= 0) { toast.error("时长须为正整数分钟"); return; }
    setBusy(true);
    try {
      await api.logTime(itemId, { minutes: m, spent_on: spentOn, note: note.trim() });
      setNote("");
      invalidate();
    } catch (e) {
      toast.error(`记工时失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteTimeEntry(id);
      invalidate();
    } catch (e) {
      toast.error(`删除失败：${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <Modal open onClose={onClose} title={`⏱ 工时${title ? ` · ${title}` : ""}`}>
      <div className="space-y-3">
        <div className="max-h-64 space-y-2 overflow-y-auto">
          {(entries.data?.entries ?? []).map((t) => (
            <div key={t.id} className="group rounded-lg border border-line px-3 py-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-medium">{t.user_name ?? t.user_id}</span>
                <span className="rounded bg-accbg px-1.5 font-medium text-acc">{fmtMinutes(t.minutes)}</span>
                <span className="text-[10px] text-mut">{t.spent_on}</span>
                <button onClick={() => remove(t.id)}
                  className="ml-auto text-[10px] text-mut opacity-0 transition-opacity hover:text-dan group-hover:opacity-100"
                  title="删除工时">✕</button>
              </div>
              {t.note && <div className="mt-1 whitespace-pre-wrap text-ink">{t.note}</div>}
            </div>
          ))}
          {!entries.data?.entries.length && (
            <div className="py-6 text-center text-xs text-mut">还没有工时记录——写下第一笔实际投入</div>
          )}
        </div>
        <div className="flex items-center justify-between rounded-lg border border-line px-3 py-1 text-xs">
          <span className="text-mut">合计</span>
          <span className="font-medium text-acc">{fmtMinutes(entries.data?.total_minutes ?? 0)}</span>
        </div>
        <div className="grid grid-cols-[1fr_1fr] gap-2">
          <label className="text-[10px] text-mut">
            分钟
            <input type="number" min={1} max={1440} value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              className="mt-0.5 w-full rounded-lg border border-line bg-bg px-2 py-1.5 text-xs text-ink" />
          </label>
          <label className="text-[10px] text-mut">
            日期
            <input type="date" value={spentOn}
              onChange={(e) => setSpentOn(e.target.value)}
              className="mt-0.5 w-full rounded-lg border border-line bg-bg px-2 py-1.5 text-xs text-ink" />
          </label>
        </div>
        <textarea rows={2} placeholder="备注（做了什么）" value={note}
          onChange={(e) => setNote(e.target.value)}
          className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-xs" />
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-mut">合计与徽标排除已删除条目</span>
          <Button size="sm" variant="primary" disabled={busy} onClick={submit}>记工时</Button>
        </div>
      </div>
    </Modal>
  );
}
