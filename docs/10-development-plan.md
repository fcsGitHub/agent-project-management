# 10 · 开发计划与迭代审阅（执行版）

> v0.4 新增。前九册回答"系统该是什么样"，本册回答"怎么把它做出来"：可执行的开发计划——迭代划分与顺序、每迭代的验收标准（DoD）与演示路径、审阅迭代机制、开源复用纪律、跨会话持续推进协议，以及**唯一进度真源**的状态看板与开发日志（附录 A/B）。
> 与 07 的分工：07 §1 圈定 MVP 范围（做什么、不做什么），07 §4 给出任务与工作量；本册把同一批任务重排为**可独立审阅的小迭代**，并补上"怎么验收、怎么持续推进"两块 07 不承担的职责。工作量估算沿用 07 §4，仅切片更细。

## 1. 总原则（五条军规）

1. **复用优先三问**：任何功能动笔前依次问——①有没有现成开源库直接可用？②有没有"库 + 薄胶水"的组合？③真的必须自研吗？三问都过才写代码。自研范围硬性收敛为三块（07 §2.5）：**事件内核**（事件表 + 投影器）、**图编排胶水**（Orchestrator 状态机）、**业务页面组装**（在 shadcn/ui 之上）；其余一律复用。
2. **禁自研清单**：UI 基础组件与图标（shadcn/ui · lucide-react）、命令面板（cmdk）、图可视化与编辑（React Flow）、agent loop 与 checkpoint/恢复（LangGraph）、实时通道（SSE，不上 WebSocket）、全文检索（SQLite FTS5）。代码审阅中发现自研这些，直接打回。
3. **小步可审**：迭代粒度 ≤ 1 周；每个迭代结束必须交付**可运行增量 + 可执行验收断言 + 给评审者的演示路径**三件套；演示不出来的迭代不开下一个。
4. **冒烟累积制**：每迭代的验收断言并入端到端冒烟基线（`tools/smoke/`，pytest 用例），只增不减（改动需在开发日志记录理由）；任何迭代收尾前基线全绿——用累积断言防倒退。
5. **确定性优先**：LLM 相关路径全部经 Provider Adapter，冒烟与 CI 跑**录制回放模式**（record/replay，同一接口两实现，回放按提示词指纹取 fixtures），不依赖真实模型、网络与 key；真实模型只在人工验收与演示时启用。

## 2. 技术栈与复用基线

| 层 | 复用 | 自研范围（胶水） |
| --- | --- | --- |
| 后端框架 | FastAPI + Uvicorn（自动 OpenAPI） | 资源路由与领域逻辑 |
| 存储 | SQLite（标准库 sqlite3，表少不引 ORM） | schema 与迁移脚本 |
| 事件内核 | —（唯一核心自研） | append-only 事件表、投影器纯函数、rebuild（目标核心 ≤300 行） |
| Agent 运行时 | LangGraph + SqliteSaver（interrupt/checkpoint/恢复） | YAML→子图装配器、工具白名单与权限层、崩溃配平 |
| LLM 接入 | OpenAI 兼容协议 | Provider Adapter（openai_compat + 录制回放双实现） |
| 内容/资产仓 | git 命令行（子进程） | 路径约定、提交封装、diff 提取 |
| 检索 | SQLite FTS5（中文按字符 bigrom 分词） | 索引维护 |
| 前端组件 | shadcn/ui（Radix + Tailwind）、lucide-react、cmdk、Sonner | 业务页面组装 |
| 前端数据/路由 | TanStack Query + Router + Table | SSE→Query 增量更新桥 |
| 图视图 | React Flow（@xyflow） | 节点/边的数据映射与角标联动 |
| 文档渲染 | react-markdown + shiki（diff 视图候选 react-diff-view） | — |
| 部署 | docker-compose（多阶段构建） | — |

**UI 规范即 Demo**：`demo.html` 是前端实现的验收参照——页面结构、信息层级（KPI 卡/审批面板/抽屉披露）、交互剧本（15 步引导）均以 Demo 为准；正式实现只做"组件化复刻 + 真数据接入"，不做视觉再设计（复用清单见 07 §2.5）。

环境约定：Python 3.12 / Node 20 / pnpm；开发机为 Windows + Git Bash——仓库内路径一律 POSIX 风格、换行 LF、脚本避免平台专有写法；`.env` 配 `LLM_API_BASE`、`LLM_API_KEY`（冒烟不依赖）。

## 3. 仓库结构（monorepo，在现有仓库内扩展）

```
agent-project-management/
├─ docs/            # 01-10 方案与本计划
├─ demo.html        # UI/交互规范原型（验收参照）
├─ app/             # 后端（FastAPI，包名 apm）
│  ├─ core/         # db.py events.py projections.py bus.py     ← 自研①事件内核
│  ├─ domains/      # projects/ features/ conversations/ items/ approvals/ runs/ assets/ ontology/ nl/
│  ├─ runtime/      # provider.py(含 rec/replay) roles.py graph_factory.py tools.py spans.py
│  ├─ orchestrator/ # state_machine.py scheduler.py gates.py    ← 自研②编排胶水
│  ├─ content/      # gitrepo.py artifacts.py prompts.py
│  └─ tests/        # pytest：单测 + API 集成（回放夹具）+ smoke/
├─ web/             # 前端（Vite + React + TS + Tailwind）      ← 自研③页面组装
├─ ontologies/      # software-dev.yaml / generic.yaml
├─ agents/          # roles/*.yaml + prompts/roles/*.md（提示词 L4）
├─ tools/           # build_review_html.py / smoke/（累积冒烟入口）
└─ docker-compose.yml
```

工程约定：

- **API-first 落法**：每个域先写 `tests/test_api_<domain>.py`（以 07 §3 契约为准），再写实现；前端类型从 OpenAPI 生成。
- 提交粒度 = 任务粒度，提交信息带迭代号（如 `I3: 消息树持久化`），便于审阅时按迭代回溯。
- 前端每页对照 demo.html 对应区块实现，完成后可并排截图入迭代日志。

## 4. 迭代计划

三个里程碑：**M1 内核与数据**（后端可测）→ **M2 人机闭环**（UI 上可演示 PRD 全流程）→ **M3 完整 MVP**（NL/Graph/资产/部署）。与 07 §4 里程碑的对应见 §4.5；与 07 的差异只有一处且是有意的——**前端主线从 M3 提前到 M2**，让第二个里程碑审阅就能在页面上走通闭环。

### M1 · 内核与数据（I0-I4，约 16 人日）

| 迭代 | 主题 | 对应 07# | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I0 | 脚手架与冒烟框架 | #1 部分、#13 部分 | FastAPI / Vite / Tailwind / shadcn / pytest / vitest / compose | 2d |
| I1 | 事件内核 | #1 | sqlite3 | 3d |
| I2 | 本体服务 + 项目/工作项域 | #2 | PyYAML + jsonschema | 4d |
| I3 | 功能域 + 对话域 | #3 | — | 5d |
| I4 | 内容仓 + 提示词文件化 | #4 | git CLI | 2d |

#### I0 · 脚手架与冒烟框架（2d）

- 目标：monorepo 骨架立起来，CI 全绿，冒烟框架能跑空基线。
- 任务：目录与配置（§3）；FastAPI `/api/health`；web/ 初始化（Vite+TS+Tailwind+shadcn/ui，复刻 Demo 的 zinc+indigo 令牌）；docker-compose 起后端占位；`tools/smoke/` 框架（顺序执行冒烟标记用例并汇总报告）；README 开发指南一节。
- DoD（并入冒烟）：`docker compose up` 健康检查通过；`pytest` 与 `pnpm build` 本地与 CI 均绿；冒烟框架输出基线报告（0 用例）。
- 演示路径：compose 起服务 → 打开前端壳（导航与空状态）。

#### I1 · 事件内核（3d）

- 目标：自研①落地——事件表、投影器、rebuild、事件查询。
- 任务：`events` append-only 表与写入事务；投影器注册表（`fold(events) → read model` 纯函数）；`POST /api/system/rebuild-projections`；`GET /api/events`（分页/过滤）；`/api/stream` SSE 占位。
- DoD（并入冒烟）：投影 == 重放重建（随机事件序 replay 一致性断言）；事件只增（update/delete 被拒）。
- 演示路径：HTTP 页面查看事件流与 rebuild 前后一致性。

#### I2 · 本体服务 + 项目/工作项域（4d）

- 目标：双内置本体加载校验；项目 CRUD（双模板）；工作项五桶与依赖。
- 任务：`ontologies/*.yaml` schema（08 §3：concepts/itemTypes/statusModel/phaseGraph/assetKinds/libraries）+ 加载校验 + 校验状态 API；项目 CRUD（software-dev/generic 实例化）；items/relations API 与投影；状态机（本体 lifecycle 驱动五桶）。
- DoD（并入冒烟）：建 software-dev 项目断言默认功能与结构生成（冒烟 1 前半）；非法本体 YAML 报校验错误；generic 项目三阶段轻流程结构正确。
- 演示路径：API 建两个项目对比结构差异。

#### I3 · 功能域 + 对话域（5d）

- 目标：03 §1-§3 核心——功能数据面、消息树、打断/挂起/恢复（状态层，暂无真实 LLM）、提示词分层组装与 L1/L3 编辑。
- 任务：features CRUD + 简报字段；conversations/messages（消息树 parentId）；interrupt/resume/archive 状态机与事件；执行中发消息 = 打断 + 注入；`GET /conversations/{id}/context`（L1-L4 分层 + 合并预览）；L1/L3 编辑 → `prompt.updated` + 版本。
- DoD（并入冒烟）：服务重启后对话状态与消息无损（冒烟 7 前半）；打断→挂起→恢复状态迁移断言；L1 编辑后新消息生效、历史不重写。
- 演示路径：用回放 provider 驱动一段对话，API 层展示打断恢复（界面 M2 上）。

#### I4 · 内容仓 + 提示词文件化（2d）

- 目标：每项目裸 Git 仓；工件读写与版本；prompts/ 目录编辑落仓。
- 任务：项目创建时初始化内容仓；artifacts 读写 API（写 = commit）；diff 提取；prompts/ 存储与编辑回写。
- DoD（并入冒烟）：工件写入产生 commit 且 diff 可取；同一工件两次修改版本史正确。
- 演示路径：CLI 展示工件 commit log 与 diff。

**M1 审阅点（正式）**：冒烟 1（前半）/ 7（前半）+ 投影一致性全绿。评审问题示例：事件 schema 是否够支撑后续域？本体 YAML 表达力是否够？

### M2 · 人机闭环（I5-I9，约 24 人日）

| 迭代 | 主题 | 对应 07# | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I5 | Agent Runtime + 轨迹 | #5、#8 | LangGraph + SqliteSaver | 7d |
| I6 | Orchestrator + 审批域 | #6、#7 | — | 7d |
| I7 | 前端骨架 + SSE + 导航壳 | #10 | TanStack Query/Router、Sonner | 3d |
| I8 | 对话视图 + 功能页 | #11 部分 | shadcn 抽屉/表单、react-markdown + shiki | 4d |
| I9 | Board + 审批中心 | #11 部分 | TanStack Table、dnd-kit（看板拖拽候选） | 3d |

#### I5 · Agent Runtime + 轨迹（7d）

- 目标：4 角色以 YAML 声明并在 LangGraph 上运行；录制回放 provider；span 落库。
- 任务：provider.py（openai_compat + rec/replay 双实现）；角色加载（agents/roles/*.yaml → 子图装配 analyze→draft→self_check→gate）；4 角色提示词初版；工具层（read_artifact/write_artifact/search_web）+ 三级权限 + fail-closed + 单次授权；Run 生命周期与 retry；崩溃合成 `run.interrupted` 配平；span 埋点（OTel 对齐 + apm.* 扩展）与查询 API。
- DoD（并入冒烟）：回放模式下 PM-Agent 产出 PRD 并挂审批；打断→注入约束→恢复→PRD 含约束（冒烟 2 前半）；span 含 graph_node_id/conversation_id/diff_ref。
- 演示路径：后端日志 + API 展示一次带打断的 Run 与 span。

#### I6 · Orchestrator + 审批域（7d）

- 目标：自研②落地——图状态机、就绪调度、Gate→审批、fail-closed 决策流。
- 任务：阶段图状态机（本体 phaseGraph 驱动）；依赖就绪调度（blocked_by 全 done → 就绪，按指派分发）；Gate 到达生成 pending 审批而非启动 Run；审批决策 API（批准/拒绝/修改后恢复）；批量批准；dangerous 工具审批；Planner→WBS 落工件 + 建工作项。
- DoD（并入冒烟）：批准 PRD 后 Planner 接续产出任务树（冒烟 2 后半）；批量启动→打断一个→恢复→awaiting_review→批量批准（冒烟 4 API 版）；拒绝与 edit_and_resume 路径断言。
- 演示路径：API 顺序演示 PRD→计划→执行→验收全链。

#### I7 · 前端骨架 + SSE + 导航壳（3d）

- 目标：Demo 的壳复刻——暗色侧栏、项目/功能两级导航、路由与数据层。
- 任务：路由结构（Dashboard/功能页/对话/Graph/Runs/资产库/审计/本体/设置）；SSE→TanStack Query 增量更新桥；暗色 rail + 状态 pill + 令牌体系（对照 demo.html CSS 变量）；空状态与引导占位。
- DoD（并入冒烟）：导航八项与 Demo 一致；SSE 推真实事件后徽标/列表实时更新。
- 演示路径：浏览器走 Demo TOUR 前 3 步的等价路径（真数据）。

#### I8 · 对话视图 + 功能页（4d）

- 目标：核心界面——消息流/步骤行/打断恢复横幅/上下文抽屉；功能页三 Tab。
- 任务：消息树渲染与流式追加；步骤行（工具/工件/耗时展开 + diff 抽屉）；打断/继续/注入交互；上下文抽屉（L1-L4 折叠披露 + 合并预览 + L1/L3 编辑与版本史）；功能页（看板切片/对话列表/工件切片 + 简报卡）；工件 Markdown 渲染。
- DoD（并入冒烟）：页面上完成"打断→补约束→继续→批准"（冒烟 2 的 UI 化）；刷新无损；抽屉可见合并提示词。
- 演示路径：demo.html TOUR 步骤 5-8 的真数据版。

#### I9 · Board + 审批中心（3d）

- 目标：五桶看板（拖拽/过滤/多选批量"让 Agent 做"）；审批中心。
- 任务：看板投影消费、卡片内联批准、指派（人/角色）；审批中心页 + 顶栏铃铛徽标（SSE）；dangerous 审批的命令展示。
- DoD（并入冒烟）：冒烟 4 全程 UI 化；审批动作全部落审计事件。
- 演示路径：demo.html TOUR 步骤 9-11 的真数据版。

**M2 审阅点（正式）**：UI 上完整走冒烟 1/2/4/5（回放模式）；对照 demo.html 核对信息层级。评审问题示例：打断体验延迟？审批疲劳度？页面层级深度是否合适？

### M3 · 完整 MVP（I10-I13，约 18 人日）

| 迭代 | 主题 | 对应 07# | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I10 | NL 命令层 L1 | #9 | cmdk | 3d |
| I11 | Graph 视图 | #12 | React Flow | 4d |
| I12 | Runs/审计/本体页 + 资产域 | #11 剩余、#15 | SQLite FTS5 | 7d |
| I13 | 部署 + 全量冒烟 + 打磨 | #13、#14 | — | 4d |

#### I10 · NL 命令层 L1（3d）

- 任务：UI-Agent（可配小模型/回放）+ 页面动作工具注册（导航/过滤/选择/批量审批白名单）；⌘K 命令面板双模式（cmdk）；只读直执/写预览确认/撤销；`ui_command` 事件。
- DoD（并入冒烟）："只看高优先级任务"解析执行生效且落事件（冒烟 3）；写操作必须显式确认；解析失败降级候选列表。
- 演示路径：demo.html ⌘K 场景的真数据版。

#### I11 · Graph 视图（4d）

- 任务：React Flow 只读渲染项目图（节点 = 阶段/Gate/任务，边 = 依赖/工件传递）；节点角标（状态/待审数）联动；节点详情抽屉（阶段契约 + 绑定对话，03 §6）；Gate 高亮。
- DoD（并入冒烟）：图结构与本体 phaseGraph 一致；点节点跳转对应对话/审批。
- 演示路径：demo.html Graph 页的真数据版。

#### I12 · Runs/审计/本体页 + 资产域（7d）

- 任务：Run 抽屉（左树右甘特 + 人机交织时间线）与 Runs 列表；审计页（过滤/展开 payload/导出 CSV）；本体页（只读 + 校验状态）；资产域全链——资产仓 Git、assets/asset_links 投影、FTS5 索引、沉淀表单 + asset_review Gate、资产库页（三库 Tab/过滤/检索/详情双链）、Agent 三工具 search/read/link。
- DoD（并入冒烟）：generic 本体第二项目走通轻流程（冒烟 5）；沉淀登录回归套件→Gate→发布→第二项目 search 命中并 link→资产页可见双链（冒烟 6）。
- 演示路径：demo.html 资产页 + 审计页的真数据版。

#### I13 · 部署 + 全量冒烟 + 打磨（4d）

- 任务：docker-compose 完整化（后端 + 前端构建 + 卷）；种子数据脚本；冒烟 7 条全量串成一键脚本（回放模式）+ 真实模型手动过一遍；打磨（空状态/快捷键/引导浮层/错误提示）。
- DoD：07 §4 七条冒烟全绿；`docker compose up` 一键起；`.env` 配 key 后真实模型走通闭环。
- 演示路径：完整 TOUR 15 步的真数据版。

**M3 审阅点（正式，终验）**：按 07 冒烟脚本逐条验收 + 03 §5 功能完备性核对表逐行核对 MVP 列。

### M4 · 本体构建闭环（semantica 融合，I14-I16，约 9 人日）

> v0.5 新增（2026-09-02）。MVP 终验后，按"调研开源吸收优点"协议启动的第一里程碑：把 semantica v0.6.7 的本体构建模式（从数据推断类型 + provenance + 版本化）裁剪进项目管理域（映射与取舍见 08 §8）。

| 迭代 | 主题 | 对应 08 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I14 | 本体归纳 Ontology Learning（learn/apply + provenance） | 08 §8.2 | — | 3d |
| I15 | 本体版本化语义 diff 与迁移 | 08 §8.1 | deepdiff（或手写投影 diff） | 3d |
| I16 | CQ 可回答性检查（Competency Question 验收锚点落地） | 08 §8.1 | — | 3d |

#### I14 · 本体归纳（3d）

- 任务：`POST /api/ontologies/{name}/learn`——扫描该本体下全部项目投影数据（items/item_relations/assets+links/runs），按 08 §8.2 四规则产出候选提案（`candidates`，带 provenance：规则 id/支持计数/样本 id）与观察项（`observations`，零使用概念）；`POST /api/ontologies/{name}/apply`——勾选候选合并为本体 patch，过校验器后写回 `ontologies/<name>.yaml`（version+1），发 `ontology.updated` 事件（含 diff 与 provenance 摘要）并热重载；本体页新增"从项目数据学习"面板（候选勾选 + provenance 折叠 + 应用）。
- DoD（并入冒烟 8）：四规则信号数据全部命中且 provenance 可溯；apply 后校验通过、version+1、事件落审计流；L2 场景 apply 后同型关系通过建卡校验；重复 learn 幂等（已应用候选不再出现）。
- 演示路径：本体页点"扫描项目数据"→ 勾选候选 → 应用 → v+1 生效。

#### I15 · 本体版本化语义 diff 与迁移（3d）

- 任务：`GET /api/ontologies/{name}/diff?from=v1&to=v2`——结构化语义 diff（concepts/relations/phases/assetKinds 的增删改，非文本 diff）；影响分析（被删概念引用的工作项/关系清单，阻塞级标红）；`ontology.updated` 事件历史查询与回放视图。
- DoD（并入冒烟 8 扩展）：删除被引用概念时 diff 报告阻塞影响清单；diff 结果与事件 payload 一致。
- 演示路径：连续两次 apply 后查 diff 与影响分析。

#### I16 · CQ 可回答性检查（3d）

- 任务：每条 competencyQuestion 声明支撑数据面（映射到投影表/事件类型）；`GET /api/ontologies/{name}/cq-check` 报告每条 CQ 的覆盖状态（可回答/缺数据/缺映射）与证据摘要；本体页 CQ 卡片显示检查结果。
- DoD（并入冒烟 8 扩展）：software-dev 四条 CQ 全部可回答；generic 项目 CQ 检查含"缺数据"状态。
- 演示路径：本体页 CQ 卡片逐条展开证据。

**M4 审阅点**：冒烟 8 + 08 §8.3 验收锚点四项全过。

### M5 · V1.x 协作与归纳增强（I17-I19，约 11 人日）

> v0.6 新增（2026-09-02）。M4 审阅后按持续迭代协议开启的新一轮：调研结论（docs/01 §C.3.1，semantica extractor 方法链 + 置信度 + provenance 纪律）转化为开发计划；另清偿 M4 审阅 B 级意见。

| 迭代 | 主题 | 对应 08 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I17 | LLM 辅助本体归纳（learn-llm 通道 + confidence + 去重合并）+ B 级修复（CQ events 证据按项目过滤） | 08 §8.4 | Provider Adapter（既有） | 3d |
| I18 | 本体模板包导出/导入（YAML + 角色包 + 提示词模板，跨项目复用，08 §6 落地） | 08 §6 | — | 3d |
| I19 | 多人协作基础（用户注册表、assignee 真实身份、审计按人过滤） | 07 §5 V1.1 | — | 5d |

#### I17 · LLM 辅助本体归纳（3d）

- 任务：`POST /api/ontologies/{name}/learn-llm`——组装提示词（本体现状 + 各概念使用统计 + 工件标题清单）经 Provider Adapter 调 `ontology-curator` 角色（新角色 YAML + 提示词 L4），解析 JSON 候选（op 限 add_field/add_relation/wire_deposit/add_role），confidence<0.65 丢弃，与规则候选去重合并；回放模式由 replay 模板按注入上下文确定性产出（可测），openai 模式即真实抽取；本体页学习面板分区展示（LLM 徽标 + confidence）。B 级修复：`cq-check` 的 events 证据按该本体项目过滤。
- DoD（并入冒烟 8）：回放模式下 learn-llm 产出确定性候选且带 confidence≥0.65 与来源 provenance；与规则候选重复时不重复提出；apply 复用既有链路（校验/版本+1/事件）；CQ events 证据在多项目下按项目过滤。
- 演示路径：学习面板点「LLM 建议」→ 候选带 confidence 徽标 → 勾选应用 → v+1。

#### I18 · 本体模板包导出/导入（3d）

- 任务：`GET /api/ontologies/{name}/export`——打包 ontology.yaml + 引用的角色 YAML + 提示词模板为单 JSON/YAML 包；`POST /api/ontologies/import`——校验后落盘为新区（改名防冲突）；本体页导出/导入入口。
- DoD（并入冒烟 8）：导出→改名导入→新本体可建项目且阶段图/字段正确；非法包 422。
- 演示路径：导出 software-dev → 导入为 software-dev-lite → 用它建项目。

#### I19 · 多人协作基础（5d）

- 任务：users 表（注册表投影 user.* 事件）、登录身份选择（单机多身份切换）、items.assignee 关联真实用户、审计/审批按人过滤、`on_behalf_of` 与真实身份打通。
- DoD（并入冒烟）：双身份操作产生按人可分审计流；assignee 过滤看板。
- 演示路径：切换身份 → 指派 → 审批中心按人过滤。

**M5 审阅点**：冒烟 8 + 各迭代 DoD + 浏览器演示路径。

### M6 · 类型系统深化（吸收 OpenProject/Plane，I20-I22，约 9 人日）

> v0.7 新增（2026-09-02）。调研结论见 docs/01 §D：OpenProject 自定义字段（八格式+双层激活+可过滤标记）、Plane 工作项类型（六属性+按属性分组看板）、LangGraph 1.0.9→1.2.11 升级评估（同大版本，可升）。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I20 | 自定义字段值落地（items.custom_fields JSON + boolean/multiselect 新字段类型 + 按本体校验 + 过滤） | 01 §D.4①② | — | 3d |
| I21 | 看板按自定义字段分组 + 卡片字段展示（boardDefaults 支持字段维度） | 01 §D.4③ | — | 3d |
| I22 | LangGraph 1.2.11 升级验证（升级→全量回归→打断-恢复演示；红则回退 pin 1.0.9 记录） | 01 §D.3 | langgraph | 3d |

#### I20 · 自定义字段值（3d）

- 任务：本体字段类型扩展 **boolean / multiselect**（校验器：multiselect 必带 values、值必须 ∈ values）；`items.custom_fields` JSON 列（schema + 存量库 ALTER 迁移）；item.created/updated 透传；API 层按概念字段校验（未声明字段 422、类型不匹配 422）；`GET /items` 增 `cf=<field>:<value>` 过滤；内置 software-dev 演示字段（bug.regression:boolean、task.tags:multiselect）。
- DoD（并入冒烟 9）：三类新类型读写正确；未声明/类型错/越界值 fail-closed；multiselect 多值存储；rebuild 后投影一致。
- 演示路径：API 建带 custom_fields 的工作项 → cf 过滤命中。

#### I21 · 看板字段分组与展示（3d）

- 任务：看板 API/前端支持按自定义字段分组（boardDefaults.group-by: field:<id>）；卡片渲染自定义字段徽标；功能页工作项表展示列。
- DoD（并入冒烟 9）：分组 API 返回正确桶；前端看板按字段分组可见（浏览器验证）。
- 演示路径：看板切"按 tags 分组"。

#### I22 · LangGraph 升级验证（3d）

- 任务：requirements 升 langgraph==1.2.11 → 全量 pytest/冒烟 → 浏览器打断-注入-恢复演示；失败则回退 1.0.9 并在附录 A 记录原因。
- DoD：全绿 + 演示通过，或回退有记录。

**M6 审阅点**：冒烟 9 + I20/I21 DoD + 浏览器字段分组演示。

### M7 · 模板中心与项目级字段激活（吸收 n8n/OpenProject，I23-I25，约 9 人日）

> v0.8 新增（2026-09-03，M6 审阅通过后按目标第 5 条调研）。调研结论见 docs/01 §F：n8n 模板市场三件套（JSON 即模板/中心模板库/自托管库）、OpenProject 双层激活（类型级+项目级，同时满足才可见）、Plane/Focalboard 认证模型（两层成员+角色；整体推迟 M8）。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I23 | 模板包注册表与浏览 API（内置+导入统一视图、预览、一键建项目） | 01 §F.2 | I18 模板包 | 3d |
| I24 | 模板中心前端页（浏览/预览/用此模板建项目；资产库联动） | 01 §F.2 | — | 3d |
| I25 | 项目级字段激活（field_overrides 事件投影：停用字段不校验、不入分组候选） | 01 §F.1 | I20/I21 | 3d |

#### I23 · 模板包注册表（3d）

- 任务：模板注册表投影（`pack.registered` 事件；`ontology.imported` 复用为导入登记）；`GET /template-packs`（内置扫描 ontologies/ + 已导入注册，含版本/概念数/CQ 摘要）；`GET /template-packs/{name}` 预览；`POST /template-packs/{name}/instantiate` 一键建项目（建项目共链路）。
- DoD（并入**新增冒烟 13**）：内置+导入模板同列表可见；instantiate 建项目后阶段图与 CQ 就位；未知模板 404。
- 演示路径：导入 lite 包 → 模板列表两条 → instantiate 建项目。

#### I24 · 模板中心前端（3d）

- 任务：模板中心页（卡片浏览 + 预览抽屉展示 concepts/phases/CQ + 「用此模板建项目」表单）；项目列表页入口；资产库「沉淀为模板包」入口（asset→pack 复用导出）。
- DoD（并入冒烟 13）：浏览器可见模板中心；从模板建项目跳转看板。
- 演示路径：模板中心 → 预览 software-dev → 一键建项目 → 看板。

#### I25 · 项目级字段激活（3d）

- 任务：`project.field_disabled/enabled` 事件 + projects 投影扩展 field_overrides；`PATCH /projects/{id}/fields`；`_validate_custom_fields` 与 board 分组候选过滤停用字段；前端项目内字段开关入口。
- DoD（并入冒烟 13）：停用 tags 后建卡带 tags 422、看板分组选择器无「标签」；重新启用后恢复。
- 演示路径：项目设置停用「标签」→ 建卡被拒 → 分组无「标签」→ 启用恢复。

**M7 审阅点**：冒烟 13 + 各迭代 DoD + 浏览器模板中心演示。

### M8 · 多人网络协作：认证与项目成员角色（吸收 Plane/Gitea，I26-I28，约 9 人日）

> v0.9 新增（2026-09-03，M7 审阅通过后按目标第 5 条调研）。调研结论见 docs/01 §G：Plane 两层角色模型（裁掉 workspace 层，留项目级三角色）、Gitea 首管理员+关注册+管理员建号模式（不做邮件邀请）、部署形态定为「可信小团队网络服务」（auth_mode=local/network 双模，SSO 推迟 V3）。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I26 | 认证基座（密码哈希+签名会话 Cookie+登录审计+auth_mode 双模+首启管理员引导） | 01 §G.3 | I19 users | 3d |
| I27 | 项目成员与角色（project_members 投影：owner/contributor/viewer，项目级访问控制） | 01 §G.1 | — | 3d |
| I28 | 网络协作收尾（登录态替代身份切换、越权 403 审计、双账号协作冒烟、部署文档） | 01 §G.2/G.4 | — | 3d |

#### I26 · 认证基座（3d）

- 任务：users 表加 password_hash（stdlib pbkdf2）；`POST /auth/login|logout`（签名 HttpOnly Cookie，会话事件入审计流）；`settings.auth_mode`（local 默认=现状免登录；network=写路由强制登录）；首启引导：`APM_ADMIN_PASSWORD` 环境变量产出管理员。
- DoD（并入**新增冒烟 14**）：network 模式未登录写路由 401；登录/登出/失败均有事件；local 模式行为与现状完全一致（回归零破坏）。
- 演示路径：切 network 模式 → 未登录被拒 → 登录管理员 → 操作放行。

#### I27 · 项目成员与角色（3d）

- 任务：project_members 投影（owner/contributor/viewer；建项目者即 owner）；成员管理 API（从已注册用户添加/移除/改角色）；访问控制依赖（network 模式：owner 全权、contributor 读写、viewer 只读，越权 403+事件）；项目设置页成员管理 UI。
- DoD（并入冒烟 14）：三角色权限矩阵按 API 断言；viewer 写操作 403 有审计。
- 演示路径：管理员建号→加为 contributor→该账号登录可协作→viewer 账号写被拒。

#### I28 · 网络协作收尾（3d）

- 任务：登录态替代本地身份切换（network 模式顶栏=当前登录人，切换=登出重登）；审批/审计强制登录人；compose 部署文档（反代 HTTPS、auth_mode 配置）；遗留 B 级「users 无认证」闭环。
- DoD（并入冒烟 14）：双账号各自登录协作全程按人归账；越权可审计；文档可照做。
- 演示路径：双浏览器双账号协作 → 审批按人 → 越权 403。

**M8 审阅点**：冒烟 14 + 各迭代 DoD + 浏览器双账号协作演示。

### M9 · 看板自动化规则（吸收 Kanboard/n8n，I29-I31，约 9 人日）

> v1.0 新增（2026-09-03，M8 审阅通过后按目标第 5 条调研）。调研结论见 docs/01 §H：Kanboard Automatic Actions 项目级「事件×动作」绑定（trigger+action+参数，自省 API 列兼容面）、n8n/Node-RED 共同的三段式抽象（trigger→condition→action，单机内嵌学模型不引编排器）、Plane Automations 项目级同位与 webhook 重复触发教训（执行须幂等）；AgentPM 事件溯源内核即天然事件源，规则引擎订阅 event_bus 即可，无需自建 dispatcher。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I29 | 自动化规则域与执行引擎（规则事件溯源 + event_bus 订阅 + 动作白名单 + 防循环） | 01 §H.1/H.2 | 事件内核/M8 归账 | 3d |
| I30 | 规则管理前端（项目设置页规则面板：事件→条件→动作，测试运行） | 01 §H.2 | — | 3d |
| I31 | 收尾（审计归账 actor_type=automation、冒烟 15、docs/12 使用指南、浏览器演示） | 01 §H.3/H.4 | — | 3d |

#### I29 · 自动化规则域与执行引擎（3d）

- 任务：`automation_rules` 投影表（project_id/trigger_event/condition_json/action_json/enabled）；`automation.rule_created/updated/deleted` 事件（rebuild 存活，与 project_members 同模式）；执行器订阅 event_bus——trigger 匹配事件类型+project、condition 字段谓词（如 concept_id/severity/priority）、action 白名单 fail-closed（指派 assignee、改 priority、设 custom_field、列间移动）；防循环：规则产出事件带 actor_type=automation，不再触发规则引擎（单层执行）；规则 CRUD API（仅 owner/contributor 可管，复用 M8 门禁）。
- DoD（并入**新增冒烟 15**）：规则创建→触发事件→动作生效（含事件与归账）；条件不匹配不执行；未知动作/字段 fail-closed 422；rebuild 后规则与执行历史一致；防循环（规则动作不引发自身/他规则）。
- 演示路径：建「缺陷创建即指派+置严重度」规则 → 新建缺陷工作项 → 自动指派与字段生效。

#### I30 · 规则管理前端（3d）

- 任务：项目设置页「自动化」面板——规则列表（启停开关）+ 新建表单（下拉选事件类型/条件字段谓词/动作白名单+参数）+ 「测试运行」（对历史最近一条匹配事件 dry-run 显示将执行的动作）；规则触发历史抽屉（最近 N 条执行记录：命中事件/动作结果/耗时）。
- DoD（并入冒烟 15）：面板 CRUD 往返 + 测试运行 dry-run 断言；启停即时生效。
- 演示路径：面板建规则 → 看板建缺陷卡 → 卡片自动指派可见 → 历史抽屉显示命中记录。

#### I31 · 收尾（3d）

- 任务：审计归账（动作事件 actor=规则 id、actor_type=automation，审计页可过滤）；docs/12 自动化使用指南（三段式模型、动作白名单、防循环语义）；遗留 C 级意见处置（出站 webhook 登记 backlog）。
- DoD（并入冒烟 15）：自动化动作在审计流可按 actor_type 过滤；文档可照做。
- 演示路径：审计页过滤 automation 归账 → 与人操作并陈的时间线。

**M9 审阅点**：冒烟 15 + 各迭代 DoD + 浏览器自动化规则演示（建规则→触发→自动动作→审计归账）。

### M10 · 出站集成：webhook 与通知（吸收 Gitea/GitLab/Redmine，I32-I34，约 9 人日）

> v1.1 新增（2026-09-03，M9 审阅通过后按目标协议调研）。调研结论见 docs/01 §I：Gitea/GitLab webhook HMAC-SHA256 签名语义（原始 body 签名、delivery ID 去重、明文 token 已被 GitLab 列为 legacy）、投递结果留痕与指数退避；Redmine 邮件通知+feeds 是自托管 PM 桌上前提、规则化通知是真实需求（Redmineflux 插件验证）→ 站内通知先行（无 SMTP 依赖），与 M9 自动化动作打通。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I32 | 出站 webhook 基座（webhooks 事件溯源 + 后台投递线程 + HMAC 签名 + 重试与投递留痕） | 01 §I.1 | 事件内核/M8 归账 | 3d |
| I33 | webhook 前端与运维（配置面板/投递历史/手动重发/测试 ping）+ 冒烟 16 | 01 §I.1 | — | 3d |
| I34 | 站内通知中心 + automation `notify` 动作 + 收尾审阅 | 01 §I.2 | M9 自动化 | 3d |

#### I32 · 出站 webhook 基座（3d）

- 任务：`webhooks` 投影表（project_id/url/secret/events_json/enabled）+ `webhook.created/updated/deleted` 事件（rebuild 存活）；投递器：post-emit hook **只入队**，后台 worker 线程投递（网络 I/O 绝不阻塞写路径——与 M9 同步执行器的本质差异）；投递头 `X-APM-Event`/`X-APM-Delivery`/`X-APM-Signature`（对原始 body 的 HMAC-SHA256，secret 每条 webhook 独立）；失败指数退避重试 3 次，`webhook.delivered/failed` 事件留痕（delivery ID 幂等）；CRUD API（M8 门禁）。
- DoD（并入**新增冒烟 16**）：webhook 注册→触发事件→本地接收桩收到请求且签名头在位；失败→重试→failed 留痕；rebuild 存活；写路径不被投递阻塞。
- 演示路径：注册 webhook → 建缺陷 → 接收桩收到 item.created 载荷。

#### I33 · webhook 前端与运维（3d）

- 任务：项目设置页「Webhooks」面板（URL/事件订阅多选/启停/删除 + secret 显示与重置）；投递历史抽屉（最近 N 条 delivered/failed + 状态码 + 耗时）；手动重发按钮（按 delivery 事件重放同 payload、新 delivery ID）；「测试 ping」按钮。
- DoD（并入冒烟 16）：面板 CRUD 往返 + 重发断言；docs/12 增 webhook 接收方验签章节。
- 演示路径：面板建 webhook → 触发 → 历史看投递 → 失败重发成功。

#### I34 · 通知中心与收尾（3d）

- 任务：`notifications` 投影（approval.requested/item.assigned（human）/automation.rule_fired/工件沉淀 → 顶栏铃铛未读数 + 下拉清单 + 已读）；automation 动作白名单增 `notify`（{user_id, message}）；审计页 integration 归账复核；docs/12 通知章节。
- DoD（并入冒烟 16）：指派/审批请求产生站内通知且未读数正确；notify 动作走 M9 防循环与归账；rebuild 存活。
- 演示路径：建缺陷 → 被指派人铃铛出现未读；规则 notify 动作落通知中心。

**M10 审阅点**：冒烟 16 + 各迭代 DoD + 浏览器演示（webhook 投递留痕 + 通知中心）。

### M11 · 邮件通知与 Atom 订阅（吸收 Redmine，I35-I37，约 9 人日）

> v1.2 新增（2026-09-03，M10 审阅通过后按目标协议调研）。调研结论见 docs/01 §J：Redmine 邮件只做即时无 digest（digest 外挂）、SMTP 走环境配置层支持 SSL/STARTTLS、自托管推荐外部 relay；Atom feed 走 per-user key 认证（阅读器免 cookie），私有项目数据曾泄漏进全局 feed（#20173）——权限裁剪必须按 key 用户可见性。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I35 | 邮件通知通道（SMTP env 可选 + 通知投影 email 通道 + 队列投递 + email.notified 留痕） | 01 §J.1 | M10 通知/投递模式 | 3d |
| I36 | Atom 订阅 feed（per-user feed key + 权限裁剪 + 标准 Atom 输出）+ 冒烟 17 | 01 §J.2 | 事件流/users | 3d |
| I37 | 通知偏好前端与收尾审阅（用户级邮件开关 + feed key 管理入口 + docs/12 章节） | 01 §J.2/J.3 | — | 3d |

#### I35 · 邮件通知通道（3d）

- 任务：`APM_SMTP_HOST/PORT/USER/PASS/FROM/TLS` 环境变量（可选，未配置=邮件通道整体关闭且文档明示）；`/notifications` 响应与通知投影增 email 分发标记；邮件投递复用 M10「入队 + 后台线程」模式；即时邮件（仅用户级启用时发，主题=通知摘要）；`email.notified/failed` 事件留痕；users.email 已有字段直接复用（`POST /users` 补 email 参数）。
- DoD（并入**新增冒烟 17**）：未配置 SMTP 时一切行为与现状一致；配置调试桩（SMTP 类接收器或 mock）后指派产生邮件投递留痕；投递不阻塞写路径；rebuild 存活（留痕事件）。
- 演示路径：配 SMTP → 指派 → 收件桩收到邮件 + 审计留痕。

#### I36 · Atom 订阅 feed（3d）

- 任务：users 增 feed_key（运行态，rotate 语义同 webhook secret）；`GET /projects/{id}/feed.atom?key=`（key 认证绕过 cookie）+ `GET /me/feed-key`（查看/换发）；Atom 1.0 XML（id/title/updated/entry 内容=事件摘要），只输出 key 用户可见项目的事件；权限：非成员项目请求返回 403（防 #20173 式泄漏）。
- DoD（并入冒烟 17）：key 认证往返；非成员 key 403；Atom XML 结构校验（well-formed + 必备元素）；rotate 后旧 key 失效。
- 演示路径：阅读器/HTTP 客户端用 key 订阅项目事件流。

#### I37 · 通知偏好前端与收尾审阅（3d）

- 任务：设置区通知偏好（邮件开关 per user，存用户级运行态）；feed key 管理入口（显示/换发/复制订阅链接）；docs/12 §8 邮件与订阅章节（SMTP env 表 + 阅读器订阅指引）；M11 审阅。
- DoD（并入冒烟 17）：偏好开关生效（关=不发邮件）；rebuild 存活。
- 演示路径：关邮件开关 → 触发通知 → 站内有、邮件无。

**M11 审阅点**：冒烟 17 + 各迭代 DoD + 浏览器演示（邮件投递留痕 + feed 订阅 + 通知偏好）。

### M12 · 报表与跨项目工作台（吸收 OpenProject，I38-I40，约 9 人日）

> v1.3 新增（2026-09-04，M11 审阅通过后按目标协议调研）。调研结论见 docs/01 §K：OpenProject 报表分三层——社区版以 custom query（可保存过滤/分组视图）+ 项目首页 widget + My page 个人工作台为轻量报表，高级报表模块属企业版；SSO/OIDC 主流=独立 IdP+应用作 OIDC client（Gitea JIT 开户受限是已知坑），维持 V3；GitLab 审计事件 DB 永久保留+流式外送归档——AgentPM「归档」应为导出/快照而非删除（保护 live==replay）。选定报表与跨项目工作台：管理者可见性是工程管理落地标准的直接缺口，且事件溯源做投影型报表零 ETL。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I38 | 报表数据层（项目健康摘要 + 跨项目「我的工作」+ 项目列表健康聚合的纯投影查询 API） | 01 §K.1 | 事件流/items/board 投影 | 3d |
| I39 | 报表前端与项目工作台（项目报表页：阶段漏斗+Gate 挂起+超期清单+吞吐；项目列表健康徽标；全局「我的工作」） | 01 §K.1 | — | 3d |
| I40 | 收尾审阅（CSV 导出 + docs 报表章节 + 冒烟 18 + M12 审阅） | 01 §K.3/K.4 | — | 3d |

#### I38 · 报表数据层（3d）

- 任务：新域 `app/apm/domains/reports.py`——纯投影查询 API（无新表、无新事件，复用既有投影）：`GET /projects/{id}/report`（阶段漏斗计数、Gate 挂起清单、超期工作项（estimate/due 与状态判定）、近 N 天吞吐（created/closed 序列）、概念分布）；`GET /my/work`（跨项目「分配给我」+ 我负责的 Gate 审批，按 M8 角色可见性）；`GET /projects` 响应补健康摘要字段（各状态计数 + 挂起 Gate 数）。时间判定用 SQLite 当前时区约定并在文档写明；权限复用 M8 门禁。
- DoD：三端点单测（造数→计数断言→权限语义断言：/report 读与 board/items 同语义、/my/work **指派即授权**（被指派者恒见自己的活跃项，OpenProject My page 同款）+ Gate 仅 owner/instance admin 可见）；rebuild 后报表数字不变（投影一致性天然保证，显式断言）；不新增任何事件类型。
- 演示路径：API 造多状态数据 → /report 各段数字与看板/列表人工核对一致。

#### I39 · 报表前端与项目工作台（3d）

- 任务：新页「报表」（`#/p/{pid}/reports`，侧栏入口）：阶段漏斗（按状态计数条形）、Gate 挂起卡片（直达审批中心）、超期清单（超期天数徽标）、吞吐 sparkline（近 14 天 created/closed）；项目列表页每卡片健康徽标（进行中/挂起/完成计数 + 挂起 Gate）；全局「我的工作」入口（侧栏，跨项目聚合视图）。api.ts 增 3 方法 + 类型。
- DoD：vitest/build 绿；浏览器验证报表页数字与看板/审计一致（截图）；「我的工作」跨项目命中断言。
- 演示路径：报表页全览 + 项目列表徽标 + 我的工作直达。

#### I40 · 收尾审阅（3d）

- 任务：报表 CSV 导出（/report?format=csv 或前端导出）；docs/12 §9 报表与工作台章节（口径定义：超期/吞吐/挂起判定规则）；冒烟 18（报表全程：造数→三端点→CSV）；M12 审阅。
- DoD（并入冒烟 18）：口径边界（无 due 不算超期、done 不进漏斗挂起段）；CSV 与 JSON 同数；rebuild 一致。
- 演示路径：冒烟 18 + 浏览器报表页复演。

**M12 审阅点**：冒烟 18 + 各迭代 DoD + 浏览器演示（项目报表页 + 项目列表健康徽标 + 我的工作）。

### M13 · 里程碑与时间线（吸收 OpenProject/Plane，I41-I43，约 9 人日）

> v1.4 新增（2026-09-04，M12 审阅通过后按目标协议调研）。调研结论见 docs/01 §L：OpenProject Gantt = 三类工作包（phase/milestone/task）×依赖连线×时间轴，里程碑日期随关联项变动（依赖传播是其核心语义）；Plane v1.16 Milestone = 按 deadline 聚合工作项的路线图锚点（与 sprint 式 Cycles 正交）；GitLab 导出仅作补充、备份走 DB 层。AgentPM 数据模型三要素齐备（milestone 概念、items.milestone_id 闲置列、depends_on 内核关系），缺日期字段与视图。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I41 | 里程碑域与工作项日期（milestone.* 事件溯源 + CRUD + items 加 start_date/due_date 列 + 关联与进度 + 报表超期口径升级） | 01 §L.1/L.2 | 本体 milestone 概念/items.milestone_id 列 | 3d |
| I42 | 时间线视图（`#/p/{pid}/timeline`：概念分组行 × 日期轴、条形/菱形、depends_on 箭头与冲突标红、里程碑进度） | 01 §L.1 | item_relations depends_on | 3d |
| I43 | 收尾（事件 NDJSON 导出 + docs/11 备份章节 + docs/12 §10 + 冒烟 19 + M13 审阅） | 01 §L.3/L.4 | — | 3d |

#### I41 · 里程碑域与工作项日期（3d）

- 任务：新域 `app/apm/domains/milestones.py`——`milestones` 投影表 + `milestone.created/updated/deleted` 事件（标题/due_date 必填 ISO 日期/状态复用本体 planned/in_progress/achieved）；CRUD API（M8 门禁）；items 加 `start_date`/`due_date` TEXT 列（CREATE+ALTER 迁移，可空，ISO 日期校验，item.created/item.updated 透传）；PATCH /items/{id} 支持 milestone_id 关联（未知里程碑 422）；里程碑进度 = 关联项 done 比例 + 逾期数（due_date < 今日且非 done）；报表超期口径升级：item.due_date 优先，其次 cf due，最后滞留（docs/12 §9 同步改）。
- DoD：单测（里程碑 CRUD+rebuild 存活/未知关联 422/日期校验 422/进度与逾期计算/报表口径三级回退）；rebuild 后进度一致。
- 演示路径：API 建里程碑+关联工作项 → GET 进度数字人工核对。

#### I42 · 时间线视图（3d）

- 任务：新页 TimelinePage（`#/p/{pid}/timeline`，rail「时间线」）：横向日期轴（默认今起前后各 30 天，可滚）；行=概念（从本体声明取序）；条形=有 start/due 的工作项（无日期项不显示、计数提示）；菱形=里程碑（due 日定位，悬停进度徽标）；depends_on 关系画连线（SVG 覆层，简化直角折线），后置项 start 早于前置项 due 时条形标红（冲突提示，不自动改期）；api.ts 增类型与方法。
- DoD：vitest/build 绿；浏览器验证条形/菱形/冲突标红与造数一致（截图）；空日期项目空态不报错。
- 演示路径：时间线页全览 + 冲突标红 + 里程碑进度。

#### I43 · 收尾审阅（3d）

- 任务：事件 NDJSON 导出 `GET /projects/{id}/events/export`（流式 NDJSON，含 prev_event_id 链，校验和行）；docs/11 补「备份与恢复」章节（SQLite 文件级 + content/ + ontologies/，导出仅作补充——GitLab 警告移植）；docs/12 §10 里程碑与时间线（口径+用法）；**新增冒烟 19**（里程碑全程：CRUD→关联→进度→报表口径→NDJSON 导出→rebuild 一致）；M13 审阅。
- DoD（并入冒烟 19）：NDJSON 逐行合法 JSON 且 prev_event_id 链连续；rebuild 后里程碑进度不变。
- 演示路径：冒烟 19 + 时间线页复演。

**M13 审阅点**：冒烟 19 + 各迭代 DoD + 浏览器演示（时间线页 + 里程碑进度 + NDJSON 导出）。

### M14 · 排程自动化与事件可携（吸收 OpenProject 15.4/GitLab，I44-I46，约 9 人日）

> v1.5 新增（2026-09-04，M13 审阅通过后按目标协议调研）。调研结论见 docs/01 §M：OpenProject 15.4 自动排程 = 手动默认 + 可选自动（Finish-to-Start 顺延，比关键路径引擎简单）；WeKan PWA = 自托管移动端最务实路线（下一轮候选）；GitLab NDJSON relation 管线印证 I43 导出需配对导入。选定排程自动化与事件可携——依赖变化后手工改期繁琐易漏、有出无进的恢复闭环。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I44 | 依赖传播自动排期（items.auto_scheduled 开关 + item.rescheduled 显式事件 + 递归传播与防环 + 时间线开关入口） | 01 §M.1 | depends_on/M13 日期列 | 3d |
| I45 | 事件 NDJSON 导入恢复（校验和/链序/冲突 409 + rebuild roundtrip） | 01 §M.3 | I43 导出 | 3d |
| I46 | 收尾审阅（docs/12 §11 + docs/11 §5.3 更新 + 冒烟 20 + M14 审阅） | 01 §M.2/M.4 | — | 3d |

#### I44 · 依赖传播自动排期（3d）

- 任务：items 加 `auto_scheduled` INTEGER 列（默认 0=手动，ALTER 迁移；PATCH 可开关）；前置项（被 depends_on 者）due 经 item.updated 变化时，对 depends_on 其且 auto_scheduled=1 的后继项计算 delta = 新 due − 旧 due，平移 start/due（保持时长，无 start 则仅平移 due），发**显式 `item.rescheduled` 事件**（payload 含 follow_of/delta/新日期，投影更新，审计归因）；多级依赖递归传播（深度上限 20 防环，遇已处理跳过）；时间线页条形 hover 标注「自动排期」。
- DoD：单测（单级传播/多级递归/环安全/手动模式不受影响/auto 开关关闭不传播/rescheduled 事件 rebuild 存活）；冒烟不断言（I46 冒烟 20 并入）。
- 演示路径：时间线造 A←B←C 链，改 A 的 due → B/C 自动顺延且审计可见 item.rescheduled 链。

#### I45 · 事件 NDJSON 导入恢复（3d）

- 任务：`POST /projects/{id}/events/import`（body = NDJSON 文本）：逐行 JSON 解析 + 校验和行匹配（sha256 重算比对）+ prev 链序校验 + 事件 id 与目标库冲突检测（任一冲突整批 409 拒绝，不做部分导入）；通过后按序 emit 追加（actor_type=system, actor_id=import）→ rebuild → 返回 {imported, rebuilt}；docs/11 §5.3 更新「恢复=导入+rebuild」实际操作步骤。
- DoD：单测（roundtrip：导出→新库导入→事件序列与投影一致/校验和不匹配 422/事件 id 冲突 409/非 NDJSON 422）。
- 演示路径：冒烟 20 并入 roundtrip。

#### I46 · 收尾审阅（3d）

- 任务：docs/12 §11 排程与可携章节（auto_scheduled 语义/rescheduled 事件审计/导入恢复操作）；docs/11 §5.3 恢复步骤落地更新；**新增冒烟 20**（自动排期传播链 + 导出→导入 roundtrip + rebuild 一致）；M14 审阅。
- DoD（并入冒烟 20）：传播只影响 auto_scheduled 项；导入后 live==replay。
- 演示路径：冒烟 20 + 时间线自动排期复演。

**M14 审阅点**：冒烟 20 + 各迭代 DoD + 浏览器演示（依赖传播 + 导入恢复 roundtrip）。

### M15 · PWA 与移动端适配（吸收 WeKan/Focalboard 教训 + vite-plugin-pwa，I47-I49，约 9 人日）

> v1.5 新增（2026-09-04，M14 审阅通过后按目标协议调研）。调研结论见 docs/01 §N：WeKan 官方商店 App 是指向演示服务器的 TWA（自托管无用）→ 可安装 PWA 指向自己的实例才是正路；Focalboard 移动 web 拥挤且移动 App 已废弃、Plane 无 PWA → 同类自托管移动端普遍短板；vite-plugin-pwa generateSW + autoUpdate，**API 永不入 SW 缓存**（事件溯源数据必须在线）。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I47 | 响应式布局基座（窄屏断点 + rail 折叠为移动导航 + 看板/表格横向滚动 + 触控目标） | 01 §N.2 | Tailwind 4 断点 | 3d |
| I48 | PWA 可安装与离线外壳（vite-plugin-pwa + manifest + generateSW + autoUpdate + API 永不缓存） | 01 §N.3 | — | 3d |
| I49 | 移动端关键路径打磨收尾审阅（docs/12 §12 + docs/11 HTTPS 注记 + 冒烟 21 + M15 审阅） | 01 §N.1/N.4 | — | 3d |

#### I47 · 响应式布局基座（3d）

- 任务：AppShell 窄屏断点（<768px rail 折叠为顶部标题栏 + 汉堡抽屉导航）；看板列容器横向滚动（列宽下限保持可读）；列表/报表/审计等表格容器横向滚动（不折行挤压）；时间线窄屏最小可用（横向滚动）；触控目标 ≥44px（图标按钮）；meta viewport 已在位（复核）。
- DoD：Playwright 375×812 视口截图 board/list/reports/my-work 四页可用（导航可达、无布局断裂）；pnpm build + vitest 绿。
- 演示路径：375px 视口走「看板 → 审批 → 通知」。

#### I48 · PWA 可安装与离线外壳（3d）

- 任务：vite-plugin-pwa（generateSW、registerType autoUpdate）；manifest（name/short_name/theme_color/icons 192+512+maskable，start_url=`/`，display standalone）；precache 构建产物 + SPA navigation fallback（index.html）；**`/api/*` 显式排除——SW 不缓存任何 API 响应（事件溯源数据必须在线）**；autoUpdate 静默更新 + 新内容提示刷新；docs/11 注记 service worker 需 HTTPS/localhost。
- DoD：构建产物含 manifest.webmanifest + sw.js；precache 清单不含 /api 路由；DevTools Network 证据 API 请求不经 SW；离线 reload 静态外壳可载入（数据区报错兜底）；pytest/冒烟全绿不动。
- 演示路径：生产构建 → 浏览器安装提示 → 断网 reload 外壳 → 恢复网络数据回归。

#### I49 · 移动端打磨收尾审阅（3d）

- 任务：关键路径移动端复核（看板卡片展开/Gate 审批按钮/通知铃/NL 命令条触控可用性）；docs/12 §12 移动端与 PWA 指南（安装步骤 + 离线边界「外壳可离线、数据必在线」+ HTTPS 部署注意）；**新增冒烟 21**（PWA 构建产物断言：dist 含 manifest + sw.js、precache 不含 /api）；全量回归 + M15 审阅。
- DoD（并入冒烟 21）：构建产物 PWA 就绪断言；pytest/冒烟全绿。
- 演示路径：冒烟 21 + 375px 视口关键路径复演。

**M15 审阅点**：冒烟 21 + 各迭代 DoD + 浏览器演示（375px 视口四页 + PWA 安装与离线外壳）。

### M16 · 自定义视图与保存筛选（吸收 OpenProject 自定义查询，I50-I52，约 9 人日）

> v1.5 新增（2026-09-04，M15 审阅通过后按目标协议调研）。调研结论见 docs/01 §O：OpenProject 自定义查询（保存过滤/分组/排序，私有/公开）是 Community 免费核心、跨项目聚合才是 Enterprise；Gitea SSO JIT 痛点（注册无 allowlist、group claim 二次登录生效）→ 需 IdP 演示环境成本高，降为下一轮候选；digest 同类均无原生内建 → backlog。选定自定义视图——AgentPM 当前过滤全部临时、刷新即失。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I50 | 视图数据层（saved_views 投影表 + view.* 事件 + CRUD + 定义校验 fail-closed） | 01 §O.1 | M6 字段过滤/M12 报表口径 | 3d |
| I51 | 视图前端（看板/列表视图管理器：保存/切换/管理 + 共享徽标） | 01 §O.1 | 看板工具栏 | 3d |
| I52 | 收尾审阅（默认视图 + docs/12 §13 + 冒烟 22 + M16 审阅） | 01 §O.2-O.4 | — | 3d |

#### I50 · 视图数据层（3d）

- 任务：`domains/views.py`——saved_views 投影表（id/name/project_id/owner_id/is_public/definition JSON/concept_id 可选收窄）+ `view.created/updated/deleted` 事件（rebuild 存活，drop_projections 清单同步）；CRUD API（owner 或 admin 可改删、成员可读私有+全项目可读 public、非成员 403+access.denied）；definition 校验 fail-closed（filters 白名单：concept/status/priority/assignee/cf:field/group_by/view 枚举，未知键/类型 422）；视图执行 = definition 展开为既有 board/group_by+cf 过滤参数（纯复用，不建第二条查询路径）。
- DoD：单测（CRUD 往返 + rebuild 存活/权限矩阵（私有 vs 共享 vs 非成员）/定义校验全矩阵/视图展开执行与手工过滤同数）；pytest 全绿。
- 演示路径：API 建视图 → GET board?view_id= 与手工过滤逐项一致。

#### I51 · 视图前端（3d）

- 任务：看板工具栏「视图」下拉（保存当前过滤为视图：名称 + 私有/共享；切换视图即应用 definition；重命名/删除；共享视图徽标「公开」）；列表视图同步支持；api.ts 增类型与方法；视图选中态入 URL（?view=）刷新/分享保持。
- DoD：build + vitest 绿；浏览器隔离复演（建视图→切换→URL 直开还原过滤）截图。
- 演示路径：375px + 桌面双视口走「保存 → 切换 → 分享」。

#### I52 · 收尾审阅（3d）

- 任务：默认视图（project.board_defaults 或项目级 default_view_id，看板直达）；docs/12 §13 自定义视图指南（定义 schema/权限/共享语义）；**新增冒烟 22**（视图全程：CRUD→权限→展开执行同数→rebuild 一致）；全量回归 + M16 审阅。
- DoD（并入冒烟 22）：视图执行与手工过滤同数；rebuild 后视图存活；pytest/冒烟全绿。
- 演示路径：冒烟 22 + 浏览器视图管理复演。

**M16 审阅点**：冒烟 22 + 各迭代 DoD + 浏览器演示（视图保存/切换/共享 + URL 直开）。

### M17 · OIDC 单点登录（吸收 Authlib 模式 + Gitea 教训，I53-I55，约 10 人日）

> v1.5 新增（2026-09-04，M16 审阅通过后按目标协议调研）。调研结论见 docs/01 §P：Authlib 模式（code flow + PKCE + state 存短命 cookie）复用 M8 会话签发；Keycloak realm import 一键演示（单测用本地 JWT 桩离线覆盖协议）；Gitea 教训四约束（JIT 一次性定角色 / allowlist 双层 / 可信 email / 账号不自动合并）。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I53 | OIDC client 基座（discovery + code flow + PKCE + id_token 验证 + JIT 建号四约束 + 本地 JWT 桩单测） | 01 §P.1/P.3 | M8 security.py 会话 | 3.5d |
| I54 | 会话整合与前端（OIDC 登录入口 + admin 配置面板 + network 门禁兼容） | 01 §P.1 | /login 页 + IdentitySwitcher | 3d |
| I55 | Keycloak 演示环境 + docs/11 §2 扩展 + docs/12 §14 + 冒烟 23 + M17 审阅 | 01 §P.2 | — | 3.5d |

#### I53 · OIDC client 基座（3.5d）

- 任务：`core/oidc.py`——issuer discovery（.well-known/openid-configuration 缓存）+ authorization URL 构造（state/nonce/PKCE S256，state 存 HttpOnly 短命 cookie）+ `/auth/oidc/callback`（code 换 token、id_token 签名/issuer/audience/nonce/exp 验证）+ **JIT 建号四约束**（claim 齐全且 email_verified → users 表建行定角色 viewer 缺省、后续登录幂等不提升；allowlist `APM_OIDC_ALLOWED_GROUPS` 非空 fail-closed 403；email 缺失/未验证拒绝；同 email 本地账号存在 → 409 不自动合并）；配置走 env（APM_OIDC_ISSUER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI）未配置=特性整体关闭（与 SMTP 同款静默语义）；单测用本地 RSA JWT 桩（mini jwks + authorize/token 桩端点）离线覆盖全协议路径。
- DoD：单测（发现缓存/回调验证全绿 + 签名篡改/issuer 伪造/nonce 重放/email 未验证/组不在 allowlist/账号冲突 409 各拒绝路径 + JIT 幂等重登不提升角色）；pytest 全绿。
- 演示路径：冒烟桩协议路径（Keycloak 真连留给 I55）。

#### I54 · 会话整合与前端（3d）

- 任务：回调成功签发 M8 同款 HMAC 会话 cookie（actor 归账走既有 events ContextVar 链路）；`GET /auth/me` source 增加 `oidc`；前端 `/login` 页 OIDC 按钮（特性关闭时不显示）+ 顶栏身份 chip 标注；本体页 admin「OIDC 配置」面板（issuer/client id/allowlist 展示，secret 不回显）；network 门禁/角色全兼容（OIDC 用户按 JIT 角色/成员角色归账）。
- DoD：单测（回调→会话→写操作 actor 归账 / viewer 门禁对 OIDC 用户生效 / logout 清会话）；build+vitest 绿。
- 演示路径：本地桩全流程「登录页 → OIDC → 会话 → 写操作审计归账」。

#### I55 · Keycloak 演示环境 + 收尾审阅（3.5d）

- 任务：`tools/keycloak/`（docker-compose + realm import JSON：realm/client/演示用户/admin 组）；docs/11 §2 扩展 OIDC env 表与流程；docs/12 §14 OIDC 单点登录指南（四约束语义/allowlist/账号冲突处置）；**新增冒烟 23**（OIDC 特性关闭零破坏 + 桩协议回归 + JIT 幂等）；全量回归 + M17 审阅。
- DoD（并入冒烟 23）：关闭时行为与 M16 一致；pytest/冒烟全绿。
- 演示路径：Keycloak 容器真连「登录 → JIT 建号 → 角色 → 审计」复演。

**M17 审阅点**：冒烟 23 + 各迭代 DoD + 浏览器演示（桩全流程 + Keycloak 真连）。

### M18 · 工作项评论与参与通知（吸收 Plane/GitLab 协作语义，I56-I58，约 9 人日）

> v1.5 新增（2026-09-04，M17 审阅通过后按目标协议调研）。调研结论见 docs/01 §Q：Plane/GitLab 评论 + @mention 即通知是协作核心（AgentPM 工作项无评论流——真实缺口）；GitLab「参与即通知」语义（评论/编辑/被提及 → 参与者收后续通知）；OpenProject 工时跟踪 Community 核心留下一轮首选候选。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I56 | 评论域（comment.* 事件 + CRUD + @mention → 通知 + 参与投影） | 01 §Q.1 | M10 通知/M11 邮件 | 3d |
| I57 | 评论前端（功能页与卡片评论抽屉 + mention 补全 + 通知跳转） | 01 §Q.1/Q.3 | 功能页/卡片 | 3d |
| I58 | 订阅与收尾（watch/subscriber + docs/12 §15 + 冒烟 24 + M18 审阅） | 01 §Q.3 | 通知投影 | 3d |

#### I56 · 评论域（3d）

- 任务：`domains/comments.py`——item_comments 投影表（id/item_id/project_id/author_id/body/mentions JSON/created_at/deleted_at）+ `comment.created/deleted` 事件（rebuild 存活，drop_projections 同步）；CRUD（项目成员可评、author/admin 可删、非成员 403）；**@mention 解析**（body 中 `@姓名` 匹配 users → mentions 列表入事件 + notifications 投影生成 mention 通知 + 邮件通道自然联动）；**参与投影**（item_participants：author/assignee/mentioned 去重集合，供后续事件通知面使用）；item 删除级联语义（工作项删除 → 评论投影随 item 查询隐藏，事件保留审计）。
- DoD：单测（CRUD + rebuild 存活/mention 解析与通知生成/参与集合去重/权限矩阵/删除隐藏）；pytest 全绿。
- 演示路径：API 评论 + mention → 通知铃与邮件同收。

#### I57 · 评论前端（3d）

- 任务：功能页评论 Tab 扩展或工作项抽屉评论区（列表 + 输入框 + `@` 成员补全下拉）；看板卡片徽标显示评论数；通知铃点击 mention 通知跳转对应工作项；api.ts 类型与方法。
- DoD：build + vitest 绿；浏览器隔离复演（A 评论 @B → B 铃铛通知 → 点击跳工作项）截图。
- 演示路径：双身份（local 切换）走「评论 → 提及 → 通知 → 跳转」。

#### I58 · 订阅与收尾审阅（3d）

- 任务：工作项订阅（`item.subscribed/unsubscribed` 事件 + 参与投影扩展：assignee/author/mentioned 自动参与 + 手动订阅切换按钮）；通知面接入参与者（item.* 后续事件通知参与者——最小面：状态变更与评论）；docs/12 §15 评论与参与通知指南；**新增冒烟 24**（评论全程：CRUD→mention 通知→参与集合→订阅→rebuild 一致）；全量回归 + M18 审阅。
- DoD（并入冒烟 24）：mention → 被提及者通知；参与者收后续事件通知；pytest/冒烟全绿。
- 演示路径：冒烟 24 + 双身份「评论 → 提及 → 通知 → 状态变更通知参与者」复演。

**M18 审阅点**：冒烟 24 + 各迭代 DoD + 浏览器演示（双身份评论提及通知闭环）。

### M19 · 工时跟踪与汇总报表（吸收 OpenProject/Redmine 执行侧语义，I59-I61，约 9 人日）

> v1.5 新增（2026-09-04，M18 审阅通过后按目标协议调研）。调研结论见 docs/01 §R：OpenProject time entry（时长/日期/备注/作者 + 个人日历）是 Community 免费核心；记时入口取 **Redmine 式显式「Log time」**（GitLab FOSS #27780 用户实测偏好，弃 GitLab 斜杠命令）；Plane worklog 仅工作项级、**项目级聚合是官方 open 缺口 #8045**——AgentPM 直接把项目工时报表纳入范围差异化补位。AgentPM 有 estimate_hours（计划侧）无 spent（实际侧），与 M14 自动排期互补。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I59 | 工时数据层（time.* 事件 + item_time_entries 投影 + CRUD + spent 汇总 + 权限对齐） | 01 §R.1/R.4 | M8 门禁/事件内核 | 3d |
| I60 | 工时前端（记工时抽屉 + spent/estimate 徽标 + docs/12 §16 + 冒烟 25） | 01 §R.2/R.4 | 评论抽屉型/卡片徽标 | 3d |
| I61 | 项目工时报表（按人/按日聚合）+ docs/11 备份核对 + 全量回归 + M19 审阅 | 01 §R.3/R.4 | M12 报表框架 | 3d |

#### I59 · 工时数据层（3d）

- 任务：`domains/timelog.py`——item_time_entries 投影表（id/item_id/project_id/user_id/minutes/spent_on/note/created_at/deleted_at）+ `time.logged/edited/deleted` 事件（rebuild 存活，drop_projections 同步）；CRUD（POST/GET/PATCH/DELETE `/items/{id}/time_entries`，记录人为 user_id=effective_actor；校验 fail-closed：minutes 正数、spent_on ISO 日期、note 长度）；item 详情/get_items 附 spent_minutes 汇总（SUM，与 estimate_hours 并列）；权限对齐 M8（local 放行/network 项目成员读写+非成员 403+删除限本人·admin）；参与投影接入（记工时者成为参与者，复用 item_participants source='time'——首次来源语义不覆盖已有行）。
- DoD：单测（CRUD 往返 + rebuild 存活/校验矩阵/汇总正确/权限矩阵/参与者接入）；pytest 全绿。
- 演示路径：API 记三笔工时 → item spent_minutes 汇总 → rebuild 一致。

#### I60 · 工时前端（3d）

- 任务：评论抽屉同型的「⏱ 工时」抽屉（条目列表：人/日/时长/备注 + 记时表单：时长+日期+备注）；看板卡片与列表视图 spent 徽标（`⏱ 2h30 / 预估 4h` 语义）；api.ts 类型与方法；docs/12 §16 工时跟踪指南；**新增冒烟 25**（记工时全程：CRUD→汇总→rebuild 一致）。
- DoD：build + vitest 绿；冒烟 25 GREEN；浏览器隔离复演（记工时 → 徽标/汇总可见）截图。
- 演示路径：双身份各记一笔 → 卡片 spent 汇总随刷新增长。

#### I61 · 项目工时报表 + 收尾审阅（3d）

- 任务：项目报表页增工时小部件（按人合计 + 按日趋势，纯投影聚合 SQL，复用 M12 报表框架与 rebuild 前后一致断言）；「我的工作」页增本周记时合计（个人最小面，个人日历视图留 backlog）；全量回归 + M19 审阅（DoD 逐项 + 附录 B + 浏览器隔离复演「记时→汇总→报表」）。
- DoD（并入审阅）：报表数字与条目清单一致（SQL 对账单测）；pytest/冒烟全绿。
- 演示路径：冒烟 25 + 双身份记时 → 报表按人/按日可见。

**M19 审阅点**：冒烟 25 + 各迭代 DoD + 浏览器演示（记时→汇总→报表闭环 + rebuild 一致）。

### M20 · 体验补齐三件套（吸收 OpenProject Gantt/My time tracking + GLFM，I62-I64，约 8 人日）

> v1.6 新增（2026-09-05，M19 审阅通过后按目标协议调研）。调研结论见 docs/01 §S：OpenProject 16.0「My time tracking」个人日历（日/周/月 + 快捷记时）是分钟粒度条目的复盘面；OpenProject Gantt 内建拖拽排程 vs Redmine 靠插件补位——AgentPM M13 时间线只读 + M14 自动排程后端之间**缺手动拖拽层**；GLFM/GFM 任务清单与表格是评论结构化主力但风味分歧多，只取交集且**存储保持纯文本原文**、渲染层转换。验证纪律更新（用户 2026-09-05）：迭代期只跑相关测试，全量回归收敛至 M20 正式审阅；HANDOFF 每轮修剪。

| 迭代 | 主题 | 对应 01 | 复用引入 | 估时 |
| --- | --- | --- | --- | --- |
| I62 | 个人工时日历（GET /my/timelog 聚合 + 周/月日历页 + 点日快捷记时） | 01 §S.1 | M19 timelog 投影/TimeLogModal 表单语义 | 3d |
| I63 | 时间线拖拽改期（条形拖拽移动 + 右缘缩放 → PATCH + 冲突重算） | 01 §S.2 | M13 TimelinePage / M14 rescheduled 审计 | 3d |
| I64 | 评论 Markdown 渲染（GFM 只读 + mention chip + 预览）+ docs/12 §17 + 冒烟 26 + M20 审阅 | 01 §S.3/S.4 | M18 评论域 | 2d |

#### I62 · 个人工时日历（3d）

- 任务：`GET /my/timelog?days=`（近 N 日本人条目按日分组 + 每日合计 + 窗口合计，纯投影聚合，days 钳 1-60；network 门禁对齐 my/work）+「我的工时」页（周视图七列/月视图网格切换、日合计徽标、点空日/日头快捷记时——弹 TimeLogModal 同款表单语义但预填 spent_on、条目点击可改删）+ 侧栏「我的工作」旁入口；api.ts MyTimelog 类型与 getMyTimelog。
- DoD：my/timelog 单测（按日分组/合计/软删剔除/越权门禁——扩展 test_timelog.py）；build+vitest 绿；相关验证只跑 test_timelog.py + build（新纪律）。
- 演示路径：记两日工时 → 日历页对应日格子出现条目与合计。

#### I63 · 时间线拖拽改期（3d）

- 任务：TimelinePage 条形 pointer 拖拽（移动=改 start/due 同步平移；右缘缩放=改 due；拖拽中半透明 + 显示悬浮日期；落点 PATCH start_date/due_date 走既有端点——M14 rescheduled 审计与自动顺延/冲突重算自动生效）；落点后依赖连线与冲突着色随查询刷新；未设日期项与里程碑菱形不参与拖拽；Esc 取消拖拽。
- DoD：改期后 events 出现 item.updated/rescheduled 审计（test_items.py 扩展一条断言）；build+vitest 绿；浏览器复演拖拽改期 + 冲突变红截图。
- 演示路径：拖动依赖链后继条形 → 落点冲突标红 → 拖回变正常。

#### I64 · 评论 Markdown 渲染 + 收尾审阅（2d）

- 任务：CommentsModal 评论正文 GFM 只读渲染（marked + DOMPurify，表格/代码块/任务清单只读、链接 target=_blank rel=noopener）+ mention `@姓名` 高亮 chip（渲染层正则，复用后端解析口径）+ 编辑框「编辑/预览」切换；存储与 API 契约不变（纯文本往返单测）；docs/12 §17 评论 Markdown 指南；**新增冒烟 26**（my/timelog 聚合 + 时间线改期审计链 + 评论原文往返 + rebuild 一致）；相关验证 + M20 审阅（全量回归 pytest/冒烟/vitest + DoD 逐项 + 附录 B + 浏览器隔离复演三件套）。
- DoD（并入审阅）：冒烟 26 GREEN；评论原文往返不变；审阅全绿。
- 演示路径：发含表格/清单/@提及评论 → 渲染正确且原文入库。

---

### 4.6 冒烟脚本 × 迭代落点（续）

| 冒烟条 | 首次全绿迭代 |
| --- | --- |
| 8 本体归纳 learn→apply→version+1→幂等 | I14 |

### 4.5 与 07 §4 里程碑的对应与差异

| 07 里程碑 | 本计划 | 差异说明 |
| --- | --- | --- |
| M1 数据层+本体+对话域（#1-5） | M1 = I0-I4（#1-4）；#5/#8 入 M2 首迭代 | Runtime 移作 M2 第一块（I5），便于与 Orchestrator 同期联调、闭环驱动 |
| M2 编排+审批+轨迹+NL（#6-10） | M2 = I5-I9（#5-#8、#10、#11 前半） | 前端主线提前（评审要早见界面）；NL 移 M3（依赖前端动作注册先就绪） |
| M3 前端完整+资产域+部署（#11-15） | M3 = I10-I13（#9、#12、#11 剩余、#15、#13/#14） | 同上 |

工作量合计约 58 人日（07 估 52，差额来自前端提前带来的集成往返），单人节奏约 7.5-9 周，与 07 一致。

### 4.6 冒烟脚本 × 迭代落点

| 07 冒烟条 | 首次全绿迭代 |
| --- | --- |
| 1 建项目断言结构 | I2（API）/ I7（UI） |
| 2 PRD 审批 + 打断注入 | I5（回放）/ I8（UI） |
| 3 NL 过滤 + ui_command | I10 |
| 4 批量启动/打断/恢复/批准 | I6（API）/ I9（UI） |
| 5 release-notes + 审计 + generic 二项目 | I6 / I12 |
| 6 资产沉淀→检索→link 双链 | I12 |
| 7 rebuild 一致 + 重启恢复 | I1/I3 起，每迭代回归 |

## 5. 审阅迭代机制

### 5.1 节奏：开发 → 自验 → 审阅 → 处置

每个迭代收尾走同一条流水线：

1. **开发**：按 §4 任务清单实施，提交带迭代号；
2. **自验**：单测 + 集成绿 → 冒烟基线全绿（累积）→ 手动过一遍演示路径；
3. **审阅**：交付迭代审阅包三件套——可运行增量（如何起、看哪个页面）、演示路径（5-8 步）、状态看板与开发日志更新；里程碑节点（M1/M2/M3）为**正式审阅**，评审者按演示路径 + 冒烟脚本实际过一遍；
4. **处置**：意见分级落账（§5.2），A 级进下一迭代首位任务。

### 5.2 意见分级与处置

| 级 | 定义 | 处置 |
| --- | --- | --- |
| A 必改 | 阻断闭环/正确性/安全问题 | 下一迭代首位任务；A 级清零才算里程碑通过 |
| B 计划内 | 体验/完善类，MVP 范围内 | 排入后续迭代任务清单（看板备注登记） |
| C 超范围 | 属 V1.x 扩展（对齐 07 §5） | 入附录 C backlog，MVP 不做 |

所有意见记入附录 B 审阅记录（日期/迭代/意见/级别/处置/落点），**先落账再动代码**。

### 5.3 回归保障

- 冒烟累积制（军规 4）+ CI 每提交跑基线；
- 里程碑审阅前做一次"全新环境验收"：clone → compose up → 冒烟全量，确保交付物不依赖开发机状态。

### 5.4 变更控制

范围变更（新增/砍掉功能、换选型）必须记入开发日志：内容、理由、对估时与后续迭代的影响；影响里程碑边界的变更需在正式审阅中确认。**不允许悄悄扩范围。**

## 6. 持续推进协议（跨会话执行纪律）

本计划面向"开发者 = 编码 Agent + 人工审阅"的协作模式。为防跨会话丢上下文、保证按计划持续推进，约定：

1. **会话开始**：读本册 → §7 状态看板定位当前迭代 → 读该迭代"任务/DoD/演示" → 从第一个未完成任务开工；存在未清零的 A 级意见时先清意见。
2. **会话结束前**：更新 §7 状态看板；在附录 A 追加日志（本次完成/关键决策/遗留与下一步入口）；新阻塞写入 §8 风险表。
3. **进度真源唯一**：§7 状态看板。代码、README、其它文档不承担进度职责；发现不一致以看板为准并即时修正。
4. **里程碑门**：M1/M2/M3 审阅未过（A 级未清零）不开下一里程碑的迭代；用户明示跳过除外。
5. **完成的定义（全局 DoD）**：MVP = 07 §1.1 全行落地 + §4 冒烟 7 条全绿 + 03 §5 核对表 MVP 列全勾 + docker 一键起。

## 7. 状态看板（唯一进度真源 · 随迭代更新）

状态取值：未开始 / 进行中 / 待审阅 / 已完成（A 级清零）/ 已跳过（记理由）。

| 迭代 / 节点 | 状态 | 开始 | 完成 | 备注 |
| --- | --- | --- | --- | --- |
| I0 脚手架与冒烟框架 | 已完成 | 2026-08-22 | 2026-08-22 | compose/pytest/vitest/smoke 基线框架 GREEN |
| I1 事件内核 | 已完成 | 2026-08-22 | 2026-08-22 | append-only 触发器、投影器、rebuild、SSE；replay 一致性断言入冒烟 |
| I2 本体 + 项目/工作项域 | 已完成 | 2026-08-22 | 2026-08-22 | 双内置本体 YAML+校验、模板实例化、五桶状态机、依赖关系、看板投影 |
| I3 功能域 + 对话域 | 已完成 | 2026-08-22 | 2026-08-22 | 消息树/打断恢复/注入、L1-L4 组装与 L1/L3 编辑版本化、重建恢复 |
| I4 内容仓 + 提示词文件化 | 已完成 | 2026-08-22 | 2026-08-22 | 每项目 git 仓、写=commit+事件、diff/版本史、charter/instruction 落仓 |
| **M1 里程碑审阅** | 已完成 | 2026-08-22 | 2026-08-22 | 冒烟 1 前半/7 前半 + 投影一致性全绿（见 tools/smoke/reports） |
| I5 Agent Runtime + 轨迹 | 已完成 | 2026-08-22 | 2026-08-22 | LangGraph 角色子图+SqliteSaver、provider rec/replay、工具三级权限、span OTel+apm.* |
| I6 Orchestrator + 审批域 | 已完成 | 2026-08-22 | 2026-08-22 | 本体 gate 重映射、阶段状态机、就绪调度、批量启动、PRD→WBS 自动接续 |
| I7 前端骨架 + SSE + 导航壳 | 已完成 | 2026-08-22 | 2026-08-22 | 暗色 rail+功能栏+⌘K+铃铛、SSE→Query 桥、路由八页 |
| I8 对话视图 + 功能页 | 已完成 | 2026-08-22 | 2026-08-22 | 消息流/步骤行/打断恢复横幅/上下文抽屉、功能页三 Tab+简报卡 |
| I9 Board + 审批中心 | 已完成 | 2026-08-22 | 2026-08-22 | 五桶看板多选批量启动、审批中心预览 diff/批量/拒绝必填理由 |
| **M2 里程碑审阅** | 已完成 | 2026-08-22 | 2026-08-22 | 浏览器实测走通建项→PRD→打断注入→批准→计划→批量执行闭环 |
| I10 NL 命令层 L1 | 已完成 | 2026-08-22 | 2026-08-22 | 确定性解析器、只读直执/写确认、ui_command 事件、降级候选 |
| I11 Graph 视图 | 已完成 | 2026-08-22 | 2026-08-22 | React Flow 只读图、阶段/Gate/任务节点、状态着色、节点抽屉 |
| I12 Runs/审计/本体页 + 资产域 | 已完成 | 2026-08-22 | 2026-08-22 | 左树右甘特+人机时间线、审计过滤导出、本体页、资产全链+FTS5+Agent 三工具 |
| I13 部署 + 全量冒烟 + 打磨 | 已完成 | 2026-08-22 | 2026-08-22 | compose 一键起、种子脚本、冒烟 7 条全绿、空状态/⌘K/引导 |
| **M3 终验** | 已完成 | 2026-08-22 | 2026-08-22 | 冒烟 7 条全绿 + 03 §5 核对表 MVP 列全勾（见附录 A 验证记录） |
| I14 本体归纳 Ontology Learning | 已完成 | 2026-09-02 | 2026-09-02 | learn/apply API、四条确定性规则+provenance、本体页学习面板；冒烟 8 全绿 |
| I15 本体版本化语义 diff 与迁移 | 已完成 | 2026-09-02 | 2026-09-02 | 版本快照（apply 双写）、语义 diff + 阻塞影响分析、ontology.updated 事件历史 API、本体页版本时间线与 diff 面板；冒烟 8 扩展全绿 |
| I16 CQ 可回答性检查 | 已完成 | 2026-09-02 | 2026-09-02 | cq_mappings 声明式映射 + 校验器、/cq-check 三态报告（可回答/缺数据/缺映射）+ 证据摘要、本体页 CQ 卡片；冒烟 8 扩展全绿 |
| **M4 里程碑审阅（正式）** | 已完成 | 2026-09-02 | 2026-09-02 | 冒烟 8 + 08 §8.3 四项验收锚点全过 + 浏览器实测演示路径（截图 docs/m4-review-ontology-page.png，见附录 B） |
| I17 LLM 辅助本体归纳 + B级修复 | 已完成 | 2026-09-02 | 2026-09-02 | learn-llm 通道（回放确定性 + confidence 0.65 阈值 + 去重合并 + 优雅降级）、apply 共链路；CQ events 证据按项目过滤；冒烟 8 扩展全绿 |
| I18 本体模板包导出/导入 | 已完成 | 2026-09-02 | 2026-09-02 | export 单 JSON 包（本体+角色+提示词）、import 改名防冲突+校验+角色复用/创建+ontology.imported 事件；冒烟 8 扩展全绿 |
| I19 多人协作基础 | 已完成 | 2026-09-02 | 2026-09-02 | users 表（user.* 事件投影+自举）、身份切换（session.identity_switched 事件）、emit 身份透传、human 指派校验+assignee_name、events actor_id/approvals decided_by 过滤、顶栏切换菜单；冒烟 9 全绿 |
| **M5 里程碑审阅（正式）** | 已完成 | 2026-09-02 | 2026-09-02 | 冒烟 12 条 + 各迭代 DoD + 浏览器演示路径（身份切换→指派→按人审计→LLM 建议→模板包导入导出，截图 docs/m5-review-collab-page.png，见附录 B） |
| I20 自定义字段值落地 | 已完成 | 2026-09-02 | 2026-09-02 | boolean/multiselect 字段类型 + items.custom_fields（ALTER 迁移）+ fail-closed 校验 + cf 过滤；顺手修两个隐藏投影 bug；pytest 79/冒烟 12 全绿 |
| I21 看板字段分组与展示 | 已完成 | 2026-09-03 | 2026-09-03 | board `group_by=field:<id>` 分桶（声明值序+空列保留、multiselect 扇出、未设置列、未知 422）+ 前端分组选择器/卡片徽标/列表字段列；浏览器验证截图 docs/i21-board-field-grouping.png；pytest 80/冒烟 12 全绿 |
| I22 LangGraph 1.2.11 升级验证 | 已完成 | 2026-09-03 | 2026-09-03 | langgraph 1.0.9→1.2.11（requirements 下限抬至 >=1.2.11）；pytest 80/冒烟 12 全绿零改动；浏览器打断-注入-恢复演示通过（revise 后 PRD 含注入约束、批准后 succeeded），截图 docs/i22-interrupt-inject-resume.png；无需回退 |
| **M6 里程碑审阅（正式）** | 已完成 | 2026-09-03 | 2026-09-03 | 冒烟 9 + I20/I21/I22 各迭代 DoD 逐项核对全过（审阅时点重跑 pytest 80/冒烟 12）+ 浏览器复演字段分组与打断-注入-恢复两条演示路径（截图 docs/m6-review-board-grouping.png、docs/m6-review-interrupt-resume.png，见附录 B） |
| I23 模板包注册表与浏览 API | 已完成 | 2026-09-03 | 2026-09-03 | 注册表=本体目录活扫描+事件合成 provenance（pack.registered 启动幂等登记 + ontology.imported 复用导入登记，不另建表避免双真源）；GET /template-packs 统一视图、预览、instantiate 建项目共链路；新增冒烟 13；pytest 85/冒烟 13 全绿 |
| I24 模板中心前端页 | 已完成 | 2026-09-03 | 2026-09-03 | TemplatesPage 浏览/预览抽屉（阶段流程+概念表+CQ）/用此模板建项目（跳转看板）；项目列表与侧栏入口；资产页「沉淀为模板包」（from-asset 发 pack.registered source=asset）；冒烟 13 扩展；pytest 87/冒烟 13/build/vitest 全绿；浏览器验证截图 docs/i24-*.png |
| I25 项目级字段激活 | 已完成 | 2026-09-03 | 2026-09-03 | `project.field_disabled/enabled` 事件投影（projects.field_overrides JSON 列+ALTER 迁移）；PATCH /projects/{id}/fields（未声明字段 422）；写入校验与看板分组候选/分组维度过滤停用字段（board 响应带 disabled_fields）；本体页字段激活面板；冒烟 13 扩展；pytest 89/冒烟 13 全绿；截图 docs/i25-field-deactivated-board.png |
| **M7 里程碑审阅（正式）** | 已完成 | 2026-09-03 | 2026-09-03 | 冒烟 13 + I23/I24/I25 各迭代 DoD 逐项核对全过（审阅时点重跑 pytest 89/冒烟 13）+ 浏览器复演模板中心一键建项目与字段停用-恢复两条演示路径（截图 docs/m7-review-instantiate-board.png、docs/m7-review-field-deactivated.png，见附录 B） |
| I26 认证基座 | 已完成 | 2026-09-03 | 2026-09-03 | core/security.py（pbkdf2 哈希+HMAC 签名会话 Token+secret 持久化）；users 加 password_hash/is_admin（ALTER 迁移，凭据不入事件）；POST /auth/login|logout|me（会话事件入审计）；auth_mode=local/network 双模 middleware（network 未登录写 401）；APM_ADMIN_PASSWORD 首启引导；新增冒烟 14；pytest 94/冒烟 14 全绿 |
| I27 项目成员与角色 | 已完成 | 2026-09-03 | 2026-09-03 | project_members 投影（owner/contributor/viewer，建项目者即 owner，member.* 事件 + rebuild 存活）；成员管理 API（末位 owner 保护、未知用户 422、重复 409）；network 写门禁按成员角色（viewer/非成员 403 + access.denied 审计）；users 注册支持可选密码（管理员建号）；本体页成员面板；冒烟 14 扩展；pytest 97/冒烟 14 全绿 |
| I28 网络协作收尾 | 已完成 | 2026-09-03 | 2026-09-03 | 会话→actor 归账（events contextvar + middleware 设/复位，登录人即事件 actor，冒烟 14 断言 item.created actor=qa-wang）；身份切换 network 422；/login 页 + api 401 跳转 + 顶栏登录态（⭐管理员/👤+登出）；部署文档 docs/11（双模 env、管理员建号、角色归账规则、反代 HTTPS）；pytest 97/冒烟 14 全绿；截图 docs/i28-login-session-chip.png |
| **M8 里程碑审阅（正式）** | 已完成 | 2026-09-03 | 2026-09-03 | 冒烟 14 + I26/I27/I28 各迭代 DoD 逐项核对全过（审阅时点重跑 pytest 97/冒烟 14）+ 浏览器双账号协作演示（network 登录→管理员建号→viewer 403 门禁→contributor 写入→审计归账链，截图 docs/m8-review-*.png 四张，见附录 B）；审阅即修 2 处前端缺陷（AppShell 全局 rail 链接硬编码 /assets 致模板入口不可达、FeaturePage 过时文案） |
| I29 自动化规则域与执行引擎 | 已完成 | 2026-09-03 | 2026-09-03 | `automation_rules` 投影表 + `automation.rule_created/updated/deleted` 事件（rebuild 存活）；执行器挂 events post-emit hook（内核即事件源，无自建 dispatcher）；trigger 白名单 4 事件 × condition（concept_id+字段谓词）× 动作白名单 fail-closed（assign/set_priority/set_field/set_status，复用工作项校验路径）；防循环双保险（automation actor 事件不进门 + dispatch 期 contextvar）；动作显式归账 actor_type=automation；CRUD API + dry-run /test + /runs 历史；新增冒烟 15；pytest 103/冒烟 15 全绿 |
| I30 规则管理前端 | 已完成 | 2026-09-03 | 2026-09-03 | 本体页「自动化规则」面板：规则列表（触发/条件/动作摘要 + 启停开关 + 删除）、新建表单（事件下拉/概念与条件谓词/动作白名单动态参数——enum 字段按本体声明出值下拉、multiselect 逗号分隔转数组）、测试运行（调 /test dry-run toast 呈现命中）、历史抽屉（调 /runs 显示已执行/被拒绝与动作明细）；api.ts 增 6 方法 + 4 类型；build/vitest 绿；浏览器验证 UI 建规则→API 触发→看板卡片自动指派+severity 徽标→历史抽屉（截图 docs/i30-automation-*.png ×3） |
| I31 自动化收尾 | 已完成 | 2026-09-03 | 2026-09-03 | 审计页发起者过滤增「⚡ 自动化」+ 域标签增 automation（rule_* 事件一键过滤）；docs/12 自动化使用指南（三段式模型/执行语义含防循环与幂等/测试运行与历史/权限边界/backlog：出站 webhook、组合与区间条件）；浏览器演示：审计页过滤 ⚡自动化 命中 4 条（2 触发 + 2 动作均归账规则 id），截图 docs/i31-audit-automation-filter.png；build 绿 |
| **M9 里程碑审阅（正式）** | 已完成 | 2026-09-03 | 2026-09-03 | 冒烟 15 + I29/I30/I31 各迭代 DoD 逐项核对全过（审阅时点重跑 pytest 103/冒烟 15）+ 浏览器复演「UI 建规则→API 触发→看板卡片自动指派→审计 ⚡ 过滤归账链」（截图 docs/m9-review-automation-card.png、docs/m9-review-audit-automation.png，见附录 B） |
| I32 出站 webhook 基座 | 已完成 | 2026-09-03 | 2026-09-03 | `webhooks` 投影表 + `webhook.created/updated/deleted` 事件（rebuild 存活；secret 不入事件为运行态、rotate 换发）；投递器 post-emit hook 只入队 + apm-webhooks 后台线程投递（写路径零阻塞，冒烟断言写 <1s 而接收端 stall 2s）；X-APM-Event/Delivery/Webhook/Signature 头（原始 body HMAC-SHA256）；失败指数退避 3 次 → webhook.delivered/failed 留痕（attempts=4）；事件订阅白名单 fail-closed；CRUD + rotate API 复用 M8 门禁；新增单测 4 项 + 冒烟 16；pytest 108/冒烟 16 全绿 |
| I33 webhook 前端与运维 | 已完成 | 2026-09-03 | 2026-09-03 | 后端补 replay（按 delivery_id 重放原事件载荷、新 delivery ID、单次尝试）+ ping（合成载荷单次尝试）端点；前端本体页「Webhooks 出站」面板：创建表单（URL+订阅事件芯片）、secret 一次性展示弹窗（rotate 换发）、行内 Ping/投递历史/换发/启停/删除、投递历史抽屉（已送达/失败徽章+attempts+状态码+耗时+重发按钮）；api.ts 增 7 方法 + Webhook/DeliveryRecord 类型；docs/12 §6 验签章节（原始字节 HMAC+常量时间比较+delivery 去重 Python 示例）；单测 5 项；浏览器验证：接收桩实测签名投递→历史抽屉两条 已送达（原始+重发，delivery ID 各异）→ 重发生效（截图 docs/i33-webhook-secret-modal.png、i33-webhook-delivery-history.png）；pytest 109/冒烟 16 全绿 |
| I34 通知中心与收尾 | 已完成 | 2026-09-03 | 2026-09-03 | `notifications` 投影表：纯投影自既有事件（item.assigned→被指派人、approval.requested→项目 Owner、notification.sent→指定用户）；通知 id 确定性（n_{事件id}_{用户}）保证已读引用 rebuild 后仍匹配；notification.read 事件溯源已读（ids/all）；GET /notifications + POST /notifications/read（按 effective_actor 归属）；automation 动作白名单增 notify（{user_id,message≤200}，走防循环与 automation 归账）；前端顶栏通知铃铛（未读徽标+清单+全部已读，15s 轮询）；docs/12 §7 通知章节；新增单测 4 项 + 冒烟 16 扩展通知断言；pytest 113/冒烟 16 全绿；浏览器验证铃铛徽标与已读清零（截图 docs/i34-notification-bell.png） |
| **M10 里程碑审阅（正式）** | 已完成 | 2026-09-03 | 2026-09-03 | 冒烟 16 + I32/I33/I34 各迭代 DoD 逐项核对全过（审阅时点重跑 pytest 113/冒烟 16）+ 浏览器复演「UI 建 webhook→触发→接收桩签名投递→投递历史留痕→指派通知铃铛」合并路径（截图 docs/m10-review-webhook-history.png、docs/m10-review-notification-bell.png，见附录 B） |
| I35 邮件通知通道 | 已完成 | 2026-09-04 | 2026-09-04 | `APM_SMTP_HOST/PORT/USER/PASS/FROM/TLS` 环境变量（可选；未配置=通道整体静默关闭，行为与 M11 前完全一致）；`domains/mailer.py`——收件人决策抽为 notifications.`plan_notifications` 纯函数（通知投影与邮件共用，两通道永不失配）；post-emit hook 只入队 + apm-mailer 守护线程即时发送（STARTTLS/465 SSL/login 可配，超时 10s）；`email.notified/failed` 留痕（to/summary/source_event_id/duration_ms，确定性 agg_id）；users.email 既有字段直接复用；新增单测 5 项 + 冒烟 17；pytest 119/冒烟 17 全绿 |
| I36 Atom 订阅 feed | 已完成 | 2026-09-04 | 2026-09-04 | users 加 feed_key（运行态，CREATE+ALTER 迁移）；新域 `domains/feed.py`：GET /me/feed-key（查看/首次生成，owner 可读自己的凭据）+ POST /me/feed-key/rotate + GET /projects/{id}/feed.atom?key=（key 认证绕过 cookie）；**权限裁剪防 #20173 式泄漏**（instance admin 全见、成员按角色、local 模式配置用户；非成员 403 并落 access.denied 留 path）；Atom 1.0 XML（xml.sax.saxutils 转义、id=urn:apm:event/{pid}/{eid}、entry 含 title/updated/author/content 摘要，latest 30）；单测 3 项（生命周期+rotate 失效/roundtrip+well-formed+content-type/非成员 403+入成员后放行）；冒烟 17 扩展 feed 断言；pytest 122/冒烟 17 全绿 |
| I37 通知偏好前端与收尾审阅 | 已完成 | 2026-09-04 | 2026-09-04 | users 加 `email_notify`（默认 1，CREATE+ALTER 迁移）；`POST /api/notifications/prefs` + GET /notifications 响应带 `email_enabled`；mailer 入队过滤 `email_notify=0`（**只停邮件、站内通知照常**——通知是事实投影，邮件是可选介质）；通知中心弹层增偏好区：邮件开关（即时生效）+ feed key 显示/换发/复制订阅链接；api.ts 增 setNotificationPrefs/getFeedKey/rotateFeedKey；test_mailer 第 6 项（开关后邮件止、站内 unread 照增）；docs/12 §8「邮件通知与 Atom 订阅」；pytest 123/冒烟 17/vitest+build 全绿 |
| **M11 里程碑审阅（正式）** | 已完成 | 2026-09-04 | 2026-09-04 | 冒烟 17 + I35/I36/I37 各迭代 DoD 逐项核对全过（审阅时点 HEAD `0270169` 重跑 pytest 123/冒烟 17）+ 浏览器隔离复演「邮件投递留痕 + feed 订阅 + 通知偏好」（本地 SMTP 接收桩实测收信、开关后邮件止站内照常、feed.atom 直开渲染、非成员 403，截图 docs/m11-review-*.png ×4，见附录 B） |
| I38 报表数据层 | 已完成 | 2026-09-04 | 2026-09-04 | 新域 `domains/reports.py`（**纯投影查询，无新表无新事件**）：GET /projects/{id}/report（五桶漏斗零填充、概念分布、pending Gate 清单、超期/滞留清单（口径：cf 声明 due 则按日期判超期，否则活跃项创建超 14 天计滞留；done/cancelled 恒排除）、近 14 天吞吐序列（item.created 与 status_changed→done 按日计数））；GET /my/work（**指派即授权**：被指派者恒见自己活跃项；Gate 仅 owner/instance admin 可见——与 approval.requested 通知接收人一致）；GET /projects 列表补 item_counts+gates_pending 健康摘要；单测 4 项（漏斗/吞吐/Gate 计数+rebuild 前后一致/404/超期口径边界含 done 排除与未到期排除/跨项目 my-work+列表健康）；pytest 127/冒烟 17 全绿 |
| I39 报表前端与项目工作台 | 已完成 | 2026-09-04 | 2026-09-04 | 新页 ReportsPage（`#/p/{pid}/reports`：五桶漏斗条形+概念 chips、挂起 Gate 卡片直达审批中心、超期/滞留清单带 reason 徽标、近 14 天吞吐双色柱图，15s 轮询）；全局 MyWorkPage（`#/my/work`：分配给我跨项目列表+等我决策 Gate 卡片，指派即授权）；AppShell rail 增「报表」（项目内）与「我的工作」（全局 ListTodo）；项目列表 PickerInner 每行健康徽标（待办/进行/完成计数+◆N 待审）；api.ts 增 ProjectReport/MyWork 类型 + getProjectReport/getMyWork；build+vitest 绿；浏览器验证（隔离环境）：报表页四 widget 与 API 数字一致（截图 docs/i39-reports-page.png）、列表徽标「待办 4 · 进行 1 · 完成 1 ◆ 1 待审」（docs/i39-picker-health.png）、我的工作 QA 王 3 项跨项目聚合/李雷 0 项+1 待决策（docs/i39-my-work.png） |
| I40 报表收尾审阅 | 已完成 | 2026-09-04 | 2026-09-04 | CSV 导出端点 `GET /projects/{id}/report.csv`（section,key,title,reason,value 五列、UTF-8、Content-Disposition 附件，与 JSON 同数）；docs/12 §9 报表与工作台（页面/API 对照表 + 漏斗/挂起 Gate/超期/滞留/吞吐口径定义 + 权限语义）；**新增冒烟 18**（造数→漏斗/概念/吞吐/Gate 断言→my/work→CSV 与 JSON 同数→列表健康摘要→rebuild 数字不变）；pytest 128/冒烟 18 全绿 |
| **M12 里程碑审阅（正式）** | 已完成 | 2026-09-04 | 2026-09-04 | 冒烟 18 + I38/I39/I40 各迭代 DoD 逐项核对全过（审阅时点 HEAD `179e3bb` 重跑 pytest 128/冒烟 18）+ 浏览器隔离复演「报表页四 widget + 我的工作跨项目聚合 + CSV 实测」（截图 docs/m12-review-reports-page.png、docs/m12-review-my-work.png，见附录 B） |
| I41 里程碑域与工作项日期 | 已完成 | 2026-09-04 | 2026-09-04 | 新域 `domains/milestones.py`：milestones 投影表 + milestone.created/updated/deleted 事件（rebuild 存活，drop_projections 清单同步补 milestones）；CRUD（POST /projects/{pid}/milestones、GET 列表带进度、GET/PATCH/DELETE /milestones/{id}）；due_date ISO 强校验 422、状态校验优先本体 milestone 概念 states（software-dev: planned/in_progress/achieved）；进度=关联项 done 比例+逾期数（due 已过且存在活跃项）；items 加 start_date/due_date 列（CREATE+ALTER 迁移，item.created 透传/item.updated 可改，ISO 校验 422）；PATCH /items 支持 milestone_id（未知/跨项目 422）；报表超期口径升级三级回退（item.due_date → cf due → 滞留，docs/12 §9 同步）；单测 4 项（CRUD+rebuild/校验 fail-closed 矩阵/进度与逾期计算+rebuild 一致/日期与报表口径边界）；pytest 132/冒烟 18 全绿 |
| I42 时间线视图 | 已完成 | 2026-09-04 | 2026-09-04 | 新页 TimelinePage（`#/p/{pid}/timeline`，rail「时间线」CalendarRange）：日期轴自动适配数据范围（无数据回退今日 -15/+30 天）、周刻度+今日 amber 竖线；行=概念（本体名映射）；条形=有 start/due 的工作项（done 绿/cancelled 灰/活跃 acc）；菱形=里程碑（amber，悬停截止日+完成比+逾期数）；**depends_on 冲突检测**——后置项 start 早于前置项 due 时条形红框+行底红色虚线连接（同行走行底边缘避让条形，不自动改期）；api.ts 增 Milestone 类型 + 里程碑 4 方法 + getItem；build+vitest 绿；浏览器验证（隔离环境）：里程碑菱形悬停进度（Beta 发布 33%）、冲突红条+虚线、日期轴刻度（截图 docs/i42-timeline.png）；**顺带补 I41 缺口**：ItemIn 增 milestone_id（创建即关联，POST 校验未知/跨项目 422 + item.created 投影持久化 + 单测第 5 项）——此前仅 PATCH 可关联 |
| I43 时间线收尾审阅 | 已完成 | 2026-09-04 | 2026-09-04 | 事件 NDJSON 导出 `GET /projects/{id}/events/export`（StreamingResponse 按全局追加序逐行输出、prev_event_id 链位保留、首行 prev 指向全局链前置事件属正常、末行校验和 events/sha256/first_prev/gaps；跨项目间隙容许——全局链含他项目事件）；docs/11 §5 备份与恢复（备份内容表/停机冷备+WAL 在线快照+Git bundle/恢复=rebuild 校验；GitLab「导出≠备份」教训移植）；docs/12 §10 里程碑与时间线（API 表/进度口径/排期字段/时间线交互/导出语义）；**新增冒烟 19**（里程碑全程：CRUD→建卡即关联→进度精确断言→报表超期口径（done 排除）→NDJSON 链序+校验和→rebuild 一致→未知项目 404）；pytest 134/冒烟 19 全绿 |
| **M13 里程碑审阅（正式）** | 已完成 | 2026-09-04 | 2026-09-04 | 冒烟 19 + I41/I42/I43 各迭代 DoD 逐项核对全过（审阅时点 HEAD `edecddd` 重跑 pytest 134/冒烟 19）+ 浏览器隔离复演「时间线页 + 里程碑进度 + NDJSON 导出实测」（截图 docs/m13-review-timeline.png，见附录 B） |
| I44 依赖传播自动排期 | 已完成 | 2026-09-04 | 2026-09-04 | items 加 `auto_scheduled` 列（默认 0=手动，CREATE+ALTER 迁移，PATCH 开关 bool→int）；`propagate_reschedule`：前置项 due 经 item.updated 变化时，对 depends_on 其且开自动的后继项平移 start/due（保时长，无日期后继跳过），**显式 item.rescheduled 事件**（payload follow_of/delta_days/新日期/depth，投影持久化，审计归因）；多级递归（深度上限 20 + visited 防环，环中每项只平移一次）；item.rescheduled 投影器（绝对日期写入，rebuild 幂等）；单测 4 项（单级传播+归因/手动模式零影响/多级递归+环安全+只移一次/rebuild 存活）；前端 Item 类型 + 时间线条形 hover「⏱ 自动排期」标注；pytest 138/冒烟 19 全绿 |
| I45 事件 NDJSON 导入恢复 | 已完成 | 2026-09-04 | 2026-09-04 | `POST /projects/{id}/events/import`（body {data: NDJSON}）：校验和重算比对（原始行 sha256，不匹配 422）+ 逐行 schema 校验（必需字段/JSON 合法/id 严格递增，422）+ 事件 id 与目标库冲突检测（任一冲突整批 409——恢复语义面向空/新库，GitLab 兼容窗口同款务实）；恢复场景目标项目可不存在但 payload 必须含其 project.created（422 否则）；通过后按序直插（保留原始 id/ts/actor，prev 重链到目标库当前头部）→ 全量 rebuild → 返回 {imported, rebuilt}；单测 2 项（roundtrip：导出→monkeypatch 第二个全新 data_dir→导入→工作项/事件流逐行一致；拒绝矩阵：源库重导 409/篡改 422/坏 JSON 422/缺校验和行 422/项目不匹配 422/无残留半导入状态）；pytest 140/冒烟 19 全绿 |
| I46 可携收尾审阅 | 已完成 | 2026-09-04 | 2026-09-04 | docs/12 §11 排程自动化与事件可携（auto_scheduled 语义/显式 rescheduled 审计/导入校验流水线与恢复语义）；docs/11 §5.3 恢复步骤更新（首选 data_dir 还原+rebuild 校验；仅有导出文件时 import 端点实操，id 冲突 409/同代版本约束）；**新增冒烟 20**（A←B←C 自动排期传播链逐项断言 + 导出→第二全新库导入→工作项日期/报表漏斗一致 + 恢复库 rebuild 不变）；pytest 141/冒烟 20 全绿 |
| **M14 里程碑审阅（正式）** | 已完成 | 2026-09-04 | 2026-09-04 | 冒烟 20 + I44/I45/I46 各迭代 DoD 逐项核对全过（审阅时点 HEAD `b1f93cb` 重跑 pytest 141/冒烟 20）+ 浏览器隔离复演「依赖传播时间线 + item.rescheduled 审计链」（截图 docs/m14-review-timeline.png、docs/m14-review-audit-rescheduled.png，见附录 B） |
| **M15 PWA 与移动端适配（I47-I49）** | 已定义 | 2026-09-04 | — | 3 迭代 / 约 9 人日（docs/01 §N + docs/10 §M15）：I47 响应式布局基座（窄屏断点 + rail 折叠 + 横向滚动 + 触控目标）/ I48 PWA 可安装与离线外壳（vite-plugin-pwa generateSW + autoUpdate，**API 永不入 SW 缓存**）/ I49 移动端打磨 + docs/12 §12 + 冒烟 21 + 审阅 |
| I47 响应式布局基座 | 已完成 | 2026-09-04 | 2026-09-04 | AppShell 窄屏断点改造：rail 与功能列 `hidden md:flex`（<768px 折叠）、topbar 增汉堡按钮（md:hidden）+ **移动导航抽屉**（slide-over：12 项导航带图标标签 + 项目功能区 + 遮罩点击/✕/导航后自动关闭）；⌘K 按钮窄屏只留图标（文字 `hidden sm:inline`）；触控目标：审批/通知铃改 `h-9 w-9` flex 居中；身份 chip `whitespace-nowrap shrink-0`、通用 Badge `whitespace-nowrap`（修 375px 下竖排折行）；看板列表视图表格包 `overflow-x-auto` + `min-w-[640px]`；Reports/MyWork/Dashboard 栅格 `grid-cols-1 md:grid-cols-3`（col-span 加 md: 前缀防窄屏隐式轨道）；TimelinePage 根容器 `overflow-auto` + Card `min-w-[640px]`（窄屏横滚保百分比轴）；build+vitest 绿；Playwright 375×812 实测五截图：看板/列表横滚/报表单列/我的工作/抽屉 + 桌面 1440 复核（docs/m15-i47-*.png ×6） |
| I48 PWA 可安装与离线外壳 | 已完成 | 2026-09-04 | 2026-09-04 | vite-plugin-pwa（v1.3.0 generateSW、registerType autoUpdate）+ workbox-window 直依赖（pnpm 严格提升不透传）；manifest（name/short_name/theme_color #18181b/display standalone/start_url `/`/icons 192+512+maskable，PIL 生成靛蓝白 A 图标）；**workbox.navigateFallbackDenylist=[/^\\/api\\//] + 零 runtimeCaching——`/api/*` 永不入 SW 缓存**（事件溯源数据必须在线）；index.html 补 manifest link + theme-color + favicon（修 404）；main.tsx 注册 SW + **顺手修缺陷 ①：sonner `<Toaster>` 全仓从未挂载——所有 toast.* 一直静默无显示，补挂 top-center richColors**；新版本就绪弹「已发布新版本 · 立即刷新」toast。**顺手修缺陷 ②：ProjectPicker 空态引导与错误态混淆**——modal 初始值 `useState(!!projects.length ? false : true)` 使离线/后端故障时误弹「新建项目」（创建必失败），改 `autoOpen={!isError && 空列表}` 传参，保留空库引导排除错误态。验证：build 产物 sw.js+manifest.webmanifest+precache 7 项（源码级无 /api）；浏览器实测（vite preview 生产构建）：SW activated/scope `/`/caches 零 /api 条目/**断网 reload 外壳完整载入**（console 仅 ERR_INTERNET_DISCONNECTED @ /api 符合预期）/新 SW 自动接管（autoUpdate 实测）；375px 移动视口生产构建正常（docs/m15-i48-*.png ×3）；vitest 2 绿、pytest 141 零影响 |
| I49 移动端打磨收尾审阅 | 已完成 | 2026-09-04 | 2026-09-04 | **新增冒烟 21** test_smoke_21_pwa.py（源码级基建断言 VitePWA 配置/navigateFallbackDenylist/零 runtimeCaching 键/manifest link/theme-color/图标两枚；web/dist 存在时产物深检：manifest standalone+start_url+maskable、precache URL 清单零 /api、sw.js 含 /^\\/api\\// denylist；无 dist 则 skip 保留源码级）；**修通知下拉 375px 左溢**（`right-0 w-80`=320px 自右缘 295px 起算左溢 25px → 小屏 `fixed inset-x-2 top-14` 全宽悬浮 + `sm:` 恢复 absolute 原位，实测 panel left:8/right:367）；docs/12 §12 移动端与 PWA（安装/布局对照表/离线边界/更新与 HTTPS 注意）；375px 关键路径触控复核：审批中心 Gate 卡片三操作按钮、通知面板（修后）、NL 命令条全宽动作列表、页面零横向溢出；**pytest 142 项全绿、冒烟基线 21 条 GREEN**（截图 docs/m15-i49-*.png ×4） |
| **M15 里程碑审阅（正式）** | 已完成 | 2026-09-04 | 2026-09-04 | 冒烟 21 + I47/I48/I49 各迭代 DoD 逐项核对全过（审阅时点 HEAD `8fb1499` 重跑 pytest 142/冒烟 21/vitest 2）+ 浏览器隔离复演「375px 移动端全页面 + PWA 安装/离线外壳/autoUpdate」（截图 docs/m15-i47-*.png ×6、m15-i48-*.png ×3、m15-i49-*.png ×4、m15-review-timeline-375.png，见附录 B）；**审阅即修 3 个既有前端缺陷**（Toaster 未挂载/ProjectPicker 离线误弹/通知下拉左溢） |
| **M16 自定义视图与保存筛选（I50-I52）** | 已定义 | 2026-09-04 | — | 3 迭代 / 约 9 人日（docs/01 §O + docs/10 §M16）：I50 视图数据层（saved_views 投影 + view.* 事件 + 定义校验 fail-closed）/ I51 视图前端（看板/列表视图管理器 + URL 直开）/ I52 默认视图 + docs/12 §13 + 冒烟 22 + 审阅；SSO/OIDC 降下一轮候选（需 IdP 演示环境）、digest/跨项目聚合报表留 backlog |
| I50 视图数据层 | 已完成 | 2026-09-04 | 2026-09-04 | 新域 `domains/views.py`：saved_views 投影表（id/project_id/name/owner_id/is_public/definition JSON，CREATE+drop_projections 清单同步）+ view.created/updated/deleted 事件（rebuild 存活）；CRUD（POST /projects/{pid}/views、GET 列表、GET/PATCH/DELETE /views/{id}）；**定义校验 fail-closed 双层**——键白名单（concept_id/status_group/status/assignee_id/priority/cf/group_by，未知键/空值/坏枚举/非 dict 422）+ 项目上下文（group_by=field:xxx 与 cf 的字段须本体声明**且项目未停用**）；**权限对齐 M8**：local 全放行；network 下 public 成员可读/private owner+admin、viewer 不可建、改删仅 owner+admin、非成员列表与详情 403；**执行纯复用**：get_items/get_board 增 view_id（definition 提供基础过滤、显式 query 参数覆盖；cf 匹配提取为模块级 `_cf_hit` 共用）；单测 4 项（CRUD+rebuild 前后一致/校验全矩阵含停用字段/执行与手工过滤同数+显式参覆盖+board 视图同数/network 可见性矩阵）；pytest **146** 全绿、冒烟 21 GREEN |
| I51 视图前端 | 已完成 | 2026-09-04 | 2026-09-04 | 看板工具栏「视图」管理器：chip 按钮（当前视图名高亮 acc/未选中中性）+ 下拉面板（视图列表：应用/公开徽标/「当前」标注/hover 删除 ✕；保存区：名称输入+项目内公开勾选+保存；退出当前视图保留过滤）；**视图=过滤参数命名快照**——应用视图把 definition 写回 URL params（priority/assignee/group，功能切片保留），删当前视图自动清 view 键；**直开 `?view=<id>` 自动补齐 definition 参数**（显式 params 优先——分享链接还原语义）；api.ts 增 SavedView 类型 + listViews/createView/patchView/deleteView；build+vitest 绿；浏览器隔离复演（生产构建）：保存「高优先级」（priority=high+公开）→ URL `?priority=high&view=vw_x`、保存「按标签分组」（group=field:tags）→ 点击切换 chip 高亮+group 键被视图定义替换、**直开 `?view=vw_x` 自动补齐 priority+group** 分组下拉即选「分组：标签」（截图 docs/m15-i51-*.png ×5：保存面板/已保存/下拉列表/切换后/直开还原） |
| I52 收尾审阅 | 已完成 | 2026-09-04 | 2026-09-04 | **默认视图**：view.made_default 事件（投影先清项目内全部再设——rebuild 重放顺序执行幂等）+ saved_views.is_default 列（CREATE+ALTER 迁移）+ `POST /views/{id}/make-default` + board 无 view/group 参数时自动落项目默认视图（响应 `applied_view_id`）；前端 chip 认 applied_view_id（默认视图落点可见）、视图列表「设为默认」/「默认」徽标、**分组控件同步实际生效值**（`group || board.data?.group_by`）；**修 db.py 迁移条件 bug**——表名误查进列名集合致 ALTER 永不执行（隔离存量库 board 500 暴露，`sqlite_master` 存在性检查与列检查拆开修正）；docs/12 §13 自定义视图指南（定义 schema 表/权限/前端与默认视图）；**新增冒烟 22**（视图全程：CRUD→校验门→执行与手工过滤同数→make-default→board 落点→rebuild 一致→删除回落）；pytest **147** 全绿、冒烟基线 **22 条 GREEN**；build+vitest 绿（截图 docs/m15-i52-default-landing.png、m15-i51-made-default.png） |
| **M16 里程碑审阅（正式）** | 已完成 | 2026-09-04 | 2026-09-04 | 冒烟 22 + I50/I51/I52 各迭代 DoD 逐项核对全过（审阅时点 HEAD `8b37d72` 重跑 pytest 147/冒烟 22/vitest 2）+ 浏览器隔离复演「视图保存/切换/公开徽标/URL 直开/默认直达」（截图 docs/m15-i51-*.png ×5、m15-i51-made-default.png、m15-i52-default-landing.png，见附录 B）；审阅即修 db.py 存量迁移条件 bug |
| **M17 OIDC 单点登录（I53-I55）** | 已定义 | 2026-09-04 | — | 3 迭代 / 约 10 人日（docs/01 §P + docs/10 §M17）：I53 OIDC client 基座（discovery + code flow + PKCE + JIT 建号四约束 + 本地 JWT 桩单测）/ I54 会话整合与前端（OIDC 按钮 + admin 配置面板 + 门禁兼容）/ I55 Keycloak 演示环境 + docs/12 §14 + 冒烟 23 + 审阅；digest/事件归档/聚合报表留 backlog |
| I53 OIDC client 基座 | 已完成 | 2026-09-04 | 2026-09-04 | 新模块 `core/oidc.py`（**零新依赖**：cryptography+httpx 已有，RS256 验签自实现——jwks kid 匹配 + RSA PKCS1v15/SHA256；不引 authlib）：discovery 一小时缓存、authorization URL（state/nonce 随机 + PKCE S256，三元组存 HttpOnly SameSite=Lax 十分钟 cookie）、`POST token_endpoint`（basic auth 换 code）、id_token 全校验（alg 白名单 RS256/签名/iss/aud/exp 60s leeway/nonce 常量时间比较）；**JIT 四约束**（Gitea 教训 docs/01 §P.3）：email 缺失或未验证 422、allowlist `APM_OIDC_ALLOWED_GROUPS` 非空无交集 403、同 email 存量账号幂等重入、同名本地账号 409 不自动合并；**角色一次性定** viewer 缺省、重登不重派（规避 #32566 时序坑）；env 未配置整体 404 关闭（SMTP 同款）；`GET /api/auth/oidc/login|callback`（回调签发 M8 同款 HMAC 会话 + 清握手 cookie）；单测 5 项（**本地 RSA JWT 桩** monkeypatch httpx get/post 离线覆盖：全协议路径/JIT 重登幂等/拒绝矩阵七例——签名篡改/issuer 伪造/过期/nonce 重放/state 不符/email 未验证/组越界/账号冲突 409/拒绝路径零建号）；pytest **152** 全绿、冒烟 22 GREEN。测试踩坑：**TestClient 默认 follow_redirects=True**——302 到外部 IdP 后 404 误导为「路由缺失」，登录/回调断言须 `follow_redirects=False`；register_user 入参是 pydantic UserIn 非 dict |
| I54 会话整合与前端 | 已完成 | 2026-09-04 | 2026-09-04 | `GET /api/auth/oidc/status` 特性探针（enabled/issuer/client_id/redirect_uri/allowed_groups，**secret 不回显**）；前端：`/login` 页「🔑 使用单点登录」按钮（status.enabled 才显示，href 直达 authorize）+ 本体页「OIDC 单点登录」诊断面板（配置展示/组白名单徽章/JIT viewer 语义注记/未配置提示 env）；api.ts oidcStatus；`tools/oidc_stub.py` **mini IdP 桩**（ThreadingHTTPServer：discovery/jwks 内存化、authorize 即 302 回 callback、token 校验 basic auth+PKCE 并 RS256 签发含 groups claim 的 id_token）——浏览器真流程演示用；门禁兼容单测（OIDC JIT 用户非成员写 403，M8 门禁自动生效）；单测 6 项；**浏览器桩全流程复演闭环**：登录页按钮 → 桩 authorize → callback → 会话（me=`u_oidc_*`/zhang.demo/source=session）→ 顶栏 chip「👤 zhang.demo」→ 越权写 403 → OIDC 面板可见（截图 docs/m17-i54-*.png ×3）；build+vitest 绿。复演踩坑：本地双端口下 redirect_uri 须指向前端域（preview 代理同源），否则会话 cookie 种在 API 域前端不可见——生产 nginx 同域天然无此问题；**Windows 允许多进程同时 LISTEN 同一端口**（桩双实例请求随机分流致 token 混乱，netstat 确认单监听是排障第一步） |
| I55 收尾审阅 | 已完成 | 2026-09-04 | 2026-09-04 | `tools/keycloak/` 演示环境（docker-compose + realm-agentpm.json：client agentpm/用户 zhang.demo·li.admin/组 agentpm-admins·users 三件套 import）与 `tools/oidc_stub.py` mini IdP 桩在位；docs/11 §2.1 OIDC env 表与流程注记（redirect_uri 同源语义/JIT 四约束摘要）；docs/12 §14 OIDC 单点登录指南（协议安全语义/JIT 四约束表/门禁兼容/Keycloak 与桩两种演示）；**新增冒烟 23**（特性关闭零破坏——404 与 local 回退不变/桩协议全路径/JIT 幂等单账号/M8 门禁保留）；pytest **154** 全绿、冒烟基线 **23 条 GREEN** |
| **M17 里程碑审阅（正式）** | 已完成 | 2026-09-04 | 2026-09-04 | 冒烟 23 + I53/I54/I55 各迭代 DoD 逐项核对全过（审阅时点 HEAD `84c57cc` 重跑 pytest 154/冒烟 23/vitest 2）+ 浏览器隔离复演「登录页 SSO → 桩 authorize → callback → 会话 → 门禁 → OIDC 面板」（截图 docs/m17-i54-*.png ×3，见附录 B） |
| **M18 工作项评论与参与通知（I56-I58）** | 已完成（审阅通过） | 2026-09-04 | 2026-09-04 | 3 迭代 / 约 9 人日（docs/01 §Q + docs/10 §M18）：I56 评论域（comment.* 事件 + @mention → 通知 + 参与投影）/ I57 评论前端（评论区 + mention 补全 + 通知跳转）/ I58 订阅（watch/subscriber）+ docs/12 §15 + 冒烟 24 + 审阅（截图 docs/m18-review-*.png ×6，见附录 B）；审阅即修 change_status actor 硬编码归因缺陷；工时跟踪留下一轮首选候选、通知层级细分/富文本留 backlog |
| **M19 工时跟踪与汇总报表（I59-I61）** | 已完成（审阅通过） | 2026-09-04 | 2026-09-04 | 3 迭代 / 约 9 人日（docs/01 §R + docs/10 §M19）：I59 工时数据层（time.* 事件 + item_time_entries 投影 + CRUD + spent 汇总 + 权限对齐）/ I60 工时前端（记工时抽屉 + spent/estimate 徽标 + docs/12 §16 + 冒烟 25）/ I61 项目工时报表（按人/按日聚合，补 Plane #8045 缺口）+ 冒烟 25 收尾 + 审阅（截图 docs/m19-i60-*.png ×4 + m19-i61-*.png ×3，见附录 B）；个人日历视图/成本费率/斜杠命令留 backlog |
| I59 工时数据层 | 已完成 | 2026-09-04 | 2026-09-04 | 新域 `domains/timelog.py`：item_time_entries 投影表（软删 deleted_at，drop_projections 同步）+ time.logged/edited/deleted 事件（rebuild 存活）；CRUD（POST/GET /items/{id}/time_entries、GET/PATCH/DELETE /time_entries/{id}）；**校验 fail-closed**（minutes∈(0,1440]/spent_on ISO 日期/note 截 500/空更新 422）；item 详情与 get_items 附 **spent_minutes 汇总**（列表单 GROUP BY 查询合并，与 estimate_hours 计划/实际并列）；权限对齐 M8（改删限本人·admin）；记工时者进参与投影（source='time' 首次来源语义）；单测 4 项；pytest **165** 全绿 |
| I60 工时前端 | 已完成 | 2026-09-04 | 2026-09-04 | 新组件 `TimeLogModal.tsx`（⏱ 抽屉：条目列表 人/时长徽标/日期/备注 + 记时表单 minutes/spent_on/note + **合计行**实时更新，`fmtMinutes` 时长格式化 1h30/45m）+ 看板卡片 **⏱ spent 徽标**（spent_minutes>0 才显示）与 ⏱ 按钮（与 💬 并列）；api.ts 增 TimeEntry 类型+4 方法+Item.spent_minutes；docs/12 §16 工时跟踪指南；**新增冒烟 25**（双身份记时→合计/详情/列表三处一致→校验门→软删缩合计→rebuild 条目与徽标复现）；浏览器隔离复演：李雷记 90m「⏱ 1h30」徽标上卡→切 QA 王见首条目再记 45m→**合计 2h15**（截图 docs/m19-i60-*.png ×4）；build+vitest 2 绿、pytest **166** 全绿、冒烟基线 **25 条 GREEN** |
| **M20 体验补齐三件套（I62-I64）** | 已定义 | 2026-09-05 | — | 3 迭代 / 约 8 人日（docs/01 §S + docs/10 §M20）：I62 个人工时日历（GET /my/timelog 聚合 + 周/月日历页 + 点日快捷记时，OpenProject 16.0 My time tracking 吸收）/ I63 时间线拖拽改期（条形拖拽移动+右缘缩放 → PATCH，补 M13 只读与 M14 自动排程之间的手动层）/ I64 评论 Markdown 渲染（GFM 只读 + mention chip + 预览，存储保持纯文本）+ docs/12 §17 + 冒烟 26 + 审阅；**验证纪律更新**：迭代期只跑相关测试、全量回归收敛至 M20 审阅（用户 2026-09-05）；start/end 打卡/依赖连线图内编辑/任务清单回写留 backlog |
| I62 个人工时日历 | 已完成 | 2026-09-05 | 2026-09-05 | `GET /my/timelog?days=`（本人条目按日分组 + 日合计 + 窗口合计，days 钳 1-60，纯投影聚合 JOIN items/projects 取标题与项目名，own-data 语义对齐 my/work）；「我的工时」页 `#/my/time`（**周/月双视图** + 今日高亮 + 前后翻页 + 窗口合计 chip；**点日期格快捷记时**：条目列表点选编辑/✕ 删除 + 工作项下拉取「我的工作」指派项 + 分钟/备注表单**预填 spent_on**；编辑仅改时长备注——time.edited 语义，改日期走工作项 ⏱ 抽屉）；侧栏「我的工作」旁 CalendarClock 入口；api.ts MyTimelog/getMyTimelog；单测 test_my_timelog_calendar_feed（按日分组/仅本人/软删剔除+rebuild 存活/钳制）；timelog **7 项**绿、build+vitest 绿 |
| I63 时间线拖拽改期 | 已完成 | 2026-09-05 | 2026-09-05 | TimelinePage 条形可拖拽（**OpenProject Gantt 内建拖拽吸收**，补 M13 只读与 M14 自动排程之间的手动层）：拖动条形整体移动（start/due 同步平移）、右缘把手缩放（仅改 due，**钳制不早于 start**）、pointer capture 跟手 + 拖拽中**半透明**（ANKO 借鉴）+ title 悬浮「改为 X ~ Y」实时预览、**Esc 取消**/pointercancel 回滚；落点即 PATCH start_date/due_date 走既有端点——M14 rescheduled 审计、依赖传播与冲突重算着色随 refetch 自动生效；单测 test_drag_move_semantics_and_audit（拖拽载荷=双日期单 PATCH→落点正确 + 自动后继 delta_days=3 传播 + item.rescheduled 审计 / 右缘=仅 due 改 start 不动）；scheduling **5 项**绿、build+vitest 绿 |
| I61 项目工时报表+收尾审阅 | 已完成 | 2026-09-04 | 2026-09-04 | `GET /projects/{id}/timelog_report`（按人合计 JOIN users + 按日趋势 + 窗口 1-90 天参数化，纯投影聚合零 ETL——**直接补位 Plane GH #8045 项目级工时分析缺口**）；my/work 增 week_minutes 本周合计（个人最小面）；ReportsPage 工时小部件（按人条形+按日趋势+合计）+ MyWorkPage 本周工时 chip；对账单测（报表聚合=条目清单逐项相等+软删剔除+404）；复演报表小部件合计 2h15=李雷1h30+QA王45m 与条目一致（截图 docs/m19-i61-*.png ×3）；build+vitest 2 绿、pytest **167** 全绿、冒烟 **25** GREEN |
| I56 评论域 | 已完成 | 2026-09-04 | 2026-09-04 | 新域 `domains/comments.py`：item_comments 投影表（软删除 deleted_at）+ item_participants 参与投影（PRIMARY KEY 去重 INSERT OR IGNORE）+ comment.created/deleted 事件（drop_projections 清单同步）；**@mention 解析**——`@姓名` 对 users.name 精确最长匹配（多字姓名「QA 王」可用、作者自身排除），mentions 入事件；**mention 通知走 M10 notification.sent 通道**（kind=mention，站内铃+邮件自然联动）；参与面接入 item.assigned（human 指派即参与）；CRUD：POST/GET /items/{id}/comments、DELETE /comments/{id}（软删），权限 local 放行/network 成员读写+非成员 403+删除 author·admin；单测 4 项（CRUD+软删除+rebuild 一致/mention 解析与逐身份通知断言/指派参与者去重/network 权限矩阵）；pytest **158** 全绿、冒烟 23 GREEN。测试踩坑：/api/notifications 按当前身份过滤——逐身份断言须 /session/identity 切换被提及者 |
| I57 评论前端 | 已完成 | 2026-09-04 | 2026-09-04 | `CommentsModal.tsx`（列表 author_name+@提及高亮/输入/**@补全下拉** lastIndexOf 后缀匹配/Ctrl+Enter/hover 删除）+ 看板卡片 💬 按钮与**评论数徽标** + **`?item=<id>` 直开**（useEffect 找 buckets 命中即开）+ 通知中心 mention 项**点击跳转**（get_notifications 以 ref_event_id→events.agg_id 解析 item_id）**且点击即置已读**；审阅即修 2：mention 摘要带工作项标题（非裸 id，测试补断言）、跳转后徽标清零；复演排障定案「铃 1 面板空」= 双后端进程双绑 8000（Windows 允许）——netstat 单监听后重建隔离环境复演全通（@补全→mentions=["qa"]→QA 王铃 1→带标题通知→跳转 Modal 开+高亮+清零，截图 docs/m18-i57-*.png ×4）；build+vitest 2 绿、pytest **158** 全绿 |
| I58 订阅与收尾 | 已完成 | 2026-09-04 | 2026-09-04 | **工作项订阅**：item.subscribed/unsubscribed 事件 + 投影（watch 参与行；退订只删 watch 行——assignee/author/mentioned 为派生参与不随退订消失，rebuild 幂等）+ `POST/DELETE /items/{id}/subscription`（自订阅）+ 评论抽屉「🔕 订阅/🔔 已订阅」切换（participants+当前身份推导）；**通知面接入参与者**（最小面：新评论与状态变更）——plan_notifications 扩展 comment.created（参与者，排除作者与被提及——后者已有定向 mention 通知，防双发）与 item.status_changed（参与者，排除操作者），**NOTIFY_EVENTS 同步扩展故邮件通道自动一致**；踩坑 2：comment.created 的 agg_id 是评论 id，item 须取 payload（单测拦住）、task 合法状态集无 todo（open/ready/in_progress/awaiting_review/done/cancelled）；**语义决策**：软删除评论不撤回已发通知（通知 append-only，撤回需负向事件成本不成比例）；docs/12 §15 评论与参与通知指南；**新增冒烟 24**（CRUD 软删→mention 通知+深链→参与集合首次来源胜出→订阅→状态变更+新评论通知参与者→rebuild 三投影一致）；单测 +1（订阅+参与者通知+退订降噪+rebuild）；pytest **160** 全绿、冒烟基线 **24 条 GREEN**、build+vitest 2 绿 |

## 8. 开发执行风险（补充 07 §6）

| 风险 | 应对 |
| --- | --- |
| LangGraph API 演进 | 版本锁定 pin；Runtime 与 Orchestrator 间内部接口隔离（07 §6 已列）；升级作为独立任务评估 |
| LLM 不可用/成本波动 | 录制回放模式隔离（军规 5）；fixtures 入库；真实模型仅人工验收 |
| Windows 开发环境差异（路径/换行/文件锁） | 仓库统一 POSIX 路径 + LF；SQLite 单写者；docker-compose 兜底复现问题 |
| 前端面积大、易返工 | demo.html 即规范，逐页复刻对照；shadcn/ui 兜底质感，不做视觉自研 |
| 单人节奏中断（跨会话） | §6 协议 + 状态看板 + 开发日志；迭代 ≤1 周保证断点小、恢复快 |
| 范围蔓延 | §5.4 变更控制；C 级意见坚决入 backlog |
| 事件/投影一致性 bug | I1 起冒烟内置 replay 一致性断言，每迭代回归 |

## 附录 A · 开发日志（逐迭代追加）

| 日期 | 迭代 | 记录 |
| --- | --- | --- |
| 2026-08-22 | — | 开发计划 v1.0 制定（本册）。方案基线 v0.3（含 demo.html UI 规范与 07 §2.5 复用清单）已就绪，下一步入口：I0 脚手架。 |
| 2026-08-22 | I0-I4 | M1 完成：事件内核（触发器强制 append-only、投影器注册表、rebuild、SSE 总线）；本体服务（software-dev/generic 双 YAML + 校验）与项目/功能/工作项域；对话域（消息树 parentId、打断/恢复/注入、L1-L4 上下文与 L1/L3 编辑版本化）；内容仓 git CLI 封装（写=commit+artifact.* 事件、diff/版本史）。环境差异：开发机 Python 3.11.5（计划 3.12），兼容无碍。 |
| 2026-08-22 | I5-I6 | M2 后端完成：LangGraph 1.0 角色子图（analyze→draft→self_check→gate→apply）+ SqliteSaver checkpoint；provider 双实现（replay 模板按 role+node 注入上下文，保证"打断→注入→恢复→产出含约束"确定性可测）；工具三级权限 fail-closed + 危险工具单次授权；span OTel+apm.* 锚点；审批域（快照、拒绝必填理由、批量、修改后恢复）；Orchestrator（本体 gate 重映射——generic 项目将 prd_review 映射为 work_review、阶段状态机 passed/skipped/active/pending、依赖就绪调度、批量启动、PRD 批准→Planner 自动接续）。自研收敛符合 §2 边界。 |
| 2026-08-22 | I7-I9+I11 | M2 前端完成：AppShell（暗色 rail 八项+功能栏+⌘K+审批铃铛）、SSE→TanStack Query 增量桥、对话视图（消息流/步骤行展开 span/打断-恢复/上下文抽屉 L1-L4+合并预览/内联审批横幅）、功能页三 Tab+简报卡、五桶看板（过滤/多选/批量"让 Agent 做"）、审批中心（diff 预览/批量/拒绝理由）、Runs 左树右甘特+人机交织时间线、React Flow 项目图（阶段/Gate/任务节点、状态着色、节点抽屉联到对话）。浏览器实测完整闭环通过。UI 组件为轻量自研（zinc+indigo 令牌与 demo.html 一致），Radix/shadcn 源码级替换列为后续 B 级意见。 |
| 2026-08-22 | I10 | NL 命令层 L1：确定性规则解析器（导航/过滤/指派者/批量审批），本体词典可扩展；只读动作直执返回客户端应用，写操作 pending_confirm→confirm 后经审批域执行；ui_command.executed 事件携带 on_behalf_of；解析失败 422 + 候选列表降级。 |
| 2026-08-22 | I12 | 资产域：资产仓 Git（frontmatter 元数据）、FTS5 中文 bigram 检索、沉淀路径 A（工件→draft→submit_review→asset_review Gate→批准发布）、Agent 三工具 search/read/link（read 触发 asset.consumed）、来源/引用双链与引用计数投影；工件抽屉"沉淀为资产"表单（本体 accepts 过滤）。 |
| 2026-08-22 | I13+终验 | 部署与终验：docker-compose（api+web/nginx 代理 SSE）、种子脚本 tools/seed.py（回放模式全流程演示数据）、README 开发指南。冒烟 7 条全绿（tools/smoke/reports/latest.md：passed 10）；pytest 50 项全绿；pnpm build/vitest 通过；compose 起栈后 /api/health 健康检查通过。功能完备性核对（03 §5 MVP 列）逐行勾验：三级导航/消息树/打断恢复/提示词披露/五类对话（操作型=MVP 子集）/审批批量+改后恢复/工件 diff/看板过滤/NL L1/发布说明/审计/资产沉淀检索双链全部落地；"转对话"与功能小图为 V1.1/V1.2 计划项。 |
| 2026-09-02 | M4 启动 | 按持续迭代协议（MVP 完成后调研开源吸收优点）：调研 semantica v0.6.7（OntologyGenerator infer_classes/infer_properties、provenance、VersionManager、CQ），裁剪映射进 08 §8「本体构建闭环」；新增 M4 = I14 本体归纳 / I15 语义 diff / I16 CQ 检查。范围变更记录：MVP 计划外新增里程碑，理由 = 用户目标第 2 条（融合 semantica 本体构建模式）+ 原路线 V2「从数据归纳概念」提前，对估时影响 +9 人日。 |
| 2026-09-02 | I14 | 本体归纳落地：`POST /api/ontologies/{name}/learn`（确定性规则 L1 字段显式化/L2 关系补注册/L3 沉淀链接补全/L4 角色覆盖，候选带 provenance：规则+support+样本 id；observations 输出零使用概念）→ `POST /api/ontologies/{name}/apply`（patch 合并→校验器把关→YAML version+1→ontology.updated 事件含 diff 摘要→热重载）；幂等（已应用候选不再提出）；未知/过期候选 422 fail-closed。Settings 新增 ontology_dir_override（测试隔离本体目录，写回不碰源仓）；conftest 加 isolated_ontologies 夹具。本体页新增学习面板（勾选+provenance 展示+应用）。测试 55 项绿（新增 4+1）；冒烟基线 11 条全绿（新增冒烟 8）。下一步入口：I15 本体版本化语义 diff 与迁移。 |
| 2026-09-02 | I15 | 本体版本化落地：新增 `app/apm/domains/ontology_versions.py`——apply 时双写版本快照（`data/ontology_history/<name>/v<N>.yaml`，旧版+新版，data/ 已 gitignore）；`GET /api/ontologies/{name}/diff`（语义 diff：concepts 增删改含字段/状态/角色/工件种类级变更 + relations/phases/asset_kinds 增删；影响分析：被删概念仍被工作项引用=阻塞、被删关系仍有数据行=阻塞，无引用删除/阶段/资产类型残留=警告；to=当前版本永远读活文件，支持对磁盘手工改动先做影响分析；活文件校验错误作 warnings 呈现不阻断分析）；`GET /api/ontologies/{name}/history`（ontology.updated 事件时间线+快照清单）。关键语义决策：**from 侧快照优先、to 侧活文件优先**——否则手改后 from==to 同源导致 diff 为空（开发中踩过）。本体页新增版本时间线（逐事件"对比"按钮）与 diff 渲染（增删改 chip+阻塞红卡+警告灰条）。测试 58 项绿（新增 3）；冒烟 8 扩展至二次 apply→v3→history→diff→手改阻塞分析，11 条全绿。下一步入口：I16 CQ 可回答性检查。 |
| 2026-09-02 | I16 | CQ 可回答性落地：新增 `app/apm/domains/ontology_cq.py`——ontology YAML 顶层可选 `cq_mappings`（question 精确匹配 competency_questions + supports 数据面声明，source 枚举 items/relations/approvals/assets/runs/events/artifacts，可带 concepts/relation_types/kinds/event_types 过滤），校验器新增四条规则（question 存在、不重复、supports 非空、events 必带 event_types）；`GET /api/ontologies/{name}/cq-check` 三态报告——answerable（任一支撑面有数据）/no_data（映射了但全空）/unmapped（未声明），证据摘要含计数+分布+样例；内置本体 software-dev 四条 CQ 全映射、generic 留一缺数据一缺映射；本体页 CQ 卡片升级为逐条状态徽标+证据行。测试 61 项绿（新增 3）；冒烟 8 扩展 CQ 全链（software-dev 四条可回答 + generic 三态）。 |
| 2026-09-02 | M4 审阅 | **M4 里程碑正式审阅通过**：① 冒烟基线 11 条全绿（pytest 61 项绿）；② 08 §8.3 四项验收锚点逐项核对（见附录 B）；③ 浏览器实测演示路径：起 uvicorn（临时数据目录、回放模式）+ seed.py + pnpm dev → 本体页「扫描项目数据」→ 候选（L1 任务×priority，support 12 + provenance 样本）→ 勾选应用 → v2 + 时间线 + 「对比」语义 diff（~任务 field-added:priority）→ CQ 卡片「可回答 4 · 缺数据 0 · 缺映射 0」逐条证据；截图 docs/m4-review-ontology-page.png。审阅意见 2 条 B 级（见附录 B），无 A 级。M4（semantica 本体构建模式融合）至此闭环。 |
| 2026-09-02 | M5 启动 | 按持续迭代协议开启新一轮调研：semantica v0.6.7 Semantic Extraction（方法降级链 llm→ml→pattern、置信度 0.65–0.85、实体级 provenance、先共指消解后抽关系），结论入 docs/01 §C.3.1——本项目 L1–L4 规则即链中 pattern 层，LLM 通道为链顶层、汇入同一人审 apply。新增 M5 = I17 LLM 辅助归纳（+清偿 M4 审阅 B 级：CQ events 证据按项目过滤）/ I18 本体模板包 / I19 多人协作基础。范围变更：计划外新增里程碑，理由 = 目标第 5 条（调研吸收优点持续推进），估时 +11 人日。 |
| 2026-09-02 | I17 | LLM 层归纳落地：新角色 `ontology-curator`（YAML + 提示词 L4 `agents/prompts/roles/ontology-curator.md`，输出契约 = 纯 JSON 候选）；`POST /api/ontologies/{name}/learn-llm`——组装上下文（概念清单/使用统计/无沉淀工件种类/资产类型/关系）→ Provider Adapter（回放模板 `ontology-curator/curate` 按"命名覆盖"启发确定性产出，openai 模式即真实抽取）→ JSON 归一化为既有 4 类 patch 候选 → confidence<0.65 丢弃 → 与 pattern 候选按 id 合并（provenance.channels = pattern/llm 双通道标注 + llm_rationale）；JSON 损坏/提供方异常 → 优雅降级仅报 error，pattern 层不受影响（fallback 链精神）；apply 改用合并扫描，LLM 候选经同一校验/版本+1/事件链路。回放模板曾误放在 `_TEMPLATES` 字典之后导致 NameError（已修——模板函数必须在注册表之前定义，记入 HANDOFF 坑）。B 级修复：cq-check events 证据 = 本体项目事件 + 全局（project_id=''）事件，其他项目不计。测试 65 项绿（新增 4：唯一候选 apply/合并去重/低置信丢弃与降级/CQ 事件过滤）；冒烟 8 扩展 learn-llm→apply v4→幂等，11 条全绿；pnpm build/vitest 通过。下一步入口：I18 本体模板包导出/导入。 |
| 2026-09-02 | I18 | 本体模板包落地：新增 `app/apm/domains/ontology_pack.py`——`GET /api/ontologies/{name}/export`（单 JSON 包：ontology + 概念引用的角色 YAML + 角色提示词 L4，缺角色记 missing_roles）；`POST /api/ontologies/import`（as_name 改名防冲突 409、validate_ontology_dict 把关 422、角色文件「存在即复用、缺失才创建」绝不覆盖、`ontology.imported` 事件落审计、热重载本体与角色注册表）。Settings.agents_dir_override + conftest 隔离 agents/ 树——导入写角色文件从此不可能污染源仓。本体页头部加「⬇ 导出模板包」（blob 下载）与「⬆ 导入」面板（粘贴包 JSON+新名字）。测试 70 项绿（新增 5：包结构/导出容错/改名导入+建项目+事件/冲突与坏包 422/新角色创建+注册表生效）；冒烟 8 扩展导出→改名导入→新建项目→冲突 409，11 条全绿；pnpm build/vitest 通过。下一步入口：I19 多人协作基础。 |
| 2026-09-02 | I19 | 多人协作基础落地：新增 `app/apm/domains/users.py`——users 表（schema + drop_projections 同步）与 `user.registered/updated` 投影（事件溯源一致，rebuild 可重建）；启动自举默认用户（users 空才发 `user.registered`，幂等）；`GET /api/users` / `POST /api/users`（id 派生：ASCII slug，中文姓名退化为 u+短随机；非法字符 422）/ `POST /api/session/identity`（切换落 `session.identity_switched` 事件，from/to 可审计）。**emit 身份透传**：core/events.emit 的 actor_id 默认改为运行时读 `settings.user_id`，并全仓清扫域函数层硬编码（events/items/features/conversations/scheduler/spans 五处）——切换身份后一切操作归属新身份审计流。items human 指派必须为注册用户（fail-closed 422）、role 指派自由；items 投影附 assignee_name。`GET /api/events` 增 actor_id、`GET /api/approvals` 增 decided_by。前端顶栏身份切换菜单。测试 75 项绿（新增 4 + 内核测试修正：聚合过滤代替绝对总数、rebuild 计数动态化——boot 自举事件会进流）；冒烟基线增至 **12 条**全绿（新增冒烟 9：双身份按人可分审计流+指派校验+过滤）。**踩坑**：夹具 teardown 顺序——monkeypatch 还原在夹具后置代码之后执行，isolated_ontologies 必须先显式清 override 再 reload，否则隔离副本残留本体缓存引发"unknown concept"跨用例污染（套跑才暴露）。下一步入口：M5 审阅。 |
| 2026-09-02 | M5 审阅 + M6 启动 | **M5 里程碑正式审阅通过**（附录 B：各迭代 DoD 全对 + 浏览器演示注册「QA 王」→ LLM 建议 → 应用 v2，截图 docs/m5-review-collab-page.png；本次演示同时隔离 data+ontologies，M4 教训落实）。随即开启新一轮调研（目标第 5 条）：OpenProject 自定义字段（八格式+双层激活+可过滤标记）、Plane 工作项类型（六属性+按属性分组）、LangGraph 1.0.9→1.2.11 评估（同大版本可升），结论入 docs/01 §D。新增 M6 = I20 自定义字段值 / I21 看板字段分组 / I22 LangGraph 升级验证。范围变更：计划外新增里程碑，理由 = 目标第 5 条（调研吸收优点持续推进），估时 +9 人日。 |
| 2026-09-02 | I20 | 自定义字段值落地：校验器新增字段类型枚举（+boolean/multiselect）与 values 必填；`items.custom_fields` JSON 列（init_db 内 PRAGMA 检查 + ALTER 迁移）；create/patch 双路径 `_validate_custom_fields`（未声明 422 / 类型严判 422，boolean 显式排除 int）；item.created/updated/assigned 三投影透传；`GET /items?cf=field:value`（multiselect 包含匹配）；get_item/list_items/get_item_detail 统一 `_parse_cf`。内置本体演示字段：bug.regression:boolean、task.tags:multiselect。**顺手修掉两个隐藏投影 bug**：① `item.updated` 投影 `sets.append(a, b)` 双参 TypeError——此前该分支从未收到过可写键，custom_fields 首次踩中；② INSERT 参数序与列序错位（cf 插在 priority 后、列在 estimate_hours 后，单事件建项时 assignee 恰好仍是位序错位最前面的，套跑才炸）。教训：**投影器 INSERT 列序与参数序必须目视逐列核对**。测试 79 项绿（新增 4：类型往返+过滤/fail-closed 三态/rebuild 一致/校验器）；冒烟 9 扩展 cf 过滤断言，12 条全绿；pnpm build/vitest 通过。下一步入口：I21 看板字段分组。 |
| 2026-09-03 | I21 | 看板按自定义字段分组与展示：`GET /projects/{id}/board` 增 `group_by` 参数（默认取本体 board_defaults.group_by，缺省 lifecycle），`field:<id>` 按概念声明字段分桶——声明 values 保持本体顺序（空列保留）、multiselect 每值一列（工作项扇出复现，label 看板语义）、boolean 用 true/false 字面量（与 cf 过滤一致）、无值项入「未设置」列（恒最后）；未声明字段/未知模式 422 fail-closed。前端：看板页分组选择器（生命周期 + 跨概念去重全部声明字段，选中状态入 URL `?group=`）、卡片自定义字段徽标（`customFieldBadges` 按概念声明渲染，功能页切片同步）、列表视图增「字段」列。测试：新增 test_board_group_by_custom_field（pytest 80 项绿）；冒烟 9 扩展分组断言（声明桶序 frontend/backend/infra/_none、未声明 422、生命周期兜底），12 条 GREEN；pnpm build/vitest 通过。浏览器验证：隔离 data+ontologies 起服务种数切「分组：标签」，multiselect 扇出与徽标可见，截图 docs/i21-board-field-grouping.png。 |
| 2026-09-03 | I22 | LangGraph 1.2.11 升级验证（docs/01 §D.3 评估结论落地）：`pip install langgraph==1.2.11` 连带 langchain-core 1.6.1 / langgraph-prebuilt 1.1.0 / sdk 0.4.4，langgraph-checkpoint-sqlite 3.1.1 不动；requirements 下限 `>=1.0.9`→`>=1.2.11`。**全量回归零改动通过**：pytest 80 项绿（Runtime 子图/录制回放/SqliteSaver 断点恢复/审批 Gate 全覆盖）、冒烟 12 条 GREEN。浏览器打断-注入-恢复演示（隔离 data+ontologies）：pm-agent 起草至 prd_review Gate 挂起（PRD commit 4773fa48）→ 对话内注入约束「必须兼容 Python 3.9…导出 Markdown」→ ▸ 继续（resume 从 checkpoint 续跑 revise）→ 产出新 PRD commit 9fa29d18 且 §5 补充约束逐条包含注入内容、重新回到 Gate → 批准后 run succeeded。截图 docs/i22-interrupt-inject-resume.png。**无需回退**；1.0.9 期间无遗留分支。M6 三个迭代（I20/I21/I22）全部完成，待 M6 正式审阅。 |
| 2026-09-03 | M6 审阅 + M7 定义 | **M6 里程碑正式审阅通过**（附录 B）：审阅时点 HEAD `6e73cde` 重跑 pytest 80 项 + 冒烟 12 条全绿；I20/I21/I22 DoD 逐项核对（类型往返/fail-closed/rebuild 一致、分组桶序/扇出/未知 422、1.2.11 零改动回归）；浏览器隔离复演两条演示路径——「按标签分组看板」（frontend×2/backend×1/infra×1/未设置×2，扇出+徽标可见）与「打断-注入-恢复」（9e781813→注入→4fffc13e 逐条含约束→批准 succeeded），截图 docs/m6-review-board-grouping.png、docs/m6-review-interrupt-resume.png；演示 console 噪声逐条查明为跨隔离环境轮询/关服后重连，非产品缺陷。随即开启新一轮调研（目标第 5 条）：OpenProject 双层字段激活（类型级+项目级同时满足）、n8n 模板市场三件套（JSON 即模板/中心库/自托管库）、Plane/Focalboard 认证模型（两层成员+角色；推迟 M8），结论入 docs/01 §F。新增 M7 = I23 模板包注册表 / I24 模板中心前端 / I25 项目级字段激活（范围变更：计划外新增里程碑，理由 = 目标第 5 条持续推进，估时 +9 人日；新增冒烟 13 于 I23）。 |
| 2026-09-03 | I23 | 模板包注册表与浏览 API：新模块 `template_packs.py`。**实现偏差（有意）**：注册表未建 `template_packs` 投影表——I18 导入即把本体落盘 ontologies 目录，目录活扫描已是单一真源，建表成双真源；注册表=活扫描 + 事件合成 provenance（`pack.registered`：lifespan 启动时对无导入记录的本体补登记，查重幂等、重启零重发；`ontology.imported`：I18 既有契约复用为导入登记，带 imported_at/by）。`GET /template-packs` 统一视图（name/display/version/source/valid + concepts/states/fields/phases/relations/CQ 摘要）；`GET /template-packs/{name}` 预览（概念含字段与角色、阶段图、CQ、board_defaults、asset_kinds）；`POST /template-packs/{name}/instantiate` 复用建项目共链路（直接调 `projects.post_project`：宪章+首特性+起草对话+内容仓 bootstrap），未知 404 / 本体校验失败 422 / 空名 422。测试：新增 4 单测（内置+导入统一视图与 provenance/预览+实例化共链路/fail-closed/启动登记幂等）；**新增冒烟 13**（导入 lite→同列表 source=imported→预览→instantiate→项目阶段图与 CQ 就位→未知 404），基线 13 条 GREEN；pytest 85 项绿。 |
| 2026-09-03 | I24 | 模板中心前端页：新页 `TemplatesPage.tsx`（路由 `#/templates`）——浏览卡片（display_name/来源徽章 内置·导入·资产沉淀/v+概念·阶段·CQ 摘要）/预览抽屉（阶段流程含 ⚑Gate、概念表含状态与字段、CQ 列表）/"用此模板建项目"表单（调 instantiate，成功后跳转新项目看板）。入口：项目列表页「🧩 模板中心」按钮 + 侧栏全局「模板」项（AppShell RAIL，global 路由）。资产联动：资产页每卡片「🧩 沉淀为模板包」→ 抽屉输包名 → `POST /template-packs/from-asset`——以资产 provenance 解析来源项目→取其本体改名落盘→发 `pack.registered`（payload source=asset，含 asset_id/origin_ontology；区别于跨实例 ontology.imported），重复 409/坏名 422/无资产 404；provenance 合成器区分 source。测试：新增 2 单测（from-asset 注册+注册表可见+实例化+事件可审计/fail-closed 三态）；冒烟 13 扩展资产→包断言；pytest 87 项绿、冒烟 13 条 GREEN、pnpm build/vitest 通过（顺手清 1 个未用导入的 TS 报错）。浏览器验证（隔离 data+ontologies）：模板中心 2 内置卡→预览抽屉→建项目「模板直建演示」自动跳新看板；资产页沉淀→注册 login-regression-pack→模板中心出现「资产沉淀」徽章卡，截图 docs/i24-template-center-preview.png、docs/i24-instantiate-board.png、docs/i24-asset-to-pack.png。 |
| 2026-09-03 | I25 | 项目级字段激活（OpenProject 式「本体声明 × 项目激活」落地）：`projects.field_overrides` JSON 列（停用字段 id 列表，schema + init_db ALTER 迁移）；`project.field_disabled/enabled` 事件投影（`_set_field_state` 增删 JSON，rebuild 后重放一致）；`PATCH /projects/{id}/fields`（field_id 需在本体声明，否则 422）；`_validate_custom_fields` 增 project_id——停用字段写入（create/patch）422 "is disabled in this project"；board 响应携带 `disabled_fields`，`group_by=field:<停用>` 422（cf 读过滤保持可用，只限制写与新维度选择——附录 A 注明口径）。前端：本体页新增「字段激活（本项目）」面板（跨概念去重字段清单，含类型/所属概念/启用开关，联动失效 board 查询缓存）；Board.tsx 分组选择器按 disabled_fields 过滤候选。测试：新增 test_field_activation.py 2 项（停用→写拒→分组拒→启用恢复；未声明 422 + rebuild 存活）；冒烟 13 扩展激活往返断言；pytest 89 项绿、冒烟 13 条 GREEN、build/vitest 通过。浏览器验证（隔离）：本体页停用「标签」→看板分组选择器即刻无「分组：标签」（截图 docs/i25-field-deactivated-board.png）→启用后恢复 disabled_fields=[]。 |
| 2026-09-03 | M7 审阅 + M8 定义 | **M7 里程碑正式审阅通过**（附录 B）：审阅时点 HEAD `7c0f7bb` 重跑 pytest 89 项 + 冒烟 13 条全绿；I23/I24/I25 DoD 逐项核对（统一视图与 provenance/instantiate 共链路与 fail-closed/资产→pack 可审计/激活停用-恢复与 rebuild 存活）；浏览器隔离复演两条演示路径——「模板中心一键建项目」（自动跳新项目看板 p_09e21ea0cf）与「字段停用-恢复」（停用标签→选择器无维度→启用恢复 disabled_fields=[]），截图 docs/m7-review-instantiate-board.png、docs/m7-review-field-deactivated.png；console 4 条 404 查明为跨隔离环境旧 ID 轮询，非产品缺陷。随即开启新一轮调研（目标第 5 条）：Plane 两层角色模型（裁掉 workspace 层留项目级三角色）、Gitea 首管理员+关注册+管理员建号（不做邮件邀请，Focalboard 邀请链接教训）、认证机制取舍（stdlib pbkdf2 + 签名 HttpOnly Cookie + auth_mode 双模，SSO 推迟 V3；部署形态定为可信小团队网络服务），结论入 docs/01 §G。新增 M8 = I26 认证基座 / I27 项目成员与角色 / I28 网络协作收尾（范围变更：计划外新增里程碑，理由 = 目标第 5 条持续推进，估时 +9 人日；新增冒烟 14 于 I26；遗留 B 级「users 无认证」由此闭环）。 |
| 2026-09-03 | I26 | 认证基座：新模块 `core/security.py`（stdlib pbkdf2_hmac 20 万次迭代哈希、HMAC-SHA256 签名会话 Token `user_id.expiry.signature`、实例 secret 持久化 data_dir/secret.key——settings 可覆盖，重启会话存活）；`users` 表加 `password_hash`/`is_admin`（schema+ALTER 迁移）。**凭据不入事件**：密码哈希与 admin 标志是投影表运行时状态，直接 UPDATE 不走事件（避免凭据进审计流）；代价 = rebuild 会清空密码，恢复路径 = 重启时 `APM_ADMIN_PASSWORD` 重引导（ensure_default_user 每次启动对默认身份 reapplied is_admin=1 与配置的密码）。`POST /auth/login`（校验+签发 HttpOnly SameSite=Lax Cookie，`session.logged_in`）、`/auth/logout`（`session.logged_out`）、`GET /auth/me`（session 优先，local 模式回落配置身份）；登录失败发 `session.login_failed` 全部入审计流。`settings.auth_mode`：local（默认，零改动）/ network（middleware 对一切 /api 非 GET 请求强制会话，/api/auth/* 豁免；GET 保持开放，只读细粒度鉴权在 I27/I28）。GET /users 等出口统一 `_safe_user` 剥离 password_hash。测试：新增 test_auth.py 4 项（哈希往返/network 门禁+审计+登出/local 零破坏/无密码用户 fail-closed）；**新增冒烟 14**，基线 14 条 GREEN；pytest 94 项绿。 |
| 2026-09-03 | I27 | 项目成员与角色：新域 `domains/members.py`。`project_members` 投影表（PK(project_id,user_id)，schema+drop 列表）；`project.member_added/removed/role_changed` 事件投影（rebuild 重放一致）；建项目即发 `project.member_added`（creator=owner，Gitea 式引导）。成员管理 API：GET/POST/PATCH/DELETE `/projects/{id}/members`（仅 owner 或实例管理员可管，network 模式下越权 403+`access.denied`；local 模式单用户直通）；末位 owner 不可移除/降级（422）、未知用户 422、非成员 404、重复 409。`POST /users` 支持可选 `password`（管理员建号语义，哈希直存不入事件）。network 写门禁升级：`project_id_for_path` 从路径解析项目上下文（/projects/{id} 直读；items/conversations/runs/approvals/artifacts 反查 project_id），viewer 与非成员写 403 + `access.denied` 审计（admin 豁免）；全局端点（assets/template-packs/users）暂不限定。前端：本体页新增「项目成员」面板（成员清单+角色徽章+改角色/移除+从已注册用户添加）。测试：新增 test_members.py 3 项（creator-as-owner+管理往返+末位 owner 保护/network 角色门禁 viewer 403+contributor 通过+非成员 403+审计/rebuild 存活）；冒烟 14 扩展成员断言；pytest 97 项绿、冒烟 14 条 GREEN、build/vitest 通过。**边界（I28 收口）**：会话→actor 归账仍走 settings.user_id，登录人身份强制落 I28。 |
| 2026-09-03 | I28 | 网络协作收尾：**会话→actor 归账打通**——`events.py` 增 actor ContextVar（`set/reset/effective_actor`），emit 默认 actor 解析为「显式参 > 会话 contextvar > settings.user_id」；auth middleware 校验通过后 `set_current_actor(登录人)`，FastAPI 线程池端点继承 context，整条域层零改动即按登录人归账（冒烟 14 断言 qa-wang 写 item.created actor=qa-wang、自建项目 owner=qa-wang）。`/session/identity` 在 network 模式 422（切换=登出重登）。前端：`/login` 登录页（LoginPage）、api 层 401 自动跳登录页、顶栏身份组件按 `/auth/me` source 分流——session 显示 ⭐管理员/👤+登出（登出→登录页），local 保留原切换菜单。部署文档 `docs/11-network-deploy.md`（auth_mode/admin_password/secret_key/TTL 环境变量、管理员建号流程、角色与归账规则、nginx 反代 HTTPS + SSE 配置）。测试：冒烟 14 扩展归账断言；pytest 97 项绿、冒烟 14 条 GREEN、build/vitest 通过。浏览器验证（隔离 network 模式）：未登录写 401 → 登录页登录 → 模板建项目进看板 → 顶栏 ⭐李雷+登出（截图 docs/i28-login-session-chip.png）。 |
| 2026-09-03 | M8 审阅 + M9 定义 | **M8 里程碑正式审阅通过**（附录 B）：审阅时点 HEAD `dec89c3` 重跑 pytest 97 项 + 冒烟 14 条全绿；I26/I27/I28 DoD 逐项核对；浏览器隔离复演双账号协作路径（network 登录→管理员建号 qa-wang→viewer 写 403+审计→升 contributor 写成功→审计时间线归账链 #16/#20/#21），截图 docs/m8-review-login.png、docs/m8-review-admin-members.png、docs/m8-review-viewer-denied.png、docs/m8-review-audit-attribution.png；console 噪声逐条归因（401×2=登出后 /auth/me 轮询属 network 预期、403×1=门禁演示本体、连接拒绝×3=后端进程被系统回收后遗留标签页重连）。**审阅即修 2 处**：①AppShell 全局 rail 链接硬编码 `/assets`（I24 引入，模板侧栏入口不可达——此前演示走项目列表页按钮入口未暴露）改为 `r.global ? r.to : ...`；②FeaturePage 空态文案「也可从看板手动建卡」过时（看板无此入口、NL L1 不含建项）删除子句；修后 build+vitest 全绿。随即开启新一轮调研（目标第 5 条）：Kanboard 三段式自动化（项目级 JSON 模板+事件动作）、n8n/Node-RED 触发-条件-动作模型、Gitea/webhook 事件出站，结论入 docs/01 §H。新增 M9 = 看板自动化规则（I29-I31，范围变更：计划外新增里程碑，理由 = 目标第 5 条持续推进，估时 +9 人日；新增冒烟 15 于 I29）。 |
| 2026-09-03 | I29 | 自动化规则域与执行引擎：新域 `domains/automations.py`。**规则即事件溯源**：`automation_rules` 投影表（schema+drop 列表），`automation.rule_created/updated/deleted` 事件投影（rebuild 重放一致）；**执行器=events post-emit hook**（events.py 增 `add_post_emit_hook`，emit 完成追加+投影+SSE 广播后同步调用，hook 异常只记日志绝不破坏写入路径；rebuild 走 `projections.apply` 不经 emit 故天然不触发）——事件内核即事件源，无需 Kanboard 式自建 dispatcher。规则模型（Kanboard 绑定 × n8n 三段式）：trigger 白名单 4 事件（item.created/updated/status_changed/assigned）× condition（concept_id + 字段谓词，内置字段∪本体声明字段）× 单动作白名单 fail-closed（assign/set_priority/set_field/set_status；创建即校验 422：未知触发/动作/用户/字段、enum 越界、未声明状态、停用字段——set_field 类型校验复用 `_validate_custom_fields` 同一路径）。**防循环双保险**：actor_type=automation 的事件不进引擎 + dispatch 期 contextvar 拦截一切嵌套 emit（单层执行）。**归账**：动作与 rule_fired 事件显式 actor_type=automation、actor_id=规则 id（复用 I28 contextvar 语义，审计页可过滤）；set_field 合并现值后整列写（I20 投影整列覆盖教训）。API：GET/POST `/projects/{id}/automations`、PATCH/DELETE `/{rule_id}`（network 写门禁经 M8 middleware 自动生效）、POST `/{rule_id}/test` dry-run（对最近一条触发事件评估，不执行）、GET `/{rule_id}/runs` 触发历史（事件合成）。装配：main.py lifespan `install_automation_engine()`（幂等）；**顺手修 domains/__init__ 投影注册清单漏 members/template_packs**（此前靠 main 导入链间接注册，非应用上下文 rebuild 会静默丢投影）。测试：新增 test_automations.py 5 项（CRUD+rebuild/触发+归账/条件门+单层防循环+停用/fail-closed 全矩阵/dry-run 不执行）；**新增冒烟 15**；pytest 103 项绿、冒烟 15 条 GREEN。 |
| 2026-09-03 | I30 | 规则管理前端：本体页（项目设置）新增「自动化规则」面板（AutomationsPanel）。规则列表行 = 名称 + 触发徽章（当创建工作项/更新字段/状态变更/指派变更）+ 条件摘要 + 动作摘要 + 测试运行/历史/启停/删除操作；新建表单三段式——「当〈事件〉」下拉、「满足〈概念〉+〈可选字段谓词〉」（内置字段与本体声明字段合并出选项）、「则〈动作〉」动态参数：assign 出用户下拉、set_priority 出高中低、set_field 出字段下拉且 enum/boolean 按本体声明出值选项（multiselect 逗号分隔转字符串数组）、set_status 出概念（条件限定则收窄）状态池；「创建规则」按钮按参数完整性禁用。「测试运行」调 `/test` dry-run 以 toast 呈现命中项与将执行动作（不执行）；「历史」抽屉调 `/runs` 显示每次触发（#事件号/时间/已执行-被拒绝徽章/动作明细）。api.ts 增 listAutomations/createAutomation/patchAutomation/deleteAutomation/testAutomation/automationHistory + AutomationRule/AutomationRuleIn/AutomationTestRun/AutomationRun 类型（action.value 多型：string|number|boolean|数组）。验证：pnpm build + vitest 绿；浏览器隔离复演——UI 建两条规则（指派 QA 王 / severity→P0，enum 值下拉动态出现）→ API 建缺陷触发 → 看板卡片自动带「👤 qa-wang」与「严重度： P0」徽标 → 历史抽屉显示「#14 已执行 · 已指派给 qa-wang」（截图 docs/i30-automation-panel.png、docs/i30-automation-fired.png、docs/i30-automation-board-card.png）；本时段 console 唯一错误为 favicon 404，非产品缺陷。**行尾注**：OntologyPage.tsx 由 CRLF 归一为 LF（docs/10 §8 既定标准），该文件本次 stat 偏大系行尾而非内容。 |
| 2026-09-03 | I31 | 自动化收尾：**审计过滤入口**——AuditPage 发起者下拉增「⚡ 自动化」（ICON 映射 ⚡）、域标签行增 `automation`（一键过滤 automation.rule_* 全家族）。**docs/12-automation-guide.md 新建**：三段式模型与配置入口、执行语义表（时机/归账/防循环双保险/Plane 幂等教训/fail-closed）、测试运行与历史语义、权限与部署（M8 门禁+事件溯源存活）、边界与 backlog（单动作多规则组合、出站 webhook、区间与 AND/OR 条件）。浏览器演示（隔离环境）：审计页发起者=⚡自动化 精确命中 4 条——#14 item.assigned(ar_9e8f) + #15 item.updated(ar_ff0d) + #16/#14 automation.rule_fired，两条规则的触发与动作均按规则 id 归账（截图 docs/i31-audit-automation-filter.png）；automation 域标签过滤 rule_* 家族正常；console 错误归因为停服时刻审批轮询 500/SSE 断连，非产品缺陷。 |
| 2026-09-03 | M9 审阅 + M10 定义 | **M9 里程碑正式审阅通过**（附录 B）：审阅时点 HEAD `064133f` 重跑 pytest 103 项 + 冒烟 15 条全绿；I29/I30/I31 DoD 逐项核对（规则事件溯源与 rebuild/触发执行与 automation 归账/条件门与单层防循环/fail-closed 全矩阵/dry-run 不执行/面板 CRUD 与动态表单/审计过滤）；浏览器隔离复演「UI 建规则→API 触发→看板卡片自动指派→审计 ⚡ 过滤归账链」（#12 item.assigned + #13 rule_fired 同归账 ar_07f8a246c7），截图 docs/m9-review-automation-card.png、docs/m9-review-audit-automation.png。随即开启新一轮调研（目标协议第 1 条）：Gitea/GitLab webhook HMAC 签名语义（原始 body 签名/delivery ID 去重/明文 token legacy 化）、Redmine 通知与 feeds 是自托管桌上前提 + 规则化通知真实需求，结论入 docs/01 §I。新增 M10 = 出站集成：webhook 与通知（I32 webhook 基座/I33 前端与运维/I34 站内通知中心 + notify 动作，范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +9 人日；新增冒烟 16 于 I32）。 |
| 2026-09-03 | I32 | 出站 webhook 基座：新域 `domains/webhooks.py`。**规则即事件溯源**：`webhooks` 投影表 + `webhook.created/updated/deleted` 事件投影（rebuild 重放一致）；**secret 不入事件**（M8-I26 凭据原则延续）——secret 仅存投影表（运行态，rebuild 置空、rotate 换发、创建时一次性返回），与 users.password_hash 同语义（附录 A 延续登记）。**投递器=入队/投递分离**：post-emit hook `enqueue` 只 put_nowait 入内存队列（满则丢并告警），`apm-webhooks` 守护线程投递——网络 I/O 绝不阻塞写路径（与 M9 同步执行器的本质差异，冒烟 16 断言写路径 <1s 返回而接收端 stall 2s）。**Gitea/GitLab 语义落地**：投递头 `X-APM-Event`（事件类型）/`X-APM-Delivery`（dl_ 投递 ID 幂等）/`X-APM-Webhook`/`X-APM-Signature`（对原始 body 字节的 HMAC-SHA256，secret 每条独立，无 secret 则缺头）；失败指数退避重试 3 次（RETRY_DELAYS=(1,4,16)s，测试可 monkeypatch），终局以 `webhook.delivered/failed` 事件留痕（attempts/status_code/duration_ms/error，rebuild 存活）。事件订阅白名单 fail-closed（item.*/approval.*/feature.created/automation.rule_fired，webhook.* 不可订阅故投递留痕事件不会二次触发投递）；URL http(s) 校验 422。CRUD + rotate API（network 写门禁经 M8 middleware 自动生效）。装配：main.py lifespan `install_webhooks_engine()`（幂等，hook 去重 + 守护线程）。测试：新增 test_webhooks.py 4 项（CRUD+secret 不入事件流+rebuild 清 secret/fail-closed、本地接收桩端到端签名验证+delivered 留痕、500→4 次尝试→failed 留痕、停用静默+启用恢复）；**新增冒烟 16**（非阻塞时序+签名+重试+rebuild 存活）。修一个自踩 bug：worker 解析行漏传 with_secret=True 致签名头缺失（单测签名断言当场拦住）。pytest 108 项绿、冒烟 16 条 GREEN、vitest/build 绿。 |
| 2026-09-03 | I33 | webhook 前端与运维：**后端补运维端点**——`_deliver` 增 retries 参数（手工动作单次尝试），`POST /webhooks/{id}/replay/{delivery_id}`（按 delivery_id 找回 delivered/failed 留痕事件→以 payload.event_id 取回原始事件→重放同载荷、新 delivery ID）、`POST /webhooks/{id}/ping`（合成 ping 载荷单次投递）；均落 webhook.delivered/failed 留痕。**前端**：本体页新增「Webhooks 出站」面板（WebhooksPanel）——创建表单（URL 输入 + 订阅事件芯片多选，白名单与后端一致）、**secret 一次性展示弹窗**（警示文案+明文 pre，关闭后只能 rotate 换发）、行内操作 Ping/投递历史/换发 secret/启停/删除、secret 失效（rebuild 后）黄标提示；投递历史抽屉（DeliveryHistory）= listEvents(agg_type=webhook, agg_id=hook id) 过滤 delivered/failed，行显示 已送达/失败徽章、delivery_id、事件→#event_id、HTTP 状态码/attempts/耗时 + 重发按钮。api.ts 增 7 方法 + Webhook/DeliveryRecord 类型（listEvents 参数类型扩展 agg_type/agg_id）。**docs/12 §6 Webhooks 出站章节**：投递语义表（头/签名/超时重试）、接收方验签 Python 示例（原始字节+常量时间比较+delivery 去重）、GitLab 明文 token 历史教训。验证：单测 5 项绿（新增 replay+ping：重放同 agg_id 新 delivery ID、ping 单次尝试、未知 delivery 404）；浏览器隔离复演——UI 建 webhook（URL+订阅芯片）→ secret 弹窗截图 → python 接收桩实测收到签名投递（X-APM-Signature 与 secret HMAC 验证、delivery ID 与留痕事件一致）→ 历史抽屉「已送达 HTTP 200 · 1 次」→ UI 重发 → 接收桩收到第二条（新 delivery ID dl_9e361a…）→ 抽屉两条记录各带重发按钮（截图 docs/i33-webhook-secret-modal.png、docs/i33-webhook-delivery-history.png）；pytest 109 项绿、冒烟 16 条 GREEN、build/vitest 绿。 |
| 2026-09-03 | I34 | 站内通知中心与收尾：新域 `domains/notifications.py`。**通知 = 既有事件的纯投影**——item.assigned（human）→被指派人、approval.requested→项目 Owner（查 project_members）、notification.sent（automation notify 动作）→指定用户；**通知 id 确定性生成 `n_{源事件id}_{接收人}`**（踩坑修复：初版用 new_id 随机 id，rebuild 后 id 漂移致已读事件引用失配、未读数回弹——单测 rebuild 断言当场拦住；事件溯源投影新生成实体的 id 必须可由事件流确定性重建）；已读状态事件溯源（`notification.read`，payload ids/all，按 actor_id 归属）；API：GET /notifications（latest 30+unread，按 effective_actor）、POST /notifications/read（未知 id 404、空参 422）。**automation 动作白名单增 notify**（{user_id, message≤200}，校验用户存在与消息长度；执行发 notification.sent，actor_type=automation/actor_id=规则 id，走 M9 防循环）。前端：AppShell 顶栏 NotificationsBell（BellRing 图标+未读徽标+清单：kind 图标/摘要/kind/时间+未读圆点，15s 轮询，全部已读）；api.ts 增 listNotifications/markNotificationsRead。**docs/12 §7 通知章节**（来源表/已读事件溯源/确定性 id 通用要求）。测试：新增 test_notifications.py 4 项（指派通知+已读+rebuild/read-all+越权 404+空参/approval 通知 Owner/notify 动作校验+触发+归账）；**套跑隔离修复**：/session/identity 全局改 settings.user_id 泄漏跨用例，测试文件加身份还原夹具（C 级已知设计，local 模式全局身份的固有语义）；冒烟 16 扩展指派通知+已读清零断言；pytest 113 项绿、冒烟 16 条 GREEN、vitest/build 绿。浏览器验证（隔离环境）：指派后铃铛徽标「3」→下拉三条 assigned 通知（图标/摘要/时间）→全部已读徽标消失（截图 docs/i34-notification-bell.png）。 |
| 2026-09-03 | M10 审阅 + M11 定义 | **M10 里程碑正式审阅通过**（附录 B）：审阅时点 HEAD `08af0c5` 重跑 pytest 113 项 + 冒烟 16 条全绿；I32/I33/I34 DoD 逐项核对（secret 不入事件/rebuild 存活/签名逐字节比对/重试留痕/写路径零阻塞/replay-ping/通知纯投影/确定性 id/notify 防循环归账）；浏览器复演（python 接收桩）「UI 建 webhook→触发→签名投递→投递历史→指派通知铃铛」合并路径，截图 docs/m10-review-webhook-history.png、docs/m10-review-notification-bell.png。随即开启新一轮调研（目标协议第 1 条）：Redmine 邮件通知只做即时无内建 digest、SMTP 走环境配置层（SSL/STARTTLS/外部 relay 推荐）；Atom feed per-user key 认证 + 私有项目数据曾泄漏进全局 feed（#20173）教训，结论入 docs/01 §J。新增 M11 = 邮件通知与 Atom 订阅（I35 邮件通道 SMTP env 可选 / I36 Atom 订阅 feed + 冒烟 17 / I37 通知偏好前端与收尾审阅，范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +9 人日；新增冒烟 17 于 I36）。 |
| 2026-09-04 | I35 | 邮件通知通道：新域 `domains/mailer.py`。**SMTP env 可选**——config 增 APM_SMTP_HOST/PORT/USER/PASS/FROM/TLS（缺省全空=通道整体静默关闭，smtp_configured() False 时 hook 直通，行为与 M11 前完全一致；465 端口自动 SMTP_SSL，否则 STARTTLS 可关）；**收件人决策单源化**：notifications.py 抽出 `plan_notifications(conn, event)` 纯函数（返回 (user_id, kind, summary) 列表），通知投影器与邮件 hook 共用——两通道收件人永不失配；**投递架构同 M10**：post-emit hook `enqueue` 只入队（解析收件人邮箱=users.email 既有字段，无邮箱跳过），`apm-mailer` 守护线程即时发送（EmailMessage 纯文本、超时 10s、send 单次尝试），终局 `email.notified/failed` 事件留痕（to/kind/summary/source_event_id/duration_ms/detail，agg_id 确定性 `em_{源事件id}_{用户}`）。装配：main.py lifespan `install_mailer()`（幂等）。测试：新增 test_mailer.py 5 项（默认关闭零行为/配置后指派即时发信+To/From/主题断言+留痕/无邮箱用户跳过/SMTP 故障→failed 留痕 worker 存活/慢 SMTP 2s 写路径 <1s 不阻塞）；**新增冒烟 17**（默认关闭→配置→stall 非阻塞→留痕→rebuild 存活）；pytest 119 项绿、冒烟 17 条 GREEN、vitest/build 绿。 |
| 2026-09-04 | I36 | Atom 订阅 feed：users 加 feed_key（运行态凭据，CREATE+ALTER 迁移）；新域 `domains/feed.py`。**key 生命周期**：GET /me/feed-key（查看自己的 key，首次自动生成——owner 可反复读取，与 webhook secret 的一次性语义刻意区分：feed key 是用户自己的阅读器凭据）、POST /me/feed-key/rotate（换发即旧 key 失效）。**feed 输出**：GET /projects/{id}/feed.atom?key=（key 认证绕过 cookie，阅读器友好）——**权限裁剪防 Redmine #20173 式泄漏**：instance admin 全见、成员按角色放行、local 模式配置用户放行；非成员 403 并落 `access.denied`（path 指向 feed.atom）；Atom 1.0 XML（xml.sax.saxutils 转义；feed id/title/updated + entry 的 id=`urn:apm:event/{pid}/{eid}`、title=`#id 事件类型 摘要`、author=actor_id、content=payload 关键字段摘要；latest 30 条，content-type=application/atom+xml）。测试：新增 test_feed.py 3 项（key 生命周期+rotate 后旧 key 401/roundtrip+ElementTree well-formed 校验+content-type/非成员 key 403+入成员后同 key 放行）；冒烟 17 扩展 feed 断言（生成/roundtrip/rotate 失效）；pytest 122 项绿、冒烟 17 条 GREEN、vitest/build 绿。 |
| 2026-09-04 | I37 | 通知偏好前端与收尾：users 加 `email_notify`（INTEGER NOT NULL DEFAULT 1，CREATE+ALTER 迁移）；notifications.py 增 `POST /api/notifications/prefs`（body {email_enabled}，按 effective_actor 更新自身 users.email_notify）+ GET /notifications 响应带 `email_enabled`；mailer.enqueue 入队前过滤 `email_notify=0`——**开关语义：只停邮件、站内通知照常**（通知=事实投影，邮件=可选投递介质）。前端 NotificationsBell 增「通知偏好」区：邮件开关即时 POST prefs；feed key 区显示/换发（确认后 rotate）/复制订阅链接（拼 feed.atom?key=）；api.ts 增 setNotificationPrefs/getFeedKey/rotateFeedKey。测试：test_mailer 第 6 项（开关后邮件止于 1 封、站内 unread 照增、email_enabled 往返）。调试期教训入档：regex 探针误删 mailer.py 中段→整文件重写修复；`/api/session/identity` 全局改 settings.user_id 跨用例泄漏（boot 注册无邮箱默认管理员、INSERT OR IGNORE 吞掉带邮箱注册）→ test_notifications/test_mailer 加 `_restore_identity` autouse 夹具；**源码修改一律用 Edit 工具（字面量安全），不再用 heredoc/regex 脚本**。pytest 123 项绿、冒烟 17 条 GREEN、vitest+build 绿。 |
| 2026-09-03 | M10 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `08af0c5` 重跑 pytest 113 项 + 冒烟 16 条全绿）：**I32** webhook CRUD + secret 不入事件流（事件流 grep 无 secret）+ rebuild 存活（secret 运行态置空、rotate 换发）+ fail-closed（ftp URL/webhook.* 订阅/空事件列表 422）✓（test_webhook_crud_secret_never_evented_and_rebuild）；本地接收桩端到端——签名 = HMAC-SHA256(secret, 原始 body) 逐字节比对 ✓、X-APM-Event/Delivery/Webhook 头在位 ✓、webhook.delivered 留痕 ✓（test_delivery_signed_and_recorded）；500→1+3 次尝试→delivery_failed 留痕（attempts=4, status_code=500）✓（test_failure_retries_then_failed_recorded）；停用静默+启用恢复 ✓（test_disabled_webhook_stays_silent）；写路径零阻塞（冒烟 16 断言写 <1s 返回 / 接收端 stall 2s）✓；**I33** replay/ping 端点（重放同 agg_id 新 delivery ID、ping 单次尝试、未知 delivery 404）✓（test_replay_and_ping）；Webhooks 面板 CRUD/订阅芯片/secret 一次性弹窗/投递历史抽屉 ✓；docs/12 §6 验签章节在位 ✓；**I34** 指派通知+已读流程+rebuild 存活 ✓、read-all+越权 404+空参 422 ✓、approval.requested 通知 Owner ✓、notify 动作校验与触发归账 ✓（test_notifications 4 项）；通知 id 确定性修复（随机 id→n_{事件id}_{用户}）与身份泄漏还原夹具已落附录 A。浏览器复演（隔离环境+python 接收桩）：UI 建 webhook（URL+订阅芯片）→ secret 一次性弹窗 → API 建缺陷 → 接收桩实测签名投递（delivery ID dl_65f2ccde… 与留痕事件一致）→ 投递历史抽屉「已送达 HTTP 200 · 1次 · 15ms」→ 指派触发通知 → 铃铛徽标「1」+ 下拉「被指派工作项『审阅触发缺陷』」（顶栏 QA 王）——单张截图覆盖两路径（docs/m10-review-webhook-history.png、docs/m10-review-notification-bell.png）。 | — | 里程碑通过 |
| 2026-09-04 | M11 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `0270169` 重跑 pytest 123 项 + 冒烟 17 条全绿）：**I35** SMTP env 缺省关闭零行为 ✓（test_off_by_default）、配置后指派即时发信（To/From/主题+留痕）✓、收件人单源 plan_notifications（两通道不失配）✓、故障 email.failed 留痕 worker 存活 ✓、慢 SMTP 2s 写路径 <1s 不阻塞 ✓；**I36** feed key 生命周期+rotate 后旧 key 401 ✓、Atom roundtrip+ElementTree well-formed+content-type ✓、非成员 403+入成员放行 ✓（test_feed 3 项）；**I37** prefs 开关后邮件止/站内 unread 照增/email_enabled 往返 ✓（test_email_pref_toggle_stops_mail_but_not_notifications）、存量库 ALTER 迁移 ✓（冒烟 17 rebuild 断言前提）。浏览器隔离复演（隔离 data+ontologies + 本地 SMTP 接收桩 :2525，演示项目 p_bf3f9022c8）：UI 建项目「邮件与订阅演示」→ API 建缺陷+指派 qa-wang → 桩实测收信（From agentpm@test.local / To qa@x.local / UTF-8 编码主题正文）→ 审计链 #10 item.created → #11 item.assigned → #12 email.notified（agg_id=em_11_qa-wang、source_event_id=11、duration_ms=1328，截图 docs/m11-review-mail-audit.png）→ 切 QA 王：铃铛「1」+ 偏好区（邮件通知开启 + Atom 订阅 key，截图 docs/m11-review-bell-prefs.png）→ 关闭邮件开关（标签即时变「已关，站内照常」）→ 二次指派：桩仍 1 封、email.notified 仍 1 条、铃铛徽标「2」（**邮件止、站内照常**）→ 切回李雷其面板显示「开启」（per-user 偏好对照）→ QA 王 feed key 展示+复制订阅链接（docs/m11-review-feed-key.png）→ 浏览器直开 feed.atom?key= 渲染 Atom XML（docs/m11-review-feed-atom.png）→ 局外人 outsider key 访问 feed 403 + access.denied（user_id/path/summary 齐全）。**语义澄清**：local 模式「当前配置用户（settings.user_id）」恒可读 feed 为既定单机可信语义（首次探针 200 即此因——配置身份恰为被测用户）；固定配置身份为李雷后 outsider key 正确复现 403，非权限漏洞。 | — | 里程碑通过 |
| 2026-09-04 | M12 定义 | 新一轮开源调研（目标协议第 1 条）三路并行：①**OpenProject 报表分层**——社区版以 custom query（可保存过滤/分组视图）+ 项目首页 widget + My page 为轻量报表，高级报表模块企业版专属 → 报表=投影查询+widget 拼装，无需报表引擎；②**SSO/OIDC**——自托管主流=独立 IdP（Keycloak/Authelia/Authentik/Kanidm）+应用作 OIDC client，Gitea JIT 开户受限、强制 SSO 须禁本地密码且留 admin 兜底 → 维持 V3（M8 决策不反转）；③**GitLab 审计事件**——DB 永久保留+流式外送归档（HTTP/GCL→Datadog）→ AgentPM「归档」=导出/快照而非删除（保护 live==replay）。结论入 docs/01 §K。新增 **M12 = 报表与跨项目工作台**（I38 报表数据层纯投影 API：项目健康+跨项目我的工作+列表聚合 / I39 报表前端与项目工作台：漏斗+Gate 挂起+超期+sparkline+列表徽标+全局我的工作 / I40 CSV 导出+docs/12 §9+冒烟 18+审阅；范围变更：计划外新增里程碑，理由=目标协议持续推进+管理者可见性是工程管理落地标准的直接缺口且事件溯源做投影报表零 ETL，估时 +9 人日；新增冒烟 18 于 I40）。 |
| 2026-09-04 | I38 | 报表数据层：新域 `domains/reports.py`——**纯投影查询**（无新表无新事件，rebuild 一致性由构造保证）。**GET /projects/{id}/report**：五桶漏斗（BUCKET_NAMES 序零填充）+概念分布+pending Gate 清单（approvals status='pending'）+超期/滞留清单+近 14 天吞吐（events 按日计数：item.created 与 item.status_changed→json_extract status_group='done'，date(ts) 分桶）。**超期口径**（docs/12 §9 将收口）：cf 声明 due/due_date/deadline（ISO 日期）早于今日→「超期 N 天」；无 due 声明→活跃项（非 done/cancelled）创建超 STALE_DAYS=14 天→「滞留超 14 天」；done/cancelled 恒排除。**GET /my/work**：指派即授权（assignee 恒见自己活跃项，免项目成员过滤——否则网络模式被指派者反而看不到自己的工作）；Gate 清单仅 project owner 或 instance admin（与 approval.requested 通知接收人单源一致）。**GET /projects** 列表补 item_counts（五桶）+gates_pending（一次 GROUP BY 扫描+ON CONFLICT 零填充）。设计取舍：初版 _visible_project_ids 成员过滤方案废弃（与指派语义冲突），/report 读语义与 board/items 一致；main.py 挂载 reports 路由。测试：test_reports.py 4 项（漏斗/概念/吞吐/Gate 计数+rebuild 前后一致+未知项目 404；超期口径边界——新鲜/未到期排除、滞留 20 天与 due 昨日命中、done 且 30 天排除；跨项目 my-work 身份切换+Gate 决策权对照+列表健康摘要）。测试教训：restore 身份须在切换**前**保存原始值（读 config.settings.user_id 再还原=还原到污染值）。pytest 127 项绿、冒烟 17 条 GREEN。 |
| 2026-09-04 | I39 | 报表前端与项目工作台：新页 **ReportsPage**（`#/p/{pid}/reports`，AppShell rail 项目内「报表」BarChart3）——五桶漏斗条形（done 绿/cancelled 灰）+概念分布 chips、挂起 Gate 卡片（payload_snapshot 已在 reports API 解析为对象，直达审批中心）、超期/滞留清单（reason amber 徽标）、近 14 天吞吐双色柱图（新建 acc/完成 ag，title 悬浮逐日数字），15s 轮询；全局 **MyWorkPage**（`#/my/work`，rail 全局「我的工作」ListTodo）——「分配给我」跨项目列表（项目名+概念+桶徽标+时间，行链至看板）+「等我决策」Gate 卡片（行链至审批中心），15s 轮询；项目列表 **PickerInner** 每行健康徽标（待办/进行/完成计数 + ◆N 待审 amber 徽标）；api.ts 增 ProjectReport/MyWork 类型 + getProjectReport/getMyWork（Approval 类型补 item_id 字段）。浏览器验证（隔离环境复用演示库）：报表页四 widget 与 API 数字一致（漏斗 4/0/1/1/0、Gate「PRD 评审·等待中」、超期「滞留 20 天的老缺陷·滞留超 14 天」、吞吐 新建 6/完成 1；截图 docs/i39-reports-page.png）；列表徽标「待办 4 · 进行 1 · 完成 1 ◆ 1 待审」（docs/i39-picker-health.png）；我的工作 QA 王 3 项聚合 vs 李雷 0 项+1 待决策（docs/i39-my-work.png）。**演示环境教训**：独立 python 脚本 emit 必须 `import apm.domains` 注册投影器再发事件（只导 core = 事件落库投影缺失），且必须带 APM_DATA_DIR——首轮探针误入 dev 库（events append-only 触发器下按「drop trg→删行→原样重建 trg」清理复原）；reports 的 payload_snapshot 初版吐原始 JSON 字符串，前端类型崩（TS 编译当场拦截）→ 后端统一解析为对象。build+vitest 绿。 |
| 2026-09-04 | I40 | 报表收尾：**CSV 导出** `GET /projects/{id}/report.csv`（stdlib csv 写 io.StringIO；五列 section/key/title/reason/value——funnel 五桶、concept 分布、throughput 总计、overdue 逐项带 reason；UTF-8 + Content-Disposition 附件，数字与 JSON 同源同数）；**docs/12 §9 报表与跨项目工作台**（入口×数据源对照表、五项口径定义表——漏斗/挂起 Gate/超期/滞留/吞吐、权限语义——/report 与看板同读、my/work 指派即授权+Gate 决策权与通知接收人同源）；**新增冒烟 18** test_smoke_18_reports.py（造数 4 项含 done/in_progress 转换+pending Gate → 漏斗/概念/吞吐/Gate 精确断言 → /my/work 聚合 → **CSV DictReader 解析与 JSON 同数** → 列表健康摘要与 report 一致 → rebuild 后三组数字不变）。pytest 128 项绿、**冒烟基线 18 条 GREEN**。 |
| 2026-09-04 | M12 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `179e3bb` 重跑 pytest 128 项 + 冒烟 18 条全绿）：**I38** 漏斗/概念/吞吐/Gate 计数 + rebuild 前后一致 ✓（test_funnel_throughput_and_gates）、未知项目 404 ✓、超期/滞留口径边界（新鲜/未到期排除、滞留 20 天与 due 昨日命中、done 且 30 天排除）✓（test_overdue_and_stale_caliber）、/my/work 指派即授权 + Gate 决策权 owner/admin 对照 ✓、列表健康摘要 ✓（test_my_work_and_list_health）；**I39** ReportsPage 四 widget / MyWorkPage / 列表徽标 build+vitest 绿 + 浏览器数字一致 ✓；**I40** CSV 与 JSON 同数 ✓（冒烟 18 DictReader 断言）、docs/12 §9 在位 ✓、冒烟 18 全程 ✓。浏览器隔离复演（审阅时点，隔离 data+ontologies，演示库 p_bf3f9022c8）：报表页漏斗 4/0/1/1/0 + 概念 chips bug×5/task×1 + 挂起 Gate「◆ PRD 评审·等待中」+ 超期「滞留 20 天的老缺陷·滞留超 14 天」+ 吞吐 新建 6/完成 1 十四日柱图（截图 docs/m12-review-reports-page.png）；CSV 实测 `curl /report.csv` 十二行逐行核对（funnel 五桶/concept×2/throughput 两行/overdue 带项目内 item id 与 reason）；切换 qa-wang「我的工作」3 项跨项目聚合（登录页校验缺失/邮件开关后仍指派/滞留 20 天的老缺陷，Bucket 徽标与项目名正确，截图 docs/m12-review-my-work.png）。 | — | 里程碑通过 |
| 2026-09-04 | M13 定义 | 新一轮开源调研（目标协议第 1 条）三路并行：①**OpenProject Gantt**——三类工作包（phase/milestone/task）×依赖连线×时间轴，里程碑日期随关联项变动（依赖传播核心语义），13.3 起独立 Gantt 模块；②**Plane v1.16**——Milestone = 按 deadline 聚合工作项/模块的路线图锚点，与 sprint 式 Cycles 正交 → 只做 Milestone 不做 Cycles；③**GitLab 导出/备份**——官方警告项目导出勿作备份（不完整+兼容窗口），正解 = DB 级备份，NDJSON 导出仅作补充。选定 **M13 = 里程碑与时间线**（排程与里程碑是「计划 vs 实际」维度最后空白；数据模型三要素齐备：milestone 概念、items.milestone_id 闲置列、depends_on 内核关系）：I41 里程碑域与工作项日期（milestone.* 事件溯源 + items 加 start_date/due_date 列 + 进度 + 报表口径升级）/ I42 时间线视图（条形/菱形/depends_on 箭头与冲突标红，不做依赖自动传播改期）/ I43 事件 NDJSON 导出 + docs/11 备份章节 + docs/12 §10 + 冒烟 19 + 审阅；范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +9 人日；新增冒烟 19 于 I43。结论入 docs/01 §L。 |
| 2026-09-04 | I41 | 里程碑域与工作项日期：新域 `domains/milestones.py`——milestones 投影表 + milestone.created/updated/deleted 事件；**drop_projections 清单同步补 milestones**（否则 rebuild 重放撞活体行 UNIQUE——新投影表接入 rebuild 必经此步，单测 rebuild 断言当场拦住）；CRUD：POST /projects/{pid}/milestones、GET 列表带进度、GET/PATCH/DELETE /milestones/{id}（M8 门禁自动生效）；due_date ISO 强校验 422；状态校验优先本体 milestone 概念 states（software-dev: planned/in_progress/achieved），无概念回退通用集；进度 = 关联项 done 比例（非 cancelled 为分母）+ 逾期数（due 已过时的活跃项计数）。**items 加 start_date/due_date**：schema CREATE+db.py ALTER 迁移（M6-I20 PRAGMA 模式复用）；item.created 透传、item.updated 投影键增两列（新增键接入投影器时通读整段——I20 教训照办）；_validate_item_dates ISO 校验 422；PATCH /items 支持 milestone_id（require_milestone 未知 422 + 跨项目 422）。**报表超期口径三级回退**：item.due_date → cf due/due_date/deadline → 滞留（docs/12 §9 同步更新）。测试：test_milestones.py 4 项（CRUD+rebuild 存活/校验 fail-closed 矩阵/进度与逾期计算+rebuild 一致/日期校验与报表口径边界——带 due_date 新建即超期、改未来日期即脱出）。测试教训：TestClient 路径 `/api` 前缀漏写 = 404 Not Found（非路由未注册，先核 URL 再查代码）。pytest 132 项绿、冒烟 18 条 GREEN。 |
| 2026-09-04 | I42 | 时间线视图：新页 **TimelinePage**（`#/p/{pid}/timeline`，AppShell rail「时间线」CalendarRange，Board 与 Graph 之间）——日期轴自动适配数据范围（取条形/菱形/今日的 min-2d..max+2d；无数据回退今日 -15/+30 天），周刻度网格 + 今日 amber 竖线；行 = 概念（本体 concepts 名映射，行序按出现序）；条形 = 有 start/due 的工作项（done 绿/cancelled 灰/活跃 acc，最小宽度 0.8%，悬停标题含状态与冲突说明）；菱形 = 里程碑（amber rotate-45 定位在 due 日，悬停显示截止日/完成比/逾期数——进度徽标走 title）；**depends_on 冲突检测**：对排期项并发拉详情取 relations，后置项 start < 前置项 due → 条形 red-500 红框 + 红色虚线连接（**同行冲突走行底边缘**避让条形，跨行走两行中心连线；不自动改期）；api.ts 增 Milestone 类型 + listMilestones/createMilestone/patchMilestone/deleteMilestone + getItem（item 详情此前无前端方法）。**顺带补 I41 缺口**：ItemIn 增 milestone_id——创建即关联（post_item 校验未知/跨项目 422、create_item payload 透传、item.created 投影 INSERT 持久化），此前仅 PATCH 可关联（演示种子数据当场暴露）；test_milestones 第 5 项（建卡即关联+坏关联 422）。浏览器验证（隔离环境）：里程碑菱形（Beta 发布·33%）/冲突红条+行底虚线/日期轴刻度（截图 docs/i42-timeline.png）；build+vitest 绿。**前端调试教训**：browser_navigate 到相同 hash URL 不触发 SPA 重载（React Query 缓存不失效，删除里程碑后头部计数仍为旧值）——需 location.reload() 强刷；SVG 连线与条形同行重叠不可见 → 连线走行底边缘。 |
| 2026-09-04 | I43 | 时间线收尾：**事件 NDJSON 导出** `GET /projects/{id}/events/export`（events_api.py StreamingResponse；按全局追加序逐行输出完整事件——id/ts/type/agg/actor/payload/prev_event_id；末行校验和 {events, sha256(全部行字节), first_prev_event_id, gaps}；**语义**：prev 链是全局的，per-project 导出首行 prev 指向链上前置事件、跨项目事件造成间隙属正常（gaps 字段显式披露），初版严格链断言被冒烟当场纠正）；未知项目 404；**docs/11 §5 备份与恢复**（GitLab「导出≠备份」移植：备份内容表 apm.db+content/+ontologies/+secret.key；停机冷备 / WAL .backup 在线快照 / Git bundle；恢复=rebuild 校验 events_replayed；导出仅补充）；**docs/12 §10 里程碑与时间线**（API 表/进度口径/排期字段三级回退指引/时间线交互/导出语义）。**新增冒烟 19** test_smoke_19_milestones.py（里程碑 CRUD→建卡即关联→进度 {2,1,0.5,逾期1} 精确断言→报表超期口径 done 排除+item.due_date 优先→NDJSON 行序+prev 链+校验和→rebuild 进度与报表不变→未知项目 404）。pytest 134 项绿、**冒烟基线 19 条 GREEN**。 |
| 2026-09-04 | M13 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `edecddd` 重跑 pytest 134 项 + 冒烟 19 条全绿）：**I41** 里程碑 CRUD 往返 + rebuild 存活 ✓（test_milestone_crud_and_rebuild）、校验 fail-closed 全矩阵（坏日期/缺日期/坏状态/未知关联/未知项目 404）✓（test_milestone_validation_fail_closed）、进度与逾期计算 + rebuild 一致 ✓（test_progress_and_overdue）、item 日期 ISO 校验 + 报表口径（item.due_date 优先：带过期 due 新建即超期、改未来即脱出）✓（test_item_dates_and_report_caliber）、创建即关联 ✓（test_link_milestone_at_creation，I42 补）；**I42** TimelinePage 四要素（日期轴/条形/菱形/冲突连接线）build+vitest 绿 + 浏览器验证 ✓；**I43** NDJSON 导出（行序+prev 链位+校验和行+gaps 披露）✓（冒烟 19）、docs/11 §5 与 docs/12 §10 在位 ✓。浏览器隔离复演（审阅时点，隔离环境演示库 p_bf3f9022c8）：时间线页日期轴 08-17..10-05 + 今日线 + 里程碑菱形（Beta 发布·截止 09-20·悬停完成 33%）+ 任务行冲突红条（编码实现 09-02→09-18 依赖设计评审）+ 行底红虚线 + 缺陷行蓝条（截图 docs/m13-review-timeline.png）；里程碑进度 API 实测 {items_total 3, done 1, ratio 0.33, overdue 0} 与菱形悬停一致；NDJSON 导出实测 35 事件 + 校验和行（sha256/first_prev=4/gaps=3 显式披露跨项目间隙）。无新增 B/C 级意见。 | — | 里程碑通过 |
| 2026-09-04 | M14 定义 | 新一轮开源调研（目标协议第 1 条）三路并行：①**OpenProject 15.4 自动排程**——手动默认 + 可选自动（Finish-to-Start 顺延），比关键路径引擎简单（无 SNET/SLT 约束类型）→ 自动化是可选项而非默认，改期须显式事件留审计；②**WeKan PWA**——自托管移动端最务实路线（Plane 原生 App 成本大、Focalboard 移动 web 反面教材）→ PWA 留下一轮首选；③**GitLab NDJSON relation 管线**——导出/导入同构 + metadata manifest、版本兼容窗口 → I43 导出需配对导入，恢复正解仍是 DB 级。选定 **M14 = 排程自动化与事件可携**（依赖变化后手工改期繁琐易漏 + 有出无进的恢复闭环）：I44 依赖传播自动排期（items.auto_scheduled 开关 + item.rescheduled 显式事件 + 递归传播与防环）/ I45 事件 NDJSON 导入恢复（校验和/链序/冲突 409 + rebuild roundtrip）/ I46 docs+冒烟 20+审阅；范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +9 人日；新增冒烟 20 于 I46。结论入 docs/01 §M。 |
| 2026-09-04 | I44 | 依赖传播自动排期：items 加 `auto_scheduled`（INTEGER NOT NULL DEFAULT 0，CREATE+ALTER 迁移；ItemPatch 增 bool 字段，入 payload 前 bool→int）。**propagate_reschedule**：patch_item 在 due_date 变更后触发——查 item_relations 中 depends_on 前置项的后继（JOIN items 取日期与开关），delta = 新旧 due 日差，仅对 auto_scheduled=1 的后继平移 start/due（保时长；无日期后继跳过），发显式 **item.rescheduled** 事件（payload follow_of/delta_days/start_date/due_date/depth——审计可见「因哪个前置项平移了多少」）；递归深度上限 20 + visited 集合防环（环中每项只平移一次）；item.rescheduled 投影器按绝对日期 UPDATE（rebuild 重放幂等，事件溯源不悄悄改——OpenProject「自动化是可选项」哲学）。前端：Item 类型补 auto_scheduled，时间线条形 hover 增「⏱ 自动排期」标注。测试：test_scheduling.py 4 项（单级传播+日期保时长+归因断言/手动模式零影响且无 rescheduled 事件/多级递归 A→B→C 各 +4 + 环 X↔Y 只平移一次/rebuild 后日期存活）。pytest 138 项绿、冒烟 19 条 GREEN、build+vitest 绿。 |
| 2026-09-04 | I45 | 事件 NDJSON 导入恢复：events_api.py 增 `POST /projects/{id}/events/import`（body {data}）。**校验流水线**：校验和行存在性 → 原始行 sha256 重算比对（篡改即 422）→ 逐行 JSON/schema（必需字段、id 严格递增）→ 事件 id 与目标库冲突检测（任一冲突整批 409，不做部分导入——恢复面向空/新库，GitLab 兼容窗口同款务实）→ 恢复语义：目标项目可不存在但 payload 必须含其 project.created（否则 422）。**追加方式**：直插保留原始 id/ts/actor，prev_event_id 重链到目标库当前头部（全局链在目标库同样成立）→ 全量 rebuild → {imported, rebuilt}。测试：test_import.py 2 项——**roundtrip**（DB1 建项目造数导出 → monkeypatch data_dir + db.reset_for_tests 切第二个全新库起第二个 TestClient → 导入 → 工作项四元组与事件流逐行与源一致）/ 拒绝矩阵（源库重导 409 / 篡改行 422 / 坏 JSON 422 / 缺校验和行 422 / 项目不匹配 422 / 拒绝后无残留半导入状态）。pytest 140 项绿、冒烟 19 条 GREEN。 |
| 2026-09-04 | I46 | 排程与可携收尾：**docs/12 §11 排程自动化与事件可携**（auto_scheduled 语义——默认手动/可选自动 + 显式 rescheduled 审计；导入校验流水线与恢复语义——空/新库、整批 409、project.created 前提）；**docs/11 §5.3 恢复步骤更新**——首选 data_dir 还原 + rebuild 校验，仅有导出文件时走 import 端点（id 冲突 409、同代版本约束写明）。**新增冒烟 20** test_smoke_20_portability.py（A←B←C 自动排期链：A due +4 → B/C 各 +4 逐项断言 + rescheduled 事件 follow_of 集合断言；**可携 roundtrip**：导出 → monkeypatch data_dir 切第二全新库导入 → 恢复库工作项日期与报表漏斗和源一致 → 恢复库内 rebuild 再验证）。测试教训：/events 列表按最新在前返回——断言事件序列需按 id 排序后比较。pytest 141 项绿、**冒烟基线 20 条 GREEN**。 |
| 2026-09-04 | M14 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `b1f93cb` 重跑 pytest 141 项 + 冒烟 20 条全绿）：**I44** 单级传播（日期保时长+follow_of/delta_days 归因）/手动模式零影响/多级递归 A→B→C + 环 X↔Y 只平移一次/rebuild 存活 ✓（test_scheduling.py 4 项）；**I45** roundtrip（导出→第二全新库导入→工作项四元组与事件流逐行一致）+ 拒绝矩阵（源库重导 409/篡改 422/坏 JSON 422/缺校验和行 422/项目不匹配 422/无半导入残留）✓（test_import.py 2 项）；**I46** docs/12 §11 与 docs/11 §5.3 在位 ✓、冒烟 20 全程（传播链+可携 roundtrip+恢复库 rebuild）✓。浏览器隔离复演（审阅时点，隔离环境演示库 p_bf3f9022c8）：造「依赖链-设计→开发→测试」三级链并全开自动排期 → PATCH A due +6 天 → B/C 自动顺延（B 09-13/09-21、C 09-21/09-27，实测 API 与时间线条形位置一致）→ 时间线页三段条形+里程碑菱形（截图 docs/m14-review-timeline.png）→ 审计页 item.rescheduled ×2 可查（follow_of 归因 + delta_days=6，截图 docs/m14-review-audit-rescheduled.png）。无新增 B/C 级意见。 | — | 里程碑通过 |
| 2026-09-04 | M15 定义 | 新一轮开源调研（目标协议第 1 条）三路并行：①**WeKan PWA 安装形态**——官方 Play 商店 App 实为 TWA 壳指向演示服务器（自托管用户无用，社区正解=从自己实例登录页「添加到主屏幕」）→ 可安装 PWA 指向自己的实例才是自托管正路，修正 §M.2「WeKan=官方 PWA/TWA」表述；②**Focalboard/Plane 移动策略**——Focalboard 移动 web 被评 cramped 且独立移动 App 已废弃（反面教材）、Plane 无原生 App 无 PWA 纯响应式 → 同类自托管移动端普遍短板，做好即超出多数同类；③**vite-plugin-pwa 技术路线**——Vite 生态事实标准（generateSW 自动 precache 起步 / autoUpdate 静默更新 / SPA 导航回退），**`/api/*` 一律 network-only 不入 SW 缓存**（事件溯源必须在线，离线写会分叉一致性——V2 再议只读快照）。选定 **M15 = PWA 与移动端适配**（关键路径移动可用 + 可安装 + 外壳离线）：I47 响应式布局基座 / I48 PWA 可安装与离线外壳 / I49 移动端打磨+docs/12 §12+冒烟 21+审阅；范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +9 人日；新增冒烟 21 于 I49。结论入 docs/01 §N。 |
| 2026-09-04 | I47 | 响应式布局基座：**AppShell 窄屏断点**（<768px）——rail 与功能列 `hidden md:flex` 折叠，topbar 增汉堡按钮开**移动导航抽屉**（fixed slide-over：RAIL 12 项带图标+标签、项目内追加「功能」列表；遮罩点击/✕/NavLink 点击后自动关闭）；⌘K 按钮窄屏只留图标；**触控目标**：审批/通知铃 `h-9 w-9` flex 居中（含 relative 保留防徽标漂移）；**修 375px 折行瑕疵**：身份 chip `shrink-0 whitespace-nowrap`（曾竖排）、通用 Badge `whitespace-nowrap`（software-dev 曾两行）；**表格/栅格适配**：看板列表 table 包 `overflow-x-auto` + `min-w-[640px]`；Reports/MyWork/Dashboard `grid-cols-1 md:grid-cols-3`（col-span 全部加 md: 前缀——1 列网格下 span 3 会生成隐式轨道撑破布局）；TimelinePage `overflow-auto` + Card `min-w-[640px]`（窄屏横滚，百分比日期轴不压缩）。meta viewport 复核已在位。验证：pnpm build + vitest 2 项绿；Playwright 375×812 五截图（看板卡片单列/列表横滚滚动条可见/报表四 widget 单列堆叠/我的工作单列/抽屉全导航+功能区）+ 1440×900 桌面复核零回归（docs/m15-i47-*.png ×6）。 |
| 2026-09-04 | I48 | PWA 可安装与离线外壳：vite-plugin-pwa v1.3.0（generateSW、autoUpdate）+ workbox-window 直依赖（**pnpm 严格 node_modules 下 virtual:pwa-register 的 workbox-window 需显式安装，否则 Rollup resolve 失败**）；tsconfig types 补 `vite-plugin-pwa/client`（否则 TS2307）；manifest（standalone/start_url `/`/theme #18181b/icons 192+512+maskable，PIL 生成）；**workbox.navigateFallbackDenylist=[/^\\/api\\//] + 零 runtimeCaching = `/api/*` 永不缓存**（SPA 导航回退不劫持 API）；index.html 补 manifest link + theme-color + favicon（修 404）。**审阅即修 2 个既有前端缺陷**：①sonner `<Toaster>` 全仓从未挂载——历次迭代的 toast.*（M9 dry-run、M10 secret 提示、M11 邮件开关等）一直静默无显示，main.tsx 补挂 top-center richColors；②ProjectPicker `useState(!!projects.length ? false : true)` 把「空库引导」与「加载失败」混淆——离线/后端故障时误弹「新建项目」模态（创建必失败），改 `autoOpen={!isError && 空列表}`，保留空库自动引导。验证：build 产物 sw.js + manifest.webmanifest + precache 7 项静态资产（源码级零 /api）；vite preview 生产构建浏览器实测：SW activated scope `/`、caches 枚举**零 /api 条目**、**断网 reload 外壳完整载入**（console 仅 /api 的 ERR_INTERNET_DISCONNECTED，符合「外壳可离线、数据必在线」）、新 SW 静默接管（autoUpdate 实测）、修后离线 modal 不再误弹；375px 移动视口生产构建正常（docs/m15-i48-*.png ×3）；vitest 2 绿、pytest 141 零影响。 |
| 2026-09-04 | I49 | 移动端打磨收尾：**新增冒烟 21**（test_smoke_21_pwa.py：源码级 VitePWA/denylist/零 runtimeCaching 键/manifest link/图标断言 + dist 产物深检 manifest standalone/start_url/maskable + precache 清单零 /api + sw.js denylist 正则在位；无 dist 时 skip——测试教训：源码注释含「runtimeCaching」字样会误判，断言须匹配配置键 `\bruntimeCaching\s*:`）；**修通知下拉 375px 左溢**（w-80 right-0 越界 → 小屏 fixed 全宽悬浮，getBoundingClientRect 实测 left:8/right:367）；docs/12 §12 移动端与 PWA 指南（安装/布局对照表/离线边界/更新与 HTTPS）；375px 关键路径复核：审批 Gate 三按钮、通知面板、⌘K 命令条全宽动作列表、零页面横溢（截图 docs/m15-i49-*.png ×4）；**pytest 142 全绿、冒烟基线 21 条 GREEN**。 |

| 2026-09-04 | M16 定义 | 新一轮开源调研（目标协议第 1 条）三路并行：①**OpenProject 自定义查询分层**——自定义查询（保存过滤/排序/分组，私有/公开）是 Community 免费核心且为仪表盘构件，跨项目聚合报表/time report PDF 才是 Enterprise → 做社区层等价、不做聚合报表；②**Gitea SSO/OIDC JIT 痛点**——ENABLE_AUTO_REGISTRATION 全有或全无无 allowlist（#27709）、group claim 第二次登录才生效或静默失效（#32566/#19722）→ 需本地 IdP 演示环境成本高，降下一轮候选（设计约束：allowlist fail-closed/claim 缺失回落最低角色）；③**通知 digest**——Redmine 无原生（靠插件）、GitLab 仅安全/流水线专项摘要 → 同类均无原生内建，AgentPM 已有邮件开关+站内+Atom 三层降噪，留 backlog。选定 **M16 = 自定义视图与保存筛选**（当前过滤全部临时刷新即失）：I50 视图数据层（saved_views 投影表 + view.* 事件 + 定义校验 fail-closed + 展开执行纯复用既有过滤）/ I51 视图前端（保存/切换/管理 + 共享徽标 + URL 直开）/ I52 默认视图+docs/12 §13+冒烟 22+审阅；范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +9 人日；新增冒烟 22 于 I52。结论入 docs/01 §O。 |
| 2026-09-04 | I50 | 视图数据层：新域 `domains/views.py` + saved_views 投影表（drop_projections 清单同步）+ view.created/updated/deleted（rebuild 存活）；CRUD + **定义校验双层 fail-closed**（键白名单/值类型/枚举 + 项目上下文：group_by/cf 字段须声明**且未停用**——cf 分支初版漏停用检查，被单测「停用后 cf 视图应 422」当场拦住补上）；**权限对齐 M8**（local 放行；network public 成员读/private owner+admin 读/viewer 不可建/改删 owner+admin/非成员 403——列表语义为过滤掉不可读行而非整体 403，详情与执行端点才 403）；**执行纯复用**：get_items/get_board 增 view_id，definition 提供基础过滤、显式 query 参覆盖；cf 匹配提取模块级 `_cf_hit` 共用（get_items 原内嵌闭包消除）。测试踩坑记录：内置本体字段 id 是 `tags` 而非「概念.字段」全称、字段停用 API 是 `{field_id, active}`、tags 合法值 frontend/backend/infra、network 模式写请求须先 /auth/login（TestClient 无会话 cookie 首请求 401）。单测 4 项 + pytest **146** 全绿、冒烟 21 GREEN。 |
| 2026-09-04 | I51 | 视图前端：看板工具栏「视图」管理器——chip 按钮（当前视图名 acc 高亮/未选中中性）+ 下拉面板（视图列表应用/公开徽标/「当前」标注/hover 删除 ✕；保存区：名称输入+项目内公开勾选；「退出当前视图」保留过滤只清 view 键）；**视图=过滤参数命名快照**：应用视图把 definition 写回 URL params（priority/assignee/group，功能切片 feature 保留），删当前视图自动清 view 键；**直开 `?view=<id>` 自动补齐 definition 参数**（useEffect 仅补 URL 缺失键、显式 params 优先——分享链接还原语义，避免 view id 成为第二过滤真源）；api.ts 增 SavedView + 4 方法。浏览器隔离复演（生产构建）：保存「高优先级」（priority=high+公开）URL 带 view id、保存「按标签分组」、点击切换 chip 高亮+group 键被视图定义替换、**直开 `?view=vw_x` 自动补齐 priority+group** 分组下拉即「分组：标签」（截图 docs/m15-i51-*.png ×5）。复演踩坑：**演示生产构建改代码后必须 SW update+reload**（autoUpdate precache 给旧 bundle，新 UI 静默不出现）；preview 代理在后端重启窗口期间歇 500（非产品缺陷）。build+vitest 绿。 |
| 2026-09-04 | I52 | 收尾：**默认视图**——`view.made_default` 事件投影先清项目内 is_default 再设目标行（事件序重放=最终态，rebuild 幂等）；saved_views.is_default 列 CREATE+ALTER 迁移；`POST /views/{id}/make-default`；board 无 view/group 参数时自动落项目默认视图并回带 `applied_view_id`；前端 chip 认 applied_view_id（默认视图落点可见）、视图列表「设为默认/默认」徽标、分组控件 `group || board.data?.group_by` 同步实际生效值。**修 db.py 迁移条件 bug**：`"saved_views" in vcols` 把表名查进列名集合恒 False → ALTER 永不执行——隔离存量库 board 500 当场暴露（新表库 CREATE DDL 直接管、单测 tmp_data 全新库测不到存量迁移，**演示隔离库才是存量迁移的真测试场**），拆分「表存在性+缺列」两步修正。docs/12 §13 自定义视图指南（heredoc 追加中文产生 GBK 乱码一次——**中文文档段落一律 Edit 工具**，截断重写修复）。**新增冒烟 22**（CRUD→校验门→执行同数→make-default→board 落点→rebuild 一致→删除回落）。pytest **147** 全绿、冒烟基线 **22 条 GREEN**、build+vitest 绿（截图 docs/m15-i52-default-landing.png、m15-i51-made-default.png）。 |
| 2026-09-04 | M17 定义 | 新一轮开源调研（目标协议第 1 条）三路并行：①**FastAPI OIDC 实现模式**——Authlib 为事实标准（code flow 的 state/nonce/PKCE verifier 存框架 session、cookie 加固在 middleware；Auth0/Vouch 提供完整参考）→ 复用 M8 HMAC 会话签发，握手后不缓存 id_token；②**本地 IdP 演示环境**——Keycloak 官方容器 realm import JSON 一键（realm/client/user 三件套，~1GB）vs Authelia 40MB 手工 YAML → 单测用本地 RSA JWT 桩离线覆盖协议路径，演示用 Keycloak compose 脚本化；③**Gitea 教训深化**——group claim 派生标志第二次登录才生效（#32566）、无 allowlist（#27709）、Entra 缺可信 email 跳账号链接页 → 提炼四约束。选定 **M17 = OIDC 单点登录**（M8 遗留 SSO 缺口）：I53 OIDC client 基座（discovery+code flow+PKCE+id_token 验证+JIT 四约束+JWT 桩单测）/ I54 会话整合与前端（OIDC 按钮+admin 配置面板+门禁兼容）/ I55 Keycloak 演示环境+docs/11 §2+docs/12 §14+冒烟 23+审阅；范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +10 人日；新增冒烟 23 于 I55。结论入 docs/01 §P。 |
| 2026-09-04 | I53 | OIDC client 基座：新模块 `core/oidc.py` **零新依赖**（cryptography/httpx 已有，RS256 验签自实现——jwks kid 匹配 + RSA PKCS1v15/SHA256，不引 authlib）；discovery 一小时缓存；authorization URL（state/nonce 随机 + PKCE S256，三元组存 HttpOnly SameSite=Lax 十分钟 cookie）；token 换取（basic auth）；id_token 全校验（alg 白名单 RS256/签名/iss/aud/exp 60s leeway/nonce 常量时间比较）；**JIT 四约束**（Gitea 教训）：email 缺失或未验证 422 / allowlist `APM_OIDC_ALLOWED_GROUPS` 非空无交集 403 / 同 email 存量账号幂等重入 / 同名本地账号 409 不自动合并；**角色一次性定** viewer 缺省、重登不重派（规避 #32566 时序坑）；env 未配置整体 404 关闭（SMTP 同款）；`GET /api/auth/oidc/login|callback` 端点（回调签发 M8 同款 HMAC 会话 + 清握手 cookie）。单测 5 项：**本地 RSA JWT 桩**（monkeypatch oidc.httpx get/post，内存 discovery/jwks/token + 桩密钥签发）离线覆盖全协议路径/JIT 重登幂等/拒绝矩阵七例/拒绝路径零建号/账号冲突 409。**测试踩坑：TestClient 默认 follow_redirects=True**——302 到外部 IdP 后外部请求产物 404，极易误判为「路由缺失」；登录/回调断言一律 `follow_redirects=False`。register_user 入参是 pydantic UserIn 非 dict。pytest **152** 全绿、冒烟 22 GREEN。 |
| 2026-09-04 | I54 | 会话整合与前端：`GET /api/auth/oidc/status` 特性探针（enabled/issuer/client_id/redirect_uri/allowed_groups，secret 不回显）；前端 /login 页「🔑 使用单点登录」按钮（未配置不显示）+ 本体页 OIDC 诊断面板；tools/oidc_stub.py mini IdP 桩（ThreadingHTTPServer）供浏览器真流程演示；门禁兼容单测（OIDC JIT 用户非成员写 403）；浏览器桩全流程复演闭环（登录页→SSO→会话→chip→403→面板，截图 docs/m17-i54-*.png ×3）；build+vitest 绿。复演踩坑：本地双端口下 redirect_uri 须指向前端域（会话 cookie 落 callback 域）；Windows 允许多进程同时 LISTEN 同一端口（桩双实例请求随机分流）。 |
| 2026-09-04 | I55 | 收尾：tools/keycloak/ 演示环境（docker-compose + realm import：client/用户/组三件套）与 tools/oidc_stub.py 在位；docs/11 §2.1 OIDC env 表；docs/12 §14 OIDC 单点登录指南（协议安全语义/JIT 四约束表/门禁兼容）；新增冒烟 23（特性关闭零破坏/桩协议全路径/JIT 幂等/门禁保留）；pytest **154** 全绿、冒烟基线 **23 条 GREEN**。 |
| 2026-09-04 | M18 定义 | 新一轮开源调研（目标协议第 1 条）三路并行：①**Plane/GitLab 评论与提及**——工作项评论线程 + `@` 提及即通知是协作核心，AgentPM 工作项无评论流（对话域消息不挂工作项）为真实缺口；②**OpenProject 工时跟踪**——work package 记录 spent time 是 Community 免费核心（16.0 增个人日历），AgentPM 有 estimate_hours 无 spent → 与 M14 自动排期互补的执行侧缺口，留下一轮首选候选；③**GitLab 通知订阅层级**——Watch/Participating/On mention/Subscribed/Custom，参与者（评论/编辑/被提及）自动成为通知对象 → M18 采「参与者+被提及」最小面。选定 **M18 = 工作项评论与参与通知**：I56 评论域（comment.* 事件 + @mention 解析 → 通知 + 参与投影）/ I57 评论前端（评论区 + mention 补全 + 通知跳转）/ I58 订阅（watch/subscriber）+ docs/12 §15 + 冒烟 24 + 审阅；范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +9 人日；新增冒烟 24 于 I58。结论入 docs/01 §Q。 |
| 2026-09-04 | I56 | 评论域：新域 `domains/comments.py`——item_comments 投影表（软删除 deleted_at）+ item_participants 参与投影（PRIMARY KEY 去重 INSERT OR IGNORE）+ comment.created/deleted 事件（drop_projections 清单同步，rebuild 存活）；**@mention 解析**：`@姓名` 对 users.name 精确最长匹配（多字姓名「QA 王」可用、作者自身排除），mentions 入事件 payload；**mention 通知走 M10 notification.sent 通道**（kind=mention，站内铃+邮件自然联动）；参与面接入 item.assigned（human 指派即参与）；CRUD：POST/GET /items/{id}/comments、DELETE /comments/{id}（软删），权限 local 放行/network 成员读写+非成员 403+删除限 author·admin；单测 4 项（CRUD+软删除+rebuild 一致/mention 解析+逐身份通知断言/指派参与者去重/network 权限矩阵）；pytest **158** 全绿、冒烟 23 GREEN。测试踩坑：/api/notifications 按当前身份过滤——逐身份断言须 /session/identity 切到被提及者再查（并发现并修复本附录 883-887 与 874-878 五行完全重复、I56 行遗漏——本次补记）。 |
| 2026-09-04 | I57 | 评论前端：新组件 `CommentsModal.tsx`（评论列表 author_name+**@提及高亮**、textarea 输入、**@补全下拉**——draft.lastIndexOf('@') 后缀匹配 users、Ctrl+Enter 发送、hover 作者可见删除 ✕）；看板卡片 💬 按钮+**评论数徽标**（有评论显示数字）+**`?item=<id>` 直开**（useEffect 在 buckets 找到即 setCommentsFor）；通知中心 mention 项**点击跳转** `#/p/{pid}/board?item=`（notifications.py get_notifications 由 ref_event_id→events.agg_id 解析出 item_id）+**点击即置已读**（markNotificationsRead 单条+invalidate，徽标随跳转清零）；api.ts 增 ItemComment 类型+3 方法。审阅即修 2：①mention 通知摘要带**工作项标题**（「T2 需求池…」而非裸 i_xxx id——_require_item 补 title 列，单测补断言）；②点击通知置已读。**复演排障**：上次「铃徽标 1 但面板空」疑云定案——双后端进程同时 LISTEN 8000（Windows 允许双绑，两次轮询打到不同数据目录实例，badge 与列表同源才显矛盾）——netstat 确认单监听后重建隔离环境（种子+预建 QA 王再发评论，避免评论先于用户落库 mention 为空）复演全通。浏览器双身份复演（生产构建+SW 清缓存）：李雷 @补全发评论→API 验证 mentions=["qa"]→切 QA 王铃徽标 1→面板 mention 通知（带标题+未读点）→点击跳转 Modal 自动开+@QA 王 蓝色高亮+徽标清零（截图 docs/m18-i57-*.png ×4）。build+vitest 2 绿、pytest **158** 全绿。 |
| 2026-09-04 | I58 | 订阅与收尾：**item.subscribed/unsubscribed** 事件+投影（watch 参与行；退订只删 watch——assignee/author/mentioned 为派生参与不随退订消失，事件序重放=最终态）+ `POST/DELETE /items/{id}/subscription` + 评论抽屉「🔕 订阅/🔔 已订阅」切换按钮；**通知面接入参与者**（最小面：新评论+状态变更）——plan_notifications 扩展两事件（comment.created 排除作者与被提及防双发/item.status_changed 排除操作者），NOTIFY_EVENTS 同步扩展→邮件通道（mailer.enqueue 同函数收人）自动一致；**两个单测当场拦住的坑**：comment.created 的 agg_id 是评论 id 不是 item（参与者查询须取 payload.item_id，首跑空通知暴露）、software-dev task 状态集无 todo（open/ready/in_progress/awaiting_review/done/cancelled，422 提醒）；**语义决策入档**：软删除评论不撤回已发通知（append-only，撤回需负向事件不成比例）；docs/12 §15 评论与参与通知指南（bash 反引号吞字一次——中文文档段落一律 Edit 工具的教训再验）；**新增冒烟 24**（CRUD 软删→mention 通知+深链→参与集合首次来源胜出→订阅→状态变更+新评论通知参与者→退订降噪→rebuild 三投影一致）；pytest **160** 全绿、冒烟基线 **24 条 GREEN**、build+vitest 2 绿。 |
| 2026-09-04 | M18 正式审阅 | DoD 逐项核对（审阅时点 HEAD `61b8afd` 重跑 pytest **161** 项 0 失败 + 冒烟 **24** 条 GREEN + vitest 2/build 绿）+ 浏览器隔离复演（隔离 data+ontologies + 生产构建 + 端口单监听确认）：李雷开抽屉→订阅切换→@补全评论→QA 王 mention 通知→点击跳转→QA 王改状态→李雷收参与者通知（截图 docs/m18-review-*.png ×6，详见附录 B）。**审阅即修 1 个 A 级缺陷**：`change_status` 签名默认 actor_id 硬编码 "u_admin"（M5-I19 全仓清 actor 硬编码的漏网之鱼）——PATCH 状态变更审计归因全错 + 参与者通知操作者排除失效（复演中 qa 改状态被记李雷名下当场暴露）→ `actor_id or events.effective_actor()` + 调用点显式传 + 回归单测。 |
| 2026-09-04 | M19 定义 | 新一轮开源调研（目标协议第 1 条）三路并行：①**OpenProject 工时模型**——time entry（时长/日期/备注/作者）挂 work package、点 spent 数字进该包记时报表，16.0 个人「My time tracking」日历，模块停用即隐藏 spent（OP-925），Community 免费；②**GitLab/Redmine 记时入口**——GitLab `/estimate`+`/spend` 斜杠命令无独立 UI，Redmine 独立「Log time」按钮，GitLab FOSS #27780 用户实测偏好显式入口 → AgentPM 取 Redmine 式；③**Plane worklog**——仅工作项级「+ Log work」，项目级聚合是官方 open 缺口 GitHub #8045 → AgentPM 本轮直接纳入项目工时报表差异化补位。选定 **M19 = 工时跟踪与汇总报表**：I59 工时数据层（time.* 事件 + item_time_entries 投影 + CRUD + spent 汇总 + 权限对齐）/ I60 工时前端（记工时抽屉 + spent/estimate 徽标 + docs/12 §16 + 冒烟 25）/ I61 项目工时报表（按人/按日）+ 全量回归 + 审阅；范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +9 人日；新增冒烟 25 于 I60。结论入 docs/01 §R。 |
| 2026-09-04 | M19 正式审阅 | DoD 逐项核对（审阅时点 HEAD `cc2af95` 重跑 pytest **167** 项 0 失败 + 冒烟 **25** 条 GREEN + vitest 2/build 绿）+ 浏览器隔离复演（隔离 data+ontologies + 生产构建 + 端口单监听确认）：李雷 ⏱ 抽屉记 90m→卡片「⏱ 1h30」徽标上卡→切 QA 王 45m→**合计 2h15** 双条目同屏（docs/m19-i60-*.png ×4）→报表页工时小部件（按人条形 李雷 1h30/QA 王 45m + 按日趋势 + 合计 2h15）→我的工作「本周工时 1h30」chip（docs/m19-i61-*.png ×3）。I59 DoD（CRUD+rebuild/校验矩阵/汇总/权限/参与接入）✓；I60 DoD（抽屉+徽标+docs/12 §16+冒烟 25）✓；I61 DoD（报表对账单测+个人周合计+全量回归）✓。无新增 B/C 级意见。 |
| 2026-09-04 | I59 | 工时数据层：新域 `domains/timelog.py`——item_time_entries 投影表（软删 deleted_at）+ time.logged/edited/deleted 事件（drop_projections 清单同步，rebuild 存活）；CRUD：POST/GET /items/{id}/time_entries、GET/PATCH/DELETE /time_entries/{id}（列表返回 entries+total_minutes+participants）；**校验 fail-closed**：minutes 整数∈(0,1440]、spent_on 须 ISO 日期（date.fromisoformat）、note 截 500、空 PATCH 422；item 详情/get_items 附 **spent_minutes**（SUM 排除软删；列表一次 GROUP BY 合并避免逐行子查询），与 estimate_hours 构成「计划 vs 实际」并列展示面（I60 徽标用）；权限对齐 M8：local 放行/network 成员读写+非成员 403+改删限本人·admin；**参与投影接入**：time.logged 复用 comments._join_participants（source='time'，INSERT OR IGNORE 首次来源语义不覆盖）；单测 4 项（CRUD+软删+rebuild 一致/校验矩阵/参与接入首源胜出/network 权限矩阵）；pytest **165** 全绿、冒烟 24 GREEN。 |
| 2026-09-04 | I60 | 工时前端：新组件 `TimeLogModal.tsx`——⏱ 工时抽屉（条目列表：人/时长徽标（`fmtMinutes` 1h30/45m）/spent_on/备注；记时表单：分钟 number 1-1440 + 日期 date 默认今天 + 备注 textarea；**合计行**随记录实时刷新，invalidate 时同步刷 board/list 的 spent_minutes）；看板卡片 **⏱ spent 徽标**（仅 spent_minutes>0 显示，title=实际投入工时）+ 卡片 ⏱ 按钮（与 💬 并列，浮层同型）；api.ts：TimeEntry 类型 + listTimeEntries/logTime/editTimeEntry/deleteTimeEntry + Item.spent_minutes 可选字段；docs/12 §16 工时跟踪指南（记时入口/展示位/语义与边界三层）；**新增冒烟 25**（双身份记时→条目/合计/详情/列表四处一致→minutes/日期校验门→软删缩合计→rebuild 条目与合计逐项复现）。TS 踩坑：Item 可选字段 spent_minutes 传入 fmtMinutes 须 `?? 0` 收窄。浏览器隔离复演（生产构建+SW 清缓存）：李雷 90m→卡片「⏱ 1h30」徽标上卡→切 QA 王 45m→**合计 2h15** 双条目同屏（截图 docs/m19-i60-*.png ×4）；build+vitest 2 绿、pytest **166** 全绿、冒烟基线 **25 条 GREEN**。 |
| 2026-09-04 | I61 | 项目工时报表+收尾：`reports.py` 新增 `GET /projects/{id}/timelog_report`——by_user（SUM GROUP BY user_id JOIN users 取名）/by_day（近 N 日零填充序列，days 参数钳 1-90）/total_minutes，纯投影聚合（M12 原则：报表零 ETL 零新表）；`my/work` 增 week_minutes（spent_on >= 本周一，个人最小面，个人日历留 backlog）；前端：ReportsPage 尾部 `TimelogCard` 小部件（按人横向条形 + 按日迷你柱图 + 合计，15s 轮询与报表页一致）、MyWorkPage 头部「本周工时」chip（复用 fmtMinutes）；api.ts 增 TimelogReport 类型 + getTimelogReport(days)；**对账单测**：报表 total/by_user/by_day 与两条工作项条目清单逐项相等、软删后报表同步缩、未知项目 404（Plane GH #8045 的正面实现——项目级聚合与条目恒可对账）；复演：报表小部件合计 **2h15**=李雷 1h30+QA 王 45m 与抽屉条目一致、「本周工时 1h30」chip 可见（截图 docs/m19-i61-*.png ×3）；build+vitest 2 绿、pytest **167** 全绿、冒烟基线 **25 条 GREEN**。 |

| 2026-09-05 | M20 定义 | 新一轮开源调研（目标协议第 1 条）三路并行（防重查先行：digest 已 §J/§O.3 两次论证留 backlog 不重查）：①**OpenProject 16.0「My time tracking」**——个人专属日历视图（日/周/月）+列表双形态+页面快捷记时，「允许精确记时」才引入 start/end 且日历成默认视图 → 分钟粒度条目配日历完全成立，AgentPM 不做打卡、日历做复盘视图；②**Gantt 拖拽生态**——OpenProject 内建条形拖拽改期/拖边改时长/手动默认+自动可选，Redmine 核心缺拖拽靠 Easy Gantt 等插件补位 → AgentPM M13 时间线只读 + M14 后端自动排程**两端齐备缺手动拖拽层**；③**评论 Markdown 渲染**——GLFM/GFM 任务清单与表格是结构化主力，但 Outline/Drupal 实证风味分歧集成成本、表格内复选框不持久 → 只取 GFM 交集、**存储保持纯文本原文**渲染层转换（marked+DOMPurify）。选定 **M20 = 体验补齐三件套**：I62 个人工时日历（GET /my/timelog + 周/月日历页 + 点日快捷记时）/ I63 时间线拖拽改期（条形拖拽移动+右缘缩放 → PATCH 复用 rescheduled 审计与冲突重算）/ I64 评论 Markdown 渲染（GFM 只读 + mention chip + 预览）+ docs/12 §17 + 冒烟 26 + 审阅；范围变更：计划外新增里程碑，理由 = 目标协议持续推进，估时 +8 人日；新增冒烟 26 于 I64。**验证纪律更新（用户 2026-09-05）**：迭代期只跑改动相关测试、全量回归收敛至 M20 审阅；HANDOFF 每轮修剪。结论入 docs/01 §S。 |

| 2026-09-05 | I62 | 个人工时日历：`GET /my/timelog?days=`（本人条目按 spent_on 分组 + 日合计 + 窗口合计；days 钳 1-60 缺省 28；纯投影聚合零 ETL，JOIN items/projects 取 item_title/project_name；own-data 语义对齐 my/work 无额外门禁——network GET 开放但 effective_actor 即会话本人）；「我的工时」页 `#/my/time`：周（周一始七列）/月（42 格）双视图、今日高亮、‹今天›翻页、窗口合计 chip、空态引导；**点日期格开快捷记时卡**：当日条目列表（点选进入编辑态高亮、✕ 删除）+ 工作项下拉（数据源 getMyWork 指派项）+ 分钟/备注表单 spent_on 预填当日；编辑仅 minutes/note（time.edited 无 item 迁移语义，改日期引导去工作项 ⏱ 抽屉）；侧栏 rail「我的工作」旁 CalendarClock「我的工时」入口；api.ts MyTimelogDay/MyTimelog + getMyTimelog(60)；单测 `test_my_timelog_calendar_feed`：按日分组与日合计/仅本人可见（他人记时不入我的 feed）/软删剔除且 rebuild 存活/窗口 days 钳 0→1、999→60；相关验证（新纪律）：timelog 7 项绿 + build 绿 + vitest 2 绿。前端踩坑：`monthOf` 未使用 TS6133 build 拦截（tsc -b 严格）。 |

| 2026-09-05 | I63 | 时间线拖拽改期：TimelinePage 条形 pointer 拖拽（setPointerCapture 跟手）——拖动条形=move（start/due 同步平移，start 缺省只移 due）、右缘 w-1.5 把手=resize（仅 due，Math.round 起点差钳制不早于 start）；拖拽中 opacity-50 + title「改为 X ~ Y」按 px/day 换算整日 delta 实时预览；**Esc 全局监听取消、pointercancel 回滚**；落点单 PATCH `{start_date?, due_date}` 走既有 `api.patchItem`——M14 propagate_reschedule（auto_scheduled 后继顺延 + item.rescheduled 审计）与依赖冲突重算着色随 `qc.invalidateQueries()` 全量 refetch 自动生效，前端零新事件零新端点；单测 `test_drag_move_semantics_and_audit` 固化拖拽前端载荷契约（双日期单 PATCH）与右缘语义（仅 due）+ delta_days=3 传播审计；scheduling 5 项绿、build+vitest 绿。**纪律重申：源码/测试追加一律 Edit 工具——本次误用 bash heredoc 追加 test_scheduling.py（引号形式无替换侥幸无损，已核 LF 与内容），后不再犯。** |

## 附录 B · 审阅记录（逐次追加）

| 日期 | 迭代/里程碑 | 意见 | 级 | 处置与落点 |
| --- | --- | --- | --- | --- |
| 2026-09-02 | M4 正式审阅 | 08 §8.3 验收锚点逐项核对：① 四类信号（L1 priority×12 / L2 遗留关系 / L3 沉淀链接 / L4 角色覆盖）learn 全命中且 provenance 可溯 ✓；② apply 后校验通过、version 递增、事件流含 ontology.updated（含 diff 摘要）✓；③ L2 场景 apply 后同型关系通过建卡 API 校验 ✓；④ 重复 learn 幂等（已应用候选不再出现）✓。浏览器演示路径实测通过（截图 docs/m4-review-ontology-page.png）。 | — | 里程碑通过 |
| 2026-09-02 | M4 正式审阅 | CQ 证据行的 events 源是全局计数（不按项目过滤），多项目同本体时口径偏大 | B | 排入后续迭代任务清单（可在 evidence 的 events 源加 project_id 过滤；不影响单项目正确性） |
| 2026-09-02 | M4 正式审阅 | 本体学习/版本面板未做权限分层（单用户 MVP 无影响，多租户时 apply 应挂审批） | B | 入附录 C backlog（对齐 07 §5 V2 治理） |
| 2026-09-02 | M5 正式审阅 | 各迭代 DoD 核对：I17 回放候选确定性+confidence≥0.65+与 pattern 合并不重复+apply 同链路 ✓，CQ events 按项目过滤 ✓；I18 导出→改名导入→新本体建项目（7 阶段图继承）✓，同名 409/坏包 422 ✓，角色复用不覆盖 ✓；I19 双身份按人可分审计流 ✓，human 指派未知用户 fail-closed ✓，assignee 过滤看板切片 ✓，审批 decided_by 过滤 ✓。浏览器演示（本次**同时隔离** data 与 ontologies 目录——M4 教训落实）：注册「QA 王」→ 自动切换（顶栏 👤 QA 王）→ 本体页「✨ LLM 建议」→ 2 条 LLM 候选（0.72，通道 llm）→ 勾选应用 → v2 + 时间线；导出/导入入口在位。截图 docs/m5-review-collab-page.png。 | — | 里程碑通过 |
| 2026-09-03 | M7 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `7c0f7bb` 重跑 pytest 89 项 + 冒烟 13 条全绿）：**I23** 注册表统一视图（内置+导入同列表、source/版本/概念/阶段/CQ 摘要）✓（test_registry_unifies_builtin_and_imported）、预览含阶段图与 CQ ✓、instantiate 建项目共链路（bootstrap 齐全）✓、未知 404/坏名 422/启动登记幂等 ✓；**I24** 资产→pack 注册（provenance 解析来源项目、pack.registered source=asset 可审计、重复 409）✓（test_from_asset_registers_pack / test_from_asset_fail_closed）、模板中心页与入口 ✓；**I25** 停用→写入 422→分组维度 422→启用恢复 ✓、未声明字段 422 ✓、rebuild 存活 ✓（test_field_activation 2 项）、冒烟 13 含资产→包与激活往返断言 ✓。浏览器复演两条演示路径（隔离 data+ontologies）：①模板中心→「用此模板建项目」→ 自动跳转新项目看板（p_09e21ea0cf，截图 docs/m7-review-instantiate-board.png）；②本体页停用「标签」→看板分组选择器即刻无该维度→启用恢复 disabled_fields=[]（截图 docs/m7-review-field-deactivated.png）。console 4 条 404 逐条查明为跨隔离环境旧项目 ID 轮询，非产品缺陷。 | — | 里程碑通过 |
| 2026-09-03 | M6 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `6e73cde` 重跑）：**I20** 三类新类型读写往返 ✓（test_custom_field_types_roundtrip）、未声明/类型错/越界 fail-closed 422 ✓（test_custom_field_validation_fail_closed）、multiselect 多值存储 ✓、rebuild 投影一致 ✓（test_custom_fields_survive_rebuild）；**I21** 分组 API 桶序/扇出/未设置列/未知 422 ✓（test_board_group_by_custom_field）、冒烟 9 含 cf 过滤+字段分组断言 ✓；**I22** langgraph 1.2.11 下 pytest 80 项全绿 + 冒烟 12 条 GREEN 零改动 ✓。浏览器复演两条演示路径（隔离 data+ontologies）：①「按标签分组看板」frontend×2/backend×1/infra×1/未设置×2，multiselect 扇出与卡片徽标可见（截图 docs/m6-review-board-grouping.png）；②「打断-注入-恢复」pm-agent 至 prd_review 挂起（commit 9e781813）→ 注入「兼容 Python 3.9 / 导出 Markdown」→ ▸ 继续 checkpoint 续跑 revise → 新稿 4fffc13e 逐条含注入约束回到 Gate → 批准后 run succeeded（截图 docs/m6-review-interrupt-resume.png）。演示中浏览器 console 的 404/连接拒绝噪声逐条查明：均为跨隔离环境旧会话轮询与关服后标签页重连，非产品缺陷。 | — | 里程碑通过 |
| 2026-09-03 | M8 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `dec89c3` 重跑 pytest 97 项 + 冒烟 14 条全绿）：**I26** pbkdf2 哈希 + HMAC 签名会话 + secret 持久化（重启会话存活）✓、login/login_failed/logout 审计事件 ✓（test_auth 4 项：登录往返/坏密码 401+审计/network 门禁 401/local 零破坏）、`_safe_user` 剥离凭据 ✓、凭据不入事件（APM_ADMIN_PASSWORD 重引导）✓；**I27** creator=owner ✓、末位 owner 保护/未知 422/重复 409 ✓（test_members 3 项含 rebuild 存活）、viewer/非成员写 403 + `access.denied` 审计 ✓；**I28** 会话→actor 归账（冒烟 14 断言 qa-wang 写 item.created actor=qa-wang、自建项目 owner=qa-wang）✓、身份切换 network 422 ✓、/login + 401 跳转 + 顶栏分流 ✓。浏览器双账号协作演示（隔离 data+ontologies + APM_AUTH_MODE=network + APM_ADMIN_PASSWORD）：①登录页登录 u_admin（截图 docs/m8-review-login.png）→ 建项目（Owner=李雷）→ 成员面板添加 QA 王=Viewer（截图 docs/m8-review-admin-members.png，顶栏 ⭐李雷+登出）；②登出→qa-wang 登录（顶栏 👤 QA 王 ·「网络模式 · 以登录身份归账」）→「新功能」提交 403 forbidden（截图 docs/m8-review-viewer-denied.png），API 复核 access.denied 事件 actor/user/project/path 四元组齐全 ✓；③管理员升 qa-wang=contributor → 同表单再提交成功 → Audit 时间线归账链完整：#16 access.denied(qa-wang) → #20 project.member_role_changed(u_admin) → #21 feature.created(qa-wang)（截图 docs/m8-review-audit-attribution.png）。console 噪声逐条归因：401×2=登出后标签页 /auth/me 轮询（network 模式预期）、403×1=门禁演示本体、连接拒绝×3=后端进程被系统回收后遗留标签页 SSE/审批轮询重连，均非产品缺陷。**审阅即修 2 处前端缺陷**：①AppShell 全局 rail 链接硬编码 `/assets`（I24 引入：所有 global 入口都落到资产页，「模板」侧栏图标不可达；此前演示走项目列表页按钮入口未暴露）→ `r.global ? r.to : /p/${pid}${r.to}`，浏览器复核「模板」→#/templates、「Assets」→#/assets；②FeaturePage 空态文案「也可从看板手动建卡」过时（看板无手动建卡入口、NL L1 意图不含建项）→ 删除该子句。修后 pnpm build + vitest 2 项全绿。 | — | 里程碑通过 |
| 2026-09-03 | M9 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `064133f` 重跑 pytest 103 项 + 冒烟 15 条全绿）：**I29** 规则 CRUD 往返 + rebuild 存活 ✓（test_rule_crud_roundtrip_and_rebuild）、触发执行与 automation 归账（item.assigned/custom_fields 生效、rule_fired×2、动作事件 actor_type=automation actor_id=规则 id）✓（test_rule_fires_with_automation_attribution）、条件门 + 单层防循环（规则 A 的 set_field 触发的 item.updated 不引爆规则 B；人工更新才触发 B；停用即静默）✓（test_condition_gate_and_single_layer_no_loop）、fail-closed 全矩阵（未知触发/动作/用户/字段、enum 越界、未声明状态 422）✓（test_rule_validation_fail_closed）、dry-run 不执行 ✓（test_dry_run_reports_without_executing）；**新增冒烟 15 全程断言** ✓；**I30** 面板 CRUD + 动态表单 + dry-run toast + 历史抽屉 ✓（浏览器复演：UI 建「缺陷建卡即指派 QA」→ API 建缺陷 → 看板卡片自动「👤 qa-wang」→ 截图 docs/m9-review-automation-card.png）；**I31** 审计页 ⚡自动化 过滤 + automation 域标签 ✓（浏览器复演：发起者=⚡自动化 精确命中 #12 item.assigned + #13 automation.rule_fired，均归账 ar_07f8a246c7 → 截图 docs/m9-review-audit-automation.png）、docs/12 指南在位 ✓。防循环与归账语义与 docs/12 文档一致。 | — | 里程碑通过 |
| 2026-09-04 | M12 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `179e3bb` 重跑 pytest 128 项 + 冒烟 18 条全绿）：**I38** 漏斗/概念/吞吐/Gate 计数 + rebuild 前后一致 ✓、未知项目 404 ✓、超期/滞留口径边界 ✓、/my/work 指派即授权 + Gate 决策权对照 ✓、列表健康摘要 ✓（test_reports.py 4 项）；**I39** ReportsPage 四 widget / MyWorkPage / 列表徽标 build+vitest 绿 + 浏览器数字一致 ✓（I39 迭代截图 docs/i39-*.png ×3）；**I40** CSV 与 JSON 同数 ✓（冒烟 18 + curl 实测十二行逐行核对）、docs/12 §9 口径与权限语义在位 ✓、冒烟 18 全程 ✓。浏览器隔离复演（审阅时点）：报表页漏斗 4/0/1/1/0 + 挂起 Gate「◆ PRD 评审」+ 超期滞留清单 + 吞吐 6/1（截图 docs/m12-review-reports-page.png）；切 qa-wang 我的工作 3 项跨项目聚合（截图 docs/m12-review-my-work.png）。无新增 B/C 级意见。 | — | 里程碑通过 |
| 2026-09-04 | M13 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `edecddd` 重跑 pytest 134 项 + 冒烟 19 条全绿）：**I41** 里程碑 CRUD 往返 + rebuild 存活 ✓、校验 fail-closed 全矩阵（坏日期/缺日期/坏状态/未知关联）✓、进度与逾期计算 + rebuild 一致 ✓、item 日期 ISO 校验 + 报表口径三级回退 ✓、创建即关联 ✓（test_milestones.py 5 项）；**I42** TimelinePage 四要素 build+vitest 绿 + 浏览器验证 ✓；**I43** NDJSON 导出（行序+prev 链位+校验和行+gaps 披露）✓（冒烟 19）、docs/11 §5 备份与 docs/12 §10 在位 ✓。浏览器隔离复演（审阅时点，隔离环境演示库 p_bf3f9022c8）：时间线页日期轴 + 今日线 + 里程碑菱形（Beta 发布·09-20·悬停完成 33%）+ 任务行冲突红条（编码实现依赖设计评审）+ 行底红虚线 + 缺陷行蓝条（截图 docs/m13-review-timeline.png）；里程碑进度 API 实测 {3, 1, 0.33, 0} 与菱形悬停一致；NDJSON 导出实测 35 事件 + 校验和行（sha256/first_prev=4/gaps=3 显式披露跨项目间隙）。无新增 B/C 级意见。 | — | 里程碑通过 |
| 2026-09-04 | M14 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `b1f93cb` 重跑 pytest 141 项 + 冒烟 20 条全绿）：**I44** propagate_reschedule 单级传播（delta 平移保时长 + item.rescheduled 归因 follow_of/delta_days）✓、手动模式零影响且无 rescheduled 事件 ✓、多级递归 A→B→C 各 +4 + 环 X↔Y 只平移一次（深度 20 + visited 防环）✓、rebuild 后日期存活 ✓（test_scheduling.py 4 项）；**I45** 导出→全新库导入 roundtrip（事件流与投影逐行一致）✓、拒绝矩阵（源库重导 409 / 篡改 422 / 坏 JSON 422 / 缺校验和 422 / 项目不匹配 422 / 拒绝后无半导入残留）✓（test_import.py 2 项）；**I46** 冒烟 20 全程（自动排期链 + 可携 roundtrip + 恢复库 rebuild 一致）✓、docs/12 §11 与 docs/11 §5.3 在位 ✓。浏览器隔离复演（审阅时点）：「依赖链-设计→开发→测试」三级链全开自动排期 → PATCH A due +6 → B（09-13/09-21）、C（09-21/09-27）自动顺延，时间线条形 hover「⏱ 自动排期」标注可见（截图 docs/m14-review-timeline.png）；审计页 item.rescheduled ×2 事件逐条展示 follow_of/delta_days=6（截图 docs/m14-review-audit-rescheduled.png）。无新增 B/C 级意见。 | — | 里程碑通过 |
| 2026-09-04 | M15 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `8fb1499` 重跑 pytest 142 项 + 冒烟 21 条 GREEN + vitest 2 项全绿）：**I47** AppShell 窄屏断点（rail/功能列折叠 + 汉堡抽屉含导航与功能区 + ⌘K 图标化 + 触控目标）✓、看板列表/时间线横向滚动 + Reports/MyWork/Dashboard 栅格单列 ✓（Playwright 375×812 五截图 + 1440 桌面复核零回归）；**I48** 构建产物 manifest.webmanifest + sw.js + precache 7 项静态资产（源码与浏览器 caches 枚举双验证**零 /api 条目**）✓、**断网 reload 静态外壳完整载入**（console 仅 /api 请求失败，符合「外壳可离线、数据必在线」）✓、autoUpdate 新 SW 静默接管实测 ✓；**I49** 冒烟 21（源码级基建 + dist 产物深检：standalone/start_url/maskable/precache 零 /api/denylist 正则）✓、docs/12 §12 与 docs/11 §4.1 在位 ✓、375px 关键路径触控复核（审批 Gate 三按钮/通知面板/⌘K 命令条/时间线横滚实证）✓。**审阅即修 3 个既有前端缺陷**：①sonner `<Toaster>` 全仓从未挂载（历次 toast 全部静默无显示）；②ProjectPicker 空库引导与加载失败混淆（离线误弹「新建项目」模态）；③通知下拉 `right-0 w-80` 在 375px 左溢 25px（改小屏 fixed 全宽悬浮）。浏览器隔离复演（隔离 data+ontologies + vite preview 生产构建）：375px 视口共 14 张截图（docs/m15-i47-*.png ×6、m15-i48-*.png ×3、m15-i49-*.png ×4、m15-review-timeline-375.png）。无新增 B/C 级意见。 | — | 里程碑通过 |
| 2026-09-04 | M16 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `8b37d72` 重跑 pytest 147 项 + 冒烟 22 条 GREEN + vitest 2 项全绿）：**I50** saved_views 事件溯源 CRUD + rebuild 存活 ✓、定义校验双层 fail-closed（键白名单/枚举 + 字段声明与停用检查）✓、权限对齐 M8（network 可见性矩阵：public 成员读/private owner+admin/viewer 不可建/非成员 403）✓、视图执行与手工过滤同数（test_views.py 4 项 + 执行纯复用既有过滤路径）✓；**I51** 视图管理器（保存/切换/公开徽标/删除/退出保留过滤）✓、URL `?view=` 直开自动补齐 definition 参数（显式 params 优先）✓（浏览器复演：保存「高优先级」→切换→直开还原，截图 docs/m15-i51-*.png ×5）；**I52** 默认视图（make-default → board 无参落点 applied_view_id + chip/分组控件同步）✓、docs/12 §13 与 docs/11 §4.1 在位 ✓、**冒烟 22 全程**（CRUD→校验门→执行同数→make-default→board 落点→rebuild 一致→删除回落）✓。**审阅即修 1 个后端缺陷**：db.py 存量迁移条件把表名误查进列名集合致 ALTER 永不执行（隔离存量库 board 500 暴露修正）。浏览器隔离复演（隔离 data+ontologies + vite preview 生产构建）：视图全程含默认直达截图 docs/m15-i51-made-default.png、m15-i52-default-landing.png。无新增 B/C 级意见。 | — | 里程碑通过 |
| 2026-09-04 | M17 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `84c57cc` 重跑 pytest 154 项 0 失败 + 冒烟 23 条 GREEN + vitest 2 项全绿）：**I53** `core/oidc.py` 零新依赖 RS256 验签（jwks kid + PKCS1v15/SHA256）✓、discovery 缓存 + code flow + PKCE S256 + state HttpOnly 短命 cookie ✓、id_token 全校验（alg/签名/iss/aud/exp/nonce）✓、**JIT 四约束**（email_verified 422/allowlist 403/同 email 幂等/同名本地账号 409 不合并 + 角色 viewer 一次性定重登不提升）✓、env 未配置整体 404 ✓（test_oidc.py 5 项本地 RSA 桩离线覆盖全协议路径 + 拒绝矩阵七例 + 拒绝路径零建号）；**I54** `/api/auth/oidc/status` 特性探针（secret 不回显）✓、登录页 SSO 按钮（未配置不显示）✓、本体页 OIDC 诊断面板 ✓、M8 门禁对 JIT 用户生效（非成员写 403 单测）✓；**I55** `tools/keycloak/`（compose + realm import：client/用户/组）与 `tools/oidc_stub.py` mini IdP 在位 ✓、docs/11 §2.1 与 docs/12 §14 在位 ✓、**冒烟 23 全程**（关闭零破坏/桩协议/JIT 幂等/门禁）✓。浏览器隔离复演（隔离 data+ontologies + network 模式 + 桩真流程）：登录页 SSO 按钮 → 桩 authorize → callback → 会话（me=`u_oidc_*`/zhang.demo/session）→ 顶栏 chip → 越权写 403 → OIDC 面板（截图 docs/m17-i54-*.png ×3）。无新增 B/C 级意见。 | — | 里程碑通过 |
| 2026-09-04 | M18 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `61b8afd` 重跑 pytest **161** 项 0 失败 + 冒烟 **24** 条 GREEN + vitest 2 项/build 绿）：**I56** 评论域（comment.* 软删 + rebuild 存活 / @mention 对 users.name 最长精确匹配作者排除 / item_participants 参与投影 INSERT OR IGNORE / CRUD 权限矩阵 local 放行·network 成员读写·非成员 403·删除限 author·admin）✓（test_comments.py 单测）；**I57** 评论前端（@补全下拉 / 卡片 💬+评论数徽标 / `?item=` 直开 / mention 点击跳转且置已读 / 摘要带工作项标题，截图 docs/m18-i57-*.png ×4）✓；**I58** 订阅（item.subscribed/unsubscribed 退订仅删 watch 行、派生参与不受影响、rebuild 幂等）✓、参与者通知最小面（comment.created 排除作者与被提及防双发 / item.status_changed 排除操作者 / NOTIFY_EVENTS 同步邮件通道一致）✓、docs/12 §15 在位 ✓、**冒烟 24 全程**（CRUD 软删→mention 通知+深链→参与集合首次来源胜出→订阅→后续事件通知参与者→退订降噪→rebuild 三投影一致）✓。浏览器隔离复演（隔离 data+ontologies + 生产构建 + 端口单监听确认）：李雷开抽屉→「🔕 订阅」→「🔔 已订阅」→ @补全发评论 → 切 QA 王 mention 通知 → 点击跳转 Modal 自动开 → QA 王改状态 → 李雷收参与者通知「状态变更为 in_progress」（截图 docs/m18-review-*.png ×6）。**审阅即修 1 个 A 级后端缺陷**：`change_status` 默认参数 actor_id 硬编码 "u_admin"——PATCH 状态变更审计归因全错（任何身份改状态都记李雷名下）且参与者通知的操作者排除失效（复演中 qa 改状态事件归因 u_admin 当场暴露）；改 `actor_id or events.effective_actor()` + PATCH 调用点显式传身份 + 回归单测 test_status_change_attributes_real_actor（M5-I19「全仓清除 actor 硬编码」的漏网之鱼，签名默认值形式存活）。 | — | 里程碑通过 |
| 2026-09-04 | M19 正式审阅 | 各迭代 DoD 核对（审阅时点 HEAD `cc2af95` 重跑 pytest **167** 项 0 失败 + 冒烟 **25** 条 GREEN + vitest 2 项/build 绿）：**I59** 工时数据层（item_time_entries 投影软删 + rebuild 存活 / 校验 fail-closed：minutes∈(0,1440]·spent_on ISO·note 截 500·空更新 422 / spent_minutes 汇总进详情与列表 / 权限对齐 M8 改删限本人·admin / 记工时者参与投影 source='time'）✓（test_timelog.py 单测）；**I60** 工时前端（⏱ 抽屉：条目列表+表单+合计行 / 卡片 ⏱ spent 徽标仅 >0 显示 / docs/12 §16 / **冒烟 25 全程**：双身份记时→四处合计一致→校验门→软删→rebuild 复现，截图 docs/m19-i60-*.png ×4）✓；**I61** 项目工时报表（timelog_report 按人/按日聚合 + ReportsPage 小部件 + MyWork 本周合计 + **对账单测**：报表聚合与条目清单逐项相等——Plane GH #8045 项目级聚合缺口的正面实现，截图 docs/m19-i61-*.png ×3）✓。浏览器隔离复演（隔离 data+ontologies + 生产构建 + 端口单监听）：李雷 ⏱ 记 90m→徽标上卡→QA 王 45m→合计 2h15→报表小部件按人/按日一致→本周工时 chip。无新增 B/C 级意见。 | — | 里程碑通过 |

## 附录 C · Backlog（C 级意见与 V1.x 候选）

对齐 07 §5 扩展路线：V1.1 多人协作与上下文完善 / V1.2 会话深化 + QA 域 + 本体资产编辑 / V1.3 可观测与语义检索 / V2 规则引擎 + 沙箱 + 资产治理 / V3 规模化与生态。审阅中的 C 级意见在此登记，MVP 结束后统一排期。

M4 审阅登记（2026-09-02）：本体学习/版本面板的 apply 权限分层与审批挂接（单用户 MVP 无影响；V2 治理范畴）。
