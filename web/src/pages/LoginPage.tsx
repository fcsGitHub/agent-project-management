/** Login page (M8-I28): network-mode session sign-in.
 * M17-I54: shows an OIDC SSO button when the feature is configured. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Button, Card, Input, cx } from "../components/ui";

export function LoginPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [userId, setUserId] = useState("u_admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const oidc = useQuery({ queryKey: ["oidc-status"], queryFn: api.oidcStatus, refetchInterval: 60_000 });

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
        {oidc.data?.enabled && (
          <>
            <div className="flex items-center gap-2 text-[11px] text-mut">
              <span className="h-px flex-1 bg-line" />或<span className="h-px flex-1 bg-line" />
            </div>
            <a
              href="/api/auth/oidc/login"
              className={cx("block w-full rounded-lg border border-line px-3 py-2 text-center text-xs",
                "text-ink hover:border-acc hover:text-acc")}
              title={`通过 ${oidc.data.issuer ?? "IdP"} 单点登录`}
            >
              🔑 使用单点登录（{oidc.data.client_id ?? "OIDC"}）
            </a>
          </>
        )}
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
