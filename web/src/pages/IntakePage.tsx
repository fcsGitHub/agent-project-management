/** I99 public intake form (docs/01 §AE.2): no-login landing page at
 *  /#/intake/:token — the token is the credential, the title the only must. */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui";

export function IntakePage() {
  const { token } = useParams();
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      const r = await api.submitIntake(token, {
        title: title.trim(),
        priority: priority || undefined,
      });
      setDone(r.title);
      setTitle("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-6">
      <div className="w-full max-w-md rounded-[12px] border border-line bg-surface p-5 shadow-sm">
        <div className="mb-1 text-sm font-semibold">📮 提交需求</div>
        <p className="mb-4 text-xs text-mut">填写后提交，团队会在看板上收到这张卡。</p>
        {done ? (
          <div className="space-y-3 text-xs">
            <div className="rounded-lg border border-line bg-bg px-3 py-3">
              ✓ 已提交「{done}」——感谢！
            </div>
            <Button size="sm" variant="outline" onClick={() => setDone(null)}>再提交一条</Button>
          </div>
        ) : (
          <div className="space-y-2 text-xs">
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !busy && title.trim() && submit()}
              placeholder="一句话描述需求"
              className="w-full rounded-lg border border-line bg-bg px-2.5 py-2"
            />
            <select value={priority} onChange={(e) => setPriority(e.target.value)}
              className="w-full rounded-lg border border-line bg-bg px-2 py-2">
              <option value="">优先级（可选）</option>
              <option value="high">高</option>
              <option value="medium">中</option>
              <option value="low">低</option>
            </select>
            {error && <div className="text-dan">{error}</div>}
            <Button size="sm" variant="primary" className="w-full justify-center"
              disabled={busy || !title.trim()} onClick={submit}>
              {busy ? "提交中…" : "提交"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
