/** Login page (M8-I28): network-mode session sign-in. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Button, Card, Input } from "../components/ui";

export function LoginPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [userId, setUserId] = useState("u_admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <div className="flex h-full items-center justify-center bg-bg p-6">
      <Card className="w-full max-w-sm space-y-3 p-6">
        <div className="text-center">
          <div className="text-lg font-bold">AgentPM 登录</div>
          <p className="mt-1 text-xs text-mut">本实例运行于网络协作模式，请用实例账号登录</p>
        </div>
        <Input placeholder="用户 ID（如 u_admin）" value={userId} onChange={(e) => setUserId(e.target.value)} />
        <Input type="password" placeholder="密码" value={password}
          onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
        <Button variant="primary" className="w-full" disabled={!userId.trim() || !password || busy} onClick={submit}>
          {busy ? "登录中…" : "登录"}
        </Button>
      </Card>
    </div>
  );

  async function submit() {
    setBusy(true);
    try {
      const r = await api.login(userId.trim(), password);
      await qc.invalidateQueries();
      toast.success(`欢迎，${r.name}`);
      navigate("/");
    } catch (e) {
      toast.error("登录失败", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }
}
