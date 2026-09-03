# HANDOFF —— 写给下一个新会话（2026-09-03 更新 · M7 三个迭代完成，待正式审阅）

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
- **I23 模板包注册表与浏览 API（本轮完成）**：
  - 新模块 `app/apm/domains/template_packs.py`：注册表 = 本体目录活扫描（单一真源）+ 事件合成 provenance（`pack.registered` 启动幂等登记 + `ontology.imported` 复用导入登记；**未建表**，避免与目录双真源——偏差已记附录 A）；`GET /template-packs` 统一视图（含概念/状态/字段/阶段/CQ 摘要）、`GET /template-packs/{name}` 预览、`POST /template-packs/{name}/instantiate` 复用 `projects.post_project` 共链路；未知 404 / 校验失败与空名 422；
  - **新增冒烟 13**（导入 lite→统一列表→预览→实例化→阶段图与 CQ 就位→未知 404）。
- **I24 模板中心前端页（本轮完成）**：
  - 新页 `web/src/pages/TemplatesPage.tsx`（`#/templates`）：浏览卡片（来源徽章 内置/导入/资产沉淀 + 概念/阶段/CQ 摘要）、预览抽屉（阶段流程含 Gate、概念表、CQ）、「用此模板建项目」表单（instantiate 后跳新项目看板）；入口 = 项目列表页按钮 + 侧栏全局「模板」项；
  - 资产联动：资产页卡片「🧩 沉淀为模板包」→ `POST /template-packs/from-asset`——以资产 provenance 解析来源项目本体，改名落盘 + 发 `pack.registered`（source=asset，含 asset_id/origin_ontology）；重复 409/坏名 422/无资产 404；
  - 浏览器验证三截图：docs/i24-template-center-preview.png、docs/i24-instantiate-board.png、docs/i24-asset-to-pack.png。
- **I25 项目级字段激活（本轮完成）**：
  - `projects.field_overrides` JSON 列（停用字段 id 列表；schema+ALTER 迁移）；`project.field_disabled/enabled` 事件投影，rebuild 重放一致；
  - `PATCH /projects/{id}/fields`（未声明字段 422）；`_validate_custom_fields` 带项目级停用检查——停用字段 create/patch 写入 422；board 响应带 `disabled_fields`、`group_by=field:<停用>` 422（cf 读过滤保持可用，只限写与新维度选择）；前端：本体页「字段激活」面板（开关）+ Board 分组候选过滤；
  - 浏览器验证：本体页停用「标签」→看板选择器即刻无该维度（截图 docs/i25-field-deactivated-board.png）→启用恢复。
- **当前验证状态**：pytest **89 项全绿**；冒烟基线 **13 条全绿**（13 = 模板注册表+字段激活往返）；`pnpm build`/`pnpm vitest` 通过。

## 3. 现在卡在哪

**没有硬阻塞。** 遗留 B/C 级意见（docs/10 附录 B/C）：本体学习/版本面板 apply 无权限分层（V2 治理）；本体版本快照无事件级归档；users 无认证（单机身份选择，网络协作属 V1.1 后续）；OpenProject 式"类型+项目双层激活"暂缓（需项目级本体覆盖机制）。

## 4. 下一步是什么（按序）

1. **M7 正式审阅**（docs/10 §M7）：冒烟 13 + I23/I24/I25 DoD 核对 + 浏览器演示（模板中心建项目复演 I24 路径；字段停用-恢复复演 I25 路径）+ 附录 B 审阅记录 + 审阅截图。
2. M7 审阅通过后：**新一轮开源调研**（目标第 5 条）→ 定 M8。首选多人网络认证（按 Plane 两层成员模型裁剪：全局用户→项目成员、角色、邀请；先决策部署形态：单机 vs 网络服务），候选还有看板自动化规则（Kanboard 三段式，docs/01 §E 已备案）。
3. 调研后按新计划继续迭代开发。

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
- **commit 纪律**：迭代号前缀；冒烟基线只增不减；范围变更先记 docs/10 附录 A。小本体主义是硬约束（概念 ≤12、字段 ≤10、关系 ≤6，校验器会拦）；别引入 RDF/SPARQL/推理机（docs/08 §2 取舍）。

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 89 项，应全绿
python tools/smoke/run_smoke.py       # 冒烟基线 13 条，应 GREEN（repo 根目录跑）
# 前端
cd web && pnpm install && pnpm dev    # http://localhost:5173
# 后端（演示/审阅时必须隔离：APM_DATA_DIR + APM_ONTOLOGY_DIR_OVERRIDE 且拷贝本体进去！）
cd app && python -m uvicorn apm.main:app --port 8000 --reload
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`；本体 `app/apm/domains/ontology.py` + 学习 `ontology_learn.py` + 版本化 `ontology_versions.py` + CQ `ontology_cq.py` + 模板包 `ontology_pack.py` + 模板注册表 `template_packs.py` + 用户 `users.py` + 工作项（含 custom_fields 校验/过滤）`items.py`；LLM 角色 `agents/roles/ontology-curator.yaml` + 回放模板 `app/apm/runtime/replay_templates.py`；前端本体页 `web/src/pages/OntologyPage.tsx`、模板中心 `web/src/pages/TemplatesPage.tsx`、看板 `web/src/pages/Board.tsx`（字段分组选择器+徽标）、外壳 `web/src/components/AppShell.tsx`（身份菜单）。
