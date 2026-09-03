# 11 · 网络协作部署指南（M8）

> 单机开发保持默认 `auth_mode=local`（免登录，行为同 MVP）。多人网络协作部署按本文操作。

## 1. 双模开关（M8-I26）

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `APM_AUTH_MODE` | `local` | `local`=单机免登录（现状）；`network`=写接口强制登录 + 项目成员角色鉴权 |
| `APM_ADMIN_PASSWORD` | 空 | 首启（及每次重启）为默认管理员 `u_admin` 设置/更新密码 |
| `APM_SESSION_TTL_HOURS` | `24` | 会话有效期（小时） |
| `APM_SECRET_KEY` | 空 | 会话签名密钥；留空则自动生成并持久化到 `data/secret.key` |

**local 模式**（默认）行为与 MVP 完全一致：顶栏为本地身份切换菜单，无需登录。

## 2. 网络模式最小配置

```bash
# docker-compose 片段
services:
  api:
    environment:
      - APM_AUTH_MODE=network
      - APM_ADMIN_PASSWORD=change-me-once   # 首启后可移除，密码已入库
      - APM_SECRET_KEY=                      # 留空自动生成 data/secret.key
```

首启后用 `u_admin` / 该密码登录（`#/login` 登录页）；随后在用户接口为同事建号：

```bash
curl -X POST http://host:8000/api/users -H "Content-Type: application/json" \
  -b cookies.txt -d '{"id":"qa-li","name":"QA 李","password":"初始密码"}'
```

（账号供给 = Gitea 模式：默认不开放自助注册，管理员建号；不做邮件邀请。）

## 3. 角色与归账规则（M8-I27/I28）

- 建项目者自动成为该项目 **owner**；owner 可在「本体 → 项目成员」面板添加/改角色/移除成员。
- **owner** 全权；**contributor** 可读写项目内资源；**viewer** 只读——写操作 403 并落 `access.denied` 审计事件。
- 网络模式下**登录人即事件 actor**：所有 item/审批/成员变动的审计流按登录人归账；本地「身份切换」菜单自动隐藏（切换 = 登出重登）。
- 实例管理员（`u_admin`）豁免项目成员检查。

## 4. 反向代理（HTTPS）

Cookie 为 `HttpOnly + SameSite=Lax`，不依赖 Secure 标志也可在 HTTP 内网使用；公网部署必须 TLS 终止在反代：

```nginx
server {
  listen 443 ssl;
  server_name apm.example.com;
  # ssl_certificate ...; ssl_certificate_key ...;
  location / {
    proxy_pass http://127.0.0.1:8080;   # web 容器（nginx 已反代 /api → api:8000）
    proxy_set_header Host $host;
    proxy_http_version 1.1;
    proxy_set_header Connection "";      # SSE 长连接
    proxy_read_timeout 1h;
  }
}
```

compose 全栈（api + web/nginx 代理 SSE）见仓库根 `docker-compose.yml`；只需追加第 2 节的环境变量。
