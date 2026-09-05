# 01 · GitHub 开源调研报告

> 调研时间：2026-08（v0.2 增补 C 部分）。目的：为 AgentPM 寻找可借鉴的设计经验与可直接复用的组件。分五部分：A. Agent/多智能体框架；B. 开源项目管理工具；C. 真实可用的 Agent 产品与语义层（评审补充）；D. 轨迹观测与人机审批生态；E. 可复用组件清单。

## A. Agent / 多智能体框架

| 项目 | Star 量级 | 许可/活跃度 | 核心设计 | 对本项目的价值 |
| --- | --- | --- | --- | --- |
| **MetaGPT** | ~70k | MIT，主仓放缓（重心转 MGX） | `Code = SOP(Team)`：角色链 Boss→PM→架构师→项目经理→工程师→QA；一行需求产出 用户故事→竞品分析→PRD→API 设计→任务分解→代码→测试；工件以 Markdown 落盘 `workspace/<project>/` | ★★★ 阶段化流水线 + 工件契约直接对应本项目生命周期建模 |
| **ChatDev** | ~34k | Apache-2.0，活跃（2.0 已发布） | ChatChain 范式：Chain→Phase→Role 三级；产物存 `WareHouse/` 带 Git 版本史；2.0 转向 YAML+可视化画布定义 agent/workflow | ★★ YAML 声明式流程 schema；`--config Human` 评审者模式 |
| **OpenHands** | ~85k | MIT，极活跃 | software-agent-sdk 五抽象（LLM/Agent/Tool/Conversation/AgentContext）；**事件溯源状态模型 + 确定性重放**；Agent Server 以 REST 跑多 agent，Docker 沙箱 | ★★★ 事件-动作-观察三元组 schema；安全确认策略 |
| **CrewAI** | ~57k | MIT，很活跃 | Crews（角色化团队，sequential/hierarchical）+ Flows（`@start/@listen/@router` 事件驱动）；Task 声明 `expected_output`/`output_pydantic` 结构化工件；checkpoint+replay | ★★ 结构化产出契约；agents.yaml/tasks.yaml 脚手架 |
| **AutoGen/AG2** | ~40k+5k | Apache-2.0 | 对话编程 + GroupChat；`human_input_mode`（ALWAYS/TERMINATE/NEVER）；AG2 v1.0：**write-ahead log 与审计轨迹**、typed channels、`hitl_hook` 跨 CLI/WebUI 暂停恢复 | ★★ HITL 三档模式；WAL 思想 |
| **LangGraph** | ~40k | MIT，活跃 | 低层级图编排（Pregel 风格状态图）；**interrupt() 挂起 → 人工审/改 state → Command(resume/update) 续跑**；checkpointer（SQLite/Postgres）+ time travel 回溯重放 | ★★★ 本项目 Agent 运行时的直接选型 |
| **AgentScope** | ~29k | Apache-2.0，活跃 | 2.0 事件总线实时流式；Agent Team leader-worker；**工具/资源粒度权限确认 + bypass 直通**；SQL/NoSQL 持久化、长任务后台 offload | ★★ 权限分级模型；沙箱 Workspace |

**A 部分结论——借鉴 Top 10：**

1. SOP 先行、阶段化流水线，每阶段固定角色与产出契约（MetaGPT）；
2. 工件即文件：Markdown 落盘、Git 版本化，人机同读（MetaGPT/ChatDev）；
3. interrupt + resume 的 HITL 原语，阶段边界挂起、人工编辑后恢复（LangGraph）；
4. 检查点与 time travel：按 thread 快照、可回滚重放历史状态（LangGraph）；
5. 事件溯源 + 确定性重放：状态由 append-only 日志推导，Agent 循环无状态（OpenHands）；
6. write-ahead log + 审计轨迹（AG2 v1.0）；
7. 任务级结构化产出契约 `expected_output` + schema（CrewAI）；
8. 声明式 YAML 定义角色与流程，非程序员可编排（ChatDev 2.0/CrewAI）；
9. 工具粒度权限 + 危险度分级审批 + bypass 模式（AgentScope/AG2）；
10. 沙箱化执行：Docker/K8s 隔离 Agent 的文件与命令（OpenHands）。

## B. 开源项目管理工具

| 工具 | Star | 核心概念模型 | UI/方法论亮点 |
| --- | --- | --- | --- |
| **Plane** | ~57k | Workspace→Project→Work Item；工作项可同时归入 **Cycle（时间盒）与 Module（内容模块，正交）** | 状态五桶 backlog/unstarted/started/completed/cancelled，组内自定义；列表/看板/甘特/日历/表格多视图；命令面板+快捷键；REST 全覆盖+Webhook+Automations |
| **Huly** | ~27k | Project→Category→Issue，项目自定义 Issue Type 与流程 | All-in-one（Tracker+Wiki+Chat+时间追踪）；GitHub Issues 双向同步 |
| **Focalboard** | ~26k（停维护） | Notion 式 Block 统一数据模型 | 看板/表格/日历同源多视图 |
| **Taiga** | ~10k | **Epic→User Story→Task + 独立 Issue** | Scrum 与 Kanban 模板项目内可互换；泳道 + WIP 限制；内置 Wiki |
| **OpenProject** | ~16k | **统一 Work Package**：类型（Epic/Story/Task/Bug/Phase/Milestone）可配置 | 状态绑定"按类型的工作流 + 角色权限"；关系枚举 relates/blocks/blocked/precedes；甘特为主打 |
| **Leantime** | ~11k | Goal→Milestone→Task（无限子任务+依赖） | 面向非项目经理；Idea 看板、Lean 画布、回顾；无障碍设计 |
| **Kanboard** | ~10k | Project→Column/Swimlane→Task→Subtask | **自动化三段式：触发器+条件+动作**；泳道第二维度、列 WIP 限制 |
| **AppFlowy** | ~76k | Page/Database 多视图 + AI | local-first（Flutter+Rust） |

**B 部分结论——借鉴 Top 10：**

1. 状态五桶分组 + 组内无限自定义状态，统计与看板按组渲染（Plane）；
2. 时间维度与内容维度正交归组，一物多归 + 可保存分享的视图（Plane）；
3. 统一"工作项"+ 可配置类型/工作流，一套实体支撑多方法论（OpenProject）；
4. Epic→Story→Task→Subtask 分层 + 独立缺陷项（Taiga）；
5. 关系类型枚举 blocks/blocked_by/relates/precedes，与依赖图联动（OpenProject）;
6. 看板泳道 + 列 WIP 限制暴露瓶颈（Taiga/Kanboard）；
7. 自动化规则三段式（触发+条件+动作），表达力强且实现简单（Kanboard）；
8. 同一数据多视图低成本切换（Plane/Leantime）；
9. 渐进披露：新手看目标导向简洁视图，高级功能收进命令面板/快捷键（Leantime/Plane）；
10. API 即产品：REST 覆盖全部资源 + Webhook，自有前端与第三方共用（Plane/Taiga）。

## C. 真实可用的 Agent 产品与语义层（评审补充调研）

> 评审意见：A/B 两部分偏"框架"，缺少**真实可日常使用**的 agent 产品参考。补充调研 DeepSeek Harness（dsh）、pi（极简运行时）与 semantica（本体/语义层）。

### C.1 DeepSeek Harness（dsh）——"Agent = Model + Harness，一切皆插件"

`deepseek-ai/deepseek-harness`，MIT，TypeScript/pnpm monorepo，`npx @deepseek-ai/dsh web` 一键启动本地 Web UI。核心设计：

| 维度 | 设计要点 | 对 AgentPM 的启示 |
| --- | --- | --- |
| 插件内核 | 基于 Cordis 插件框架：模型、工具、会话、沙箱、审批、UI 全部是可替换插件，**无特权内核**；组合分 bundle → profile → patch 三层声明式配置 | 系统模块（审批策略/持久化/压缩）设计为"能力缝"（capability seam），MVP 用默认实现、后续可换 |
| 会话持久化 | 内存 Session 即 **append-only SessionEvent 日志，唯一真源**；JSONL/SQLite 双后端；`SessionHeader`（fork 血统 parentSession/seedLength）与事件流分离；崩溃恢复用合成 `turn/end{interrupted}` 事件配平而非截断 | 与本方案事件溯源完全同构，直接吸收其工程细节：fork 血统、合成配平事件、头/流分离 |
| 轨迹可视化 | 原则 "Every run is traceable"：日志记录模型所见的一切（系统提示、推理、工具调用、上下文注入），Web UI 的 **Trajectory 视图可按来源检查**；恢复/分叉/搜索/重放共用同一事件流；live 与 replay 用同一投影函数 | 轨迹页 = 事件流的一个投影；"live 即 replay" 保证实时视图与历史回放渲染一致 |
| 上下文压缩 | compaction 是**可选能力缝**而非主干：`start/summary/end` 三事件锁 + 摘要以 `surfaceOp:replace` 生效，防止"假完成" | 长对话压缩采用三事件锁模式，压缩事件本身入轨迹 |
| 审批 | `allowed-once / rejected / cancelled`，**fail-closed**；按会话策略 ask/never；审批 asked/decided 均写入会话日志 | 审批粒度"单次授权"+fail-closed+审计入流，采纳进 05 文档 |
| 模式预设 | Standard / Code（模型写程序编排）/ Minimal（两工具基准）/ Creator（自定义 preset） | 项目模板 = preset 思路；轻量/完整模板对应 Minimal/Standard |

### C.2 pi（badlogic 极简 coding agent）——"不需要的就不造"

`earendil-works/pi`（原 badlogic/pi-mono，pi.dev）。极简分层：pi-ai（LLM 客户端，仅抽象 4 种协议）→ pi-agent-core（**约 418 行的 agent loop**）→ pi-tui → pi-coding-agent（CLI 壳）。默认仅 4 个工具（read/write/edit/bash），系统提示+工具定义合计 **<1000 token**。

- **会话即 JSONL 树**：每条消息含 id/parentId，单文件内天然支持分支；`/fork`、`/tree` 任意点跳转；自动压缩有损但 JSONL 保留全史；
- **扩展机制**：TypeScript Extensions（registerTool/registerCommand/替换内置工具/UI widget）+ Skills 标准 + npm 分发；
- **哲学**：拒绝 MCP（上下文开销 7-9%）、拒绝内置子 agent/plan mode/todo（用"自己+tmux"、PLAN.md、TODO.md 文件替代）。

对 AgentPM：**最小内核 + 一切可替换**是 MVP 的纪律标尺——每个候选特性先问"pi 会怎么做"（能不能用一个文件/一个简单机制替代）；会话树（id/parentId）直接采纳为对话分支的数据结构。

### C.3 semantica——图原生语义层（本体模块参考）

`semantica-agi/semantica`（MIT，~10k star）："开源版 Palantir for AI Agents"，位于 LLM/向量库/agent 框架**之下的语义层**。核心实体：Entity / Relation / **Fact（双时态）** / Decision（因果仅限 CAUSED/INFLUENCED/PRECEDENT_FOR 三种受控枚举）/ Provenance（W3C PROV-O）；本体可从数据推断类型（OWL Class 层级），VersionManager 提供 create_version/diff/migrate，Knowledge Explorer（Sigma.js）做图谱浏览与 Ontology Hub 编辑。

**吸收（简化后）**：① Competency Questions（能力问题）驱动设计——项目模板先回答"要回答哪些管理问题"；② 关系类型受控枚举，防关系爆炸；③ 本体即数据 + 版本化/diff；④ Ontology Hub 式浏览编辑 UI 的简化版。
**砍掉**：RDF/OWL/SPARQL/推理机全家桶（JSON Schema 足够）、双时态与 PROV-O（事件溯源已覆盖）、多存储后端、LLM 自动生成本体（项目域概念少，手写模板更可控）。落地设计见 `08-ontology.md`。

#### C.3.1 v0.6.7 补充调研（2026-09-02，M5 前置调研：LLM 辅助归纳）

semantica 的 Semantic Extraction 模块给出一条**方法链**（fallback chain）：`pattern/regex`（<5ms，固定格式）→ `rules`（语言规则）→ `ml/spacy`（NER 模型）→ `huggingface`（领域模型）→ `llm`（1-10s，"对隐式实体与自定义标签 schema 召回率最高"），方法返回空自动降级，推荐默认 `["llm", "ml", "pattern"]`。流水线五步：NER → Relations（复用 NER 输出、每条关系带 context 句子供审计）→ Events → **Coreference（先共指消解再抽关系，否则产生重复节点）** → Triplets（`validate_triplets` → 序列化 RDF）。配套纪律：置信度阈值 0.65–0.85、结构化标识符用 regex 而非 LLM、每实体 provenance 链回源文档（ProvenanceManager）。

**对本项目的启示（M5-I17 采纳）**：① 本项目已有的确定性学习规则（08 §8.2 L1–L4）恰好等价于链中的 **pattern 层**——LLM 通道不是替代而是链的顶层，两者产出汇入同一人审通道；② LLM 候选必须带 confidence 并设展示阈值（0.65）；③ LLM 候选的 provenance 链回来源工件（path+commit）；④ 候选去重（与规则候选 id 冲突时合并而非重复提出）。仍然不做：NER 模型层、RDF 序列化、共指消解（结构化投影数据天然无共指问题）。

### D. 类型系统与自定义字段（2026-09-02，M6 前置调研）

#### D.1 OpenProject——自定义字段与双层激活

字段格式：Boolean / Date / Float / Integer / Link / List / Text / Long text / **User / Version**（后两者把"人"与"版本"当一等字段）；Hierarchy 与加权列表为企业版。关键机制：**双层激活**——字段必须①加入工作包类型（表单配置）**且**②在项目中激活才可见（15.0 起加字段不再自动全项目生效）；字段可标记"可用作过滤器/全局可搜索"；List/User/Version/Hierarchy 支持多选；除 Boolean 外均可标必填（16.6 起必填只在 UI 展示该字段时强校验，不阻塞遗留数据编辑）。

#### D.2 Plane——工作项类型与六种属性

Work Item Types：**六种属性类型**（Text / Number / Dropdown 单选多选 / Boolean / Date / **Member picker**），每类型可无限组合；类型定义在工作区级，项目级为 Pro 功能；看板/列表可**按自定义属性分组与排序**；多版本字段 behaves like 内建属性。

#### D.3 LangGraph 版本评估（2026-09-02）

安装 1.0.9（+langchain-core 1.2.16），PyPI 最新 **1.2.11**——同一 1.x 大版本线的次版本演进，无破坏性大版本跨越。结论：**可升、非急需**。收益为修复与新原语；风险集中在锁定的 `SqliteSaver` checkpoint 兼容与 `interrupt` 恢复语义（Runtime 主路径）。处置：M6 内做一次独立升级验证迭代（升 → 全量测试/冒烟/浏览器打断-恢复演示，红则回退 pin 1.0.9 并记录），不与其他改动混车。

#### D.4 对本项目的启示（M6 采纳）

① **字段类型补齐**：本项目本体字段目前 string/enum/number/date/ref 四类——补 **boolean 与 multiselect**（两家的共同交集），member picker 已由 ref→users 覆盖；② **自定义字段值落地**：本体已声明字段但工作项**无处存值**（priority/estimate_hours 是内建列）——补 `items.custom_fields`（JSON）+ 按本体校验 + 过滤，这是 D.1/D.2 的核心价值；③ **按字段分组看板**（Plane）：I21 看板分组维度支持自定义字段；④ 双层激活（OpenProject）暂缓——需要项目级本体覆盖机制，V1.x 再评估。

**C 部分结论——补充借鉴 Top 6：**

1. 会话 = append-only 事件日志（唯一真源），fork/血统/回放/搜索全部免费获得（dsh）；
2. live 与 replay 共用同一投影函数，实时视图即历史回放（dsh）；
3. 审批 fail-closed + 单次授权 + 审计入流（dsh）；
4. 压缩/审批/持久化等做成"能力缝"，内核只留 agent loop（dsh/pi）；
5. 会话内树状分支：消息 id/parentId 单文件即可 fork（pi）；
6. 极简标尺：<1000 token 系统提示、4 个默认工具起步，按需加（pi）。

## D. 轨迹观测与人机审批生态

**通用轨迹数据模型**（Langfuse data-model / OpenInference 规范，二者高度趋同）：

- `trace`（一次端到端运行）→ 嵌套 `span` 树，span 类型含 agent/tool/chain/generation/event；
- 每 span 记录：input/output、起止时间、model、token usage、cost、level(error)、parentId、metadata、sessionId；
- Agent-as-judge 类工作用「思考→行动→观察」交替轨迹作为评审输入。

**可视化 UI 模式**：

- Langfuse：**左树 + 右甘特瀑布**混合；每步聚合延迟与费用并颜色编码瓶颈；父 span 延迟含子 span 需注明；error 标红；tool call 参数折叠；
- AgentOps：**session replay 时间旅行**：回放运行、逐步查看精确状态、费用/延迟分解。

**审计与安全**：

- 审批状态机统一为 `pending → in_review → approved / rejected`；批准、拒绝、auto-approve 全部写**不可变审计日志**（内容 diff、审批人、时间）；
- 权限：**deny-by-default**，只读/写/危险三级，任务级工具授权（Oso）；OpenHands confirmation policy 默认逐动作确认、可配 auto-approve。

**HITL 标准模式**：

- LangGraph：`interrupt()` → checkpointer 持久化 → 人审 → `Command(resume=value)` / `Command(update=...)` 改态恢复；interrupt-id→值 的 resume map 支持批量审批；
- AutoGen：`human_input_mode` ALWAYS/TERMINATE/NEVER 三档。

**OTel GenAI semconv**（可复用 schema）：`gen_ai.operation.name`（invoke_agent/execute_tool/chat…）、`gen_ai.request.model`、`gen_ai.usage.input_tokens/output_tokens`、`gen_ai.tool.name`、`gen_ai.agent.name`、`gen_ai.input/output.messages`。

## E. 可直接复用的组件

| 组件 | 用途 | 引入时机 |
| --- | --- | --- |
| LangGraph（含 checkpointer） | Agent 运行时：图执行、interrupt、恢复、time travel | MVP |
| dsh 会话日志工程细节 | fork 血统（parentSession/seedLength）、崩溃合成事件配平、压缩三事件锁、live/replay 同投影 | MVP（设计采纳） |
| pi 的会话树格式 | 消息 id/parentId 树状分支，单文件 fork | MVP（对话分支数据结构） |
| OTel SDK + GenAI semconv | 轨迹埋点标准 schema | MVP（埋点）→ V2（导出） |
| 自托管 Langfuse（MIT） | 高级轨迹分析 UI | V2 扩展，MVP 用内置轻量轨迹页 |
| OpenHands 事件 schema 思想 | Action/Execution/Observation 事件类型设计参考 | MVP（参考设计） |
| CrewAI YAML 脚手架思想 | 角色声明文件格式 | MVP |
| semantica 设计思想 | Competency Questions、受控关系枚举、本体版本化 diff | MVP（双内置本体）→ V2（自定义） |
| AppFlowy Page/Database 多视图 | 资产库 UI 参考：卡片/表格同源多视图 + 模板 | MVP（资产页） |
| dsh `session_query` 思想 | Agent 检索历史沉淀物（本项目升级为治理过的资产检索，09 §4） | MVP（search_assets 工具） |
| Kanboard 三段式规则 | 自动化规则引擎 | V2 |
| React Flow | 前端图可视化/图编辑 | MVP |
| **shadcn/ui + Radix + lucide + cmdk + Sonner** | 前端组件体系/图标/命令面板/通知，视觉对标 Linear/Plane/Huly（v0.3 Demo 已按其语言绘制，清单见 07 §2.5） | MVP |

## F. M7 前置调研：模板市场 / 项目级字段激活 / 多人认证（2026-09-03）

> 目标第 5 条触发：M6 审阅通过后开启新一轮调研。三个候选方向的开源做法与取舍如下。

**F.1 OpenProject 双层字段激活（候选③，补 §D.4 遗留）**

- 官方文档确认其自定义字段可见需**同时满足两条件**：类型级激活（Administration → Work Packages → Types → 表单配置里勾选字段）+ 项目级启用（Project settings → Work packages 里启用）。字段全局注册、按「类型 × 项目」双向作用域。
- 对本项目的映射：本体即类型系统，字段已按概念声明作用域；缺的是**项目级激活层**——项目可停用本体已声明字段（停用后建卡校验拒绝该字段、看板分组候选不再出现），而无需改动本体源文件。
- 采纳：项目级字段开关走**事件投影**（`project.field_disabled/enabled` → projects 投影扩展），默认全激活；校验器与看板分组候选读取投影。**不做**文件级本体覆盖（M4 审阅事故教训：覆盖写会污染源文件；投影化才可 rebuild、可审计）。

**F.2 n8n 模板市场模式（候选②）**

- n8n 模板生态三件套：① **JSON 即模板**（workflow 导出/导入，社区 GitHub 仓库以 JSON 文件分发）；② **中心模板库**（n8n.io/workflows，上万模板、分类与创作者档案；创作者计划要求先发布 3 个免费模板才能卖——社区对此摩擦不小）；③ **自托管自定义模板库**（self-hosted 实例可把模板源指向内部 URL）。
- 对本项目的映射：I18 模板包（单 JSON=本体+角色+提示词）已等价「JSON 即模板」；`ontology.imported` 事件已在审计流；缺的是**注册表与浏览层**。内置模板（ontologies/ 目录）与已导入包统一成模板库 API；建项目 API 本就支持指定 ontology，一键建项目天然承接。
- 采纳：模板中心 = 注册表投影 + 浏览/预览 API + 前端页；**不做**销售/分成（内部库优先，n8n 创作者计划的摩擦是反例）。

**F.3 Plane / Focalboard 多人认证（候选①）**

- Plane：Instance → Workspaces → Projects 三层；邀请两层（先 workspace 成员后 project 成员）；角色 Admin/Member/Guest；自托管支持 SSO（OIDC/SAML/LDAP）+ IdP 组同步。工程量 = 密码哈希/会话/邀请流/角色权限四位一体。
- Focalboard：首个注册用户即管理员、看板 Share 生成一次性 token 注册链接；但 2023 年起仅社区维护，邀请链接失效类 issue 多发——警示一次性链接的健壮性设计。
- 结论：**认证整体推迟到 M8+**。理由：① 单机场景下 I19 身份切换已覆盖审计与指派；② 密码/会话/邀请是横切改造（middleware、全部路由、前端 session），要做就一次做对，不宜与功能迭代混车；③ 模板市场与字段激活不依赖认证。M8 设计时按 Plane 两层成员模型（全局用户 → 项目成员）裁剪，SSO 列 V3。

**F.4 M7 取舍**

M7 = **模板中心 + 项目级字段激活**（I23-I25）：继续本体线，全部复用既有资产（I18 模板包、I12 资产域、I20-I21 字段与分组）；多人网络认证列 M8（先做部署形态决策：单机 vs 网络服务）。

## G. M8 前置调研：多人网络认证与部署形态（2026-09-03）

> 目标第 5 条触发：M7 审阅通过后开启。首选方向 = 多人网络认证；部署形态先决策。

**G.1 Plane：两层角色模型（裁剪底稿）**

- 每个用户在 **workspace 级**持有一个角色，在其加入的**每个项目级**另持有一个角色——两层独立；Workspace Owner/Admin 对所有项目自动拥有完全访问（无需显式加入）；公开项目对所有 workspace 成员可见，**Guest 例外**（未被邀请不能进公开项目）；权限矩阵按「层级 × 角色」二维展开。
- 对本项目的映射：**砍掉 workspace 层**（AgentPM 项目即顶层，全局用户池等价单 workspace），保留项目级 owner / contributor / viewer 三角色（对应 Plane Admin/Member→Contributor/Guest 裁剪）；无 workspace 管理员的「自动加入」语义——需要时用「项目创建者即 owner」表达。

**G.2 Gitea：首管理员与账号供给模式（引导底稿）**

- 安装向导完成 → 首个注册用户自动成为管理员（另有 CLI `gitea admin user create` 兜底）→ 之后 `DISABLE_REGISTRATION` 关闭开放注册，**仅管理员建号**；协作者不走邮件邀请——先有账号，再由管理员/仓库主在 Settings→Collaboration 添加（读/写/管理三级），API 同样提供。
- 对本项目的映射：首启引导（env `APM_ADMIN_PASSWORD` 或首访设置页）产出一个管理员；**默认关闭开放注册**，账号由管理员创建——与 I19 已有的 users 注册表天然衔接；**不做邮件邀请链接**（Focalboard 一次性链接失效 issue 多发是前车之鉴，且省掉 SMTP 依赖）。

**G.3 认证机制取舍**

- 密码哈希用标准库 `hashlib.pbkdf2_hmac`（不新增依赖，够用）；会话 = 服务端签名 HttpOnly Cookie（settings 密钥，重启可存活），会话事件（logged_in/failed/logout）进审计流——与事件溯源原则一致。
- 部署形态决策：**走「可信小团队网络服务」**（docker-compose + 反代 HTTPS 已具备），不做多租户 SaaS；`settings.auth_mode`：`local`（默认，现状单机免登录，开发/演示不受影响）/ `network`（登录强制 + 项目级鉴权）。SSO/LDAP/OAuth2 明确推迟 V3。
- I28 收尾要点：本地「身份切换」菜单在网络模式降级为登录态展示（切换身份 = 登出再登录），审批/审计强制登录人，越权 403 有事件。

**G.4 M8 取舍**

M8 = **多人网络协作（认证 + 项目成员角色）**，I26 认证基座 / I27 项目成员与角色 / I28 网络协作收尾，约 9 人日。看板自动化规则（Kanboard 三段式）继续留在 backlog。

## H. M9 前置调研：看板自动化规则（2026-09-03）

> 目标第 5 条触发：M8 审阅通过后开启。首选方向 = 看板自动化规则（HANDOFF 候选清单首位）；SSO/OIDC 维持 V3 推迟，本体版本事件级归档留 backlog。

**H.1 Kanboard Automatic Actions：项目级「事件×动作」绑定（主借鉴）**

- 每条自动动作由两个属性定义：**监听的事件**（trigger）+ **绑定到该事件的动作**（action，带用户自定义参数）；**每个项目有自己的一组自动动作**（per-project 配置，非全局）。系统提供自省 API：列出可用动作、可用事件、以及「某动作兼容哪些事件」（动作声明兼容面，框架负责分发）。
- 架构 = 经典观察者模式：Event（任务移动/创建/评论/每日 cron）→ Listener/Dispatcher 匹配已注册绑定 → Action（改 assignee/颜色/分类/关闭等）→ Binding（项目级 action+event+参数三元组）。另有 webhook 出站（事件触发即 POST JSON 到预定义 URL）。
- 对本项目的映射：绑定模型直接采用（项目级规则 = trigger + action + 参数）；**dispatcher 不需要自建**——AgentPM 事件溯源内核本身就是全量事件源（event_bus 已在 emit 时发布 SSE），规则引擎订阅内核事件即可，比 Kanboard 改造成本更低。

**H.2 n8n / Node-RED：三段式是最小通用抽象（数据模型借鉴）**

- 两者共同抽象 = **trigger → (filter/condition) → action** 三段式；n8n 面向 API 业务编排与 AI agent，Node-RED 面向事件驱动/IoT 流；openHAB 社区直接把 Node-RED 当可视化 trigger/condition/action 规则引擎用。
- 结论：单机内嵌场景不需要引入编排器（依赖重、模型外置），**学其三段式数据模型即可**：在 Kanboard 的「事件×动作」二元绑定上加一层可选 condition（字段谓词），表达力大增而复杂度近常数。

**H.3 Plane / Taiga：PM 工具的自动化形态与教训**

- Plane：Project Settings → Automations → Create automation（**项目级**触发式自动化，与 Kanboard 同位）；Plane Runner 在 workspace 事件上跑脚本；webhook 出站。**教训**：其 webhook 有「一次状态变更触发 3 次调用」的重复事件 issue——规则执行必须幂等/去重。
- Taiga：只有出站 webhook，自动化完全外接 n8n——即「不内嵌规则引擎」的形态，验证了内嵌的价值主张。
- 归账衔接：AgentPM M8 已有 actor 归账与审计流，自动化动作应显式归账（actor_type=automation），人机审计流才能区分「谁改的」。

**H.4 M9 取舍**

M9 = **看板自动化规则（三段式）**：I29 规则域与事件订阅执行（规则本身事件溯源：automation.rule_created/updated/deleted，rebuild 存活；执行挂 event_bus 订阅，动作白名单 fail-closed，防循环：规则产出事件不触发规则引擎）/ I30 前端规则管理（项目设置页规则面板：选事件→条件→动作，测试运行）/ I31 收尾（审计归账 + 冒烟 15 + 文档 + 演示），约 9 人日。出站 webhook 留 backlog（先内嵌后外联）。

## I. M10 前置调研：出站集成——webhook 与通知（2026-09-03）

> 目标协议触发：M9 审阅通过后开启。工程管理落地标准的下一个缺口 = 与外部系统的集成出站（IM/CI/邮件靠 webhook；团队知情权靠通知）。

**I.1 Gitea/GitLab Webhook：签名与投递语义（主借鉴）**

- **HMAC-SHA256 签名是正路**：Gitea 用 `X-Gitea-Signature`（并兼容 GitHub 的 `X-Hub-Signature-256`）；GitLab 已把明文 `X-Gitlab-Token` 列为不推荐的 legacy（其 issue #50745/#37380 记录了从明文比较到 HMAC 摘要的演进）。要点：**对原始请求体字节做 HMAC**（JSON 重序列化会破坏签名）、接收方常量时间比较。
- **投递语义**：`X-Gitea-Event`（事件类型）与 `X-Gitea-Delivery`（投递 ID）头支撑接收方过滤与幂等去重；真实世界的坑（Gitea 修复记录）：先取原始 payload 再算 HMAC、secret trim、验证失败要返回真实错误。
- 对本项目的映射：出站 webhook 项目级配置（URL/secret/事件订阅/启停）；投递带 `X-APM-Event`/`X-APM-Delivery` + `X-APM-Signature`（HMAC-SHA256）；投递结果（delivered/failed）落事件流，失败指数退避重试 + 手动重发。

**I.2 Redmine：通知是自托管 PM 的桌上前提**

- Redmine 的立身之本之一 = 内置邮件通知 + RSS/Atom feeds；per-project 通知粒度是十余年的 feature request（#7349），第三方插件（Redmineflux）补规则化告警——说明**「规则化通知」是真实需求**。
- Plane 等新世代工具同样把通知中心（铃铛 + 未读数）作为标配。
- 对本项目的映射：站内通知中心（顶栏铃铛：指派/审批请求/规则触发/超期）无 SMTP 依赖（M8 明确不引 SMTP），先行落地；自动化动作白名单增 `notify` 把 M9 的规则引擎与通知打通——邮件/RSS 留 backlog（有真实部署需求再加）。

**I.3 M10 取舍**

M10 = **出站集成：webhook 与通知**：I32 webhook 基座（规则即事件溯源 + 投递器后台线程化——**post-emit hook 只入队不阻塞写路径**，与 M9 的同步执行器本质差异）+ HMAC 签名 + 重试与投递留痕 / I33 webhook 前端（配置面板 + 投递历史 + 手动重发 + 测试 ping）+ 冒烟 16 / I34 站内通知中心 + automation `notify` 动作 + 收尾审阅，约 9 人日。邮件/RSS、SSO/OIDC、本体版本事件级归档、移动端适配留 backlog。

## J. M11 前置调研：邮件通知与 Atom 订阅（2026-09-03）

> 目标协议触发：M10 审阅通过后开启。出站集成的「机器通道」（webhook）已通，本轮补「人的通道」（邮件 + 订阅 feed）。本体版本事件级归档搜索超时、且属内部治理价值，继续留 backlog；SSO 维持 V3。

**J.1 Redmine 邮件通知：即时为纲、SMTP 可选配置（主借鉴）**

- Redmine 内建**只有即时（事件触发）邮件**，无 digest 模式——要 digest 得外挂工具。教训即取舍：AgentPM 邮件同样**只做即时**（M10 通知中心的每个通知即一封候选邮件），digest 复杂度不引入。
- SMTP 配置是环境变量/配置文件层（`configuration.yml` 按环境分 production/development），支持 SSL 465 / STARTTLS / 认证；自托管推荐外部 relay（Mailgun/SendGrid）提升可靠性。
- 对本项目的映射：`APM_SMTP_HOST/PORT/USER/PASS/FROM/TLS` 环境变量**可选**配置——未配置则邮件通道整体静默关闭（保持 docker-compose 零依赖哲学，M8 不引 SMTP 的决策不反转）；配了即启用。投递复用 M10 的「队列 + 后台线程」模式（网络 I/O 不阻塞写路径），`email.notified` 事件留痕（收件人/主题/结果）。users.email 字段自 I19 就存在，正好补上用途。

**J.2 Redmine Atom feeds：feed key 认证与权限前车之鉴**

- Redmine 的 activity/issue feed 均走 **Atom + per-user key 认证**（`/issues.atom?key=ID`），让阅读器无需 cookie 即可订阅；feed 内容只含人类可读事件（issue #6885 明确其机器可读性受限）。
- **前车之鉴**：issue #20173 私有项目数据曾泄漏进全局 RSS——feed 权限过滤必须按 key 所属用户的可见性裁剪。
- 对本项目的映射：`GET /projects/{id}/feed.atom`（事件流的标准化 Atom 视图）+ per-user feed key（运行态生成/rotate，同 webhook secret 的展示一次语义）；**权限过滤**：只输出该 key 用户为成员的项目事件；Atom 而非 RSS（现代阅读器均支持，Redmine #1521 的兼容请求不再必要）。

**J.3 M11 取舍**

M11 = **邮件通知与 Atom 订阅**：I35 邮件通道（SMTP env 可选 + 队列投递 + email.notified 留痕 + 未配置静默关闭）/ I36 Atom 订阅 feed（feed key + 权限裁剪 + 冒烟 17）/ I37 通知偏好前端与收尾审阅，约 9 人日。digest、RSS 1.0 兼容、SSO/OIDC、本体版本事件级归档、移动端适配继续留 backlog。

## K. M12 前置调研：报表与跨项目工作台（2026-09-04）

> 目标协议触发：M11 审阅通过后开启。候选四项（报表增强 / SSO / 事件归档 / 移动端），调研后选定**报表与跨项目工作台**——对「工程管理落地标准」最直接的缺口是管理者可见性（项目健康、瓶颈、跨项目态势），且事件溯源架构做投影型报表零 ETL、与既有纪律完全同构。

**K.1 OpenProject 报表分层：社区版 = custom query + widget，企业版才有报表模块（主借鉴）**

- OpenProject 的报表能力分三层：① **custom query**（工作包表的可保存过滤/分组/排序视图）作为轻量"workaround-dashboards"；② **项目首页 widget**（工作包表、成员、新闻、日历等挂件）+ **My page** 个人工作台（"分配给我的工作包"等）；③ **高级自定义报表/仪表盘模块**——企业版专属。跨项目工作包列表同样支持过滤/分组/保存。
- 官方明确把"可保存的查询视图"当作报表的第一形态，仪表盘是 widget 的拼装而非独立报表引擎。
- 对本项目的映射：AgentPM 不需要报表引擎——**事件流 + 投影器就是现成的报表数据层**（rebuild 一致性已有冒烟兜底）：`GET /reports/...` 纯投影查询（阶段漏斗计数、Gate 挂起、超期清单、吞吐趋势、跨项目"我的工作"），前端报表页 = widget 式卡片拼装。企业级"高级自定义报表"不引入（YAGNI，backlog 记录）。

**K.2 SSO/OIDC：独立 IdP 是主流，维持 V3 推迟（M8 决策不反转）**

- 自托管 SSO 的主流模式：**独立身份源**（Keycloak/Authelia/Authentik/Kanidm）+ 各应用作为 OIDC client 接入；Gitea 也可反向作为 OAuth2 provider。
- 已知坑：Gitea 原生 OIDC 登录**只对已存在账号生效**、自动开户（JIT provisioning）受限，社区常与 LDAP/反代认证组合；"严格强制 SSO"需禁用本地密码登录，且要有本地 admin 兜底防锁死。
- 对本项目的映射（留给 V3）：`auth_mode=oidc` + JIT 开户（首次登录自动 user.registered）+ 保留 local admin 兜底账号；测试需引 IdP 容器（Keycloak/Automated-docker），横切改动大、演示成本高——工程管理落地标准的当前瓶颈不在认证方式，维持推迟。

**K.3 GitLab 审计事件：DB 永久保留 + 流式外送归档（backlog 依据）**

- GitLab 审计事件**在数据库中无限期保留**（无内建 retention/pruning）；长期归档的官方推荐是**流式外送**（HTTP 端点 / Google Cloud Logging → Datadog 等外部平台），事件类型可过滤；高级搜索建在其上。
- 对本项目的映射：AgentPM events 表同构（append-only、无限增长是事件溯源的本质而非缺陷）。「归档」的正确形态 = **导出/快照工具**（如 `events.export` 按 agg_type/时间窗出 NDJSON）而非删除——任何删除都会破坏 live==replay 不变量；M10 webhook 外送已具备"流式外送"雏形（订阅 webhook.* 即可接外部日志平台）。本体版本事件级归档继续 backlog。

**K.4 M12 取舍**

M12 = **报表与跨项目工作台**：I38 报表数据层（纯投影查询 API：项目健康摘要 + 跨项目「我的工作」+ 项目列表健康聚合）/ I39 报表前端与项目工作台（项目报表页：阶段漏斗 + Gate 挂起 + 超期清单 + 吞吐；项目列表健康徽标；全局「我的工作」入口）/ I40 收尾审阅（CSV 导出 + docs + 冒烟 18），约 9 人日。SSO/OIDC（V3）、事件导出归档、移动端适配、高级自定义报表留 backlog。

## L. M13 前置调研：里程碑与时间线（2026-09-04）

> 目标协议触发：M12 审阅通过后开启。三路调研（Gantt/时间线、里程碑与路线图、事件导出归档），选定**里程碑与时间线**——排程与里程碑跟踪是工程管理落地标准里「计划 vs 实际」维度的最后一块空白，且 AgentPM 本体已有 milestone 概念、items.milestone_id 列自 MVP 就闲置待用、内核固定关系含 depends_on——数据模型三要素齐备，缺的只是日期字段与视图。

**L.1 OpenProject Gantt：工作项类型 × 依赖 × 时间轴（主借鉴）**

- OpenProject 的 Gantt = 三类工作包（phase/milestone/task）在同一时间轴上排布，**依赖关系连线**（depends/blocks），拖拽改期；里程碑日期会随关联工作项变动（FAQ：要锁定里程碑日期须移除关系）——即「依赖传播」是其核心语义；13.3 起拆出独立 Gantt 模块。
- 社区版免费含 Gantt；条形颜色/分组按层级（project → phase → task）。
- 对本项目的映射：时间线页 = 概念行分组（从本体 stages/concepts 取行）× 日期轴；条形 = 有起止日期的工作项；菱形 = milestone 概念实例；**depends_on 关系画箭头**（内核既有关系类型，关系数据已存在 item_relations 表）——不做依赖自动传播改期（复杂度外推，backlog），只做可视化 + 冲突提示（后置项早于前置项完成日时标红）。

**L.2 Plane v1.16：Milestone = 按 deadline 聚合的路线图单元（佐证）**

- Plane 2025 年 v1.16 引入 **Milestones**（把 work items/modules/cycles 聚到一个 deadline 下，如「Q4 发布」「3 月 15 日 Beta」）与 Recurring Cycles（周期性 sprint 循环）；Cycles 是时间盒（sprint），Milestones 是日期锚点（deadline），二者正交。
- 对本项目的映射：不做 Cycles（无 sprint 文化假设）；Milestone = 事件溯源实体（`milestone.created/updated/deleted`，due_date 必填），工作项经 items.milestone_id 关联（列已存在，ALTER 迁移不需要）；里程碑进度 = 关联项 done 比例 + 逾期计数，复用 M12 报表口径。软件研发本体已声明 milestone 概念（planned/in_progress/achieved），无需本体变更。

**L.3 GitLab 导出/备份：NDJSON 导出仅作补充，备份走 DB 层（backlog 依据）**

- GitLab 官方明确警告**不要用项目导出文件做备份**（导出不完整、版本兼容窗口仅两个 minor 版本）；自托管实例的正解是 `gitlab-backup` rake + 数据库/对象存储级备份；API 导出（NDJSON）适合单项目自动化补充。
- 对本项目的映射：事件流导出 `GET /projects/{id}/events/export`（NDJSON，append-only 天然有序，含 prev_event_id 链校验）作**补充性数据出口**；真正备份 = SQLite 文件级（data_dir/apm.db + content/ 资产仓 + ontologies/），写成部署文档章节（docs/11 补充）而非新功能；不做导入（live==replay 保证重放即可重建投影）。

**L.4 M13 取舍**

M13 = **里程碑与时间线**：I41 里程碑域与工作项日期（milestone.* 事件溯源 + CRUD + items 加 start_date/due_date 列（ALTER 迁移）+ milestone 关联与进度；报表超期口径升级为 item.due_date 优先）/ I42 时间线视图（`#/p/{pid}/timeline`：概念分组行 × 日期轴、条形/菱形、depends_on 箭头与冲突标红、里程碑进度徽标）/ I43 收尾（事件 NDJSON 导出 + docs/11 备份章节 + docs/12 §10 + 冒烟 19 + 审阅），约 9 人日。依赖自动传播改期、Cycles/sprint、SSO、移动端留 backlog。


## M. M14 前置调研：排程自动化与事件可携（2026-09-04）

> 目标协议触发：M13 审阅通过后开启。三路调研（移动端/PWA、依赖传播排程、事件导入恢复），选定**排程自动化与事件可携**——「计划 vs 实际」的执行力缺口（依赖变化后手工改期繁琐易漏）与 M13 导出的恢复闭环（有出无进）。移动端 PWA（WeKan 路线）留下一轮候选。

**M.1 OpenProject 15.4 自动排程：默认手动 + 可选自动（主借鉴）**

- OpenProject 的 Gantt 有两种排程模式：**手动（默认）**——日期保持人工设置；**自动（15.4 新增）**——依赖前置变化时后继日期自动顺延（Finish-to-Start），且自动模式比关键路径引擎简单（无 SNET/SLT 任意约束类型，社区有相关讨论）。设计哲学：自动化是**可选项而非默认**，避免「日期被系统悄悄改掉」的失控感。
- 对本项目的映射：items 加 `auto_scheduled` 开关（默认 0=手动，语义与 OpenProject 一致）；前置项 due 变化时对开启自动排期的后继项（depends_on 入边）平移 start/due（保持时长），**每次改期发显式 item.rescheduled 事件**（审计可见「谁/因哪个前置项改的」，不悄悄改投影）；传播递归处理多级依赖，访问标记防环。OpenProject 不支持的约束类型继续不做。

**M.2 WeKan PWA：自托管移动端的最务实路线（backlog 依据）**

- 自托管三强的移动端分层：Plane = 原生 App（评级高但维护两个平台成本大）；**WeKan = 官方 PWA/TWA**（可安装、自托管实例直接用）；Focalboard = 反面教材（移动 web 拥挤难用、独立开发停滞）。
- 对本项目的映射（下一轮候选）：PWA manifest + service worker 离线壳 + 窄屏 rail/看板横滚/触控目标——纯前端可增量做，不阻塞后端演进；本轮不启动。

**M.3 GitLab NDJSON 导入管线：有出必有进（I43 配对）**

- GitLab 的 relation 导出 = NDJSON 文件 + metadata manifest，导入走同构管线；版本兼容窗口两个 minor；**恢复的正解仍是 DB 级备份**，导入用于迁移/选择性恢复。
- 对本项目的映射：`POST /projects/{id}/events/import`（NDJSON → 逐行校验 schema/prev 链 → 追加进事件流 → rebuild 校验投影一致）。安全边界：仅接受**校验和匹配 + 事件 id 不与目标库冲突**的文件（冲突 409），即「空项目或全新库恢复」语义——与 docs/11 §5.3「只剩导出文件时按序重放」的既有表述闭环。

**M.4 M14 取舍**

M14 = **排程自动化与事件可携**：I44 依赖传播自动排期（items.auto_scheduled 开关 + item.rescheduled 显式事件 + 递归传播与防环 + 时间线开关入口）/ I45 事件 NDJSON 导入恢复（校验和/链序/冲突 409 + rebuild roundtrip）/ I46 收尾（docs/12 §11 + docs/11 §5.3 更新 + 冒烟 20 + M14 审阅），约 9 人日。PWA/移动端（下一轮首选）、约束类型（SNET/SLT）、原生 App 留 backlog。

## N. M15 前置调研：PWA 与移动端适配（2026-09-04）

> 目标协议触发：M14 审阅通过后开启。三路调研（WeKan PWA 安装形态、Focalboard/Plane 移动策略、vite-plugin-pwa 技术路线），选定 **PWA 与移动端适配**——本轮落地 M14 调研中的候选（§M.2），并修正两处事实：WeKan 官方商店 App 实为指向演示服务器的 TWA（自托管无用）；Plane 并无原生 App 与 PWA（纯响应式 web）。

**N.1 WeKan：自托管移动端 = 可安装 PWA（主借鉴，修正 §M.2）**

- WeKan 官方 Play 商店「App」是 **TWA（Trusted Web Activity）壳，指向官方演示服务器**——自托管用户反馈「无用」，社区正解是从自己实例的登录页「添加到主屏幕」（Android Chrome / iOS Safari 均可）。教训：**自托管场景下应用商店壳没有意义，可安装 PWA（manifest + service worker + 主屏图标）才是正路**——用户安装的必须是「自己的服务器」。
- 对本项目的映射：不做任何原生壳/TWA；PWA manifest 的 start_url/scope 指向实例自身根路径，安装后以 standalone 独立窗口启动。

**N.2 Focalboard / Plane：同类开源移动端普遍是短板（机会点）**

- Focalboard：移动 web 被评「cramped and unintuitive」，独立移动 App 已废弃并入 Mattermost——**反面教材**：不投入响应式的自托管工具在移动端失守。
- Plane：web-first（Next.js/Django），**无官方原生 App、无 PWA**，移动端纯靠响应式且无专门投入。
- 结论：自托管同类在移动端普遍弱势，做好响应式 + PWA 即超出多数同类水准；验收以「关键路径可用」为准（看板/列表/审批/通知），不追求原生级交互。

**N.3 vite-plugin-pwa：Vite 生态事实标准（技术路线）**

- `vite-plugin-pwa`（Workbox 封装）自动生成 manifest + service worker：`generateSW` 模式（自动 precache 构建产物，起步首选）vs `injectManifest`（自定义缓存逻辑，暂不需要）；`registerType: 'autoUpdate'` 静默更新 + 提示刷新。AgentPM 事件数据必须在线（SSE/审批实时），**离线只缓存静态外壳（app shell 模式），`/api/*` 一律 network-only 不入缓存**——事件溯源系统做离线写会造成一致性分叉，明确不做（V2 再议只读快照）。
- 已知坑：SPA 需要 navigation fallback（index.html）；service worker 仅在 secure context（HTTPS 或 localhost）生效——docs/11 部署文档需注明。

**N.4 M15 取舍**

M15 = **PWA 与移动端适配**：I47 响应式布局基座（窄屏断点 + rail 折叠移动导航 + 看板/表格横向滚动 + 触控目标）/ I48 PWA 可安装与离线外壳（manifest + generateSW + autoUpdate + API 永不缓存 + HTTPS 部署注记）/ I49 移动端关键路径打磨收尾（docs/12 §12 + 冒烟 21 + M15 审阅），约 9 人日。API 数据离线缓存/离线写（一致性风险）、Push 推送（需 VAPID 服务端）、原生 App/TWA（WeKan 教训）留 backlog。

## O. M16 前置调研：自定义视图与保存筛选（2026-09-04）

> 目标协议触发：M15 审阅通过后开启。三路调研（Gitea SSO/OIDC JIT 痛点、Redmine/GitLab 通知 digest、OpenProject 自定义查询分层），选定**自定义视图与保存筛选**——同类自托管项目管理的 Community 层核心日常功能，AgentPM 当前所有过滤（优先级/执行者/字段/分组）均为临时状态，刷新即失。

**O.1 OpenProject 自定义查询：Community 免费 vs Enterprise 报表（主借鉴）**

- **自定义查询（custom query）= 保存的过滤器 + 排序 + 分组，Community 免费核心**；可私有可公开，工作项表格支持列配置/过滤/分组/排序，查询是工作项视图的底层概念（一页可载多个查询），也是项目仪表盘的构件。
- **Enterprise 独占**：跨项目聚合的高级报表模块、time report PDF、portfolio 视图、team planner。
- 对本项目的映射：做 Community 层等价——**saved_views**（保存的过滤/分组/排序组合，私有/项目内共享），报表页保持 M12 固定五 widget（跨项目聚合属 Enterprise 层，不做）；看板分组（M6-I21）与列表过滤展开为视图定义的组成部分。

**O.2 Gitea SSO/OIDC：JIT 注册的经典痛点（候选降级依据）**

- Gitea 经验：`ENABLE_AUTO_REGISTRATION` 开 JIT，但①注册**全有或全无**——IdP 有号即可注册实例，无细粒度 allowlist（issue #27709）；②group claim（admin/restricted）**第二次登录才生效**或部分 IdP 静默失效（issue #32566/#19722）；③部分 IdP 重定向到账号链接页而非静默注册。
- 对本项目的启示（做 SSO 时的设计约束）：JIT 建 users 行须配管理员域名/组 allowlist（fail-closed）；group claim 缺失时回落默认最低角色，绝不依赖 admin claim；回调路径显式处理账号链接分支。
- **本轮不选**：SSO 需要本地 IdP（Keycloak/Authelia）演示环境，成本高且坑集中在 IdP 兼容性——作为下一轮候选（届时按上述约束设计）。

**O.3 通知 digest：同类自托管均无原生内建（backlog 依据）**

- Redmine 无原生 digest（逐事件即发邮件，digest 靠社区插件）；GitLab 只有安全告警/流水线等专项摘要，无通用活动 digest。
- 结论：digest 是「减噪」增值而非核心缺口，且 AgentPM 已有「邮件开关 + 站内通知 + Atom feed」三层降噪（M11）；保持 backlog（实现路径：notifications 投影 + 定时汇总未读一封发出，可用外部 cron 触发端点，无需内建调度器）。

**O.4 M16 取舍**

M16 = **自定义视图与保存筛选**：I50 视图数据层（saved_views 投影表 + view.* 事件 + CRUD + 定义校验 fail-closed + rebuild 存活）/ I51 视图前端（看板/列表「视图」管理器：保存当前过滤、切换、重命名/删除、项目内共享徽标）/ I52 收尾（默认视图排序 + docs/12 §13 + 冒烟 22 + M16 审阅），约 9 人日。SSO/OIDC（按 O.2 约束设计，下一轮候选）、通知 digest、跨项目聚合报表（Enterprise 层）留 backlog。

## P. M17 前置调研：OIDC 单点登录（2026-09-04）

> 目标协议触发：M16 审阅通过后开启。三路调研（FastAPI OIDC 实现模式、本地 IdP 演示环境、Gitea 教训深化），选定 **OIDC 单点登录**——M8 遗留的 SSO 缺口，按 §O.2 约束设计。

**P.1 FastAPI OIDC 实现模式（技术路线）**

- **Authlib** 是 FastAPI 生态事实标准 OIDC client：authorization code 流的 state/nonce/PKCE verifier 存框架 session；session cookie 加固（HttpOnly/SameSite/secure）在 middleware 层完成；Auth0/Vouch 提供完整「code flow + PKCE + session middleware + claim 提取」参考实现。
- 对本项目的映射：**复用 M8 既有会话体系**——OIDC 回调验证 id_token 后签发与本地登录同款的 HMAC 签名 HttpOnly cookie；state 用一次性随机值存短命 cookie（SameSite=Lax 防 CSRF）；confidential client 场景 PKCE(S256) 顺手启用；token 只在握手期使用，会话内不缓存 id_token（凭据不入事件，同 M8 语义）。

**P.2 本地 IdP 演示环境（Keycloak vs Authelia）**

- **Keycloak**：官方容器 + realm import JSON 一键（realm/client/test user 三件套），admin console 可视化，代价 ~1GB 内存；**Authelia**：~40MB 轻量，但 client 全手工 YAML。
- 取舍：单测用「本地 JWT 签发桩」（自签 RSA 密钥 + mini jwks/authorize/token 端点）完全离线覆盖协议路径；演示/审阅环境用 Keycloak docker-compose（realm import 脚本化进 tools/），避免 Authelia 手工配置易错。

**P.3 Gitea 教训深化 → 设计约束清单（主借鉴）**

1. **JIT 注册一次性定角色**：注册时按 claim 定角色，claim 缺失 → 默认最低角色（viewer），**后续登录不再变更角色**（Gitea group-claim 标志第二次登录才生效的时序坑 #32566 的反向规避——幂等无提升）。
2. **allowlist 双层**：IdP 侧组过滤（Keycloak group filtering）是第一层；应用侧 `APM_OIDC_ALLOWED_GROUPS` 非空时不在名单 fail-closed 403（Gitea 无 allowlist 的教训 #27709）。
3. **信任链**：只信「验证过签名/issuer/audience」的 id_token claims；email 缺失或未验证 → 注册拒绝（Gitea Entra 跳账号链接页的教训：注册依赖可信 email claim）。
4. **账号链接**：同 email 已存在本地账号时**不自动合并**——显式 409 提示管理员处理（合并是管理动作不是登录副作用）。

**P.4 M17 取舍**

M17 = **OIDC 单点登录**：I53 OIDC client 基座（discovery + authorization code + PKCE + id_token 验证 + JIT 建号四约束 + 本地 JWT 桩单测）/ I54 会话整合与前端（OIDC 登录按钮 + admin 面板配置 + network 门禁兼容）/ I55 Keycloak 演示环境（realm import 脚本）+ docs/11 §2 扩展 + docs/12 §14 + 冒烟 23 + M17 审阅，约 10 人日。通知 digest、事件归档、跨项目聚合报表继续留 backlog。

## Q. M18 前置调研：工作项评论与参与通知（2026-09-04）

> 目标协议触发：M17 审阅通过后开启。三路调研（Plane/GitLab 评论与提及、OpenProject 工时跟踪、GitLab 通知订阅层级），选定 **工作项评论与参与通知**——AgentPM 工作项目前无评论流（对话域消息不挂工作项），协作闭环的最后一个明显缺口。

**Q.1 Plane/GitLab：评论 + @mention 是协作核心（主借鉴）**

- Plane 工作项：评论线程 + `@` 提及成员即通知 + 活动日志并列呈现；GitLab：讨论线程 + mention 产生 todo 与邮件。
- AgentPM 映射：评论 = 事件溯源域（`comment.created/deleted`，agg 挂工作项）；**@mention 解析为通知**（复用 M10 通知投影 + M11 邮件通道，收件人 = 被提及用户）；**评论者自动成为参与者**（GitLab 参与语义：评论/编辑/被提及即参与 → 参与者收后续事件通知）。

**Q.2 OpenProject 工时跟踪：Community 核心（下一轮候选）**

- work package 记录 spent time（时长/日期/备注/作者）是 **Community 免费**功能，16.0 增个人「My time tracking」日历。AgentPM 有 estimate_hours（计划）无 spent（实际）——与 M14 自动排期（计划侧）互补的执行侧缺口。
- 本轮不选：工时数据模型简单但配套（报表口径、个人视图）体量不小；评论协作频次更高、与既有通知体系联动更直接。**留下一轮首选候选**。

**Q.3 GitLab 通知订阅层级：参与即通知（订阅面设计）**

- GitLab 层级：Watch（全项目）/ Participating（参与的项）/ On mention / Subscribed（手动订阅未参与的项）/ Custom。参与者自动成为通知对象。
- AgentPM 映射：M10 通知触发面扩展——评论被提及（Q.1）+ **工作项订阅**（`watch` 动作：assignee 自动订阅 + 手动订阅/退订）；通知层级细分（watch 级全量 vs mention 级）留 V2，本轮做「参与者+被提及」最小面。

**Q.4 M18 取舍**

M18 = **工作项评论与参与通知**：I56 评论域（comment.* 事件 + CRUD + @mention → 通知 + 参与投影）/ I57 评论前端（功能页与卡片评论抽屉 + mention 补全 + 通知点击跳转工作项）/ I58 订阅与收尾（watch/subscriber + docs/12 §15 + 冒烟 24 + M18 审阅），约 9 人日。工时跟踪（下一轮首选候选）、通知层级细分、评论 Markdown 富文本留 backlog。

---

## R. M19 前置调研：工时跟踪（2026-09-04）

> 目标协议触发：M18 审阅通过后开启。§Q.2 已初判「OpenProject Community 核心留下一轮首选候选」，本轮三路深化（OpenProject 工时模型 / GitLab·Redmine 记时语义 / Plane worklog 现状），选定 **M19 = 工时跟踪与汇总报表**——AgentPM 有 estimate_hours（计划侧）无 spent（实际侧），与 M14 自动排期互补的执行侧缺口。

**R.1 OpenProject：time entry 模型 + 个人日历（Community 免费核心）**

- work package 上点 spent time 数字 → 进入该包的 time tracking report（全部 time entry 列表）；entry = 时长/日期/备注/作者，可在项目/全局报表聚合（[官方文档](https://www.openproject.org/docs/user-guide/time-and-costs/time-tracking/)）。
- 16.0 新增「My time tracking」模块：**个人日历视图**记时/复盘（[发布博客](https://www.openproject.org/blog/time-tracking-module/)）；移动端有 Log Time（[指南](https://www.openproject.org/docs/mobile-app-guide/core-features/time-tracking/)）。
- 模块级开关：time tracking 模块停用时 spent time 不再显示（[OP-925](https://community.openproject.org/journals/22989/diff/description)）——功能可见性跟模块走，不是全局恒显。

**R.2 GitLab / Redmine：记时入口的两种语义**

- GitLab：评论里的 `/estimate` + `/spend 2h` **斜杠快捷命令**，无独立记时 UI；CE 免费层即有（[官方文档](https://docs.gitlab.com/user/project/time_tracking/)、[论坛讨论](https://forum.gitlab.com/t/does-gitlab-ce-come-with-time-tracking-for-projects/40881)）。
- Redmine：独立「Log time」按钮 + timelog 条目；用户对比后**更偏好显式入口**（[GitLab FOSS #27780](https://gitlab.com/gitlab-org/gitlab-foss/-/issues/27780)：「Redmine 的 Log time 链接比 /estimate /spend 更合口味」）；高级报表常靠插件（[Redmineflux 指南](https://www.redmineflux.com/redmine-time-tracking-guide/)）。
- → AgentPM 取 **Redmine 式显式「记工时」入口**（与既有 💬 评论抽屉同型），不做斜杠命令解析。

**R.3 Plane：worklog 仅工作项级，项目级聚合是官方 open 缺口**

- work item 上「+ Log work」记 时:分 + 描述（[官方文档](https://docs.plane.so/core-concepts/issues/time-tracking)）；**项目级聚合分析不存在**，GitHub [#8045](https://github.com/makeplane/plane/issues/8045) 为 open feature request——AgentPM 本轮直接把**项目级工时报表**纳入范围，差异化补位。

**R.4 M19 设计映射与取舍**

- 数据模型：`time.logged/edited/deleted` 事件 + item_time_entries 投影表（item_id/user_id/minutes/spent_on/note，软删）；item 维度 spent 汇总 = SUM(entries)，与 estimate_hours 并列展示（计划 vs 实际）。
- 记时入口：显式「＋ 记工时」（R.2 结论）；spent 徽标进卡片与列表。
- 聚合报表：项目级 按人/按日 工时报表（R.3 差异化）；个人视角最小面并入「我的工作」（本周记时条数与合计），个人日历视图留 backlog。
- 不做：成本/费率（OpenProject 的 cost 属 Enterprise 增强）、斜杠命令、计时器实时打卡（记时条目即可满足落地标准）。

**R.5 M19 取舍**

M19 = **工时跟踪与汇总报表**：I59 工时数据层（time.* 事件 + item_time_entries 投影 + CRUD + spent 汇总 + 权限对齐 + 单测）/ I60 工时前端（记工时抽屉 + spent/estimate 徽标 + docs/12 §16 + 冒烟 25）/ I61 项目工时报表 + 收尾审阅（按人/按日聚合 + 全量回归 + M19 审阅），约 9 人日。个人日历视图、成本费率、斜杠命令留 backlog。

## S. M20 前置调研：体验补齐——个人工时日历 / 时间线拖拽改期 / 评论 Markdown（2026-09-05）

> 目标协议触发：M19 审阅通过后开启。防重查先行：digest 已两次论证留 backlog（§J/§O.3）不再重查。本轮三路（OpenProject My time tracking 日历 / Gantt 拖拽交互生态 / 评论 Markdown 渲染风味），选定 **M20 = 体验补齐三件套**——M19 工时数据已落但缺日常记时入口面、M13 时间线只读与 M14 自动排程之间缺手动拖拽层、M18 评论为纯文本缺结构化渲染，三个「最后一块 UI 面」互不依赖、适合同里程碑三迭代并行推进。

**S.1 OpenProject 16.0「My time tracking」：个人日历是复盘视图不是打卡器**

- 16.0（2025-05 发布）新增 My time tracking 模块：**个人专属空间**（只看自己的条目），**日历视图（日/周/月）+ 列表视图**双形态，页面内快捷记时（[发布博客](https://www.openproject.org/blog/time-tracking-module/)、[用户指南](https://www.openproject.org/docs/user-guide/time-and-costs/my-time-tracking/)）。
- 管理员启用「允许精确记时」后支持 start/end 时间且**日历成为模块默认视图**（[16.0 release notes](https://www.openproject.org/docs/release-notes/16/16-0-0/)）——精确打卡是可选项而非前提，分钟粒度条目配日历完全成立。
- → AgentPM 取舍：记时条目保持 M19 的 分钟+spent_on 粒度（R.2 决策沿用），**不做 start/end 打卡**；日历做 周/月双视图 + 日合计 + 点日快捷记时（复用 I60 抽屉表单语义），个人视角与「我的工作」并列入侧栏。

**S.2 Gantt 拖拽改期：OpenProject 内建 vs Redmine 插件生态**

- OpenProject Gantt **内建**拖拽排程：条形拖拽改期、拖边改时长、图内调序；前置/后继依赖图内直建；15.4 起手动（默认）/自动双排程模式（[Gantt 文档](https://www.openproject.org/docs/user-guide/gantt-chart/)、[排程模式](https://www.openproject.org/docs/user-guide/gantt-chart/scheduling/)）——「自动化是可选项而非默认」哲学已在 §M 调研确认。
- Redmine 核心 Gantt 缺拖拽/缩进等基本交互（[opensource.com 评测](https://opensource.com/article/21/3/open-source-project-management)），靠 Easy Gantt（免费层：拖拽移动任务/里程碑、拖拽建依赖）等插件补位（[easy-gantt](https://www.redmine.org/plugins/easy-gantt)）；开源 canvas 路线 redmine_canvas_gantt 拖拽中半透明、端点拖拽建依赖（[GitHub](https://github.com/tiohsa/redmine_canvas_gantt)）。
- AgentPM 现状缺口：M13-I42 TimelinePage 为**只读** Gantt-lite（条形/里程碑菱形/依赖连线/冲突标红），M14 后端已有手动 PATCH 改期 + rescheduled 审计 + 自动顺延——**两端齐备，缺的恰是图上拖拽这层中间 UI 面**。
- → 取舍：条形拖拽移动（改 start/due）+ 右缘缩放（改 due）+ 拖拽中半透明 + 落点 PATCH 复用既有审计与冲突重算着色；**依赖连线图内编辑不做**（关系编辑留既有表单，图内连线 backlog）。

**S.3 评论 Markdown 渲染：风味差异是集成痛点，存储原文是底线**

- GitLab GLFM：任务清单（`- [ ]`/`- [x]`）、表格、折叠块、代码高亮是评论结构化主力（[GLFM 文档](https://docs.gitlab.com/user/markdown/)）；GitHub GFM 任务清单语义同源（清单项以 `[ ]` 起头即渲染复选框，[释义](https://inventivehq.com/blog/what-are-task-lists-and-how-to-use-them-in-markdown)）。
- 风味差异造成真实集成成本：Outline/Drupal 均要处理 GLFM vs GFM 分歧（[Outline #11903](https://github.com/outline/outline/discussions/11903)、[Drupal #3378201](https://www.drupal.org/project/markdown_easy/issues/3378201)）；任务清单复选框在 HTML 表格内状态不持久、嵌套清单样式是已知设计难点（[GitLab CSS Lab #40](https://gitlab.com/gitlab-org/csslab/-/issues/40)）——第三方渲染只取交集（GFM 基本面）最稳。
- → 取舍：评论**存储仍是纯文本原文**（comment.created 事件与 API 契约不变），渲染层做 GFM 只读转换（marked + DOMPurify 消毒，XSS fail-closed）；任务清单只读不回写（评论非状态载体，状态走工作项字段）；mention 沿用既有 @解析、渲染高亮为 chip；编辑框加「预览」切换。编辑器工具栏不做。

**S.4 M20 设计映射与验证纪律（新协议）**

- I62 个人工时日历：`GET /my/timelog?days=`（按日条目+合计，纯投影聚合）+「我的工时」页（周/月视图 + 日合计 + 点日快捷记时）+ 侧栏入口。
- I63 时间线拖拽改期：TimelinePage 条形 pointer 拖拽移动/右缘缩放 → PATCH start_date/due_date（复用 M14 审计与冲突重算）；仅对有日期项启用。
- I64 评论 Markdown 渲染：marked+DOMPurify 只读渲染 + mention chip + 预览切换；冒烟 26 收尾。
- **验证纪律（用户 2026-09-05 更新）**：每迭代只跑改动相关测试（对应 test_*.py + build），不再每轮全量；全量回归收敛到 M20 正式审阅（每里程碑一次 ≤ 每 5 轮一次）。HANDOFF.md 每轮收口时修剪防膨胀。

**S.5 M20 取舍**

M20 = **体验补齐三件套**：I62 个人工时日历（my/timelog 聚合 + 周/月日历页 + 快捷记时）/ I63 时间线拖拽改期（条形拖拽/缩放 → PATCH + 冲突重算）/ I64 评论 Markdown 渲染（GFM 只读 + mention chip + 预览）+ docs/12 §17 + 冒烟 26 + M20 审阅，约 8 人日。start/end 精确打卡、依赖连线图内编辑、任务清单回写、编辑器工具栏留 backlog。

## T. M21 前置调研：日程集成——依赖图内编辑 / 清单项转子任务 / iCal 订阅（2026-09-05）

> 目标协议触发：M20 审阅通过后开启。防重查先行：start/end 打卡 §S.1 已明确不做（分钟粒度即够）、digest §J/§O.3 两次论证留 backlog、基线对比同类 Community 层普遍缺位（frappe-gantt 无原生 baseline）。本轮三路（图内依赖编辑生态 / GitHub tasklist→sub-issue 语义 / iCal 订阅面），选定 **M21 = 日程集成三件套**——「依赖图内建（进）+ 日程 iCal 订阅出去（出）+ 清单项提取成真工作项（提取）」互不依赖、全是 backlog 承诺项。

**T.1 依赖连线图内编辑：社区 fork 专门补位即需求实证**

- frappe-gantt 核心库：拖拽/缩放/进度/依赖**渲染**内建，但**拖拽创建依赖不支持**（[官方仓](https://github.com/frappe/gantt)、[Bryntum 评测](https://bryntum.com/blog/creating-a-gantt-chart-with-frappe-gantt/)）；[@workiom/frappe-gantt fork](https://www.npmjs.com/package/@workiom/frappe-gantt) 专门新增「hover 条形显端点圆圈 → 拖拽到另一条形建依赖」——fork 的存在本身就是高频需求的实证。
- OpenProject 依赖在图内直建（§S.2）；Redmine 侧 Easy Gantt 免费层同样主打「拖拽建关系」（§S.2）。
- → AgentPM 取舍：TimelinePage 自研渲染（无库）上实现同款交互——条形两端 hover 圆圈、拖到目标条形落点 → `POST relations depends_on`（复用 M4 关系域），冲突重算着色即时生效；反向依赖/自依赖 422 由后端既有校验承担。

**T.2 清单项转子任务：GitHub 的「提取」语义而非「回写」**

- GitHub 2025-02 起支持**把任务清单项转换为 sub-issue**：hover 复选框出「Convert to sub-issue」，转换后**该项从清单移除**——草稿项升格为真实可跟踪工作项（[官方 changelog](https://github.blog/changelog/2025-02-18-github-issues-projects-february-18th-update/)、[社区讨论 #151832](https://github.com/orgs/community/discussions/151832)、[tasklists 文档](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/about-tasklists)）。
- 用户对 hover 误触有抱怨（[#4261](https://github.com/orgs/community/discussions/4261)）——转换入口须显式而非 hover 悬浮。
- → AgentPM 取舍：与「评论非状态载体」原则不冲突——这是**提取**（从纯文本清单项创建真工作项），不是回写清单状态。评论渲染中清单项 hover 显「转为子任务」按钮（显式点击）→ 创建 `task` 概念工作项（标题=清单项文本，depends_on 关系留表单）→ 渲染层把该项替换为工作项链接 + 已提取徽标（**不改原文**，提取映射走 `extracted_tasks` 记录——comment.created 事件与存储零改动）。任务清单 checkbox 回写仍不做。

**T.3 iCal 日历订阅：OpenProject 内建 vs Redmine 插件补位**

- OpenProject 13.0 内建**日历订阅**：任意日历以 ICS URL 订阅到外部日历客户端（[官方文档](https://www.openproject.org/docs/user-guide/calendar/)、[产品博客](https://www.openproject.org/blog/calendar-subscriptions/)）；Redmine 核心 ICS feed 至今 open（[#1077](https://www.redmine.org/issues/1077)），靠 redmine-tasks-ics-subscription 等插件补位（个人指派项只读 ICS，[插件页](https://www.redmine.org/plugins/redmine-tasks-ics-subscription)）。
- ICS feed 无推送提醒——提醒由订阅方日历客户端负责（这是订阅协议的固有语义，不是缺陷）。
- → AgentPM 取舍：`GET /my/calendar.ics?key=`（复用 M11 feed_key 认证与权限语义——只含本人可见面）——内容=分配给我的活跃项（VEVENT：start/due 全日事件 + 状态后缀）+ 项目里程碑（截止日全日事件）；手写 VEVENT 文本（零新依赖，saxutils 同款转义思路）；「我的工作/我的工时」页给出订阅链接（与 Atom feed 同位）。IETF RFC 5545 文本格式，冒烟断言 VEVENT 计数与字段。

**T.4 M21 设计映射与验证纪律（沿用 2026-09-05 更新）**

- I65 依赖图内编辑：TimelinePage 条形端点圆圈 + 拖拽连线 → POST relations + 冲突重算；连线绘制复用 I63 坐标体系（SVG 层已有）。
- I66 iCal 订阅：`/my/calendar.ics?key=` + users.feed_key 复用 + 我的工作页订阅链接 + 冒烟 27 部分。
- I67 清单项转子任务：`POST /comments/{id}/extract-task`（清单项索引 + 概念默认 task）+ extracted_tasks 记录 + 渲染层替换链接 + 显式按钮。
- 验证纪律：每迭代只跑改动相关测试；全量回归收敛至 M21 正式审阅；HANDOFF 每轮修剪。

**T.5 M21 取舍**

M21 = **日程集成三件套**：I65 依赖连线图内编辑（端点圆圈拖拽 → depends_on + 冲突重算）/ I66 iCal 日历订阅（/my/calendar.ics + feed_key + VEVENT 全日事件）/ I67 评论清单项转子任务（提取语义 + extracted_tasks + 渲染链接）+ docs/12 §18 + 冒烟 27 + M21 审阅，约 8 人日。start/end 打卡、任务清单 checkbox 回写、甘特基线对比、digest 留 backlog。

## U. M22 前置调研：治理与效率——全局搜索 / 项目归档克隆 / 批量编辑（2026-09-05）

> 目标协议触发：M21 审阅通过后开启。防重查先行：全局搜索/项目归档/克隆/批量编辑在 docs/01 均无既有调研（grep 确认）；digest 与 start/end 打卡维持既往结论。本轮三路（OpenProject 全局搜索 / OpenProject·Redmine 归档与克隆语义 / Plane 批量操作形态），选定 **M22 = 治理与效率三件套**——数据量增长后「找得到（搜索）+ 管得住（归档）+ 动得快（批量）」是落地标准的日常运营面。

**U.1 全局搜索：跨内容类型 + 快捷过滤**

- OpenProject 全局搜索：关键字/ID **跨内容类型**（工作包、wiki 等）检索，结果页按类型快捷过滤（[Global search](https://www.openproject.org/docs/mobile-app-guide/core-features/global-search/)、[Search features](https://www.openproject.org/docs/user-guide/search/)）；跨项目列表同样支持搜索/过滤/保存视图。
- AgentPM 现状：⌘K 命令面板只做导航与过滤（I10），工作项/评论/资产无统一文本检索面；FTS5 已在栈内（资产域中文 bigram，docs/09 §5）。
- → 取舍：`GET /search?q=` 复用 FTS5——items.title/描述 与评论 body 入虚拟表（中文 bigram 同款 tokenizer），结果按项目可见性裁剪（`_visible` 同款）+ 类型 chips（工作项/评论/资产）；⌘K 面板增「搜索 'xx'」入口跳结果页。不做 wiki 类内容（无此域）。

**U.2 项目归档与克隆：只读可逆 vs 创建时复制**

- OpenProject 归档：项目设置 Information 页 ⋯ 菜单「Archive project」（实例/项目管理员）——归档后项目**只读**（数据不可变）并移出活跃列表，**可逆**（unarchive 恢复）；删除才不可逆（恢复靠备份）（[Manage project information](https://www.openproject.org/docs/user-guide/projects/project-settings/project-information/)、[Restoring backup](https://www.openproject.org/docs/installation-and-operations/operation/restoring/)）。
- 克隆：OpenProject 支持复制项目（结构+工作包等，需权限）；Redmine 在**创建项目时**勾选「Copy projects」并选择复制内容（issues/members/versions，[Feature #4687](https://www.redmine.org/issues/4687)——管理员限定曾是长期痛点）。
- → 取舍：①归档=`project.archived/reopened` 事件 + projects.status 列（active/archived），归档项目**全端只读门禁**（写路径 409 + SSE/报表仍可见），列表默认隐藏 + 「显示已归档」开关；②克隆=`POST /projects/{id}/clone`（新名 + 选择复制：结构/工作项/里程碑，**成员不复制**防越权——创建时勾选语义同 Redmine），逐实体走既有 emit 链路保审计。

**U.3 批量操作：checkbox 选择 + 底部批量条**

- Plane 批量更新：列表 checkbox 逐个/全选 → **底部批量操作条**应用修改（无右键菜单形态，[Bulk ops 文档](https://docs.plane.so/core-concepts/issues/bulk-ops)）；分组视图下批量条曾因选择丢失出 bug（[#8683](https://github.com/makeplane/plane/issues/8683)——分组状态与选择状态要解耦）。
- AgentPM 现状：看板卡片多选只有「批量让 Agent 做」（M2）与审批中心批量决策（M2），无批量字段编辑。
- → 取舍：列表视图增 checkbox 多选 + 底部批量条（改状态/指派/优先级/设置里程碑）→ `POST /projects/{id}/items/batch-patch`（ids+patch，**逐项发 item.updated 事件**——审计与 automation hook 保真，失败项逐条返回不整批回滚）；选择状态与分组/过滤解耦（#8683 教训）。

**U.4 M22 设计映射与验证纪律（沿用）**

- I68 全局搜索：FTS5 虚表 items/search + comments/search（中文 bigram）+ 触发器同步；`GET /search?q=` 可见性裁剪 + ⌘K 入口 + 结果页（类型 chips + 点击直达）。
- I69 归档与克隆：status 列（ALTER 迁移）+ archived/reopened 事件 + 写门禁 409 + 列表开关 + clone 端点（复制选择 + 审计事件 project.cloned）。
- I70 批量编辑：列表 checkbox + 批量条 + batch-patch 端点（逐事件、逐项结果）；冒烟 28 收尾。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M22 审阅；HANDOFF 每轮修剪。

**U.5 M22 取舍**

M22 = **治理与效率三件套**：I68 全局搜索（FTS5 复用 + 可见性裁剪 + ⌘K 入口）/ I69 项目归档与克隆（只读可逆 + 创建时复制语义 + 成员不复制）/ I70 批量编辑（checkbox + 底部批量条 + 逐事件 batch-patch）+ docs/12 §19 + 冒烟 28 + M22 审阅，约 8 人日。digest、start/end 打卡、甘特基线、编辑器工具栏留 backlog。

## V. M23 前置调研：计划对照与总览——甘特基线 / 组合聚合 / Markdown 工具栏（2026-09-05）

> 目标协议触发：M22 审阅通过后开启。防重查先行：本体版本事件级归档 §K.3 已有立场（导出/快照而非删除）继续 backlog；digest、start/end 打卡维持既往结论。本轮三路（基线快照生态 / 组合总览的 Community 形态 / GitHub 工具栏实现），选定 **M23 = 计划对照与总览三件套**——「基线（计划钉住）+ 组合（跨项目看见）+ 工具栏（写得更顺）」。

**V.1 甘特基线：时点快照，不随改期漂移**

- Redmine 核心**无基线**：两条独立日期对（计划 start/due vs 实际）的诉求长期 open（[#13419](https://www.redmine.org/issues/13419)、[论坛讨论](https://www.redmine.org/boards/1/topics/35027)）；Easy Redmine（[Gantt 插件](https://www.easy8.com/redmine-gantt-plugin)）与 Redmineflux（「Set Baseline = 某时点计划快照」，[指南](https://redmineflux.com/)）以插件售卖验证了需求真实存在。
- 通用语义（Monday/TeamGantt/Instagantt 一致）：基线 = **创建瞬间的日期快照**，后续排程变化不影响它，图上叠加对比展示偏差。
- → AgentPM 取舍：每项目保留**单一活动基线**——`POST /projects/{id}/baseline`（快照全部已排期项的 start/due + 里程碑 due，写入 `project.baseline_set` 事件 payload，投影 baselines 表）/ 清除事件；TimelinePage 叠加**幽灵条形**（半透明灰）表达基线位置，当前条形偏离即着色提示；不做多基线历史链（backlog）。

**V.2 组合总览：Community 用项目列表 + 聚合 widget 补位**

- OpenProject **Portfolios 是 Enterprise 独占**（[Portfolios 文档](https://www.openproject.org/docs/user-guide/portfolios/)）；Community 的等价物 = 项目列表 + 全局工作包表 + 应用首页 widget（[FAQ](https://www.openproject.org/docs/user-guide/projects/projects-faq/)、[首页](https://www.openproject.org/docs/user-guide/home/)）。
- → AgentPM 取舍：`GET /portfolio/report`（可见项目聚合：每项目 五桶分布/挂起 Gate/超期滞留/工时合计 + 总计行，纯投影聚合零 ETL）+ Dashboard 顶部「组合总览」卡（复用 M12 报表框架，15s 轮询同款）；不做自定义 widget 拖装（Enterprise 增强范畴）。

**V.3 Markdown 工具栏：GitHub 官方路线 = 纯 textarea 加按钮**

- GitHub 评论框本质是**纯文本 textarea + Markdown 工具栏**，无 WYSIWYG（[官方声明](https://github.com/orgs/community/discussions/3864)）；其开源实现 [github/markdown-toolbar-element](https://github.com/github/markdown-toolbar-element) 就是往 textarea 上加格式化按钮的 Web Component——选区包裹插入，焦点管理是关键细节。
- 重型 WYSIWYG（TipTap/ProseMirror）能做 Notion 式体验但有长文性能与存储格式转换成本（[HN 讨论](https://news.ycombinator.com/comments?id=30299800)）——与「存储纯文本」原则冲突。
- → AgentPM 取舍：CommentsModal 编辑框上加**手写紧凑工具栏**（加粗/斜体/行内代码/链接/列表/任务清单/引用——选区包裹插入，无选区插入占位符），零新依赖、textarea 不动、存储仍纯文本；预览切换保留。

**V.4 M23 设计映射与验证纪律（沿用）**

- I71 甘特基线：baselines 投影（project_id + snapshot JSON）+ baseline.set/cleared 事件 + TimelinePage 幽灵条形与偏差提示。
- I72 组合总览：`/portfolio/report`（`_visible` 裁剪可见项目集合）+ Dashboard 组合卡。
- I73 Markdown 工具栏：选区包裹插入 + docs/12 §20 + 冒烟 29 收尾。
- 验证纪律：每迭代只跑相关测试（动 events 内核则升级全量）；全量收敛至 M23 审阅；HANDOFF 每轮修剪。

**V.5 M23 取舍**

M23 = **计划对照与总览三件套**：I71 甘特基线（单活动基线快照 + 幽灵条形偏差）/ I72 组合总览（portfolio/report 聚合 + Dashboard 卡）/ I73 Markdown 工具栏（GitHub 路线选区包裹）+ docs/12 §20 + 冒烟 29 + M23 审阅，约 8 人日。多基线历史、widget 拖装、WYSIWYG、digest、start/end 打卡留 backlog。

## W. M24 前置调研：结构与数据管理——子任务层级 / CSV 导入 / 泳道与多基线（2026-09-05）

> 目标协议触发：M23 审阅通过后开启。防重查先行：widget 拖装维持 §K.1 的 Enterprise/YAGNI 立场；事件级归档维持 §K.3 立场。本轮三路（工作包层级 / CSV 导入 / 泳道避让与多基线），选定 **M24 = 结构与数据管理三件套**——AgentPM items.parent_id 列自 MVP 闲置、数据进出只有手工创建与报表导出、时间线同概念重叠是 M21 审阅 C 级观察——三者都是「结构化数据管理」的真实缺口。

**W.1 工作包层级：缩进与后代过滤是 Community 标配**

- OpenProject：层级=父子关系，表格右键 **Indent/Outdent** 建层级、排序保持父子完整、「children」分屏视图，15.5 新增 **Descendants of 过滤器**展示所有层级后代（[层级文档](https://www.openproject.org/docs/user-guide/work-packages/work-package-relations-hierarchies/)、[15.5 发布](https://www.openproject.org/blog/openproject-15-5-release/)）；Plane 有 sub-work items（其 #7279 即子项过滤 bug）。
- AgentPM 现状：items.parent_id 列自 MVP 就在（ItemIn 可传）但**无校验、无 UI、无遍历**——数据模型等了 24 个迭代。
- → 取舍：①写路径校验 fail-closed（parent 存在/同项目/不得成环——沿父链上溯）②列表视图缩进呈现（children 嵌套渲染 + 展开/折叠）③抽屉/详情「↳ 子任务」区 + 「+ 子任务」快捷创建（预填 parent_id）④`GET /items?parent=id` 直查与 `descendants=1` 递归后代。

**W.2 CSV 导入：Redmine 核心内置，列映射 + 逐行校验**

- Redmine 内置导入：Issues 页 Import 链接 → CSV 首行表头**自动匹配字段**或手工映射，自定义字段可导，多项目导入靠把 Project 列映射到文件列（[HowTo import issues](https://www.redmine.org/projects/redmine/wiki/HowTo_import_issues)、[#25808](https://www.redmine.org/issues/25808)）；OpenProject 官方无内建 UI，靠 OpenProjectExcel 外部工具（[博客](https://www.openproject.org/blog/synchronize-excel-openproject/)）——内建导入是自托管的普遍期待。
- → 取舍：`POST /projects/{id}/items/import`（CSV 文本体：首行表头固定列名 title/concept_id/status/priority/start_date/due_date/estimate_hours/parent_title——**parent 按标题引用已存在项**实现层级导入；逐行走 create_item 全量校验）+ 返回逐行 ok/行号/错误（fail-closed 不整批回滚——复用 I70 批量语义）；`GET /projects/{id}/items/import-template`（带表头与示例行的模板）；工作项 CSV 导出（items 导出补充报表导出）。UI：列表工具栏「导入 CSV」上传框 + 结果表 + 模板下载链接。

**W.3 泳道避让与多基线：区间图染色 + 分 Row 渲染**

- 泳道避让是经典**区间图染色**：按 start 排序，贪心把每个条形放进第一条「末线 ≤ 新 start」的子行，min-heap 维护行末线，O(n log n)（[TimelinePacking](https://metacpan.org/pod/Algorithm::TimelinePacking)、[CLRS 贪心](https://www.calameo.com/books/0008647671f94aa8e9f06)）。
- 多基线：MS Project 支持 11 条基线，多条并用自定义条形样式 **Row 偏移分色渲染**防重叠（[MS 官方](https://support.microsoft.com/en-us/project/create-or-update-a-baseline-or-an-interim-plan-in-project-desktop)、[Ten Six 指南](https://tensix.com/displaying-two-gantt-chart-baselines-in-microsoft-project/)）；Easy Gantt 亦多基线同图对比。
- → 取舍：①TimelinePage 概念行内**子行拆分**（贪心泳道分配，行高自适应——直接修 M21/M22 的重叠 C 级观察）②基线升级为**多基线**：baselines 表去 UNIQUE、`baseline.list` 返回全部、GET `?which=` 选择展示某条或全部幽灵（全部时按行偏移防叠）、UI「基线」下拉切换显隐；`set` 语义不变（追加新快照，保留历史）。

**W.4 M24 设计映射与验证纪律（沿用）**

- I74 子任务层级：create/patch parent 校验（存在/同项目/防环）+ descendants 递归（CTE 或应用层沿链）+ 列表缩进树 + 子任务快捷创建；冒烟覆盖层级 roundtrip。
- I75 CSV 导入导出：import 端点（逐行校验报告）+ 模板下载 + items.csv 导出 + 列表工具栏入口。
- I76 泳道与多基线：贪心子行分配 + baselines 多条化（schema 迁移：UNIQUE 去除）+ 幽灵条形 Row 偏移渲染 + 基线切换 UI；docs/12 §21 + 冒烟 30 收尾。
- 验证纪律：每迭代只跑相关测试（动 schema/内核升级全量）；全量收敛至 M24 审阅。

**W.5 M24 取舍**

M24 = **结构与数据管理三件套**：I74 子任务层级（parent 校验防环 + 缩进树 + descendants）/ I75 CSV 导入导出（列映射 + 逐行校验报告 + 模板）/ I76 泳道避让与多基线（区间染色子行 + 多基线历史与切换）+ docs/12 §21 + 冒烟 30 + M24 审阅，约 9 人日。widget 拖装、WYSIWYG、digest、start/end 打卡、打印 PDF 留 backlog。

## X. M25 前置调研：计划治理深化——基线偏差报表 / blocks 闭锁 / 列表分页（2026-09-05）

> 目标协议触发：M24 审阅通过后开启。防重查先行：关系受控枚举内核已有（blocks/blocked_by/relates/precedes，§A.4）；分页与偏差报表无既有调研。本轮三路（MS Project 偏差表与 OpenProject 基线对比 / OpenProject 关系功能语义 / GitLab 分页性能），选定 **M25 = 计划治理深化三件套**——基线已能存（M23/M24）、关系已能连（M4/M65），本轮补「读得出偏差 + 关系带后果 + 列表扛得住量」。

**X.1 基线偏差报表：Variance 表的列语义**

- MS Project 内建 **Variance 表**：同屏列出 scheduled 与 baseline 的 start/finish，偏差一目了然（[官方指南](https://support.microsoft.com/en-us/project/create-or-update-a-baseline-or-an-interim-plan-in-project-desktop)）；偏差五型 start/finish/duration/cost/work，公式 `X Variance = Current X − Baseline X`（[OnePager](https://www.onepager.com/community/blog/baselining-and-variance-analysis/)）。
- OpenProject 的基线对比 = **工作包表在给定期间的 diff**（基于保存视图，[Baseline comparison](https://www.openproject.org/docs/user-guide/work-packages/baseline-comparison/)）——同为「表对比」形态。
- → AgentPM 取舍：`GET /projects/{id}/baseline-variance?baseline_id=`（对比指定基线或最新：每已排期项 start/due 偏差天数 + 未变化项省略 + 汇总行，纯投影对比零 ETL）；TimelinePage「偏差表」抽屉 + 组合卡联动；只做日期偏差（cost/work 无此域）。

**X.2 blocks 闭锁与关系可视化：关系要有后果**

- OpenProject **blocks 有关闭闭锁**：A blocks B 时 B 在 A 关闭前**不能置为 closed/resolved**（[关系文档](https://www.openproject.org/docs/user-guide/work-packages/work-package-relations-hierarchies/)）；**precedes 支持 lag**（最小间隔工作日，在 Relations 页编辑，[排程文档](https://www.openproject.org/docs/user-guide/gantt-chart/scheduling/)）；关系在 Gantt 中渲染为箭头（[Gantt 模块](https://www.openproject.org/docs/user-guide/gantt-chart/)）。
- AgentPM 现状：关系类型受控枚举（blocks/blocked_by/relates/precedes）建了枚举但**无任何功能语义**，时间线只画 depends_on 冲突。
- → 取舍：①**blocks 闭锁**——change_status 时若有未完结的 blocks 关系指向本项且 blocker 非 done/cancelled → 422（`"blocked by X"`）；②时间线连线扩展（depends_on 之外的 blocks/precedes 以不同虚线样式绘制）；③precedes lag 字段（relation 行加 lag_days，M14 自动排期沿用 delta 计算的下一步接口，本轮只存储与展示）。**blocked_by 视为 blocks 的反向视图**（存储单向）。

**X.3 列表分页：offset 起步，接口留 keyset 余地**

- GitLab：offset 分页在深页码有性能瓶颈，推荐 **keyset（cursor）分页**且 API per_page 上限 100（[keyset 指南](https://docs.gitlab.com/development/database/keyset_pagination/)、[offset 优化](https://docs.gitlab.com/development/database/offset_pagination_optimization/)）；SQLite 单机 demo 规模下 offset 足够。
- AgentPM 现状：get_items 返回全量——数据量增长后列表/网络传输无界。
- → 取舍：`GET /items?limit=&offset=`（默认全量保持兼容，显式传参才分页；limit 钳 1-200）+ 响应 `total` 计数；列表前端「加载更多」；keyset 留 backlog（SQLite 规模不需要）。

**X.4 M25 设计映射与验证纪律（沿用）**

- I77 基线偏差表：baseline-variance 端点（对比基线快照 vs 当前行，偏差天数=当前−基线）+ TimelinePage 偏差抽屉。
- I78 blocks 闭锁与关系可视化：change_status 闭锁守卫 + 时间线多关系连线样式 + precedes lag_days 存储展示。
- I79 列表分页：limit/offset + total + 「加载更多」；docs/12 §22 + 冒烟 31 收尾。
- 验证纪律：每迭代只跑相关测试（动 change_status 则升级全量）；全量收敛至 M25 审阅。

**X.5 M25 取舍**

M25 = **计划治理深化三件套**：I77 基线偏差表（variance 端点 + 抽屉）/ I78 blocks 闭锁与关系可视化（含 precedes lag 存储）/ I79 列表分页（limit/offset + total + 加载更多）+ docs/12 §22 + 冒烟 31 + M25 审阅，约 9 人日。keyset 分页、cost/work 偏差、lag 自动排期联动、widget 拖装留 backlog。
