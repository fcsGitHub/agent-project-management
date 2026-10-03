# 12 · 自动化与集成指南

> 时效：2026-10-03 更新（M102-I308 随版解冻——覆盖至 v0.16.0 全部自动化面：规则引擎 / 通知与 watch / 定时 sweep / 机器接入 / 指令模板与运行产物。M92~M97 逐轮核验自动化面零新增[webhooks worker 内部/依赖跟随/旅程复演/UX 读侧/账号安全=部署面归 docs/11 §2.6]；M99~M101 逐轮核验自动化面零新增[发布工程=docs 面归 docs/11/看板拖拽=前端交互面非自动化五域/发布工程]；真源指针体检=M98-I296 首巡抓获并修正「动作六种」漏记——实为七种[create_recurring 日历节拍自 M13-I40 即在·M91 重写时遗失]·M102-I308 二巡零漂移[NOTIFY_KINDS 9 员/WATCHABLE_EVENTS/ACTION_TYPES 七种/run_daily_sweep 对账一致]。（此前的里程碑堆叠版[§1~§40·覆盖止于 M43]退役——章节级细节真源=[docs/10 §7 看板](10-development-plan.md)，本页按**用户任务**组织；每节末尾的「真源」指向代码中的权威枚举/实现，**文档描述语义，代码持有清单**——两处冲突时以代码为准并请回报，这是活文档的契约）。
> 相关文档：部署与认证底座=[docs/11](11-network-deploy.md)（env 速查单一真源=[.env.example](.env.example)）；前端界面语义=[docs/06](06-webui-design.md)。

## 任务速查

| 我想要… | 去哪节 |
| --- | --- |
| 「缺陷被打上严重度标签就自动派给某人」 | §1 规则引擎 |
| 「任务完成/失败时提醒我」（自定义关注） | §2.3 watch |
| 「每周一自动收项目周报」 | §3 定时任务 |
| 「外部系统实时收到项目事件」 | §4.2 webhook 出站 |
| 「脚本/CI 调 API」 | §4.1 PAT |
| 「把一条好提示词存下来复用」 | §5.1 指令模板 |

---

## 1. 规则引擎：trigger → condition → action

项目内自动化规则（Kanboard Automatic Actions 的项目级「事件×动作」绑定 × n8n 三段式抽象）。规则本身事件溯源（`automation.rule_*`），执行挂在事件内核 post-emit hook 上——**事件内核即事件源**，无轮询、无外置 dispatcher。真源：`app/apm/domains/automations.py`。

### 1.1 在哪里配置

项目 → 侧栏「本体」（项目设置页）→ **自动化规则** 面板：列表（触发徽章/条件摘要/动作摘要/测试运行/历史/启停/删除）+ 三段式新建表单。

### 1.2 三段式

- **触发**：创建工作项 / 更新字段 / 状态变更 / 指派变更等事件（与 watch 白名单同源的事件集，见 §2.3）；
- **条件**（可选）：「满足〈概念〉+〈字段谓词〉」——字段可为内置（priority / status / assignee_id）或本体声明字段（severity、regression…）。谓词当前为**标量相等 / multiselect 包含**（区间与 AND/OR 留真实需求再上——backlog）；
- **动作**（七种，真源 `_execute_action` 与 `ACTION_TYPES`）：`assign` 指派 / `set_priority` 置优先级 / `set_field` 设自定义字段（enum/boolean 按本体声明出值；multiselect 逗号分隔）/ `set_status` 改状态（状态池按概念收窄）/ `notify` 发站内提醒 / `create_recurring` 按日历节拍自动建卡（M13-I40·到点日 emit item.created，需 action.concept_id+title≤200）/ `run_agent` 让 Agent 执行（项目级角色指令生效）——与 sweep 的 `_respawn_recurring` 互补：前者日历节拍、后者完成节拍（`recurrence_days`）。

每条规则绑定**单个动作**——组合动作=多条规则（同触发按创建顺序执行）。

### 1.3 执行语义（重要）

| 语义 | 说明 |
| --- | --- |
| 时机 | 触发事件**落库后**执行；条件对事件发生后的工作项状态求值 |
| 归账 | 动作事件与 `automation.rule_fired` 均以 `actor_type=automation`、`actor_id=<规则id>` 归账——审计页「发起者 → ⚡ 自动化」可单独过滤 |
| 防循环 | 双保险：automation 归账的事件不再进引擎 + dispatch 期间嵌套 emit 不进引擎（**单层执行**：规则动作永远不会触发其他规则，包括它自己） |
| 幂等 | 规则绑定在事件流上而非轮询状态——每条事件至多命中一次（Plane「一次变更触发 3 次」教训，docs/01 §H.3） |
| fail-closed | 创建即校验：未知触发/动作/用户/字段、enum 越界、未声明状态、停用字段一律 422；运行时被拒（如指派人已删）记录为「被拒绝」，不影响触发方 |

### 1.4 测试运行、历史与权限

- **测试运行**：对最近一条同类型触发事件 dry-run（显示将命中谁、将做什么），**零写操作**；
- **历史**：`automation.rule_fired` 事件流（事件号/时间/已执行·被拒绝/明细）——rebuild 后完整；
- **权限**：规则 CRUD 属项目写（network 模式 owner/contributor 可管理，viewer 与非成员 403 落 `access.denied`；local 单用户直通）；路由×门禁对账由 `tools/check_write_gates.py` 机械锁定。

---

## 2. 通知：让人在该看见时看见

站内铃铛 + 邮件 + ntfy 推送三通道**共用同一收件人决策**（`plan_notifications` 纯函数——两通道永远不会对「该通知谁」分歧）；投递路径统一过 `pref_allows` 偏好门。真源：`app/apm/domains/notifications.py`（`NOTIFY_KINDS`）+ `mailer.py` / `pusher.py`。

### 2.1 通知种类与偏好（真源 `NOTIFY_KINDS`）

| kind | 含义 |
| --- | --- |
| assigned | 指派给我 |
| approval | 审批请求 |
| comment | 参与项新评论 |
| item | 参与项状态变更 |
| mention | @提及（**不可关**——pref_allows 直通） |
| due_soon | 临近截止提醒（sweep 产生，§3） |
| approval_reminder | 审批超时提醒（升级链，§3） |
| report_weekly | 周报已生成（sweep 产生，§3） |
| watch | 自定义关注（§2.3） |

另：规则 `notify` 动作产生 `rule_notify` 通知（**默认送达**、不在偏好面板九类之内——要停它就停用那条规则）。偏好：铃铛面板逐类×通道开关；已读事件溯源（`notification.read`），rebuild 后未读数精确还原。

### 2.2 邮件与推送通道（默认关闭）

| 通道 | 启用 | 说明 |
| --- | --- | --- |
| 邮件 | `APM_SMTP_HOST`+`APM_SMTP_FROM` 同时设置 | 465 走 SSL 其余 STARTTLS；**静默时段**（per-user HH:MM 窗口·跨午夜支持·邮件暂停而站内照流——Slack DND 语义）；周报 digest 邮件豁免静默（本身就是批处理窗口）；周报可带 Markdown 附件+HTML part |
| ntfy 推送 | **用户自配**：铃铛偏好里填自己的 ntfy topic URL（+可选 token）——opt-in per user，无全局 env | mailer 镜像语义（投递事实落 `push.notified/failed` 事件）；清空 URL 即同撤 token；服务端过 SSRF 门（内网须知见 docs/11 §2.3） |

SMTP 未配置时邮件通道整体静默关闭，行为与 M11 前一致。

### 2.3 watch：自定义关注（用户自建通知规则）

「人×项目×事件类型（+可选条件）」的通知订阅——**把系统通知的九类固定面扩展为用户自定义面**。真源：`app/apm/domains/watch.py`（`WATCHABLE_EVENTS`）。

- **可关注事件（15 类白名单）**：`item.created/updated/status_changed/assigned`、`comment.created`、`approval.requested/decided`、`risk.created/updated/closed`、`expense.recorded`、`attachment.created`、`artifact.report_generated`、`run.succeeded/failed`。**设计排除**：`run.interrupted` 不入（门暂停已有 approval.requested 通知，双份破坏噪声预算——M55 降噪折叠的延续）；requested/started/tokens/spans 等过程事实是记账不是新闻；
- **条件化**：`condition` 字段扁平全等匹配（如 `{"severity":"high"}`——所有键对都须命中·M55）；
- **规则级通道路由**（M62）：单条 watch 可指定 channels（如只走邮件），缺省跟随全局 kind×channel 偏好；
- **管理**：铃铛偏好面板创建/暂停/删除（暂停修 M55 的「删了重加」坑）；导入导出 JSON（与指令模板同构·重名不 clobber）；多规则命中**只发一份**（单事件去重）；自事件抑制（自己的动作不通知自己）；
- **递归防线**：watch 产生的是 `notification.sent`，被排除在可关注白名单外——watch 永远不会触发 watch。

---

## 3. 定时任务：每日 sweep

`run_daily_sweep`（每日心跳·`sweep.run` 事件幂等去重——重放/重启不重复执行；`force` 可重跑，仅 admin）。真源：`automations.py`。全体成员：

| 任务 | 语义 |
| --- | --- |
| `_notify_due_soon` | 临近截止的工作项给指派人发 due_soon 通知（derived `overdue` 字段也在此计算） |
| `_respawn_recurring` | 周期任务到点重生（`item.respawned`——完成自动重建，M43） |
| `_report_status_weekly` | ISO 周报（`weekly_report_day` 配置默认周一·可关）——汇编+评论语料+可选 AI 叙事[失败降级]→`report_weekly` 通知+digest 邮件+订阅者副本（`report_subscribers`，§2.2） |

---

## 4. 机器接入：PAT / webhook 出站 / Atom / 邮件入口

### 4.1 PAT（脚本与 CI 调 API）

GitHub PAT 语义：**raw token 仅创建时展示一次**（display-once），落库只存 SHA-256；`Authorization: Bearer apm_…` 的有效 token **即其创建者**（无细粒度 scope——单人/可信小团队取舍；最小权限=为每个用途建独立 token，可随时撤销）。真源：`tokens.py`；网络模式认证底座见 docs/11。

### 4.2 webhook 出站（外部系统实时收事件）

项目 → 本体页 → **Webhooks 出站** 面板：接收端 URL+订阅事件白名单（item.* / approval.* / feature.created / automation.rule_fired），secret 仅展示一次（可「换发」——旧签名立即失效）。真源：`webhooks.py`。

| 头 | 值 |
| --- | --- |
| `X-APM-Event` | 事件类型（如 `item.created`） |
| `X-APM-Delivery` | 投递 ID（`dl_` 前缀）——接收方按它幂等去重 |
| `X-APM-Webhook` | 本条 webhook 的 id |
| `X-APM-Signature` | `HMAC-SHA256(secret, 原始请求体字节)` 十六进制摘要 |

投递：`POST` JSON（事件完整字典）；单次 5s 超时；失败按 1s/4s/16s 退避共至多 4 次尝试；每次终局落事件流（`webhook.delivered` / `webhook.delivery_failed`）；「投递历史」抽屉可查、失败可**一键重发**（新 delivery ID）、「Ping」发合成载荷。投递在后台线程执行，**绝不阻塞写路径**。

接收方验签（Python）：

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

要点（GitLab 明文 token 历史教训）：**只认 HMAC 不认明文 token**；对**原始字节**算摘要；常量时间比较。

### 4.3 Atom 订阅 feed

`GET /projects/{id}/feed.atom`——项目动态的只读 Atom 流；`GET /me/feed-key` 取个人订阅键（可 rotate 撤旧）。真源：`feed.py`。

### 4.4 邮件入口与外部收件

- **IMAP 邮件转任务**：`[项目名] 主题` 路由建项，回复转评论（真源 `imap_in.py`——M34/M35）；
- **外部 intake**：匿名收件表单→项目待审池（真源 `intake.py`——M33）。

---

## 5. 指令模板与运行产物

### 5.1 指令模板库（`.prompt.md` 语义）

项目 → 本体页 → **指令模板**：可复用的角色指令/任务提示（Copilot `.prompt.md` 模式）。**草稿语义**：模板只是起草助手——从模板发起的 run 仍是普通 run，审批门照挂、人审不绕过；内容经 prompts/ 管线 git 版本化；导入导出重名**永不 clobber**。真源：`prompt_templates.py`（M69）。

### 5.2 项目级指令层（prompt_layers）

L1.5 指令层：项目级/功能级/角色级三层可版本化指令（`prompt_layers` 表 version++ 追溯）；与仓库 `.prompt.md`/`AGENTS.md` 的嵌套语义=**深层优先**（更靠近执行面的覆盖更外层）。真源：`conversations.py` + `runtime/roles.py`（M67）。

### 5.3 run 产物回流（write-back）

run 结束后其产出自动回流到绑定的工作项（同步 post-emit hook——**第六员**：同一 run 幂等，不产生重复评论）。真源：`comments.py` `_run_writeback`（M70）。全部 post-emit hook 消费面（7 个）：assets / automations / comments[write-back] / mailer / pusher / watch / webhooks——**hook 只入队不阻塞写路径**。

---

## 6. 边界与 backlog

- 条件谓词=标量相等/multiselect 包含；区间、AND/OR 组合待真实需求；
- 单规则单动作；watch 白名单/规则动作集演进=代码真源先行、文档随轮解冻；
- **运行态安全状态不入事件流**（webhook secret 换发、登录失败锁定计数——运行态而非账本事实）；
- LLM API key 运行时注入（.env/环境变量），永不入事件流与文档；真实 LLM 面的行为验证=待办轮（候选池首位）；
- 新增自动化面时的文档纪律：**同轮解冻本页对应节**（时效戳+覆盖声明随手更新——收口 DoD 含 docs/11 时效戳核对，本页同规）。
