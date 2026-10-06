# 11 · 网络协作部署指南

> 时效：2026-10-06 更新（M112-I350 解冻——覆盖至 v0.21.0 全部部署面：双模认证[本档 M8 骨架/匿名首访主动登录引导=M95-I287 health 暴露 auth_mode+SPA 守卫/密码自助修改与会话失效=M96-I290 §2.6]/OIDC SSO[§2.1]/PAT 机器接入[§2.2]/推送与出站观测[§2.3]/写门语义须知[§2.4 写路由 142=中间件 75+台账 67·M112-I350 对账修正]/部署后自检速查[§2.5]/账号与凭据须知[§2.6 M96-I290]/一键发布演练[§5.2.1 `tools/release_drill.py`·发布轮收口 DoD 必跑·M89/M91/M93/M95/M97/M99/M101/M103/M105/M107/M109/M112 十二次执行·最近一次 RTO 9.3s]/部署链已验证声明[M86-I260 双镜像首验+M88-I266 v0.9.0 重建对账+M93-I282/M97-I294 依赖车后双镜像重建对账+M99-I299/M101-I305 零漂移重建对账（连续第二轮）+M103-I312 lucide 小车后重建对账+M105-I318 pwa 构建插件 major 车后双镜像重建对账+M107-I323 零漂移重建对账[双生态全零·后端连续第五轮]+M109-I327 lucide minor 车后双镜像重建对账[后端运行时 13 项连续第六轮零漂移·镜像内 pip 对账 13/13]+M112-I349 langgraph patch 车后双镜像重建对账]；app 镜像 python:3.12-slim/web 镜像 node:24-alpine；web 构建链 vite 8 Rolldown/vitest 5 node≥22.12]；自动化与集成面使用指南=[docs/12](12-automation-guide.md)（M91-I275 重写解冻·任务五域拓扑）；a11y 对比 token 基线见 docs/06 §7；env 速查单一真源=[.env.example](.env.example)）。依赖底座：httpx2 2.13/openai 3.24/pydantic 2.13/langgraph 1.2.13[Python≥3.10——镜像 python:3.12-slim 已满足]。

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

### 2.2 PAT 机器接入（M26-I199，可选）

机器/脚本以 Bearer 令牌代替会话 cookie 调用写端点：

- 登录后「我的工作」→ 机器接入令牌：创建（**display-once**——明文只显示一次，服务端只存哈希）、吊销。
- 调用方式：`Authorization: Bearer apm_pat_xxx`；令牌以其创建者为事件 actor（权限=本人）。
- 会话 cookie 优先于 Bearer——脚本环境务必登出态或独立 cookie jar（M66 坑）。

### 2.3 推送与出站观测（M67-I202/I206，可选）

- **ntfy 推送**：`APM_PUSH_URL=https://ntfy.corp.test/agentpm`（我的工作→推送通道配置写入用户偏好；服务端出站复用 webhook SSRF 门——自托管内网 ntfy 需 `APM_WEBHOOK_ALLOW_PRIVATE=1`）。
- **Prometheus**：`APM_METRICS_ENABLED=1` 后 `GET /api/metrics` 暴露计数（events 账本的读侧投影；抓取目标配到该路径）。

### 2.4 写门语义须知（M80-I240 起）

- network 模式下**全部 142 条写路由**有门（M112-I350 解冻对账修正=中间件 75+台账 67——M113-I338 webhook 双注册去重 -6 与 M115-I345 labels 三写路由 +3 的净差·原记 143=78+67）：`/api/projects/*` 与 id 白名单由中间件把守，其余由域内成员门/实例门/admin 门把守（对账：`python tools/check_write_gates.py`）。
- 部署者须知：非项目成员写操作 403（含 cycles/milestones/features/risks 的改期/删除）；资产库 org 治理动作（退役/归档/恢复/评审）需登录（实例成员）；本体 learn/apply 与 sweep force 仅 admin。
- local 模式零影响（可信单用户语义不变）。

### 2.5 部署后自检速查（M86-I262）

部署完成后按序自检（全部应绿/✓）：

```bash
docker compose ps                 # api=healthy（healthcheck 打 /api/health）·web=Up
curl localhost:${WEB_PORT}/api/health   # version 应为镜像版本（四锚一致由冒烟 86+88 锁定）
# —— 机械防腐七件（宿主机 repo 内跑，部署前自检）——
python tools/check_env_doc.py     # env 文档对账
python tools/check_write_gates.py # 路由×门禁对账
python tools/check_test_dates.py  # 测试日期×窗口端点对账
cd web && pnpm vitest run         # 前端单测（含 axe a11y 锁）
cd app && python -m pytest --ignore=tests/smoke   # 后端全量（分片跑，>10 分钟）
python tools/smoke/run_smoke.py   # 冒烟基线（repo 根目录）
# —— 发布轮收口追加（M88 起·收口 DoD 机制位）——
python tools/release_drill.py     # 一键发布演练（备份→毁库→恢复→对账→RTO·EXIT=0 即过）
grep -n "解冻" docs/11-network-deploy.md | head -1   # 时效戳应与当前版本一致
```

部署故障速查（M86 验证实录）：

| 症状 | 根因 | 处置 |
| --- | --- | --- |
| api 启动即崩 `bool_parsing` | compose 布尔透传传空串（已修：`:-false` 默认）——自建 compose 需给布尔 env 非空默认 | 升级到含修复的 compose 文件 |
| api 启动即崩 `No module named cryptography` | requirements 缺声明（已修）——自建镜像核对 requirements 含全部显式依赖 | 升级镜像 |
| 升级后启动 `no such column` | 上次启动中途崩溃留下半成品 schema 卷（init_db 对部分创建态不自愈） | `docker compose down -v` 清卷重启（**丢数据**——先确认卷内无价值数据） |
| 恢复/删 data 目录报 `PermissionError` | content/ 内 **git 对象文件为只读属性**（Windows） | 清只读属性后重删（`attrib -r /s` 或脚本 chmod） |
| WEB_PORT 起不来 | 宿主 5173 常被其他项目占用 | `WEB_PORT=其他端口 docker compose up -d` |

### 2.6 账号与凭据须知（M96-I290）

- 普通用户自助改密：右上身份区「改密」→ 旧密码再认证 → 成功后**该账号全部会话立即失效**（含本机），需用新密码重登；失败有审计（`user.password_change_failed`），成功/重置落 `user.password_changed`/`user.password_reset`（载荷永不含密码）。
- 管理员重置：`POST /api/users/{uid}/password`（admin 门）。SSO（OIDC JIT）账号无本地密码，改密/重置一律 409。
- 会话令牌 v2：四段 `user_id.epoch.expiry.signature`（三段 legacy 令牌=epoch 0 兼容，改密后即死）；boot 重放 `APM_ADMIN_PASSWORD` **不** bump epoch——重启不影响在线会话。
- 部署者须知：改密=该账号全员重登；无密码复杂度策略（与创建流一致，留观）。

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
- **一键备份（M60-I180）**：`python tools/backup.py -o backups/apm-YYYYMMDD.zip` ——在线备份 API 取 apm.db 一致快照（WAL 帧并入，活机安全）+ content/ 与 assets-repo/ 全量（含 Git 历史）+ 生效本体目录 + manifest.json（时间/事件数/数据目录），单 zip 产物；
- **事件导出（补充）**：`GET /api/projects/{id}/events/export`（NDJSON，按全局追加序，含 prev_event_id 链与校验和行）——用于单项目异地留存/审计，不作为恢复手段（恢复 = 重放：`POST /api/system/rebuild-projections` 可由事件流重建全部投影）。

### 5.2.1 恢复演练（M60-I180）

- **恢复**：`python tools/restore.py backups/apm-XXX.zip --data-dir data [--ontologies-dir ontologies]` ——先剥陈旧 `-wal/-shm` 侧车（防污染恢复快照）再落库/内容仓/资产仓；本体目录仅在显式给出 `--ontologies-dir` 时覆盖（覆盖活本体是决策不是副作用）；
- **演练三步（定期执行）**：① `python tools/backup.py -o drill.zip` → ② `--data-dir` 指向空目录执行 restore → ③ 启动 api 后 `POST /api/system/rebuild-projections`（`events_replayed` 应等于 manifest 的 event_count）。**备份会自己跑，演练是为了证明恢复仍然有效**；冒烟 65 固化了该闭环（备份→清空→恢复→一致性断言）；
- 连续流复制（Litestream 等 WAL→对象存储方案）不内置：单机手动档已覆盖；接入时以其恢复产物替换演练第 ② 步的输入即可。
- **M86-I261 首次全链演练实录（v0.8.0 数据）**：备份→毁库→恢复→rebuild 后项目数/事件数/FTS 命中/工件内容逐字节一致，恢复 RTO≈0.4s（小规模）。三条演练纪律：①备份源缺失时工具已 loud fail（sqlite3.connect 对缺失路径静默建空库会让「空备份」通过——I261 已修，**毁库必须闸在备份 EXIT=0**）；②Windows 下 content/ 的 git 对象文件为只读属性，毁库删目录需先清属性（`attrib -r /s` 或脚本 chmod）；③演练造数与基线对账分开记录（项目数/事件数/FTS 命中/工件内容四项足够）。
- **M88-I267 一键演练（发布轮节律的机制位）**：`python tools/release_drill.py` 一条命令跑全流程——临时隔离目录造数（seed）→基线四项→backup→**毁库闸在备份 EXIT=0**→restore→rebuild→四项对账（项目数/事件数/FTS 命中/工件内容 sha）→分步计时 RTO；EXIT=0 且 `reconciled: True` 即过。三条 M86 纪律已内嵌（毁库闸/只读属性清理/四项对账口径）。**脚本化才暴露的两个坑**（手工演练不触发）：`with sqlite3.connect()` 只管事务不关连接——泄漏句柄会让毁库 WinError 32；对 POST 端点误发 GET 得 405。发布轮收口跑一次（见 §2.5 自检速查）；`--keep` 保留演练目录供检查。

### 5.3 恢复

1. **首选：还原 `data_dir/`**（或用备份的 apm.db 替换）→ 启动 api → `POST /api/system/rebuild-projections` 校验投影一致（`events_replayed` 应等于事件总数）；
2. **仅有事件导出文件时（M14-I45 起）**：调用 `POST /api/projects/{id}/events/import`（body `{"data": "<NDJSON 全文>"}`）——校验和/结构校验通过后按序追加并自动 rebuild；注意：id 与目标库冲突（非空库）会整批 409，导入/导出需同代版本（live==replay 保证重放即重建投影）。
