# AgentPM —— 基于 Agent 的项目管理系统 · 方案设计

> 版本：v0.4（2026-08-22，新增开发执行计划；v0.3 含两轮评审意见修订）
> 定位：一套以「人指挥、Agent 执行」为核心的项目管理 Web 系统的完整方案设计，覆盖需求 → 设计 → 开发 → 测试 → 交付全生命周期。

## v0.4 修订说明（本轮新增：开发执行计划）

| 要求 | 落点 |
| --- | --- |
| 制定可用于执行的开发计划：审阅迭代、按计划持续推进完成开发；尽量复用开源、避免从头自研 | **10 全新分册**：五条军规（复用优先三问/禁自研清单/小步可审/冒烟累积制/录制回放确定性）、I0-I13 迭代计划（M1 内核与数据 → M2 人机闭环 → M3 完整 MVP，每迭代带 DoD 与演示路径）、审阅迭代机制（审阅包三件套 + 意见 A/B/C 分级处置 + 变更控制）、跨会话持续推进协议、**状态看板 = 唯一进度真源** + 开发日志/审阅记录附录 |

## v0.3 修订说明（本轮新增：累计资产设计）

| 评审意见 | 落点 |
| --- | --- |
| 补充累计资产设计：产品库/测试库/文档库，方便累积资产、资产管理与检索 | **09 全新分册**：工件 vs 资产边界、沉淀三路径（手动/Gate 建议/复盘挖掘）、消费四通道（建项引用/Agent 工具/模板/回流）、FTS→向量检索分级、入库治理与审计、资产仓存储与资产库页面 |
| 资产管理划归本体 | 08 §3 概念模型新增 `assetKinds[]`/`libraries[]`，工件 `deposits-to` 沉淀映射；§5 驱动点加资产库行；02/03/04/06/07 全部联动（资产服务、流程 9、assets/asset_links 表、📚 资产库页、MVP 范围与冒烟断言） |

## v0.2 修订说明（回应评审 5 条意见）

| 评审意见 | 落点 |
| --- | --- |
| 1. 从用户使用流程梳理，明确典型使用流程 | 03 全册重写：8 条详细剧本（流程 0-8）+ 功能完备性核对表 |
| 2. 补充真实可用 agent 调研（deepseek harness、轨迹×图可视化、pi-agent 极简 runtime、dsh 插件化） | 01 新增 C 部分（dsh=DeepSeek Harness、pi、semantica）；05 §3.5 Graph×Trajectory 联动视图 |
| 3. 使用层级：项目下挂功能、功能下挂对话；提示词按层披露；可持久化随时打断更改 | 03 §1-§3（层级模型/提示词四层/打断全景）；02 §2.5/§3；04 新增 features/conversations/messages/prompt_layers |
| 4. 支持自然语言操作页面 | 06 §5 自然语言操作层（UI-Agent，与页面同构 API）；07 MVP 含 L1 级 |
| 5. 增加本体模块（参考 semantica 简化） | 08 全新分册；01 C.3 取舍分析；04/06/07 相应联动 |

## 电梯陈述

AgentPM 把软件项目的**管理流程本身建模为一张可编排的图（Project Graph）**：节点是阶段与任务，边是依赖与工件传递；**人类是图的编排者与审批者**，角色化 Agent（PM/架构/计划/开发/测试/发布）是图的执行者。导航沿**项目 → 功能 → 对话**三层下钻：对话是持久、可打断、可恢复的人机交互原子单元，提示词按层（项目宪章/功能简报/会话指令）披露与编辑。系统以**事件溯源**记录一切人与 Agent 的操作，天然产出**人机交织的轨迹**与**不可变审计日志**；阶段产物以 **Markdown/Git 工件**落盘，可 diff、可评审、可回滚；页面既可点击操作，也可**一句话操作**。项目类型由**本体**定义（内置软件研发/通用两套，YAML 可定制）；**值得复用的工件经入库评审沉淀为组织级资产**（产品库/测试库/文档库），供所有项目的 Agent 检索复用——项目是临时的，资产是复利的。

## 方案文档导航

| 文档 | 内容 | 回应的需求 |
| --- | --- | --- |
| [docs/01-open-source-research.md](docs/01-open-source-research.md) | 开源调研：agent 框架 + 项目管理工具 + **真实可用产品（dsh/pi/semantica）** + 轨迹/审批生态 | 需求 1 / 评审 2 |
| [docs/02-overall-design.md](docs/02-overall-design.md) | 核心理念（含会话为中心、本体驱动）、导航层级×信息深度、系统架构、技术选型 | 需求 2/5 |
| [docs/03-lifecycle-and-usage-flow.md](docs/03-lifecycle-and-usage-flow.md) | **层级模型 + 提示词分层 + 随时打断 + 8 条详细使用剧本 + 功能完备性核对表** + 生命周期六阶段 | 需求 3 / 评审 1/3 |
| [docs/04-data-model-and-persistence.md](docs/04-data-model-and-persistence.md) | 数据模型（含功能/对话/消息树/提示词层）、事件溯源、轨迹 schema、检查点与工件 | 需求 2 |
| [docs/05-hitl-trajectory-audit.md](docs/05-hitl-trajectory-audit.md) | 人机协作、Graph 编排、审批工作流、**四种轨迹视图（含 Graph×Trajectory 联动）**、审计 | 需求 2/5 / 评审 2 |
| [docs/06-webui-design.md](docs/06-webui-design.md) | WebUI 信息架构、页面线框（含功能页/对话视图）、**自然语言操作层**、新手/专家双模式 | 需求 4 / 评审 4 |
| [docs/07-mvp-and-roadmap.md](docs/07-mvp-and-roadmap.md) | MVP 范围（含对话/NL L1/本体/资产库）、模块拆解、API 概要、扩展路线 | 需求 6 |
| [docs/08-ontology.md](docs/08-ontology.md) | **项目本体模块**：概念/关系/阶段图 + **资产类型与库注册**，semantica 简化设计 | 评审 5 / 评审 6 |
| [docs/09-asset-library.md](docs/09-asset-library.md) | **资产库与知识沉淀**：产品/测试/文档三库、沉淀-复用飞轮、检索、治理 | 评审 6 |
| [docs/10-development-plan.md](docs/10-development-plan.md) | **开发执行计划**：迭代划分（I0-I13）、每迭代 DoD 与演示路径、审阅迭代机制、复用纪律、状态看板（唯一进度真源） | 需求 6 / 开发要求 |

> 🖥️ **交互式演示**：[demo.html](demo.html) —— 主要用户流程的可点击前端原型（浏览器直接打开，静态模拟数据、无后端）。视觉与交互对标 **Linear / Plane / Huly** 的开源设计语言（shadcn/ui 质感 + Lucide 图标，正式实现复用清单见 07 §2.5）。内置 **15 步引导剧本**（对应 03 册流程 0–9）：建项目 → PRD 起草 → 提示词分层披露 → Gate 审批 → 看板派工 → 执行对话 → 打断-修改-恢复 → Graph×轨迹联动 → 自然语言操作 → 资产沉淀入库 → 检索复用 → 审计回溯；也可自由浏览 Dashboard/看板/图/对话/Runs/资产库/审计/本体设置八个页面，审批、打断、入库等操作会实时改写状态并落入审计事件流。

## 核心设计决策（TL;DR）

| # | 决策 | 来源与理由 |
| --- | --- | --- |
| D1 | **流程即图**：项目生命周期建模为 DAG，人编排、Agent 执行 | LangGraph + graph engineering；可控、可审计、可局部重跑 |
| D2 | **事件溯源**：append-only 事件表，状态 = fold(events) | OpenHands/dsh；一次存储支撑状态、轨迹、审计三投影 |
| D3 | **工件即文件**：PRD/设计/WBS 均为 Markdown 入 Git 仓 | MetaGPT workspace；可 diff、可评审、人机同读 |
| D4 | **interrupt + 审批恢复**：阶段门与危险动作挂起，人批准/改态后 resume | LangGraph 原语 + dsh fail-closed/单次授权 |
| D5 | **状态五桶 + 本体驱动生命周期**：桶固定、组内状态由本体定义 | Plane + OpenProject 可配置类型 |
| D6 | **三级工具权限 + deny-by-default** | AgentScope/OpenHands/Oso 安全模型 |
| D7 | **轨迹 schema 对齐 OTel GenAI semconv** + apm.* 扩展（节点/对话锚点） | 可导出 Langfuse/Phoenix；MVP 内置轻量存储 |
| D8 | **渐进披露 WebUI**：默认看板+推进，高级功能收进命令面板与抽屉 | Leantime/Plane；提示词同样分层披露 |
| D9 | **声明式角色（YAML）+ 能力缝**：角色/压缩/审批/持久化皆可替换 | CrewAI YAML + dsh "Everything is a Plugin" |
| D10 | **API-first**：REST 覆盖全部资源，页面与 NL 命令共用同一 API | Plane/Taiga；NL 与 UI 同构的前提 |
| D11 | **会话为中心**（v0.2）：项目→功能→对话，消息树（id/parentId）支持分支血统 | dsh 会话日志 + pi 会话树；交互前中后同上下文 |
| D12 | **提示词四层披露**（v0.2）：L0 全局/L1 宪章/L2 简报/L3 指令/L4 角色，可见可编辑可版本化 | 评审 3；dsh "模型可见即入日志" |
| D13 | **自然语言即操作**（v0.2）：UI-Agent 把意图翻译为应用 API，只读直执/写预览确认/全量审计 | 评审 4；与页面同构故低成本高覆盖 |
| D14 | **本体驱动的类型系统**（v0.2）：ontology.yaml 编译出类型/看板/阶段图/角色挂点/NL 词典 | 评审 5；semantica 简化（CQ/受控关系/本体即数据） |
| D15 | **极简纪律**：内核（agent loop+事件+投影）保持小，特性先问"能否用文件/简单机制替代" | pi 标尺（418 行 loop/<1000 token 提示词） |
| D16 | **资产沉淀闭环**（v0.3）：工件经入库评审沉淀为组织级资产，带来源/引用双链，Agent 可检索复用并再沉淀 | 评审 6；"项目是临时的，资产是复利的"；资产类型与库由本体注册（D14 延伸） |

## 一图看懂

```
┌───────────────────────── WebUI（渐进披露 + NL 双通道）─────────────────────────┐
│ Dashboard │ 功能页(看板/对话/工件) │ 对话视图 │ Graph │ Runs │ 资产库 │ 审计·本体  │
│        ⌘K 命令栏 = 命令模式 + 自然语言模式（UI-Agent）· 🔔审批中心               │
└────────────────────────────────────┬───────────────────────────────────────────┘
                                     │ REST + SSE（同一 API 服务页面与 NL）
┌────────────────────────────────────▼───────────────────────────────────────────┐
│                          应用服务（FastAPI）                                     │
│  项目/功能 │ 对话服务(消息树/打断/提示词分层) │ 工作项(本体驱动) │ 审批 │ 轨迹   │
│  NL 命令路由 │ 本体服务(校验/编译) │ 资产服务(沉淀/检索/双链) │ Orchestrator    │
├────────────────────────────────────────────────────────────────────────────────┤
│              Agent Runtime（LangGraph，能力缝：压缩/审批/持久化可替换）          │
│        角色Agent(YAML): PM/Architect/Planner/Dev/QA/Release/UI-Agent           │
│        资产工具: search_assets / read_asset / link_asset                       │
├────────────────────────────────────────────────────────────────────────────────┤
│                 事件总线（append-only；live 与 replay 同一投影）                 │
│   工作项事件 │ 对话/消息事件 │ Agent运行事件(Span) │ 审批事件 │ ui_command │ 本体 │
│   资产事件(asset.*)                                                          │
├──────────────────────────────┬─────────────────────────────────────────────────┤
│ 内容仓（Git，每项目一仓）      │ 元数据存储（SQLite→PG）                           │
│ artifacts/ · prompts/        │ events / features / conversations / messages /   │
│ ontology/ontology.yaml       │ runs / spans / approvals / checkpoints /         │
│         ▼                    │ assets / asset_links (+FTS5)                     │
│ 资产仓（Git，全局一仓）        │                                                 │
│ libraries/<库>/<资产>         │                                                 │
└──────────────────────────────┴─────────────────────────────────────────────────┘
```

## 开发与运行（实现已就绪）

MVP 已按 [docs/10-development-plan.md](docs/10-development-plan.md) 迭代 I0–I13 完成：后端 FastAPI + 事件溯源内核 + LangGraph Runtime + 本体驱动域，前端 React（复刻 demo.html 设计令牌），冒烟基线 7 条全绿（`tools/smoke/`）。MVP 后持续迭代（M4）：融合 semantica 本体构建模式——**本体学习**（I14，从项目数据归纳本体变更候选：扫描→人审→应用，带 provenance，冒烟基线增至 11 条）；I15 语义 diff / I16 CQ 检查进行中。

```bash
# 一键起（Docker）
docker compose up -d --build
python tools/seed.py                 # 灌入演示数据（回放模式，无需 LLM key）
# → 前端 http://localhost:5173  API http://localhost:8000/api/health

# 本地开发
cd app && pip install -r requirements.txt
python -m uvicorn apm.main:app --port 8000 --reload
cd web && pnpm install && pnpm dev   # http://localhost:5173（代理 /api → 8000）

# 测试与冒烟（回放模式，确定性、不依赖模型/网络）
cd app && python -m pytest           # 单测 + 集成
python tools/smoke/run_smoke.py      # 累积冒烟基线（只增不减）
```

- **LLM 接入**：默认 `replay`（确定性回放，模板按 role+node 注入上下文）；`.env` 配 `APM_PROVIDER_MODE=openai`、`APM_LLM_API_BASE`、`APM_LLM_API_KEY` 后走真实模型（`record` 模式可录制 fixtures）。
- **存储**：`data/` 下 SQLite（事件真源 + 投影 + checkpoints）与内容/资产 Git 仓；`POST /api/system/rebuild-projections` 可全量重放校验。
- **本体/角色**：`ontologies/*.yaml` 与 `agents/roles/*.yaml` 改文件后 `POST /api/system/reload-ontologies` 即生效。
- **迭代记录**：开发日志与状态看板见 docs/10 附录 A/B 与 §7。
