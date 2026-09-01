# HANDOFF —— 写给下一个新会话（2026-09-02 更新）

> 你是完全没有任何上下文的新会话。先读完本文件，再按「下一步」开工。**不要重新调研已调研过的东西，不要重做已完成的事。**

## 1. 我们在做什么

**AgentPM**（`D:\project\agent-project-management`）：一套「人指挥、Agent 执行」的项目管理 Web 系统。项目生命周期建模为图（阶段+Gate+任务），角色化 Agent（PM/架构/计划/开发/测试/发布，YAML 声明）执行，人在审批门批准/拒绝/改后恢复；事件溯源记录一切；工件 Markdown 入 Git；本体（ontology YAML）是项目类型系统；资产库沉淀可复用工件。

**长期目标（用户设定，持续有效）**：
1. 接管并持续迭代优化本项目；
2. 融合开源项目 **semantica**（semantica-agi/semantica）的本体构建模式进项目管理；
3. 每轮结束：上下文占用超 30% 就压缩；
4. 每轮结束：更新本文件 HANDOFF.md（新会话先读它再继续）；
5. 开发计划完成一轮后：调研相关开源、吸收优点、更新设计与开发计划、继续推进。

**进度真源**：[docs/10-development-plan.md](docs/10-development-plan.md) §7 状态看板——发现任何文档与代码不一致，以看板为准并即时修正。

## 2. 已经完成什么

### MVP（I0–I13，全部完成，2026-08-22 终验通过）
后端 FastAPI + 事件溯源内核（append-only events + 投影器 + rebuild）+ LangGraph Runtime（角色子图、录制回放 provider、SqliteSaver）+ Orchestrator（阶段状态机、Gate→审批）+ 对话域（消息树、打断/恢复、提示词 L1–L4）+ 资产域（Git 仓 + FTS5 + 沉淀/检索/双链）+ NL 命令 L1 + 前端 React 全套页面 + docker-compose 一键起。冒烟基线当时 7 条。

### M4 · 本体构建闭环（semantica 融合，2026-09-02 启动）
- 调研结论（不要重查）：semantica v0.6.7 的本体构建核心 = `OntologyGenerator.generate_ontology(data)`（infer_classes/infer_properties，无 LLM）、每条推断带 provenance、VersionManager（diff/migrate）、CQ 验收锚点。裁剪映射见 **docs/08 §8**。
- **I14 本体归纳（本轮完成，commit `2583172`）**：
  - `POST /api/ontologies/{name}/learn`：四条确定性规则扫描该本体下所有项目的投影数据 → 候选提案（带 provenance：规则 id/support/样本 id）+ observations（零使用概念）。规则：L1 字段显式化（priority/estimate_hours 在用未声明）、L2 关系补注册（遗留未注册 relation_type）、L3 沉淀链接补全（deposits_to 缺失）、L4 角色覆盖（runs 实际角色未绑定概念）。
  - `POST /api/ontologies/{name}/apply`：勾选候选 → patch 合并 → 校验器 → 写回 `ontologies/<name>.yaml`（version+1）→ `ontology.updated` 事件 → 热重载。幂等（已应用的候选不再提出）；未知/过期候选 422。
  - 前端本体页新增「🔬 本体学习」面板（扫描→勾选→应用）。
- **当前验证状态**：pytest **55 项全绿**（app/ 下跑）；冒烟基线 **11 条全绿**（`python tools/smoke/run_smoke.py`，报告在 tools/smoke/reports/latest.md）；`pnpm build` / `pnpm vitest` 通过。

## 3. 现在卡在哪

**没有硬阻塞。** 唯一注意项：本轮尚未起 docker compose / 浏览器手动过一遍本体页面板（测试覆盖了 API 与交互逻辑，UI 仅 pnpm build + vitest 验证）。若你要做 M4 正式审阅，按 10 §5 补一次浏览器演示路径即可。

## 4. 下一步是什么（按序）

1. **I15 · 本体版本化语义 diff 与迁移**（docs/10 M4 表，估 3d）：`GET /api/ontologies/{name}/diff?from=&to=`——结构化语义 diff（concepts/relations/phases/assetKinds 增删改）+ 影响分析（删除被引用概念 → 阻塞影响清单）；`ontology.updated` 事件历史查询。DoD 见 10；并入冒烟 8 扩展。
2. **I16 · CQ 可回答性检查**（估 3d）：competencyQuestion 映射到投影表/事件类型，`GET /api/ontologies/{name}/cq-check` 报告覆盖状态；本体页 CQ 卡片显示。
3. **M4 审阅**：冒烟 + docs/08 §8.3 验收锚点四项 + 浏览器演示。
4. M4 之后：按目标第 5 条再调研一轮开源（候选方向见 docs/10 附录 C / docs/07 §5 扩展路线），更新计划，继续推进。

## 5. 有哪些坑不要再踩

- **测试/冒烟绝不能写真实 `ontologies/` 源目录**：本体学习会写回 YAML。测试必须用 conftest 的 `isolated_ontologies` 夹具（拷贝到 tmp + `config.settings.ontology_dir_override`，Settings 上加了 override 字段）。改完本体相关代码要 `reload_all()` 清缓存。
- **sqlite Row 没有 `.get()`**：投影查询结果用 `row["col"]` 取值；可选列值可能为 None，不要 `row.get()`。
- **`Ontology.concepts` 是 dict**（`{id: Concept}`），不是 list；遍历用 `.values()`。
- **asset_links.target_ref 是 JSON 字符串**（投影时 json.dumps），解析用 `json.loads`，不是 yaml。
- **事件 → 投影是唯一数据路径**：测试造 runs/assets 数据用 `events.emit(...)` 发真实事件（如 `run.requested`、`asset.drafted/published/linked`、`item.related`），不要直接 INSERT 投影表——否则破坏「live == replay」一致性（冒烟 7 会抓）。注意 `run.requested` 只被投影消费、不触发引擎副作用（已验证）。
- **本体为全局 YAML**（`ontologies/*.yaml`），项目按名引用；不要假设有项目级本体文件。
- **事件 append-only 有触发器强制**，任何 UPDATE/DELETE events 直接报错——这是设计。
- **Windows + Git Bash 环境**：仓库内路径一律 POSIX 风格、LF；pytest 在 `app/` 目录下跑（`cd app && python -m pytest`）；前端在 `web/`（pnpm）。
- **commit 纪律**：提交信息带迭代号（如 `M4-I15: ...`）；冒烟基线只增不减；范围变更先记 docs/10 附录 A 再动代码。
- `.playwright-mcp/` 下的 console log 是历史遗留未跟踪文件，与代码无关，别提交它。
- **文档表述**：项目自述"事件溯源 + 本体驱动"；semantica 融合的取舍（不做 RDF/SPARQL/推理机/双时态）写在 docs/08 §2/§8.1，别在新代码里引入这些重型机制——小本体主义是约束（概念 ≤12、自定义关系 ≤6 等，校验器会拦）。

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 55 项，应全绿
python tools/smoke/run_smoke.py       # 冒烟基线 11 条，应 GREEN（repo 根目录跑）
# 前端
cd web && pnpm install && pnpm dev    # http://localhost:5173
# 后端
cd app && python -m uvicorn apm.main:app --port 8000 --reload
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`；本体 `app/apm/domains/ontology.py` + **本体学习 `app/apm/domains/ontology_learn.py`**；角色运行时 `app/apm/runtime/`；编排 `app/apm/orchestrator/`；前端本体页 `web/src/pages/OntologyPage.tsx`。
