# HANDOFF —— 写给下一个新会话（2026-09-02 更新 · M5 全部完成并通过正式审阅）

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

### M5 · V1.x 协作与归纳增强（2026-09-02 启动）
- 调研（**已完成，别重查**）：semantica v0.6.7 Semantic Extraction = 方法降级链 `llm→ml→pattern` + 置信度 0.65–0.85 + 实体级 provenance，结论在 docs/01 §C.3.1。本项目 L1–L4 规则即链中 pattern 层。
- **I17 LLM 辅助归纳（本轮完成，commit `a244899`）**：
  - 新角色 `ontology-curator`（`agents/roles/ontology-curator.yaml` + 提示词 `agents/prompts/roles/ontology-curator.md`，输出契约 = 纯 JSON 候选）；
  - `POST /api/ontologies/{name}/learn-llm`：上下文组装 → Provider Adapter（回放模板 `ontology-curator/curate` 确定性产出"命名覆盖的工件→资产沉淀"建议；openai 模式 = 真实抽取）→ JSON 归一化 → confidence<0.65 丢弃 → 与 pattern 候选按 id **去重合并**（`provenance.channels` 标 pattern/llm 双通道 + rationale）→ **apply 共用同一校验/版本化/事件链路**；
  - JSON 损坏/provider 异常 → 优雅降级（llm.error），pattern 层不受影响（fallback 链精神）；
  - 前端学习面板加「✨ LLM 建议」按钮 + LLM 徽标/confidence/rationale/层统计行；
  - **B 级修复**（M4 审阅遗留）：`cq-check` 的 events 证据按本体项目过滤（保留全局 project_id='' 事件）。
- **I18 本体模板包（完成，commit `4873523`）**：
  - `GET /api/ontologies/{name}/export`：单 JSON 包（format=`agentpm-ontology-pack`）= ontology.yaml + 概念引用的角色 YAML + 角色提示词模板（L4）；缺角色文件记 `missing_roles` 不阻断。
  - `POST /api/ontologies/import`：`as_name` 改名防冲突（已存在 **409**）→ 校验器把关（422）→ 角色文件「存在即复用、缺失才创建」（**绝不覆盖既有角色/提示词**）→ 落盘 → 热重载本体+角色注册表 → `ontology.imported` 事件落审计流。
  - Settings 新增 `agents_dir_override`，conftest `isolated_ontologies` 夹具现在**同时隔离 agents/ 树**；前端本体页有「⬇ 导出模板包」「⬆ 导入」。
- **I19 多人协作基础（本轮完成，commit `9813d01`）**：
  - `app/apm/domains/users.py`：users 表 = `user.registered/updated` 事件投影（rebuild 可重建）；启动自举默认用户（李雷/u_admin，users 空才发事件）；`GET /api/users`、`POST /api/users`（ASCII slug / 中文姓名 u+短随机 id）、`POST /api/session/identity`（切换落 `session.identity_switched` 事件，from/to 可审计）。
  - **emit 身份透传**：`core/events.emit` actor_id 运行时读 `settings.user_id`，全仓清扫了五处域函数硬编码——切换身份后一切操作归新身份审计流。
  - human 指派必须为注册用户（422 fail-closed）、items 附 `assignee_name`；`GET /api/events?actor_id=`、`GET /api/approvals?decided_by=`；前端顶栏身份切换菜单（注册+切换+当前高亮）。
  - **夹具坑修复**：`isolated_ontologies` teardown 会先显式清 override 再 reload（monkeypatch 还原晚于夹具后置代码，否则隔离副本残留缓存→跨用例"unknown concept"污染）。
- **M5 正式审阅（通过，commit `cf53199`）**：pytest 75 项绿、冒烟基线 **12 条**全绿（冒烟 9 = 双身份按人可分审计流）；浏览器实测：注册「QA 王」→ 自动切换 → 本体页「✨ LLM 建议」2 条候选（0.72）→ 应用 → v2 时间线；导出/导入入口在位。截图 `docs/m5-review-collab-page.png`。**本次演示正确隔离了 data+ontologies（M4 教训落实）。**
- **当前验证状态**：pytest **75 项全绿**；冒烟基线 **12 条全绿**；`pnpm build`/`pnpm vitest` 通过。

## 3. 现在卡在哪

**没有硬阻塞。** 遗留 B/C 级意见（docs/10 附录 B/C）：本体学习/版本面板 apply 无权限分层（V2 治理范畴）；本体版本快照无事件级完整 YAML 归档（"从事件重建任意版本"留作备选）；users 无认证（单机身份选择，非登录鉴权——多人**网络协作**属 V1.1 后续）。

## 4. 下一步是什么（按序）

1. **M5 已收口，按目标第 5 条开启新一轮调研 → 更新计划（M6）→ 继续开发**。调研候选（按价值排序）：
   - **未完成的调研**：OpenProject/Plane 类型系统与自定义字段演进（上轮搜索超时，别当成已调研）；
   - **LangGraph 版本升级评估**（docs/10 §8 风险表挂账项）；
   - **多人网络协作**：认证（登录态）+ WebSocket/SSE 多端同步（V1.1 主线深化）；
   - **本体/资产模板市场**（08 §6 V3）：模板包已就绪，差分享通道。
2. 每轮照旧：调研结论入 docs/01 → 更新 docs/10 里程碑 → 实现首个迭代（测试/冒烟全绿）→ 提交 → 看板/日志 → 更新本文件。

## 5. 有哪些坑不要再踩

- **起服务做演示/审阅必须同时隔离本体目录**：M4 审阅时 apply 把候选写回了真实 `ontologies/software-dev.yaml`（演示只隔离了 data 目录），污染源文件、差点打破冒烟基线（learn 断言依赖未声明字段）。已还原。做法：环境变量 `APM_ONTOLOGY_DIR_OVERRIDE=<演示目录>`（Settings 的 ontology_dir_override 字段会被 BaseSettings 读 env）；**只设 APM_DATA_DIR 不够**。
- **replay_templates.py 的模板函数必须定义在 `_TEMPLATES` 字典之前**：字典字面量 import 时求值，函数放字典后 = NameError（I17 踩过，表现为 learn-llm 降级 unavailable）。
- **测试/冒烟绝不能写真实 `ontologies/` 源目录**：测试必须用 conftest 的 `isolated_ontologies` 夹具；改完本体相关代码要 `reload_all()` 清缓存。
- **diff 的 from/to 语义不对称**（I15 踩坑）：from 侧快照优先、to 侧当前版本永远读活文件。两边同源则 diff 恒空；两边都读快照则手改影响分析失效。
- **apply 会双写同号快照**：连续两次 apply 会重写同版本快照文件，以"该版本被 supersede 时的内容"为准。
- **测试造信号必须发真实事件**（`item.related`/`run.requested`/`asset.*`/`approval.*`），不要直插投影表；**事件记得带 project_id**（I17 起 CQ 证据按项目过滤，漏带会被当全局事件或漏计）。正式测试曾漏 emit 导致 learn 没候选——先怀疑测试数据再怀疑代码。
- **sqlite Row 没有 `.get()`**（用 `row["col"]`）；`Ontology.concepts` 是 dict（`.values()` 遍历）；`asset_links.target_ref` 是 JSON 字符串（json.loads）。
- **本体为全局 YAML**（`ontologies/*.yaml`）项目按名引用；事件 append-only 有触发器强制；Windows + Git Bash：POSIX 路径、pytest 在 `app/` 下跑；`.playwright-mcp/` 的 console log 别提交。
- **commit 纪律**：提交信息带迭代号；冒烟基线只增不减；范围变更先记 docs/10 附录 A 再动代码。semantica 取舍（不做 RDF/SPARQL/推理机/双时态）见 docs/08 §2/§8.1，别引入重型机制——小本体主义是硬约束（校验器会拦）。

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 75 项，应全绿
python tools/smoke/run_smoke.py       # 冒烟基线 12 条，应 GREEN（repo 根目录跑）
# 前端
cd web && pnpm install && pnpm dev    # http://localhost:5173
# 后端（演示/审阅时加 APM_ONTOLOGY_DIR_OVERRIDE 与 APM_DATA_DIR 隔离！）
cd app && python -m uvicorn apm.main:app --port 8000 --reload
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`；本体 `app/apm/domains/ontology.py` + 本体学习 `app/apm/domains/ontology_learn.py`（含 learn-llm LLM 层）+ 本体版本化 `app/apm/domains/ontology_versions.py` + CQ 检查 `app/apm/domains/ontology_cq.py` + 模板包 `app/apm/domains/ontology_pack.py` + **用户/身份 `app/apm/domains/users.py`**；LLM 角色 `agents/roles/ontology-curator.yaml` + 回放模板 `app/apm/runtime/replay_templates.py`；编排 `app/apm/orchestrator/`；前端本体页 `web/src/pages/OntologyPage.tsx`。
