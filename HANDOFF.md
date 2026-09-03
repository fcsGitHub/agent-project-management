# HANDOFF —— 写给下一个新会话（2026-09-03 更新 · M10-I32 完成，下一步 I33 webhook 前端与运维）

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
- **当前验证状态**：pytest **108 项全绿**；冒烟基线 **16 条全绿**（16 = webhook 全程）；`pnpm vitest`/`pnpm build` 绿。
- **M10 已定义（`64ca1de`，docs/01 §I + docs/10 §M10）**：调研 Gitea/GitLab webhook（HMAC-SHA256 对原始 body 签名、X-Gitea-Event/Delivery 头幂等去重、明文 token 已被 GitLab legacy 化）、Redmine（邮件通知+feeds 是自托管桌上前提；规则化通知由 Redmineflux 插件验证为真实需求）→ **M10 = 出站集成：webhook 与通知（I32 webhook 基座——后台投递线程，post-emit hook 只入队绝不阻塞写路径（与 M9 同步执行器的本质差异）/ I33 webhook 前端与运维 + 冒烟 16 / I34 站内通知中心 + automation notify 动作，约 9 人日）**；邮件/RSS、SSO/OIDC、本体版本事件级归档、移动端适配留 backlog。

## 3. 现在卡在哪

**没有硬阻塞。** 遗留 B/C 级意见（docs/10 附录 B/C）：本体学习/版本面板 apply 无权限分层（V2 治理）；本体版本快照无事件级归档；users 无认证 → **M8-I26 闭环**；OpenProject 式「类型+项目双层激活」已于 M7-I25 落地。

## 4. 下一步是什么（按序）

1. **M10-I33 开工：webhook 前端与运维**（docs/10 §M10）：项目设置页「Webhooks」面板——URL/事件订阅多选（白名单）/启停/删除 + secret 一次性显示与 rotate 重置；投递历史抽屉（`/api/events?agg_type=webhook&agg_id=` 查 delivered/failed：attempts/status_code/duration_ms）；手动重发（按 delivery 事件重放 payload、新 delivery ID——需后端补 replay 端点）+「测试 ping」；docs/12 增接收方验签章节。
2. I34 站内通知中心（notifications 投影 + 顶栏铃铛）+ automation `notify` 动作 → **M10 正式审阅**（冒烟 16 + DoD + 演示：webhook 投递留痕 + 通知中心）。
3. 审阅通过后：新一轮开源调研（目标协议第 1 条）→ 定 M11（候选：邮件/RSS 通知、SSO/OIDC、本体版本事件级归档、移动端适配）。

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
- **commit 纪律**：迭代号前缀；冒烟基线只增不减；范围变更先记 docs/10 附录 A。小本体主义是硬约束（概念 ≤12、字段 ≤10、关系 ≤6，校验器会拦）；别引入 RDF/SPARQL/推理机（docs/08 §2 取舍）。
- **全局导航入口的 to 映射别硬编码**（M8 审阅踩坑）：AppShell rail 曾把所有 global 入口写死 `/assets`，模板入口静默失效一个里程碑——因为存在备用入口（项目列表页按钮），常规演示没暴露。加导航项时逐条点一遍图标。
- **演示中后端后台进程可能被系统回收**（Windows exit 1073807364）：长演示中途截图前先探 `GET /api/health`，别把连接拒绝误判为产品问题；遗留标签页的 SSE/审批轮询会持续重连刷 console 噪声。

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 103 项，应全绿
python tools/smoke/run_smoke.py       # 冒烟基线 15 条，应 GREEN（repo 根目录跑）
# 前端
cd web && pnpm install && pnpm dev    # http://localhost:5173
# 后端（演示/审阅时必须隔离：APM_DATA_DIR + APM_ONTOLOGY_DIR_OVERRIDE 且拷贝本体进去！）
cd app && python -m uvicorn apm.main:app --port 8000 --reload
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`；本体 `app/apm/domains/ontology.py` + 学习 `ontology_learn.py` + 版本化 `ontology_versions.py` + CQ `ontology_cq.py` + 模板包 `ontology_pack.py` + 模板注册表 `template_packs.py` + 用户 `users.py` + 工作项（含 custom_fields 校验/过滤）`items.py`；LLM 角色 `agents/roles/ontology-curator.yaml` + 回放模板 `app/apm/runtime/replay_templates.py`；前端本体页 `web/src/pages/OntologyPage.tsx`、模板中心 `web/src/pages/TemplatesPage.tsx`、看板 `web/src/pages/Board.tsx`（字段分组选择器+徽标）、外壳 `web/src/components/AppShell.tsx`（身份菜单）。
