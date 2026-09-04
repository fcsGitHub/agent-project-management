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

### 2.1 OIDC 单点登录（M17，可选）

配置以下环境变量即启用 SSO（缺任一必需项则特性整体关闭，行为与未配置时完全一致）：

```bash
- APM_OIDC_ISSUER=https://sso.corp.test/realms/agentpm   # 必需
- APM_OIDC_CLIENT_ID=agentpm                             # 必需
- APM_OIDC_CLIENT_SECRET=...                             # 必需
- APM_OIDC_REDIRECT_URI=https://apm.corp.test/api/auth/oidc/callback  # 必需；须与对外域名同源
- APM_OIDC_ALLOWED_GROUPS=agentpm-users                  # 可选；非空时组外用户 fail-closed 403
```

- 登录页出现「🔑 使用单点登录」入口；回调成功签发与本地登录同款会话 cookie；
- **JIT 注册四约束**（详见 docs/12 §14）：email 必须已验证；角色一次性定 viewer 缺省、重登不提升；组白名单 fail-closed；同 email/name 的本地账号冲突 409 不自动合并（合并 = 管理员手工动作）；
- **redirect_uri 必须与前端同源**（经反代时指向对外域名）——回调会话 cookie 落在该域；
- 本地演示：`tools/keycloak/docker-compose.yml`（realm import 一键）或 `tools/oidc_stub.py`（无容器 mini IdP）。

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

### 4.1 PWA 与移动端（M15-I48）

前端构建为可安装 PWA（vite-plugin-pwa，generateSW + autoUpdate）：

- **可安装**：浏览器访问部署地址后，地址栏出现「安装」/「添加到主屏幕」——manifest 指向实例自身，安装后以独立窗口启动（WeKan 教训：自托管场景应用商店壳无意义，装的必须是自己的服务器）。
- **离线边界**：service worker 仅缓存静态外壳（HTML/JS/CSS/图标/manifest），断网时 reload 可载入外壳与导航；**`/api/*` 一律透传网络不入缓存**（事件溯源数据必须在线，SSE/审批实时性），离线时数据区按请求失败兜底显示。
- **HTTPS 要求**：service worker 仅在 secure context（HTTPS 或 localhost）注册——内网 HTTP 部署无 SW（行为与 I48 前一致），移动端安装与离线外壳需按第 4 节配 TLS。
- **更新**：发新版后 SW 后台自动下载新版本，下次打开即新版；新 SW 就绪时会弹出「已发布新版本 · 立即刷新」提示（sonner toast）。
- **移动端布局**：<768px 视口自动折叠为汉堡抽屉导航（I47），看板/表格横向滚动，触控目标 ≥36px。


## 5. 备份与恢复（M13-I43）

原则（GitLab 官方教训移植，docs/01 §L.3）：**导出不等于备份**——事件导出仅是补充性数据出口，真正的备份以存储层为准。

### 5.1 需要备份的内容

| 内容 | 位置 | 说明 |
| --- | --- | --- |
| 事件流 + 全部投影 | `data_dir/apm.db`（SQLite 单文件） | 唯一事实源；投影可由事件重建，但直接备份文件最简 |
| 工件资产仓 | `data_dir/content/`（Git 仓） | 工件 Markdown 及其历史 |
| 本体/角色/模板 | `ontologies/`、`agents/` | 内置文件可从发行版恢复，导入/生成的必须备份 |
| 会话签名密钥 | `data_dir/secret.key` | 丢失则全部会话失效（重新登录即可，非致命） |

### 5.2 备份方式

- **停机冷备（最简可靠）**：停止 api 进程后拷贝 `data_dir/` 整目录（SQLite 单文件 + Git 仓直接可拷）；
- **在线热备**：SQLite 处于 WAL 模式，`sqlite3 data/apm.db ".backup backup.db"` 可在线取一致性快照；`content/` 为 Git 仓可 `git bundle` 或直接 rsync；
- **事件导出（补充）**：`GET /api/projects/{id}/events/export`（NDJSON，按全局追加序，含 prev_event_id 链与校验和行）——用于单项目异地留存/审计，不作为恢复手段（恢复 = 重放：`POST /api/system/rebuild-projections` 可由事件流重建全部投影）。

### 5.3 恢复

1. **首选：还原 `data_dir/`**（或用备份的 apm.db 替换）→ 启动 api → `POST /api/system/rebuild-projections` 校验投影一致（`events_replayed` 应等于事件总数）；
2. **仅有事件导出文件时（M14-I45 起）**：调用 `POST /api/projects/{id}/events/import`（body `{"data": "<NDJSON 全文>"}`）——校验和/结构校验通过后按序追加并自动 rebuild；注意：id 与目标库冲突（非空库）会整批 409，导入/导出需同代版本（live==replay 保证重放即重建投影）。
