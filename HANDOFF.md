# HANDOFF —— 写给下一个新会话（2026-09-04 更新 · M17 已定义（I53-I55 OIDC 单点登录），下一步 I53）

> 你是完全没有任何上下文的新会话。先读完本文件，再按「下一步」开工。**不要重新调研已调研过的东西，不要重做已完成的事。**

## 1. 我们在做什么

**AgentPM**（`D:\project\agent-project-management`）：一套「人指挥、Agent 执行」的项目管理 Web 系统。项目生命周期建模为图（阶段+Gate+任务），角色化 Agent（YAML 声明）执行，人在审批门批准/拒绝/改后恢复；事件溯源记录一切；工件 Markdown 入 Git；本体（ontology YAML）是项目类型系统；资产库沉淀可复用工件。

**长期目标（用户设定，持续有效）**：
1. 接管并持续迭代优化本项目；
2. 融合开源项目 **semantica** 的本体构建模式进项目管理；
3. 每轮结束：上下文占用超 30% 就压缩（本文件即压缩产物）；
4. 每轮结束：更新本文件 HANDOFF.md，新会话先读它再继续；
5. 开发计划完成一轮后：调研相关开源、吸收优点、更新设计与开发计划、继续推进。

**进度真源**：[docs/10-development-plan.md](docs/10-development-plan.md) §7 状态看板——发现任何文档与代码不一致，以看板为准并即时修正。

## 2. 已经完成什么

### MVP（I0–I13，2026-08-22 终验）与 M4·本体构建闭环（I14–I16，2026-09-02 正式审阅通过）
- **MVP**：FastAPI + 事件溯源内核 + LangGraph Runtime + Orchestrator + 对话域 + 资产域 + NL 命令 + React 全套页面 + docker-compose。
- **M4（semantica 融合第一里程碑）**：I14 本体归纳（learn 四条确定性规则 L1–L4 + provenance + apply 版本化）、I15 版本化语义 diff + 数据影响分析、I16 CQ 可回答性检查（cq_mappings + 三态报告）。浏览器实测审阅通过，截图 `docs/m4-review-ontology-page.png`。

### M5 · V1.x 协作与归纳增强（I17–I19，2026-09-02 正式审阅通过）
- 调研（docs/01 §C.3.1）：semantica Semantic Extraction 方法降级链 `llm→ml→pattern` + 置信度 + provenance；本项目 L1–L4 规则即链中 pattern 层。
- **I17 LLM 辅助归纳**（`a244899`）：`ontology-curator` 角色 + `POST /api/ontologies/{name}/learn-llm`（回放确定性/openai 真实、confidence≥0.65、与 pattern 候选去重合并、JSON 损坏优雅降级、apply 共链路）；CQ events 证据按项目过滤（B 级修复）。
- **I18 本体模板包**（`4873523`）：`GET /export`（单 JSON 包=本体+角色+提示词）、`POST /import`（改名防冲突 409、校验 422、角色复用不覆盖、`ontology.imported` 事件）；`agents_dir_override` 测试隔离；前端导出/导入入口。
- **I19 多人协作基础**（`9813d01`）：users 表=事件投影+自举默认用户；注册/切换身份（`session.identity_switched` 事件）；**emit 身份透传**（全仓清除 actor 硬编码）；human 指派校验 + `assignee_name`；`/events?actor_id=`、`/approvals?decided_by=`；顶栏身份菜单。
- **M5 正式审阅通过**（`cf53199`）：浏览器实测注册「QA 王」→ LLM 建议 → 应用 v2，截图 `docs/m5-review-collab-page.png`（演示已正确隔离 data+ontologies）。

### M6 · 类型系统深化（2026-09-02 启动；调研结论 docs/01 §D，**别重查**）
- 调研：OpenProject 自定义字段（八格式、类型+项目双层激活、可过滤标记）；Plane 工作项类型（六属性、按属性分组看板）；LangGraph 1.0.9→1.2.11 同大版本可升（I22 验证）。
- **I20 自定义字段值（本轮完成，commit `e2c80b8`）**：
  - 本体字段类型 +boolean/multiselect（校验器管类型枚举与 values 必填）；内置 software-dev 演示字段 `bug.regression:boolean`、`task.tags:multiselect`；
  - `items.custom_fields` JSON 列（init_db PRAGMA 检查 + ALTER 迁移，存量库无损）；create/patch 双路径按概念声明校验（未声明/类型错/越界 422 fail-closed）；`GET /items?cf=field:value` 过滤（multiselect 包含匹配、boolean 字面量）；
  - **顺手修掉两个隐藏投影 bug**（docs/10 附录 A I20 行）：`item.updated` 投影 `sets.append(a,b)` 双参 TypeError（此前从未触发）；INSERT 参数序与列序错位（套跑才炸）。
- **I21 看板字段分组与展示**：
  - `GET /projects/{id}/board` 增 `group_by` 参数（缺省取本体 `board_defaults.group_by`）；`field:<id>` 按概念声明字段分桶：声明 values 保持本体序（空列保留）、multiselect 每值一列（工作项扇出复现）、boolean 用 true/false 字面量（与 cf 过滤一致）、无值项入「未设置」列恒最后；未声明字段/未知模式 422 fail-closed；
  - 前端：看板页分组选择器（生命周期+跨概念全部字段，状态入 URL `?group=`）、卡片自定义字段徽标（`customFieldBadges`，web/src/lib/fmt.ts）、列表视图「字段」列、功能页切片同步徽标；
  - 浏览器验证截图 `docs/i21-board-field-grouping.png`。
- **I22 LangGraph 1.2.11 升级验证（本轮完成）**：
  - langgraph 1.0.9→1.2.11（连带 langchain-core 1.6.1 / prebuilt 1.1.0 / sdk 0.4.4；checkpoint-sqlite 3.1.1 不动），requirements 下限抬至 `>=1.2.11`；
  - **全量回归零改动通过**：pytest 80 绿、冒烟 12 GREEN——Runtime 子图/录制回放/SqliteSaver 断点恢复/审批 Gate 在 1.2.11 下行为不变，无需回退；
  - 浏览器打断-注入-恢复演示（隔离环境）：pm-agent 至 prd_review Gate 挂起 → 注入约束 → ▸ 继续（checkpoint 续跑 revise）→ 新 PRD commit 逐条包含注入约束、回到 Gate → 批准后 succeeded。截图 `docs/i22-interrupt-inject-resume.png`。
- **M6 正式审阅通过（`b5668e9`，附录 B）**：审阅时点重跑 pytest 80/冒烟 12 全绿；三迭代 DoD 逐项核对；浏览器隔离复演「按标签分组看板」与「打断-注入-恢复」（截图 docs/m6-review-board-grouping.png、docs/m6-review-interrupt-resume.png）；console 噪声逐条查明非产品缺陷。
- **M7 已定义（`cd8b5dd`，docs/01 §F + docs/10 §4.7）**：调研 OpenProject 双层字段激活、n8n 模板市场、Plane/Focalboard 认证 → **M7 = 模板中心 + 项目级字段激活（I23-I25，约 9 人日）**；多人网络认证推迟 M8（横切改造，先做部署形态决策）。
- **I23 模板包注册表与浏览 API**：
  - 新模块 `app/apm/domains/template_packs.py`：注册表 = 本体目录活扫描（单一真源）+ 事件合成 provenance（`pack.registered` 启动幂等登记 + `ontology.imported` 复用导入登记；**未建表**，避免与目录双真源——偏差已记附录 A）；`GET /template-packs` 统一视图（含概念/状态/字段/阶段/CQ 摘要）、`GET /template-packs/{name}` 预览、`POST /template-packs/{name}/instantiate` 复用 `projects.post_project` 共链路；未知 404 / 校验失败与空名 422；
  - **新增冒烟 13**（导入 lite→统一列表→预览→实例化→阶段图与 CQ 就位→未知 404）。
- **I24 模板中心前端页**：
  - 新页 `web/src/pages/TemplatesPage.tsx`（`#/templates`）：浏览卡片（来源徽章 内置/导入/资产沉淀 + 概念/阶段/CQ 摘要）、预览抽屉（阶段流程含 Gate、概念表、CQ）、「用此模板建项目」表单（instantiate 后跳新项目看板）；入口 = 项目列表页按钮 + 侧栏全局「模板」项；
  - 资产联动：资产页卡片「🧩 沉淀为模板包」→ `POST /template-packs/from-asset`——以资产 provenance 解析来源项目本体，改名落盘 + 发 `pack.registered`（source=asset，含 asset_id/origin_ontology）；重复 409/坏名 422/无资产 404；
  - 浏览器验证三截图：docs/i24-template-center-preview.png、docs/i24-instantiate-board.png、docs/i24-asset-to-pack.png。
- **I25 项目级字段激活**：
  - `projects.field_overrides` JSON 列（停用字段 id 列表；schema+ALTER 迁移）；`project.field_disabled/enabled` 事件投影，rebuild 重放一致；
  - `PATCH /projects/{id}/fields`（未声明字段 422）；`_validate_custom_fields` 带项目级停用检查——停用字段 create/patch 写入 422；board 响应带 `disabled_fields`、`group_by=field:<停用>` 422（cf 读过滤保持可用，只限写与新维度选择）；前端：本体页「字段激活」面板（开关）+ Board 分组候选过滤；
  - 浏览器验证：本体页停用「标签」→看板选择器即刻无该维度（截图 docs/i25-field-deactivated-board.png）→启用恢复。
- **M7 正式审阅通过（`6ed9867`，附录 B）**：审阅时点 HEAD `7c0f7bb` 重跑 pytest 89/冒烟 13 全绿；I23/I24/I25 DoD 逐项核对；浏览器隔离复演「模板中心一键建项目」（自动跳新看板）与「字段停用-恢复」（截图 docs/m7-review-instantiate-board.png、docs/m7-review-field-deactivated.png）。
- **M8 已定义（`77aafbd`，docs/01 §G + docs/10 §M8）**：调研 Plane 两层角色模型（裁掉 workspace 层，留项目级 owner/contributor/viewer）、Gitea 首管理员+关注册+管理员建号（不做邮件邀请——Focalboard 邀请链接教训）、认证取舍（stdlib pbkdf2 + 签名 HttpOnly Cookie；`auth_mode=local/network` 双模，SSO 推迟 V3；部署形态定为可信小团队网络服务）→ **M8 = 多人网络协作（I26 认证基座 / I27 项目成员与角色 / I28 网络协作收尾，约 9 人日）**；遗留 B 级「users 无认证」由 M8 闭环。
- **I26 认证基座（本轮完成）**：
  - 新模块 `app/apm/core/security.py`：pbkdf2 哈希（stdlib，20 万迭代）、HMAC 签名会话 Token、实例 secret 持久化 `data_dir/secret.key`（重启会话存活）；
  - users 表加 `password_hash`/`is_admin`（ALTER 迁移）。**凭据不入事件**（附录 A）：密码是投影表运行时状态，rebuild 会清空——恢复路径 = 重启时 `APM_ADMIN_PASSWORD` 重引导（ensure_default_user 每次启动 reapplied）；
  - `POST /auth/login|logout` + `GET /auth/me`：登录成功/失败/登出均有 session.* 审计事件；HttpOnly SameSite=Lax Cookie；
  - `settings.auth_mode`：local（默认，现状零改动）/ network（middleware 对 /api 非 GET 强制会话，/api/auth/* 豁免）；`GET /users` 等出口 `_safe_user` 剥离凭据；
  - **新增冒烟 14**（network 门禁+审计+登出+local 零破坏）。
- **I27 项目成员与角色（本轮完成）**：
  - 新域 `app/apm/domains/members.py`：`project_members` 投影表 + `project.member_added/removed/role_changed` 事件（rebuild 存活）；建项目即发 member_added（creator=owner）；
  - 成员管理 API `GET/POST/PATCH/DELETE /projects/{id}/members`（owner 或实例管理员可管；末位 owner 保护 422；未知用户 422、非成员 404、重复 409）；`POST /users` 支持可选 password（管理员建号）；
  - network 写门禁升级：`project_id_for_path` 路径→项目解析（items/conversations/runs/approvals/artifacts 反查），viewer/非成员写 403 + `access.denied` 审计（admin 豁免）；前端本体页「项目成员」面板；
  - **边界（I28 收口）**：会话→actor 归账仍走 settings.user_id，登录人身份强制落 I28。
- **I28 网络协作收尾（本轮完成）**：
  - **会话→actor 归账打通**：events.py actor ContextVar（middleware 设登录人，线程池端点继承 context，域层零改动），emit 归账顺序=显式参 > 会话 > settings.user_id；冒烟 14 断言 qa-wang 写 item.created actor=qa-wang、自建项目 owner=qa-wang；
  - `/session/identity` network 模式 422（切换=登出重登）；前端 `/login` 登录页 + api 层 401 自动跳登录 + 顶栏按 `/auth/me` source 分流（session→⭐/👤+登出，local→原切换菜单）；
  - 部署文档 `docs/11-network-deploy.md`（auth_mode/admin_password/secret_key/TTL、管理员建号流程、角色与归账规则、nginx 反代 HTTPS+SSE）；
  - 浏览器验证（隔离 network 模式）：未登录写 401 → 登录页 → 模板建项目 → 顶栏 ⭐李雷+登出（截图 docs/i28-login-session-chip.png）。
- **I29 自动化规则域与执行引擎（本轮完成，目标协议更新为「持续调研开源+修缺陷+迭代至工程管理落地标准」后开工）**：
  - 新域 `app/apm/domains/automations.py`：规则即事件溯源（`automation_rules` 表 + `automation.rule_created/updated/deleted`，rebuild 存活）；
  - **执行器 = events post-emit hook**（events.py 增 `add_post_emit_hook`，emit 追加+投影+SSE 后同步调用；hook 异常只记日志不破坏写入；rebuild 不经 emit 天然不触发）——事件内核即事件源，无自建 dispatcher（docs/01 §H 结论落地）；
  - 规则模型：trigger 白名单 4 事件 × condition（concept_id+字段谓词）× 单动作白名单 fail-closed（assign/set_priority/set_field/set_status；创建即 422 校验，set_field 复用 `_validate_custom_fields`）；**防循环双保险**（automation actor 不进门 + dispatch 期 contextvar）；动作显式归账 actor_type=automation/actor_id=规则 id；set_field 合并现值再整列写（I20 整列覆盖教训）；
  - API：CRUD `/projects/{id}/automations`（M8 门禁自动生效）+ `/test` dry-run + `/runs` 历史；main.py lifespan `install_automation_engine()` 幂等装配；
  - **顺手修 domains/__init__ 投影注册清单漏 members/template_packs**（此前靠 main 导入链间接注册，非应用上下文 rebuild 会静默丢投影）；
  - 新增 test_automations.py 5 项 + **冒烟 15**；pytest **103** 项全绿、冒烟 **15** 条 GREEN。
- **I30 规则管理前端（本轮完成）**：
  - 本体页（项目设置）新增「自动化规则」面板：列表（触发徽章/条件摘要/动作摘要 + 测试运行/历史/启停/删除）、三段式新建表单（当〈事件〉→满足〈概念+可选谓词〉→则〈动作动态参数〉；enum 字段按本体声明出值下拉、multiselect 逗号分隔转数组、set_status 状态池按条件概念收窄）；
  - 测试运行 = `/test` dry-run toast；历史抽屉 = `/runs`（#事件号/已执行-被拒绝徽章/动作明细）；
  - api.ts 增 6 方法 + 4 类型（AutomationRule 等，action.value 多型）；
  - 浏览器隔离复演：UI 建两条规则 → API 建缺陷触发 → 看板卡片自动「👤 qa-wang + 严重度： P0」徽标 → 历史抽屉「#14 已执行」（截图 docs/i30-automation-panel.png、i30-automation-fired.png、i30-automation-board-card.png）。
- **I31 自动化收尾（本轮完成）**：
  - 审计页（AuditPage）发起者过滤增「⚡ 自动化」+ 域标签增 `automation`（rule_* 家族一键过滤）；
  - **docs/12-automation-guide.md 新建**：三段式模型、执行语义表（时机/归账/防循环/幂等教训/fail-closed）、测试运行与历史、权限与部署、backlog（出站 webhook、组合与区间条件）；
  - 浏览器演示：审计页 ⚡自动化 过滤命中 4 条（2 触发 + 2 动作，均按规则 id 归账），截图 docs/i31-audit-automation-filter.png。
- **M8 正式审阅通过（`978da42`+`630e91f`，附录 B）**：
  - 审阅时点 HEAD `dec89c3` 重跑 pytest 97/冒烟 14 全绿；I26/I27/I28 DoD 逐项核对（凭证与审计/三角色矩阵与 rebuild/归账断言）；
  - 浏览器双账号协作演示（隔离 network 模式）：登录页登录 → 建项目（Owner=李雷）→ 管理员建号 qa-wang → 成员面板加 Viewer → viewer 写 403（access.denied 四元组审计）→ 升 Contributor 写成功 → 审计时间线归账链 #16/#20/#21 完整；截图 docs/m8-review-login.png、m8-review-admin-members.png、m8-review-viewer-denied.png、m8-review-audit-attribution.png；
  - **审阅即修 2 处前端缺陷**：①AppShell 全局 rail 链接硬编码 `/assets`（I24 引入，「模板」侧栏图标不可达——此前演示走项目列表页按钮入口未暴露）改 `r.global ? r.to : ...`；②FeaturePage 空态文案「也可从看板手动建卡」过时（看板无此入口、NL L1 无建项意图）删除子句。修后 build+vitest 全绿；
  - console 噪声归因：401×2=登出后 /auth/me 轮询（network 预期）、403×1=门禁演示本体、连接拒绝=后端进程被系统回收后遗留标签页重连，均非产品缺陷。
- **M9 已定义（`630e91f`，docs/01 §H + docs/10 §M9）**：调研 Kanboard Automatic Actions（项目级「事件×动作」绑定+自省 API）、n8n/Node-RED 三段式抽象（trigger→condition→action，单机内嵌学模型不引编排器）、Plane Automations 与 webhook 重复触发教训（执行须幂等）→ **M9 = 看板自动化规则（I29 规则域与执行引擎 / I30 规则管理前端 / I31 收尾，约 9 人日）**；AgentPM 事件内核即天然事件源（订阅 event_bus，无需自建 dispatcher）；出站 webhook 留 backlog，SSO 维持 V3。
- **M9 三迭代完成（I29 `e6a779e` / I30 `d8dd982` / I31 `bcc264a`）**：
  - I29：`domains/automations.py`——规则事件溯源（automation_rules 表 + rule_* 事件，rebuild 存活）；执行器挂 events post-emit hook（`add_post_emit_hook`，同步调用、异常只记日志；rebuild 不经 emit 天然不触发）；trigger 白名单×condition 谓词×动作白名单 fail-closed；防循环双保险（automation actor 不进门 + dispatch contextvar）；动作归账 actor_type=automation；**顺手修 domains/__init__ 投影注册清单漏 members/template_packs**；单测 5 项 + 冒烟 15。
  - I30：本体页「自动化规则」面板（三段式新建表单、enum 按本体出值下拉、multiselect 逗号转数组、测试运行 dry-run、历史抽屉）；api.ts 6 方法 4 类型；OntologyPage.tsx 行尾归一 LF（docs/10 §8 标准）。
  - I31：审计页「⚡ 自动化」发起者过滤 + automation 域标签；docs/12-automation-guide.md 使用指南。
- **M9 正式审阅通过（`440e4ae`，附录 B）**：
  - 审阅时点 HEAD `064133f` 重跑 pytest 103/冒烟 15 全绿；I29/I30/I31 DoD 逐项核对（规则事件溯源与 rebuild/触发与 automation 归账/条件门与单层防循环/fail-closed 全矩阵/dry-run 不执行/面板与审计过滤）；
  - 浏览器隔离复演：UI 建「缺陷建卡即指派 QA」→ API 建缺陷 → 自动指派 qa-wang → 看板卡片自动徽标 → 审计页 ⚡自动化 过滤精确命中 #12 item.assigned + #13 rule_fired（同归账 ar_07f8a246c7）；截图 docs/m9-review-automation-card.png、docs/m9-review-audit-automation.png。
- **M10-I32 出站 webhook 基座（本轮完成，目标协议「持续调研+修缺陷+迭代」继续）**：
  - 新域 `app/apm/domains/webhooks.py`：`webhooks` 投影表 + `webhook.created/updated/deleted` 事件（rebuild 存活）；**secret 不入事件**（运行态：创建/rotate 一次性返回、rebuild 置空，同 users.password_hash 语义）；
  - **投递器 = 入队/投递分离**：post-emit hook `enqueue` 只入内存队列，`apm-webhooks` 守护线程投递——网络 I/O 零阻塞写路径（冒烟 16 断言写 <1s / 接收端 stall 2s）；
  - Gitea/GitLab 语义：`X-APM-Event/Delivery/Webhook/Signature` 头（原始 body HMAC-SHA256）；失败指数退避 3 次（RETRY_DELAYS 可 monkeypatch）→ `webhook.delivered/failed` 留痕（attempts=4）；订阅白名单 fail-closed（webhook.* 不可订阅→留痕事件不会二次投递）；
  - CRUD + rotate API（M8 门禁自动生效）；单测 4 项 + **冒烟 16**；
  - 自踩即修：worker 解析漏传 with_secret=True 致签名缺失——单测签名断言当场拦住。
- **M10-I34 通知中心与收尾（本轮完成）**：新域 `app/apm/domains/notifications.py`——通知=既有事件纯投影（item.assigned→被指派人、approval.requested→Owner、notification.sent→指定用户）；已读事件溯源；**通知 id 确定性 `n_{事件id}_{用户}`**（随机 id 会在 rebuild 后失配——新坑已记 §5）；automation 白名单增 `notify`；AppShell 顶栏 NotificationsBell（未读徽标+清单+全部已读）；docs/12 §7；单测 4 项（含身份泄漏还原夹具）+ 冒烟 16 扩展。
- **M10 正式审阅通过（`25b7ff6`，附录 B）**：
  - 审阅时点 HEAD `08af0c5` 重跑 pytest 113/冒烟 16 全绿；I32/I33/I34 DoD 逐项核对（secret 不入事件/rebuild 存活/签名逐字节比对/重试留痕 attempts=4/写路径零阻塞/replay-ping/通知纯投影/确定性 id/notify 防循环归账）；
  - 浏览器复演（python 接收桩）：UI 建 webhook → secret 弹窗 → API 建缺陷 → 接收桩实测签名投递（delivery ID 与留痕一致）→ 投递历史「已送达 HTTP 200 · 1次 · 15ms」→ 指派触发通知 → 铃铛徽标「1」；截图 docs/m10-review-webhook-history.png、docs/m10-review-notification-bell.png。
- **M11 已定义（本提交，docs/01 §J + docs/10 §M11）**：调研 Redmine 邮件通知（只做即时无内建 digest、SMTP 走环境配置层、外部 relay 推荐）与 Atom feed（per-user key 认证、私有项目数据曾泄漏进全局 feed #20173——权限裁剪按 key 用户可见性）→ **M11 = 邮件通知与 Atom 订阅（I35 邮件通道 SMTP env 可选未配则静默关闭 / I36 Atom 订阅 feed + feed key + 冒烟 17 / I37 通知偏好前端与收尾审阅，约 9 人日）**；digest、SSO/OIDC、本体版本事件级归档、移动端适配留 backlog。
- **M11-I35 邮件通知通道（本轮完成）**：
  - 新域 `app/apm/domains/mailer.py`：`APM_SMTP_HOST/PORT/USER/PASS/FROM/TLS` 环境变量可选（未配置=通道整体静默关闭，`smtp_configured()` 直通，行为与 M11 前一致；465 自动 SMTP_SSL、其余 STARTTLS 可关）；
  - **收件人决策单源化**：notifications.py 抽出 `plan_notifications(conn, event)` 纯函数，通知投影与邮件 hook 共用（两通道收件人永不失配）；post-emit hook 只入队 + `apm-mailer` 守护线程即时发送（EmailMessage 纯文本，超时 10s）；`email.notified/failed` 留痕（agg_id 确定性 `em_{源事件id}_{用户}`）；
  - 单测 5 项（默认关闭/即时发信/无邮箱跳过/故障留痕/慢 SMTP 不阻塞写路径）+ **冒烟 17**；**pytest 119 全绿、冒烟 17 GREEN、vitest/build 绿**。
- **M11-I36 Atom 订阅 feed（本轮完成）**：
  - users 加 feed_key（运行态凭据，CREATE+ALTER 迁移）；新域 `app/apm/domains/feed.py`；
  - GET /me/feed-key（查看/首次生成——owner 可反复读，与 webhook secret 一次性语义刻意区分）+ POST /me/feed-key/rotate（换发旧 key 即 401）；
  - GET /projects/{id}/feed.atom?key=：key 认证绕过 cookie；**权限裁剪防 Redmine #20173 式泄漏**（admin 全见/成员按角色/local 配置用户；非成员 403+access.denied 带 path）；Atom 1.0 XML（saxutils 转义、latest 30、content-type=application/atom+xml）；
  - 单测 3 项 + 冒烟 17 扩展 feed 断言；**pytest 122 全绿、冒烟 17 GREEN、vitest/build 绿**。
- **M11-I37 通知偏好前端与收尾（本轮完成）**：
  - users 加 `email_notify`（默认 1，CREATE+ALTER 迁移）；`POST /api/notifications/prefs`（按 effective_actor 更新自身）+ GET /notifications 响应带 `email_enabled`；mailer 入队过滤 `email_notify=0`——**开关语义：只停邮件、站内通知照常**（通知=事实投影，邮件=可选投递介质）；
  - NotificationsBell 增「通知偏好」区：邮件开关（即时 POST prefs）+ feed key 显示/换发/复制订阅链接；api.ts 增 setNotificationPrefs/getFeedKey/rotateFeedKey；
  - test_mailer 第 6 项（开关后邮件止、站内 unread 照增）；docs/12 §8「邮件通知与 Atom 订阅」（SMTP env 表 + 阅读器订阅指引）；**pytest 123 全绿、冒烟 17 GREEN、vitest/build 绿**。
- **M11 正式审阅通过（本提交，附录 B）**：
  - 审阅时点 HEAD `0270169` 重跑 pytest 123/冒烟 17 全绿；I35/I36/I37 DoD 逐项核对；
  - 浏览器隔离复演（隔离 data+ontologies + 本地 SMTP 接收桩 :2525）：UI 建项目 → API 建缺陷+指派 → 桩实测收信 → 审计链 #10→#11→#12 email.notified（docs/m11-review-mail-audit.png）→ QA 王 铃铛+偏好区（docs/m11-review-bell-prefs.png）→ 关邮件开关 → 二次指派：桩仍 1 封、铃铛「2」（邮件止站内照常）→ feed key+订阅链接（docs/m11-review-feed-key.png）→ 浏览器直开 feed.atom 渲染 XML（docs/m11-review-feed-atom.png）→ 局外人 key 403+access.denied；
  - **语义澄清（非缺陷）**：local 模式「当前配置用户 settings.user_id」恒可读 feed=单机可信既定语义；探针须先固定配置身份再验 403（坑已记 §5）。
- **M10-I33 webhook 前端与运维（本轮完成）**：
  - 后端运维端点：`_deliver` 增 retries 参数；`POST /webhooks/{id}/replay/{delivery_id}`（按留痕事件回放原始载荷、新 delivery ID、单次尝试）、`POST /webhooks/{id}/ping`（合成 ping 载荷）；均落留痕事件；
  - 前端本体页「Webhooks 出站」面板：创建表单（URL+订阅芯片）、**secret 一次性弹窗**（rotate 换发）、Ping/投递历史/换发/启停/删除、投递历史抽屉（已送达/失败徽章+重发）；api.ts 增 7 方法 + 2 类型；
  - docs/12 §6 Webhooks 出站章节（投递语义表 + 接收方验签 Python 示例：原始字节 HMAC + 常量时间比较 + delivery 去重）；
  - 浏览器验证：python 接收桩实测签名投递（验 HMAC、delivery ID 与留痕一致）→ 历史抽屉 → UI 重发 → 接收桩收第二条新 delivery ID（截图 docs/i33-webhook-secret-modal.png、i33-webhook-delivery-history.png）。
- **M10 已定义（`64ca1de`，docs/01 §I + docs/10 §M10）**：调研 Gitea/GitLab webhook（HMAC-SHA256 对原始 body 签名、X-Gitea-Event/Delivery 头幂等去重、明文 token 已被 GitLab legacy 化）、Redmine（邮件通知+feeds 是自托管桌上前提；规则化通知由 Redmineflux 插件验证为真实需求）→ **M10 = 出站集成：webhook 与通知（I32 webhook 基座——后台投递线程，post-emit hook 只入队绝不阻塞写路径（与 M9 同步执行器的本质差异）/ I33 webhook 前端与运维 + 冒烟 16 / I34 站内通知中心 + automation notify 动作，约 9 人日）**；邮件/RSS、SSO/OIDC、本体版本事件级归档、移动端适配留 backlog。
- **M12 已定义（本提交，docs/01 §K + docs/10 §M12）**：三路调研——OpenProject 报表分层（社区版=custom query+widget+My page，高级报表企业版；→ 报表=投影查询+widget 拼装）、SSO/OIDC（独立 IdP+OIDC client 主流，Gitea JIT 受限；维持 V3）、GitLab 审计事件（DB 永久保留+流式外送；→ 归档=导出而非删除）→ **M12 = 报表与跨项目工作台（I38 报表数据层纯投影 API / I39 报表前端与项目工作台 / I40 CSV+docs/12 §9+冒烟 18+审阅，约 9 人日）**；SSO（V3）、事件导出归档、移动端、高级自定义报表留 backlog。
- **M12-I38 报表数据层（本轮完成）**：
  - 新域 `app/apm/domains/reports.py`——**纯投影查询，无新表无新事件**（rebuild 一致性由构造保证，测试仍显式断言）；GET /projects/{id}/report（五桶漏斗+概念分布+pending Gate+超期/滞留+近 14 天吞吐）、GET /my/work（**指派即授权**+Gate 仅 owner/instance admin）、GET /projects 列表补 item_counts+gates_pending；
  - 超期口径：cf 声明 due（ISO 日期）早于今日→「超期 N 天」，否则活跃项创建超 14 天→「滞留」（docs/12 §9 于 I40 收口）；
  - 初版成员可见性过滤方案废弃——与「被指派者须见自己的工作」冲突，指派即授权；
  - test_reports.py 4 项；**pytest 127 全绿、冒烟 17 GREEN**。
- **M12-I39 报表前端与项目工作台（本轮完成）**：
  - ReportsPage（`#/p/{pid}/reports`）：五桶漏斗条形+概念 chips、挂起 Gate 卡片、超期/滞留清单（reason 徽标）、14 天吞吐双色柱图；全局 MyWorkPage（`#/my/work`）：分配给我+等我决策；rail 增「报表」「我的工作」；PickerInner 行健康徽标；api.ts 增 ProjectReport/MyWork + 2 方法；
  - 浏览器验证：报表页数字与 API 一致、列表徽标、QA 王 3 项 vs 李雷 0 项+1 待决策（截图 docs/i39-reports-page.png、i39-picker-health.png、i39-my-work.png）；build+vitest 绿；
  - 坑：独立脚本 emit 必须先 `import apm.domains`（注册投影器）且带 APM_DATA_DIR（首轮探针误入 dev 库已按「drop trg→删行→重建 trg」清理复原）。
- **M12-I40 报表收尾（本轮完成）**：
  - CSV 导出 `GET /projects/{id}/report.csv`（section,key,title,reason,value 五列，与 JSON 同数）；docs/12 §9 报表与工作台（入口对照+五项口径定义+权限语义）；**新增冒烟 18**（漏斗/吞吐/Gate/my-work/CSV 同数/列表摘要/rebuild 不变）；pytest **128** 全绿、**冒烟 18 GREEN**。
- **M12 正式审阅通过（本提交，附录 A/B）**：
  - 审阅时点 HEAD `179e3bb` 重跑 pytest 128/冒烟 18 全绿；I38/I39/I40 DoD 逐项核对（纯投影三端点+rebuild 一致/口径边界/指派即授权/CSV 与 JSON 同数/冒烟 18 全程）；
  - 浏览器隔离复演：报表页漏斗 4/0/1/1/0 + Gate「◆ PRD 评审」+ 滞留清单 + 吞吐 6/1（docs/m12-review-reports-page.png）；CSV curl 十二行逐行核对；qa-wang 我的工作 3 项跨项目聚合（docs/m12-review-my-work.png）；无新增 B/C 级意见。
- **M13-I41 里程碑域与工作项日期（本轮完成）**：
  - 新域 `domains/milestones.py`：milestones 投影表 + milestone.* 事件（rebuild 存活；**drop_projections 清单补 milestones**——新投影表必经此步否则重放撞 UNIQUE）；CRUD + 进度（done 比例 + 逾期数）+ 状态校验优先本体 milestone 概念 states；
  - items 加 start_date/due_date（CREATE+ALTER），ISO 校验 422，created/updated 透传；PATCH /items 支持 milestone_id（未知/跨项目 422）；报表超期口径三级回退（item.due_date → cf → 滞留，docs/12 §9 已同步）；
  - test_milestones.py 4 项；pytest **132** 全绿、冒烟 18 GREEN。
- **当前验证状态**：pytest **132 项全绿**；冒烟基线 **18 条全绿**；`pnpm vitest`/`pnpm build` 绿。
- **M13 已定义（本提交，docs/01 §L + docs/10 §M13）**：三路调研——OpenProject Gantt（三类工作包×依赖连线×时间轴，依赖传播核心语义）、Plane v1.16 Milestone（deadline 锚点，与 Cycles 正交→只做 Milestone）、GitLab 导出/备份（导出仅补充、备份走 DB 层）→ **M13 = 里程碑与时间线（I41 里程碑域与工作项日期：milestone.* 事件溯源 + items 加 start_date/due_date 列 + 进度 + 报表口径升级 / I42 时间线视图：条形/菱形/depends_on 箭头与冲突标红，不做依赖自动传播 / I43 事件 NDJSON 导出 + docs/11 备份章节 + docs/12 §10 + 冒烟 19 + 审阅，约 9 人日）**；依赖自动传播改期、Cycles、SSO、移动端留 backlog。
- **M13-I42 时间线视图（本轮完成）**：
  - TimelinePage（`#/p/{pid}/timeline`，rail「时间线」）：日期轴自适应+周刻度+今日线、概念分行条形、里程碑菱形（悬停进度）、depends_on 冲突红条+行底虚线（不自动改期）；api.ts 增 Milestone 4 方法 + getItem；**顺带补 I41 缺口：ItemIn 支持 milestone_id（创建即关联，fail-closed 校验+投影持久化）** + test_milestones 第 5 项；
  - 浏览器验证（隔离环境）：菱形悬停进度/冲突红条+行底虚线/日期轴刻度（截图 docs/i42-timeline.png）；build+vitest 绿；
  - 坑：browser_navigate 同 hash URL 不重载 SPA（React Query 缓存旧值）→ location.reload() 强刷；同行 SVG 连线被条形遮住 → 走行底边缘。
- **M13-I43 时间线收尾（本轮完成）**：
  - 事件 NDJSON 导出 `GET /projects/{id}/events/export`（全局追加序+prev 链位+校验和行 events/sha256/first_prev/gaps；per-project 导出首行 prev 指向全局链、跨项目间隙属正常——初版严格链断言被冒烟纠正）；
  - docs/11 §5 备份与恢复（导出≠备份；WAL .backup 在线快照；恢复=rebuild 校验）；docs/12 §10 里程碑与时间线；
  - **新增冒烟 19**（里程碑全程+NDJSON 链序+rebuild 一致）；pytest **134** 全绿、**冒烟 19 GREEN**。
- **M13 正式审阅通过（本提交，附录 A/B）**：
  - 审阅时点 HEAD `edecddd` 重跑 pytest 134/冒烟 19 全绿；I41/I42/I43 DoD 逐项核对（里程碑 CRUD+rebuild/校验矩阵/进度计算/日期校验/创建即关联/时间线四要素/NDJSON 链序+校验和）；
  - 浏览器隔离复演：时间线页日期轴+今日线+里程碑菱形（悬停 33%）+冲突红条+行底虚线（docs/m13-review-timeline.png）；进度 API 实测与菱形一致；NDJSON 导出 35 事件+校验和行实测；无新增 B/C 级意见。
- **M14 已定义（本提交，docs/01 §M + docs/10 §M14）**：三路调研——OpenProject 15.4 自动排程（手动默认+可选自动，Finish-to-Start 顺延）、WeKan PWA（自托管移动端务实路线，下一轮）、GitLab NDJSON 管线（导出/导入同构）→ **M14 = 排程自动化与事件可携（I44 依赖传播自动排期：items.auto_scheduled + item.rescheduled 显式事件 + 递归防环 / I45 事件 NDJSON 导入恢复：校验和/链序/冲突 409 + roundtrip / I46 docs+冒烟 20+审阅，约 9 人日）**；PWA、约束类型、原生 App 留 backlog。
- **M14-I44 依赖传播自动排期（本轮完成）**：
  - items 加 `auto_scheduled`（默认 0=手动，ALTER 迁移，PATCH 开关）；前置项 due 变更触发 `propagate_reschedule`——对 depends_on 其且开自动的后继平移 start/due（保时长），**显式 item.rescheduled 事件**（follow_of/delta_days/depth，投影持久化）；递归深度 20 + visited 防环；
  - test_scheduling.py 4 项（单级+归因/手动零影响/多级+环安全/rebuild 存活）；时间线 hover「⏱ 自动排期」；**pytest 138 全绿、冒烟 19 GREEN、build+vitest 绿**。
- **M14-I45 NDJSON 导入恢复（本轮完成）**：
  - `POST /projects/{id}/events/import`：校验和重算（原始行 sha256）+ schema/id 递增校验 + 冲突 409 整批拒绝（恢复面向空/新库）+ 目标项目可不存在但 payload 必含其 project.created；按序直插（保留原始 id/ts，prev 重链目标头部）→ 全量 rebuild；
  - roundtrip 测试（monkeypatch data_dir + db.reset_for_tests 切第二全新库）+ 拒绝矩阵；**pytest 140 全绿、冒烟 19 GREEN**。
- **M14-I46 排程与可携收尾（本轮完成）**：
  - docs/12 §11 排程自动化与事件可携（语义/审计/导入流水线）；docs/11 §5.3 恢复步骤更新（import 端点实操）；
  - **新增冒烟 20**（A←B←C 自动排期传播 + 导出→第二全新库导入 roundtrip + 恢复库 rebuild 一致）；pytest **141** 全绿、**冒烟 20 GREEN**。
- **M14 正式审阅通过（`73f7667`，附录 A/B）**：
  - 审阅时点 HEAD `b1f93cb` 重跑 pytest 141/冒烟 20 全绿；I44/I45/I46 DoD 逐项核对（单级传播保时长+归因/手动零影响/多级+环安全/rebuild 存活；roundtrip 事件流与投影逐行一致/拒绝矩阵六例/冒烟 20 全程；docs/12 §11 与 docs/11 §5.3 在位）；
  - 浏览器隔离复演：「依赖链-设计→开发→测试」三级链全开自动排期 → PATCH A due +6 → B/C 自动顺延（时间线 hover「⏱ 自动排期」，docs/m14-review-timeline.png）；审计页 item.rescheduled ×2 逐条 follow_of/delta_days=6（docs/m14-review-audit-rescheduled.png）；无新增 B/C 级意见。
- **M15 已定义（本提交，docs/01 §N + docs/10 §M15）**：三路调研——WeKan PWA 安装形态（官方商店 App=指向演示服务器的 TWA，自托管无用→可安装 PWA 指向自己的实例才是正路，修正 §M.2）、Focalboard/Plane 移动策略（Focalboard 移动 web cramped + 移动 App 已废弃、Plane 无 PWA 纯响应式→同类移动端普遍短板）、vite-plugin-pwa（generateSW + autoUpdate + SPA 导航回退；**/api/* 一律 network-only 不入 SW 缓存**——事件溯源必须在线，离线写分叉一致性）→ **M15 = PWA 与移动端适配（I47 响应式布局基座 / I48 PWA 可安装与离线外壳 / I49 移动端打磨+docs/12 §12+冒烟 21+审阅，约 9 人日）**；离线写、Push 推送、原生 App/TWA 留 backlog。
- **M15-I47 响应式布局基座（本轮完成，`f287725`+`983f843`）**：
  - AppShell 窄屏断点（<768px）：rail 与功能列 `hidden md:flex` 折叠；topbar 汉堡按钮开**移动导航抽屉**（slide-over：12 项导航 + 项目功能区，遮罩/✕/导航后自动关闭）；⌘K 窄屏只留图标；审批/通知铃 `h-9 w-9` 触控目标；
  - 修窄屏折行：身份 chip `whitespace-nowrap shrink-0`（曾竖排）、通用 Badge `whitespace-nowrap`；
  - 表格/栅格适配：看板列表 table `overflow-x-auto` + `min-w-[640px]`；Reports/MyWork/Dashboard `grid-cols-1 md:grid-cols-3`（**col-span 必须加 md: 前缀——1 列网格下 span 3 会生成隐式轨道撑破布局**）；时间线 `overflow-auto` + `min-w-[640px]`；
  - 验证：build+vitest 绿、pytest 141 不受影响；Playwright 375×812 五截图 + 1440 桌面复核（docs/m15-i47-*.png ×6）。
- **M15-I48 PWA 可安装与离线外壳（本轮完成，`16ce83e`+`87d3262`）**：
  - vite-plugin-pwa v1.3.0（generateSW + autoUpdate）+ workbox-window 显式依赖；manifest standalone/icons 192+512+maskable（PIL 生成）；tsconfig types 补 `vite-plugin-pwa/client`；
  - **`/api/*` 永不入 SW 缓存**：navigateFallbackDenylist + 零 runtimeCaching——事件溯源数据必须在线；
  - **审阅即修 2 个既有前端缺陷**：①sonner `<Toaster>` 从未挂载（历次 toast 全部静默）→ main.tsx 补挂；②ProjectPicker 离线/故障误弹「新建项目」模态（空库引导与错误态混淆）→ `autoOpen={!isError && 空列表}`；
  - 实测：precache 7 项零 /api、caches 枚举零 /api、**断网 reload 外壳完整载入**、新 SW 静默接管、离线 modal 不再误弹；375px 生产构建正常（docs/m15-i48-*.png ×3）；
  - 坑：pnpm 下 virtual:pwa-register 需显式装 workbox-window，否则 Rollup resolve 失败。
- **M15 三迭代完成（I47 `f287725`/I48 `16ce83e`/I49 `3d86ecf`）**：响应式布局基座（窄屏汉堡抽屉 + 横滚 + 栅格响应式 + 触控目标）→ PWA 可安装与离线外壳（vite-plugin-pwa generateSW+autoUpdate，`/api` 永不入缓存）→ 收尾（冒烟 21 + docs/12 §12 + docs/11 §4.1 + 关键路径触控复核）。
- **M15 正式审阅通过（`771b366`，附录 A/B；该提交同时把 HANDOFF.md 行尾 CRLF 归一为 LF——仓库 §8 标准，全文 diff 属预期）**：
  - 审阅时点 HEAD `8fb1499` 重跑 pytest 142/冒烟 21/vitest 2 全绿；I47/I48/I49 DoD 逐项核对（窄屏折叠与抽屉/横滚与栅格/precache 零 /api 双验证/断网 reload 外壳/autoUpdate 接管/冒烟 21 产物深检/关键路径触控）；
  - **审阅即修 3 个既有前端缺陷**：①sonner `<Toaster>` 全仓从未挂载（历次 toast 静默）；②ProjectPicker 空库引导与加载失败混淆（离线误弹新建模态）；③通知下拉 375px 左溢 25px；
  - 浏览器隔离复演（隔离 data+ontologies + vite preview 生产构建）：375px 视口 14 张截图（docs/m15-i47/i48/i49-*.png + m15-review-timeline-375.png）；无新增 B/C 级意见。
- **M16 已定义（本提交，docs/01 §O + docs/10 §M16）**：三路调研——OpenProject 自定义查询分层（保存过滤/分组/排序是 Community 免费核心、跨项目聚合才是 Enterprise→做社区层等价）、Gitea SSO JIT 痛点（注册无 allowlist #27709、group claim 二次登录生效 #32566→需 IdP 演示环境成本高，降下一轮候选）、通知 digest（Redmine 靠插件/GitLab 仅专项摘要→同类均无原生，已有三层降噪，留 backlog）→ **M16 = 自定义视图与保存筛选（I50 视图数据层 saved_views 投影+view.* 事件+定义校验 fail-closed / I51 视图前端（保存/切换/管理+共享徽标+URL 直开）/ I52 默认视图+docs/12 §13+冒烟 22+审阅，约 9 人日）**。
- **M16-I50 视图数据层（本轮完成，`668aced`+`06ae4a2`）**：
  - 新域 `domains/views.py`：saved_views 投影表 + view.* 事件（rebuild 存活）；CRUD；定义校验双层 fail-closed（键白名单 + 字段须声明且**未停用**——cf 分支漏停用检查被单测拦住补上）；权限对齐 M8（local 放行 / network public 成员读、private owner+admin、viewer 不可建、非成员 403）；
  - **执行纯复用**：get_items/get_board 增 view_id（definition 为基础过滤、显式 query 参覆盖）；`_cf_hit` 提取模块级共用；
  - 测试踩坑：字段 id 是 `tags`（非 concept.field 全称）、停用 API `{field_id, active}`、tags 值 frontend/backend/infra、network 写请求须先 /auth/login；**pytest 146/冒烟 21**。
- **M16-I51 视图前端（本轮完成，`010f5f1`+`eebe385`）**：看板工具栏「视图」管理器（保存当前过滤+公开勾选、下拉切换应用 definition 写回 URL params、公开徽标、hover 删除、退出视图保留过滤）；**直开 ?view=<id> 自动补齐 definition 参数**（显式 params 优先）；api.ts SavedView+4 方法；复演：保存→切换→直开还原全过（docs/m15-i51-*.png ×5）。**复演坑：改前端代码后生产构建页面须 SW update+reload 才见新 UI**（autoUpdate precache 旧 bundle）。
- **M16-I52 收尾（本轮完成，`71e61c1`+`7d35d41`）**：默认视图（made_default 事件先清后设 rebuild 幂等 + is_default 列 + board 无参落点 applied_view_id + 前端 chip/徽标/分组控件同步）；**修 db.py 迁移条件 bug**（表名误查列名集合 → ALTER 永不执行，隔离存量库 500 暴露——**演示隔离库才是存量迁移的真测试场**）；docs/12 §13；**新增冒烟 22**；pytest **147** 全绿、冒烟 **22** GREEN。
- **M16 正式审阅通过（本提交，附录 A/B）**：
  - 审阅时点 HEAD `8b37d72` 重跑 pytest 147/冒烟 22/vitest 2 全绿；I50/I51/I52 DoD 逐项核对（事件溯源 CRUD+rebuild/双层 fail-closed 校验/M8 可见性矩阵/执行同数/URL 直开还原/默认视图直达/冒烟 22 全程）；
  - **审阅即修 1 个后端缺陷**：db.py 存量迁移条件把表名误查进列名集合致 ALTER 永不执行（隔离存量库 500 暴露）；
  - 浏览器隔离复演（隔离 data+ontologies + vite preview 生产构建）：视图保存/切换/公开徽标/URL 直开/默认直达（docs/m15-i51-*.png ×5 + m15-i51-made-default.png + m15-i52-default-landing.png）；无新增 B/C 级意见。
- **M17 已定义（本提交，docs/01 §P + docs/10 §M17）**：三路调研——FastAPI OIDC 模式（Authlib 事实标准：code flow + PKCE + state 存短命 cookie，复用 M8 HMAC 会话签发、握手后不缓存 id_token）、本地 IdP 取舍（Keycloak realm import 一键演示 vs Authelia 手工 YAML → 单测用本地 RSA JWT 桩离线覆盖、演示用 Keycloak compose）、Gitea 教训四约束（JIT 一次性定角色幂等不提升 #32566 反向规避 / allowlist 双层 #27709 / email 可信校验 / 账号不自动合并 409）→ **M17 = OIDC 单点登录（I53 OIDC client 基座+JWT 桩单测 / I54 会话整合与前端 / I55 Keycloak 演示环境+docs/12 §14+冒烟 23+审阅，约 10 人日）**；env 未配置=特性静默关闭（SMTP 同款）。
- **M17-I53 OIDC client 基座（本轮完成，`82f748c`+`30d21d5`）**：
  - `core/oidc.py` 零新依赖（RS256 验签自实现，cryptography RSA PKCS1v15+SHA256 + jwks kid 匹配）；discovery 缓存 / code flow + PKCE S256 / state 三元组 HttpOnly 短命 cookie / id_token 全校验（alg/签名/iss/aud/exp/nonce）；
  - **JIT 四约束**（Gitea 教训）：email_verified 必须 / allowlist `APM_OIDC_ALLOWED_GROUPS` fail-closed / 同 email 幂等重入 / 同名本地账号 409 不合并；**角色一次性定 viewer、重登不重派**（规避 #32566）；env 未配置整体 404；
  - 单测 5 项：本地 RSA JWT 桩（monkeypatch oidc.httpx）离线覆盖全协议路径 + 拒绝矩阵七例；**pytest 152/冒烟 22**；
  - **坑：TestClient 默认 follow_redirects=True**，302 到外部 IdP 后的 404 极易误判为路由缺失——OIDC 端点断言必须 `follow_redirects=False`。
- **当前验证状态**：pytest **152 项全绿**；冒烟基线 **22 条全绿**；`pnpm vitest`/`pnpm build` 绿。

## 3. 现在卡在哪

**没有硬阻塞。** 遗留 B/C 级意见（docs/10 附录 B/C）：本体学习/版本面板 apply 无权限分层（V2 治理）；本体版本快照无事件级归档；users 无认证 → **M8-I26 闭环**；OpenProject 式「类型+项目双层激活」已于 M7-I25 落地。

## 4. 下一步是什么（按序）

1. **I54 会话整合与前端**（M17 第 2 迭代，docs/10 §M17）：`GET /auth/me` source 增加 `oidc` 标注（或顶栏 chip 显示）→ 前端 `/login` 页 OIDC 按钮（`GET /api/auth/oidc/status` 探测特性开关，关闭不显示）→ 本体页 admin「OIDC 配置」面板（issuer/client id/allowlist 展示，secret 不回显）→ network 门禁/角色对 OIDC 用户兼容断言（JIT viewer 写 403）→ build+vitest 绿 + 桩全流程浏览器复演 → 「M17-I54」三段式提交。
2. I55 Keycloak 演示环境（tools/keycloak compose + realm import）+ docs/11 §2 扩展 + docs/12 §14 + 冒烟 23 + M17 正式审阅。

## 5. 有哪些坑不要再踩

- **投影器 INSERT 的列序与参数元组必须逐列目视核对**（I20 踩坑，连续三处错）：加列时参数插错位（cf 插到 priority 后、列在 estimate_hours 后）→ assignee 列错位存值；占位符个数改了两次才对（16 列 = 15 `?` + 字面量 1）。**单用例可能过、套跑才炸，别信单绿**。
- **`sets.append(a, b)` 双参 TypeError**：item.updated 投影隐藏 bug，被 custom_fields 首次踩中——新键接入既有投影器时把整段逻辑读一遍。
- **起服务做演示/审阅必须同时隔离 data 与 ontologies**：env `APM_DATA_DIR` + `APM_ONTOLOGY_DIR_OVERRIDE`（还要 `cp -r ontologies/. <override目录>/`，override 目录不会自动建文件）；**只设 APM_DATA_DIR 不够**（M4 审阅污染源文件事故）。
- **replay_templates.py 模板函数必须定义在 `_TEMPLATES` 字典之前**（import 时求值，放后面 = NameError）。
- **测试/冒烟绝不写真实 `ontologies/` 源目录**：用 conftest `isolated_ontologies`（已同时隔离 agents/ 树）；改本体相关代码要 `reload_all()`。
- **夹具 teardown 顺序**：monkeypatch 还原晚于夹具后置代码——`isolated_ontologies` 必须先显式清 override 再 reload，否则隔离副本残留缓存→跨用例"unknown concept"。
- **diff 的 from/to 语义不对称**（I15）：from 快照优先、to=当前版本永远读活文件；两边同源 diff 恒空。
- **测试造信号必须发真实事件**（带 project_id）；sqlite Row 无 `.get()`；`Ontology.concepts` 是 dict；`asset_links.target_ref` 是 JSON 字符串；事件 append-only 触发器强制。
- **前端是 HashRouter**：浏览器直接导航要用 `/#/p/{pid}/board`（不带 `/#` 会落在项目列表页，别当成 bug 查后端）。
- **打/恢复演示（或相关测试）的确定性时序**：run 由后台线程执行，"interrupted" 状态 = 挂在 Gate 待评审；注入 = 对话内发消息（engine 把 run 开始后的用户消息收集为 constraints）；恢复 = ▸ 继续（resume 端点可带 instruction，Gate 挂起时走 revise）。参考 `app/tests/test_runtime.py` 的 `test_interrupt_inject_resume_*`。
- **演示环境 console 会有 404/连接拒绝噪声**：长命浏览器标签页会跨隔离库轮询旧会话 ID、并在关服后持续重连——审阅时逐条核对来源再下结论，别当成产品缺陷，也别忽略。
- **写自动化相关断言先想清「活规则已在造数阶段触发过」**（I29 单测+冒烟各踩一次）：规则一建好，后续造的每条数据都可能真实触发动作——别拿已被活规则改过的状态去证明 dry-run 不执行；要验证静默就把所有规则都停用再数事件。
- **`items` 投影对 custom_fields 是整列覆盖**（I20 踩坑、I29 再防一次）：任何「改一个字段」的路径都必须合并现值后再发 item.updated，直接透传部分 dict 会清掉其他字段。
- **投影器新生成实体的 id 禁止随机**（I34 踩坑）：通知 id 初版用 new_id，rebuild 后 id 漂移、已读事件引用失配、未读数回弹——投影中新实体 id 必须由事件流确定性导出（如 `n_{事件id}_{用户}`）。**单测 rebuild 断言要直接对比 id/未读数**。
- **/api/session/identity 全局改 settings.user_id 会跨用例泄漏**（local 模式全局身份的固有语义）：依赖 effective_actor 的测试，文件内加身份还原夹具（保存→yield→还原）。
- **改源码一律用 Edit 工具，禁 heredoc/python 脚本做源码修改**（I35 踩坑两次）：`\t`/`\n` 多层转义污染源文件；regex 探针误删 mailer.py 中段——探针脚本只读不改；临时调试探针提交前必须清理（grep 探针标记）。**python 写文本文件必须 `write_bytes` 或 `write_text(..., newline="\n")`**（I50 踩坑：Windows 默认把 \n 转 CRLF，整文件行尾漂移制造全文 diff 噪声，已两次归一）。
- **权限裁剪探针受 settings.user_id 全局身份影响**（M11 审阅踩坑）：local 模式「当前配置用户」恒放行（单机可信语义）——用 /me/feed-key 造 key 再测 403 时，先 /session/identity 固定配置身份为管理员，否则被测用户恰是配置身份会假性 200。
- **commit 纪律**：迭代号前缀；冒烟基线只增不减；范围变更先记 docs/10 附录 A。小本体主义是硬约束（概念 ≤12、字段 ≤10、关系 ≤6，校验器会拦）；别引入 RDF/SPARQL/推理机（docs/08 §2 取舍）。
- **全局导航入口的 to 映射别硬编码**（M8 审阅踩坑）：AppShell rail 曾把所有 global 入口写死 `/assets`，模板入口静默失效一个里程碑——因为存在备用入口（项目列表页按钮），常规演示没暴露。加导航项时逐条点一遍图标。
- **演示中后端后台进程可能被系统回收**（Windows exit 1073807364）：长演示中途截图前先探 `GET /api/health`，别把连接拒绝误判为产品问题；遗留标签页的 SSE/审批轮询会持续重连刷 console 噪声。

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 142 项，应全绿
python tools/smoke/run_smoke.py       # 冒烟基线 21 条，应 GREEN（repo 根目录跑）
# 前端
cd web && pnpm install && pnpm dev    # http://localhost:5173
# 后端（演示/审阅时必须隔离：APM_DATA_DIR + APM_ONTOLOGY_DIR_OVERRIDE 且拷贝本体进去！）
cd app && python -m uvicorn apm.main:app --port 8000 --reload
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`；本体 `app/apm/domains/ontology.py` + 学习 `ontology_learn.py` + 版本化 `ontology_versions.py` + CQ `ontology_cq.py` + 模板包 `ontology_pack.py` + 模板注册表 `template_packs.py` + 用户 `users.py` + 工作项（含 custom_fields 校验/过滤）`items.py`；LLM 角色 `agents/roles/ontology-curator.yaml` + 回放模板 `app/apm/runtime/replay_templates.py`；前端本体页 `web/src/pages/OntologyPage.tsx`、模板中心 `web/src/pages/TemplatesPage.tsx`、看板 `web/src/pages/Board.tsx`（字段分组选择器+徽标）、外壳 `web/src/components/AppShell.tsx`（身份菜单）。
