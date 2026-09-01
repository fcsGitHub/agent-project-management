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

## 附录 B · 审阅记录（逐次追加）

| 日期 | 迭代/里程碑 | 意见 | 级 | 处置与落点 |
| --- | --- | --- | --- | --- |
| 2026-09-02 | M4 正式审阅 | 08 §8.3 验收锚点逐项核对：① 四类信号（L1 priority×12 / L2 遗留关系 / L3 沉淀链接 / L4 角色覆盖）learn 全命中且 provenance 可溯 ✓；② apply 后校验通过、version 递增、事件流含 ontology.updated（含 diff 摘要）✓；③ L2 场景 apply 后同型关系通过建卡 API 校验 ✓；④ 重复 learn 幂等（已应用候选不再出现）✓。浏览器演示路径实测通过（截图 docs/m4-review-ontology-page.png）。 | — | 里程碑通过 |
| 2026-09-02 | M4 正式审阅 | CQ 证据行的 events 源是全局计数（不按项目过滤），多项目同本体时口径偏大 | B | 排入后续迭代任务清单（可在 evidence 的 events 源加 project_id 过滤；不影响单项目正确性） |
| 2026-09-02 | M4 正式审阅 | 本体学习/版本面板未做权限分层（单用户 MVP 无影响，多租户时 apply 应挂审批） | B | 入附录 C backlog（对齐 07 §5 V2 治理） |

## 附录 C · Backlog（C 级意见与 V1.x 候选）

对齐 07 §5 扩展路线：V1.1 多人协作与上下文完善 / V1.2 会话深化 + QA 域 + 本体资产编辑 / V1.3 可观测与语义检索 / V2 规则引擎 + 沙箱 + 资产治理 / V3 规模化与生态。审阅中的 C 级意见在此登记，MVP 结束后统一排期。

M4 审阅登记（2026-09-02）：本体学习/版本面板的 apply 权限分层与审批挂接（单用户 MVP 无影响；V2 治理范畴）。
