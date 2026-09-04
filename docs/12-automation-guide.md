# 12 · 自动化规则使用指南（M9）

> 看板自动化规则 = **触发 → 条件 → 动作** 三段式（docs/01 §H：Kanboard Automatic Actions 的项目级「事件×动作」绑定 × n8n/Node-RED 三段式抽象）。
> 规则本身事件溯源（`automation.rule_*`），执行挂在事件内核 post-emit hook 上——**事件内核即事件源**，无轮询、无外置 dispatcher。

## 1. 在哪里配置

项目 → 侧栏「本体」（项目设置页）→ **自动化规则** 面板：

- **列表**：每条规则一行——触发徽章、条件摘要、动作摘要，以及 测试运行 / 历史 / 启停 / 删除 操作；
- **新建规则**：三段式表单
  - 「当〈触发事件〉」：创建工作项 / 更新字段 / 状态变更 / 指派变更；
  - 「满足〈概念〉+〈可选字段谓词〉」：概念可选（如 缺陷 bug）；条件字段可为内置字段（priority / status / assignee_id）或本体声明字段（如 severity、regression）；
  - 「则〈动作〉」：指派给（用户下拉）/ 置优先级（高·中·低）/ 设自定义字段（enum、boolean 按本体声明出值选项；multiselect 用逗号分隔多个值）/ 改状态（状态池按所选概念收窄）。

## 2. 执行语义（重要）

| 语义 | 说明 |
| --- | --- |
| 时机 | 触发事件**落库后**执行；条件对事件发生后的工作项状态求值 |
| 归账 | 动作事件与 `automation.rule_fired` 均以 `actor_type=automation`、`actor_id=<规则id>` 归账——审计页「发起者 → ⚡ 自动化」可单独过滤 |
| 防循环 | 双保险：automation 归账的事件不再进引擎 + dispatch 期间的一切嵌套 emit 不进引擎（**单层执行**：规则动作永远不会触发其他规则，包括它自己） |
| 幂等教训 | Plane webhook「一次变更触发 3 次」的教训（docs/01 §H.3）：规则绑定在事件流上而非轮询状态，每条事件至多命中一次 |
| fail-closed | 创建时即校验：未知触发/动作/用户/字段、enum 越界、未声明状态、停用字段一律 422；运行时动作被拒（如指派人被删）记录为「被拒绝」，不影响触发方 |

## 3. 测试运行与历史

- **测试运行**：对项目内最近一条同类型触发事件做 dry-run——显示「命中哪个工作项、将执行什么动作」，**不执行任何写操作**；
- **历史**：每条规则的触发留痕（事件号 / 时间 / 已执行·被拒绝 / 动作明细），来自 `automation.rule_fired` 事件流——rebuild 后依然完整。

## 4. 权限与部署

- 规则 CRUD 属项目写操作：network 模式下 owner / contributor 可管理（viewer 与非成员 403 并落 `access.denied` 审计），local 模式单用户直通；
- 规则随项目数据存于事件溯源库，rebuild / 迁移天然存活；部署形态与 M8 相同（docs/11）。

## 5. 边界与后续（backlog）

- 每条规则绑定**单个动作**——需要组合动作时建多条规则（同触发事件按创建顺序执行）；
- 出站 webhook（事件 → 外部 URL）登记 backlog：先内嵌后外联；
- 条件谓词当前为标量相等 / multiselect 包含；区间与组合条件（AND/OR）留待有真实需求再加。

## 6. Webhooks 出站（M10-I32/I33）

项目 → 本体页 → **Webhooks 出站** 面板：配置接收端 URL + 订阅事件（白名单：item.* / approval.* / feature.created / automation.rule_fired），创建后 **secret 仅展示一次**（可随时「换发 secret」，旧签名立即失效）。

### 6.1 投递语义（对齐 Gitea/GitLab，docs/01 §I.1）

| 项 | 值 |
| --- | --- |
| 方法 / 体 | `POST` JSON，体 = 事件完整字典（原始字节） |
| `X-APM-Event` | 事件类型（如 `item.created`） |
| `X-APM-Delivery` | 投递 ID（`dl_` 前缀），接收方按它做幂等去重 |
| `X-APM-Webhook` | 本条 webhook 的 id |
| `X-APM-Signature` | `HMAC-SHA256(secret, 原始请求体字节)` 的十六进制摘要 |
| 超时 / 重试 | 单次 5s 超时；失败按 1s/4s/16s 指数退避重试 3 次，共至多 4 次尝试 |

每次投递终局都落事件流（`webhook.delivered` / `webhook.delivery_failed`：attempts、status_code、duration_ms、error），「投递历史」抽屉可查；失败投递可**一键重发**（新 delivery ID、单次尝试）；「Ping」发送合成测试载荷。投递在后台线程执行，**绝不阻塞写路径**。

### 6.2 接收方验签（Python 示例）

```python
import hmac, hashlib

def verify(secret: str, raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)   # 常量时间比较

raw = request.get_data()            # 原始字节！不要 json.loads 后重序列化
if not verify(WEBHOOK_SECRET, raw, request.headers["X-APM-Signature"]):
    abort(401)
event = json.loads(raw)
if event["id"] <= last_seen_id:     # X-APM-Delivery 去重，幂等处理
    return "dup"
```

要点（来自 GitLab 明文 token 的历史教训）：**只认 HMAC 签名不认明文 token**；对**原始字节**计算摘要（重序列化会破坏签名）；比较用常量时间函数。

## 7. 站内通知中心（M10-I34）

顶栏铃铛 = 当前登录身份的通知流（15s 轮询 + 操作后刷新）：

| 通知来源 | kind | 接收人 |
| --- | --- | --- |
| 工作项被指派给人类成员（`item.assigned`） | assigned | 被指派人 |
| 阶段门/工件审批请求（`approval.requested`） | approval | 项目 Owner |
| 自动化规则 `notify` 动作 | rule_notify | 动作指定的用户 |

- **已读状态事件溯源**（`notification.read`，记录 ids 或 all），rebuild 后未读数精确还原；
- 通知 id 确定性生成（`n_{源事件id}_{接收人}`），保证重放后与已读事件引用一致——这是事件溯源投影的通用要求（**投影生成的新实体 id 禁止随机**）；
- 自动化规则里选「通知」动作即给指定用户发站内提醒（走 M9 防循环与 automation 归账，不产生邮件依赖）。

## 8. 邮件通知与 Atom 订阅（M11-I35/I36/I37）

### 8.1 邮件通道（默认关闭）

邮件与站内通知**共用同一收件人决策**（`plan_notifications` 纯函数），两条通道永远不会对"该通知谁"产生分歧。SMTP 未配置时整个通道静默关闭，行为与 M11 之前完全一致：

| 环境变量 | 说明 | 默认 |
| --- | --- | --- |
| `APM_SMTP_HOST` | SMTP 主机（与 FROM 同时设置才启用通道） | 空（关闭） |
| `APM_SMTP_PORT` | 端口；`465` 走 SMTP_SSL，其余走 STARTTLS | 587 |
| `APM_SMTP_USER` / `APM_SMTP_PASS` | 登录凭据（可选） | 空 |
| `APM_SMTP_FROM` | 发件人地址 | 空 |
| `APM_SMTP_TLS` | 非 465 端口是否 STARTTLS | true |

执行语义（与 M10 webhook 同构）：

- **写路径零阻塞**：post-emit hook 只把邮件放入内存队列，`apm-mailer` 后台线程负责真实 SMTP I/O（超时 10s）；
- **投递留痕**：每封邮件的成功/失败落 `email.notified` / `email.failed` 事件（含耗时、失败原因），审计页可查；
- **用户级偏好**：通知中心「邮件通知」开关（`users.email_notify`，默认开）。关闭后**只停邮件、站内通知照常**——通知是事实投影，邮件是可选的投递介质。

### 8.2 Atom 订阅 feed

在通知中心弹层底部获取个人 feed key，用任意 RSS/Atom 阅读器订阅项目动态：

```
GET /api/projects/{project_id}/feed.atom?key={feed_key}
```

- `key` 认证替代 cookie，适合阅读器等无法带会话的客户端；feed key 可随时换发（旧 key 立即失效）；
- **权限裁剪**：非项目成员即使持有合法 key 也返回 403 + `access.denied`（防 Redmine #20173 式 token 越权泄漏）；
- feed 返回该项目最近 30 条可见动态（Atom 1.0，XML 转义）。

## 9. 报表与跨项目工作台（M12-I38/I39/I40）

报表是**只读聚合**：全部数字来自对既有投影（items/approvals/events）的查询，无新表、无新事件，rebuild 一致性由构造保证（冒烟 18 显式断言）。

### 9.1 页面与 API

| 入口 | 内容 | 数据源 |
| --- | --- | --- |
| 项目内「报表」页 `#/p/{pid}/reports` | 五桶漏斗、概念分布、挂起 Gate 卡片、超期/滞留清单、近 14 天吞吐柱图 | `GET /api/projects/{id}/report` |
| 全局「我的工作」`#/my/work` | 分配给我的活跃项（跨项目）+ 等我决策的 Gate | `GET /api/my/work` |
| 项目列表（首页）每行徽标 | 待办/进行/完成计数 + ◆N 待审 | `GET /api/projects` 内嵌健康摘要 |
| CSV 导出 | `GET /api/projects/{id}/report.csv`（section,key,title,reason,value 五列，UTF-8） | 与 JSON 同数 |

### 9.2 口径定义

| 指标 | 口径 |
| --- | --- |
| 漏斗（funnel） | 工作项按 `status_group` 五桶计数（待办池/就绪/进行中/已完成/已取消），桶序固定、空桶补零 |
| 挂起 Gate（gates_pending） | `approvals.status = 'pending'` 的审批（阶段门/工件审批），卡片直达审批中心 |
| 超期 | 活跃项（非 done/cancelled）的截止日期早于今天 →「超期 N 天」。截止日期取值顺序（M13-I41 起三级回退）：① 工作项自身的 `due_date` 字段；② `due`/`due_date`/`deadline` 自定义字段；③ 两者皆无 → 按滞留口径处理 |
| 滞留 | 活跃项未声明 due，且创建时间超过 14 天（`STALE_DAYS`）→「滞留超 14 天」；已完成/已取消恒不参与 |
| 吞吐（throughput） | 近 14 天逐日计数：新建 = `item.created`；完成 = `item.status_changed` 且结果桶为 done |

### 9.3 权限语义

- `/report` 与看板/列表同读语义（项目内读取开放）；
- `/my/work` **指派即授权**：被指派者恒可见自己的活跃项（否则网络模式下被指派者反而看不到自己的工作）；Gate 清单仅项目 Owner 或实例管理员可见——与 `approval.requested` 通知的接收人决策同源。

## 10. 里程碑与时间线（M13-I41/I42/I43）

### 10.1 里程碑

里程碑是**截止日期锚点**（Plane v1.16 语义：与 sprint 式时间盒正交），把工作项聚到一个 deadline 下：

| API | 说明 |
| --- | --- |
| `POST /api/projects/{id}/milestones` | 创建（title + due_date 必填，ISO 日期；status 初始 planned） |
| `GET /api/projects/{id}/milestones` | 列表（按 due_date 排序，含进度） |
| `GET /api/milestones/{id}` | 详情（进度 + 关联工作项清单） |
| `PATCH /api/milestones/{id}` | 改标题/描述/截止日/状态 |
| `DELETE /api/milestones/{id}` | 删除（关联工作项保留，milestone_id 悬空） |

- 状态取值优先本体 milestone 概念的 states（software-dev：planned / in_progress / achieved），本体未声明时回退通用集；
- **进度口径**：done 比例 = 关联项中 done 数 ÷ 非 cancelled 总数；逾期数 = 里程碑截止日已过时的活跃关联项数；
- 工作项在**创建时**（`POST .../items` 带 `milestone_id`）或之后（`PATCH /items/{id}`）关联；未知/跨项目里程碑 422。

### 10.2 工作项排期日期

`items.start_date` / `items.due_date`（ISO 日期，可空，创建与 PATCH 均可设置）——时间线条形的定位依据；**报表「超期」口径自 M13 起为三级回退**：item.due_date → due 类自定义字段 → 滞留（见 §9.2）。

### 10.3 时间线视图

`#/p/{pid}/timeline`（侧栏「时间线」）：

- 日期轴自动适配数据范围（周刻度 + 今日竖线）；
- 行 = 概念（按本体声明名），条形 = 有起止日期的工作项（已完成绿 / 已取消灰 / 活跃蓝 / **依赖冲突红**）；
- 菱形 = 里程碑，定位在其截止日，悬停显示进度；
- `depends_on` 关系中「后置项开始早于前置项截止」视为冲突：红条 + 红色虚线连接（同行走行底边缘）；**只提示不自动改期**（OpenProject 的依赖传播改期留 backlog）。

### 10.4 事件导出

`GET /api/projects/{id}/events/export`（NDJSON，`application/x-ndjson`）：按全局追加序逐行输出项目事件（含 prev_event_id 链位），末行校验和（events 数 / sha256 / 首行 prev / 间隙数）。**导出是补充性数据出口，不是备份**（备份见 docs/11 §5）；跨项目间隙（gaps>0）属正常——全局链包含其他项目的事件。

## 11. 排程自动化与事件可携（M14-I44/I45/I46）

### 11.1 依赖传播自动排期

工作项可开启 `auto_scheduled`（默认**手动**，OpenProject 15.4 同款哲学——自动化是可选项）：

```
PATCH /api/items/{id}  {"auto_scheduled": true}
```

- 前置项（被 `depends_on` 指向者）的 `due_date` 变化时，开启自动排期的后继项自动**平移 start/due（保持时长）**；多级依赖递归传播（深度上限 20，环安全）；
- 每次平移都是**显式 `item.rescheduled` 事件**（payload 含 follow_of/delta_days/新日期/depth）——审计可见「因哪个前置项平移了多少」，投影按绝对日期写入，rebuild 幂等；
- 手动模式（默认）不受任何影响；时间线条形 hover 标注「⏱ 自动排期」。

### 11.2 事件导入恢复

与导出配对（§10.4）：

```
POST /api/projects/{id}/events/import   {"data": "<NDJSON 全文>"}
```

- 校验流水线：校验和重算比对（原始行 sha256，篡改即 422）→ 逐行 JSON/schema + id 严格递增（422）→ 事件 id 与目标库冲突检测（**任一冲突整批 409**，不做部分导入）；
- **恢复语义面向空/新库**：目标项目可不存在，但 payload 必须包含其 `project.created` 事件；
- 通过后按序追加（保留原始 id/ts/actor，prev 重链到目标库当前头部）→ 全量 rebuild → 返回 `{imported, rebuilt}`；
- 操作步骤见 docs/11 §5.3；导出/导入版本需同代（无跨版本兼容承诺）。

## 12. 移动端与 PWA（M15-I47/I48/I49）

AgentPM 前端为可安装 PWA（vite-plugin-pwa，generateSW + autoUpdate），<768px 视口自动切换移动布局。

### 12.1 安装

- 浏览器访问部署地址：桌面 Chrome/Edge 地址栏「安装」；Android Chrome 菜单「添加到主屏幕」；iOS Safari 分享菜单「添加到主屏幕」。
- manifest 指向实例自身（start_url `/`、standalone 独立窗口、图标 192/512 + maskable）——安装的是「你自己的服务器」，不依赖任何应用商店（WeKan TWA 教训，docs/01 §N.1）。

### 12.2 移动端布局（I47）

| 区域 | 桌面（≥768px） | 移动（<768px） |
| --- | --- | --- |
| 导航 | 左侧图标 rail + 功能列 | 汉堡按钮 → 抽屉（导航 + 功能列表） |
| 看板 | 多列并排 | 单列横向滑动（列宽下限保持可读） |
| 列表/表格页 | 全宽表格 | 横向滚动（`min-w-[640px]`，不挤压折行） |
| 报表/我的工作/首页 | 三列栅格 | 单列堆叠 |
| 时间线 | 全宽 | 横向滚动（日期轴百分比不压缩） |
| 触控目标 | 常规 | 审批/通知铃 36px、rail 44px、⌘K 窄屏图标化 |

### 12.3 离线边界（I48）

- **外壳可离线**：service worker precache 全部静态资产（HTML/JS/CSS/图标/manifest）——断网 reload 后外壳、导航、布局完整可用；
- **数据必在线**：`/api/*` 一律透传网络，永入 SW 缓存（`navigateFallbackDenylist` + 零 runtimeCaching）——事件溯源与 SSE/审批实时性要求在线；离线时数据区按请求失败兜底显示，恢复网络后自动回归；
- 不做离线写（一致性分叉风险，V2 再议只读快照）。

### 12.4 更新与部署注意

- **更新**：新版发布后 SW 后台下载并静默接管，下次打开即新版；新 SW 就绪时弹「已发布新版本 · 立即刷新」toast；
- **HTTPS**：service worker 仅在 secure context（HTTPS 或 localhost）注册——内网纯 HTTP 部署无 SW/安装能力（其余功能不变），移动端完整体验需按 docs/11 §4 配 TLS；
- 构建产物断言见冒烟 21（dist 含 manifest.webmanifest + sw.js、precache 零 /api、denylist 在位）。

## 13. 自定义视图与保存筛选（M16-I50/I51/I52）

把常用过滤组合存为命名视图——OpenProject「自定义查询」的 Community 等价物（docs/01 §O.1）。视图 = 过滤参数的快照，执行时**复用既有过滤路径**（不建第二条查询实现）。

### 13.1 定义与 API

定义（definition）键白名单（fail-closed，未知键/空值/坏枚举 422）：

| 键 | 含义 | 校验 |
| --- | --- | --- |
| `concept_id` | 概念收窄 | 透传 items 过滤 |
| `status_group` | 五桶之一 | backlog / todo / in_progress / done / cancelled |
| `status` | 具体状态 | 透传 items 过滤 |
| `assignee_id` / `priority` | 执行者 / 优先级 | 透传 |
| `cf` | 字段过滤 `field:value` | 字段须本体声明**且项目未停用**；multiselect 包含匹配 |
| `group_by` | 看板分组 | `lifecycle` 或 `field:<id>`（同上声明+停用校验） |

- API：`POST /projects/{pid}/views`（name+definition+is_public）、`GET /projects/{pid}/views`、`GET/PATCH/DELETE /views/{id}`、`POST /views/{id}/make-default`（项目级唯一默认，`view.made_default` 事件先清后设，rebuild 幂等）。
- 执行：`GET /projects/{pid}/items?view_id=` 与 `GET /projects/{pid}/board?view_id=`——definition 提供基础过滤，显式 query 参数可覆盖。

### 13.2 权限（对齐 M8）

- local 模式全放行（单机可信语义）；
- network 模式：**public** 视图项目成员可读；**private** 仅 owner 与实例管理员可读；viewer 不可创建；改/删仅 owner 与实例管理员；非成员访问列表/详情/执行一律 403。

### 13.3 前端与默认视图

- 看板工具栏「👁 视图」下拉：保存当前过滤、切换（definition 写回 URL 参数，功能切片保留）、公开徽标、hover 删除、设为默认；
- 选中态入 URL（`?view=`）；**直开 `?view=<id>` 自动补齐定义参数**（显式参数优先）——分享链接即还原；
- 默认视图：无显式 view/group 的看板请求自动落项目默认视图（board 响应 `applied_view_id`，工具栏 chip 与分组控件同步显示）。

## 14. OIDC 单点登录（M17-I53/I54/I55）

network 模式的 SSO 扩展：通过任意标准 OIDC 提供方（Keycloak/Authelia/authentik/Entra ID）登录，JIT（首次登录自动）建号。未配置 env 时特性整体关闭，行为与 M17 之前完全一致。

### 14.1 流程与安全语义

- **协议**：Authorization Code + PKCE(S256)；state/nonce/verifier 存 HttpOnly 短命 cookie（10 分钟），回调三方全验（RS256 签名 via jwks、iss/aud/exp/nonce）后才进入建号逻辑；握手后**不缓存 id_token**（凭据不入事件，会话 = M8 同款 HMAC cookie）。
- **JIT 注册四约束**（Gitea 教训，docs/01 §P.3）：

| 约束 | 语义 | 违反时 |
| --- | --- | --- |
| email 可信 | email 存在且 `email_verified=true` 才受理 | 422 |
| 组白名单 | `APM_OIDC_ALLOWED_GROUPS` 非空时须有交集（fail-closed） | 403 |
| 角色一次性 | 建号即 viewer 缺省；**重登不重派角色**（规避 Gitea #32566 二次登录时序坑） | — |
| 不自动合并 | 同 name 本地账号已存在 → 409，合并须管理员显式操作 | 409 |

- **门禁兼容**：JIT 用户与本地建号用户走同一 M8 门禁——未加入项目成员前写操作 403（`access.denied` 审计）；角色提升走管理员建号接口，不由 IdP claim 自动决定。

### 14.2 配置与演示

- 配置走 `APM_OIDC_*` 环境变量（表见 docs/11 §2.1）；本体页「OIDC 单点登录」面板为只读诊断（secret 不回显）。
- Keycloak 演示：`tools/keycloak/docker-compose.yml`（realm import：client `agentpm` + 用户 zhang.demo/li.admin + 组）→ `docker compose up -d` → 按 §2.1 设 env；
- 无容器环境：`python tools/oidc_stub.py`（mini IdP，:9001）——authorize 即回 callback，适合本地真流程演示。

## 15. 评论与参与通知（M18-I56/I57/I58）

工作项支持评论线程：看板卡片右下 💬 按钮打开评论抽屉（显示评论数徽标），功能页与看板 `?item=<id>` 链接可直开对应工作项的评论区。

### 15.1 评论与 @提及

- **发评论**：输入框写内容，Ctrl+Enter（或点「发送」）提交；评论按时间正序展示，作者名 + 时间可见，本人或管理员可 hover 删除（✕，软删除——审计流保留）。
- **@提及**：输入 `@` 后从下拉选择成员（支持多字姓名如「QA 王」），被提及者会收到**专属 mention 通知**（站内铃 + 邮件，若开启）；评论正文中的 @姓名 以高亮展示。提及解析按用户全名精确匹配，未注册姓名不生成通知。

### 15.2 参与与订阅

- **自动参与**：以下三种情况自动成为工作项「参与者」——评论（作者）、被 @提及、被指派（human 指派）。参与者来源以**首次加入**为准（指派后评论不改变来源标注）。
- **手动订阅**：评论抽屉左下「🔕 订阅」按钮，订阅后无需参与讨论也能收到该工作项的动态；再次点击退订（只移除手动订阅，自动参与不受影响）。

### 15.3 通知面

| 事件 | 谁会收到 | 通知内容 |
| --- | --- | --- |
| 评论 @提及 | 被提及者（作者除外） | 「xx 在工作项「<标题>」的评论中提到了你」（点击跳转评论区） |
| 新评论 | 参与者（作者与被提及者除外——他们已收到各自的定向通知） | 「参与的工作项「<标题>」有新评论：<前 60 字>」 |
| 状态变更 | 参与者（操作者除外） | 「参与的工作项「<标题>」状态变更为 <状态>」 |
| 指派 / 审批 / 自动化 | 原有语义不变（M10/M11） | — |

- 通知中心（顶栏铃铛）点击 mention 通知会**直达该工作项的评论抽屉并自动置已读**；「全部已读」一键清零。邮件通道与站内共用同一收件人决策（`plan_notifications`），邮件为资料内 opt-in。
- 通知为事件溯源投影：rebuild 后通知行 id 与已读状态逐条复现（`n_<事件id>_<用户id>`）。

## 16. 工时跟踪（M19-I59/I60/I61）

工作项支持工时记录（OpenProject time-entry 语义）：计划侧 `estimate_hours`（预估）与实际侧 spent（已投工时）并列，构成「计划 vs 实际」对照。

### 16.1 记工时

- **入口**：看板卡片右下 ⏱ 按钮打开「⏱ 工时」抽屉（显式入口，Redmine 式——不做斜杠命令解析）。
- **记一笔**：填 时长（分钟，1-1440）+ 日期（默认今天）+ 备注（做了什么，截 500 字）→「记工时」。记录人 = 当前身份，条目按 日期+时间 排序。
- **删除**：hover 自己的条目点 ✕（软删除——条目从列表与合计消失，事件保留审计）；管理员可删任何人条目（network 模式下本人或 admin）。
- **合计**：抽屉底部实时显示合计（排除已删除条目）；记工时者自动成为该工作项参与者（见 §15.2）。

### 16.2 工时展示

| 位置 | 展示 |
| --- | --- |
| 看板卡片 / 列表视图 | 有工时时显示「⏱ 2h30」徽标（`fmtMinutes`：不足 1 小时显分钟） |
| 工作项详情 | `spent_minutes` 字段与 `estimate_hours` 并列 |
| 项目报表（I61） | 按人合计 + 按日趋势小部件 |
| 我的工作（I61） | 本周记时合计（个人最小面） |

### 16.3 语义与边界

- **校验 fail-closed**：minutes 须为 1-1440 正整数、日期须 ISO 格式（YYYY-MM-DD）、空更新 422。
- **权限**：与评论一致——local 放行；network 模式项目成员可记/读，非成员 403，改/删限本人或 admin。
- **事件溯源**：`time.logged/edited/deleted` 三事件，rebuild 后条目、合计与卡片徽标逐项复现。
- **不做**（有意取舍，docs/01 §R.4）：成本/费率（OpenProject Enterprise 范畴）、斜杠命令、实时计时器打卡；个人日历视图留 backlog。

## 17. 个人工时日历与评论 Markdown（M20-I62/I63/I64）

### 17.1 个人工时日历（I62）

- **入口**：侧栏「我的工时」（`#/my/time`，在工作项无关的全局区，与「我的工作」并列）。
- **视图**：周（周一始七列）/月（42 格）双视图切换，「‹ 今天 ›」翻页，今日高亮，窗口合计徽章（近 60 天，`GET /my/timelog?days=60`——本人条目按日分组 + 日合计 + 窗口合计）。
- **快捷记时**：点任意日期格开「记到这天」卡——工作项下拉（取「我的工作」指派项）+ 分钟/备注，**spent_on 预填点选日**；当日已有条目列在卡内，点条目进入编辑（仅时长/备注），✕ 删除。改日期请走工作项 ⏱ 抽屉（`time.edited` 语义不含工作项迁移）。
- **数据边界**：只看自己的条目（own-data，语义同 `/my/work`，无项目级门禁）；月视图中非当月日期置灰，超出 60 天窗口的日期无数据。

### 17.2 时间线拖拽改期（I63）

- **拖动条形**=整体移动（start/due 同步平移；无 start_date 的项只移 due）；**拖右缘把手**=改截止日（钳制不早于 start）。
- 拖拽中条形**半透明**并悬浮「改为 X ~ Y」实时预览；**Esc 取消**，落点即 PATCH `start_date/due_date`（一次一个工作项）。
- **审计与联动全自动**：走既有 PATCH 端点——`item.rescheduled` 审计、auto_scheduled 依赖链顺延、依赖冲突红条重算，全部由后端既有逻辑完成，前端零新事件零新端点。手动拖拽不触发自动排期开关的变更（auto_scheduled 是工作项自身的开关，M14 语义）。

### 17.3 评论 Markdown 渲染（I64）

- **存储与契约不变**：评论正文仍是纯文本原文入库（`comment.created` payload 字节不变），Markdown 只是**渲染层转换**（docs/01 §S.3——GLFM/GFM 只取交集）。
- **支持**（marked + DOMPurify 消毒，XSS fail-closed）：表格、任务清单（`- [x]` 只读展示不回写——状态走工作项字段）、代码块/行内代码、引用、标题、链接（自动 `target=_blank rel=noopener`）；单个换行渲染为换行（GitHub 评论同款 `breaks` 语义）。
- **@提及**：渲染层按 users.name 最长优先匹配高亮为蓝色 chip（口径与后端 `_parse_mentions` 一致）；通知仍由后端解析发起，渲染层不参与通知。
- **编辑器**：输入框右下「👁 预览 / ✏️ 编辑」切换，预览即最终渲染效果；发送后原文入库。
