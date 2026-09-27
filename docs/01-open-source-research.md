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

## Y. M26 前置调研：流程纪律——看板 WIP 限制 / 评论编辑与修订史 / 状态流转白名单（2026-09-05）

> 目标协议触发：M25 审阅通过后开启。防重查先行：digest 三次论证留 backlog（§J/§O.3）不查、事件级归档两次论证（导出快照形态，删除破坏 live==replay）不查、打印/PDF 属 Enterprise 独占面价值低（§O.1）。本轮三路（Kanboard/Taiga WIP 限制执行语义 / Redmine·GitLab 评论编辑与审计 / OpenProject·YouTrack 流转约束），选定 **M26 = 流程纪律三件套**——「在制品纪律（WIP）+ 协作审计纪律（评论史）+ 状态机纪律（流转白名单）」，§A 借鉴结论第 6 条「列 WIP 限制」的最后一块未实现承诺。

**Y.1 看板 WIP 限制：软约束是主流语义（Kanboard）**

- Kanboard 内建**列级 Task Limit**：达到上限后**列背景变红**——视觉警示而非阻止放入（[官方文档](https://docs.kanboard.org/v1/user/boards/)）；Changelog 修复过「limit 计所有 open 任务而非过滤后任务」（[ChangeLog](https://github.com/kanboard/kanboard/blob/main/ChangeLog)）——口径是列内全部未完项。Taiga 同样列 WIP 限制内建（[PCMag 评测](https://uk.pcmag.com/productivity-2/91533/taiga)）。
- Jira 社区确认硬阻止需外力（[Atlassian Community](https://community.atlassian.com/forums/Jira-Product-Discovery-questions/How-to-set-WIP-Limits-within-a-Kanban-board/qaq-p/2365059)）。
- → AgentPM 取舍：**软约束**——本体 `board_defaults.wip_limits`（`status_group → limit` 映射，声明式进类型系统）+ 看板列头「3/5」徽标、超限列头变红 + title 提示，**不阻止**状态变更（AgentPM 状态变更有拖拽/批量/NL/Agent 多入口，硬拦截只挡一个入口反而入口不一致——软约束天然全局一致）；计数口径=列内全部项（Kanboard 修复语义）。

**Y.2 评论编辑与修订史：同类有缺口，事件溯源零成本补齐**

- Redmine 原生**不记录 note 编辑历史**，审计要装插件（[comment_edit_history](https://www.redmine.org/plugins/comment_edit_history)——存每次修订全文+编辑者+时间）；GitLab 编辑评论只有 "edited" 标记，**完整编辑史是多年 open feature request #3706**（[gitlab#3706](https://gitlab.com/gitlab-org/gitlab/-/issues/3706)）——公认审计缺口。
- → AgentPM 取舍：事件溯源让这个「同类要插件/做不到」的能力**近零成本**——`comment.updated` 事件（edit 动作显式落事件）+ `comment_revisions` 投影表（每次编辑前的旧 body 存修订行）+ 作者本人可编辑 + 抽屉「已编辑」徽标 + 修订历史列表（谁/何时/旧文）。不做删除评论（软删除也是删除，留 backlog 统一考量）；mentions 修订不重发通知（编辑降噪）。

**Y.3 状态流转白名单：OpenProject 配置矩阵的声明式简化**

- OpenProject 用管理 UI 配置 **role × type 的允许流转矩阵**（[官方博客](https://www.openproject.org/blog/status-and-workflows/)）；YouTrack 用 workflow **state-machine 规则脚本**控制流转/必填（[JetBrains 文档](https://www.jetbrains.com/help/youtrack/devportal/state-machine-per-issue-type.html)）。
- → AgentPM 取舍：本体概念级 `transitions` 白名单声明（`{from: open, to: in_progress}` 列表，缺省不声明=全允许向后兼容）——声明后 change_status 校验 `from→to ∈ 白名单` 违规 422；配置矩阵的 role 维度不引入（AgentPM 角色三档且已有写门禁，语义重复）；transition 必填字段（YouTrack）留 backlog。与 M25-I78 blocks 闭锁同层：都是 change_status 内的**纪律守卫**，全入口一致继承。

**Y.4 M26 设计映射与验证纪律（沿用）**

- I80 看板 WIP 限制：本体 board_defaults.wip_limits + 看板列头计数徽标超限红（软约束）。
- I81 评论编辑与修订史：comment.updated 事件 + comment_revisions 投影 + 「已编辑」徽标与历史抽屉。
- I82 状态流转白名单：本体 transitions 声明 + change_status 校验（缺省全兼容）；docs/12 §23 + 冒烟 32 于 I82 + 审阅。
- 验证纪律：每迭代只跑相关测试（I82 动 change_status 升级全量）；全量收敛至 M26 审阅。

**Y.5 M26 取舍**

M26 = **流程纪律三件套**：I80 看板 WIP 限制（Kanboard 软约束语义）/ I81 评论编辑与修订史（事件溯源补 GitLab #3706 缺口）/ I82 状态流转白名单（OpenProject 矩阵的声明式简化）+ docs/12 §23 + 冒烟 32 + M26 审阅，约 9 人日。transition 必填字段、评论删除、role 维度矩阵、WIP 硬拦截留 backlog。

## Z. M27 前置调研：排期深化——lag 排期联动 / 跨项目里程碑路线图 / 里程碑燃尽（2026-09-05）

> 目标协议触发：M26 审阅通过后开启。防重查先行：评论删除 M18 已实现（软删除 deleted_at）；事件级归档四次记录立场（导出形态）不查；digest 三次论证不查；Cycles §L.2 已论证不做（时间盒用里程碑承载）。本轮三路（MS Project/OpenProject lag 语义与自动排期 / GitLab roadmap 跨项目缺口与 OpenProject team planner / Jira·Taiga·Plane 燃尽与速率），选定 **M27 = 排期深化三件套**——M14 排期引擎缺 lag 输入（I78 已备存储）、跨项目只见卡片不见时间线（M23 组合卡）、进度只见当前快照不见趋势（M12 done_ratio）。

**Z.1 lag 排期联动：MS Project lead/lag 与 OpenProject 关系 lag**

- MS Project：**lead（负 lag）使后继与前继重叠，lag 推迟后继开始**（[官方文档](https://support.microsoft.com/en-us/project/add-lead-or-lag-time-to-a-task)）；默认按**工作日**计，要按日历日用「edays」（[Reddit 实践](https://www.reddit.com/r/microsoftproject/comments/1amx02m/microsoft_project_lag_times_follow_a_different/)）。
- OpenProject：Relations 页 lag 值按**工作日**（lag=2 → 后继在前继完成后第 3 个工作日启动；**lag=-1 → 后继与前继同日启动**，[排程文档](https://www.openproject.org/docs/user-guide/gantt-chart/scheduling/)）；15.4 起 Relations 驱动**自动排期**。
- → AgentPM 取舍：I78 的 `lag_days` 接入 **M14 依赖传播引擎**——后继 start = 前置 due + 1 + lag（正=间隔等待，负=lead 重叠）；口径用**日历日**（MS Project「edays」语义——AgentPM 无工作日历域，引入工作日历是独立 backlog）；时间线连线注记「+N 天」（|N|≥1 时）；auto_scheduled 项受影响，手排期项不传播（M14 语义不变）。

**Z.2 跨项目里程碑路线图：同类 Community 层普遍缺位**

- GitLab Roadmap 只在 group 级渲染 epics+milestones 时间线，**跨项目视图是多年 open request**（[epic #1105](https://gitlab.com/groups/gitlab-org/-/epics/1105)）；保存 roadmap 视图也是 open issue（[#231522](https://gitlab.com/gitlab-org/gitlab/-/issues/231522)）。
- OpenProject **Team Planner（按人周历拖拽排期）是 Enterprise 独占**（[文档](https://www.openproject.org/docs/user-guide/team-planner/)），社区版建议用 Gantt 替代（[12.1 发布博客](https://www.openproject.org/blog/openproject-12-1-release/)）。
- → AgentPM 取舍：`GET /portfolio/roadmap`——调用方可见项目（`_visible` 三层，与组合总览同口径）的全部里程碑按 due_date 排布：行=项目、条=里程碑（进度条 done_ratio + 超期红 + 当日竖线），前端「📅 路线图」页（Dashboard 组合卡入口）——**跨项目时间线对 AgentPM 是纯投影聚合**（GitLab 的 epic #1105 缺口在事件溯源+成员可见性模型下不存在）。按人周历（team planner 面）仍留 backlog（Enterprise 价值面 + 无工时日历域）。

**Z.3 里程碑燃尽：不绑 sprint 的时间盒进度趋势**

- Jira 内建 sprint burndown/velocity（[官方教程](https://www.atlassian.com/agile/tutorials/burndown-charts)）；Taiga 是开源 Scrum 报表最全（burndown 内建，[评测](https://spryn.io/blog/agile-sprint-management/best-self-hosted-sprint-management-tools-in-2026)）；Plane Cycles 也有 burndown + velocity 仪表（[文档](https://docs.plane.so/core-concepts/cycles)）。
- → AgentPM 取舍：AgentPM 无 Cycles（§L.2），燃尽绑**里程碑**（due_date 即时间盒终点）：`GET /milestones/{id}/burndown`——**事件重放** item.status_changed 按 done 事件日累计关联项完成数 → 剩余曲线 vs 理想线（created→due 线性），**纯事件重放零新表**（事件溯源红利，同 Z.2）；报表页「🔥 燃尽」卡选里程碑渲染 SVG 折线 + 今日竖线；速率（周完成数）作为燃尽卡注记，不单独成卡。done 重放口径=首次进入 done 组的日期（from 非 done→to done）。

**Z.4 M27 设计映射与验证纪律（沿用）**

- I83 lag 排期联动：M14 传播引擎接入 lag_days（正 lag/负 lead）+ 时间线连线「+N 天」注记。
- I84 跨项目里程碑路线图：`/portfolio/roadmap` 投影聚合 + 「📅 路线图」页。
- I85 里程碑燃尽：`/milestones/{id}/burndown` 事件重放 + 报表燃尽卡；docs/12 §24 + 冒烟 33 于 I85 + 审阅。
- 验证纪律：每迭代只跑相关测试（动 scheduling/传播引擎则升级相关面）；全量收敛至 M27 审阅。

**Z.5 M27 取舍**

M27 = **排期深化三件套**：I83 lag 排期联动（lag/lead 接入 M14 传播）/ I84 跨项目里程碑路线图（`/portfolio/roadmap` 补 GitLab #1105 缺口）/ I85 里程碑燃尽（事件重放 + 报表卡）+ docs/12 §24 + 冒烟 33 + M27 审阅，约 9 人日。工作日历、按人周历（team planner 面）、独立速率卡、Cycles 留 backlog。

## AA. M28 前置调研：落地闭环——工时锁定审批 / 成员负载横切 / 打印视图（2026-09-05）

> 目标协议触发：M27 审阅通过后开启。防重查：评论删除（M18 已实现）、事件归档（M8/M10/M11 三次论证留 backlog）、digest（三次）、Cycles（§L.2）——均不查。

**AA.1 工时锁定与审批（Redmine 插件生态 / Tempo 模式）**

- Redmine 原生只有记时无审批；完整的 **log → submit → lock → approve** 流靠插件（[Redmineflux Timesheet](https://www.redmine.org/plugins/redmineflux-timesheet-plugin)、[Easy8 Timesheet](https://www.easy8.com/redmine-timesheet)——「完成后锁定并送经理审批，经理纵览下属工时」）。[ProWorkflow](https://help.proworkflow.com/en/articles/15999078-how-to-use-timesheet-approval) 把语义讲透：**锁定 = 冻结该期间的记时与修改**，未经审批不得再动；[Tempo](https://help.tempo.io/timesheets/latest/understanding-the-project-time-approval-workflow) 按期间审批（period approval）而非逐条。[Ones 对比文](https://ones.com/blog/top-6-open-source-time-tracking-project-management-platforms-compared/)指出 Taiga 等开源工具普遍缺审批门——**计薪/结算场景的刚需**。[OpenProject](https://www.openproject.org/docs/user-guide/time-and-costs/time-tracking/) 原生有「My time tracking」周历但审批/锁定未见开源版（Enterprise 时间锁定）。
- 对本项目的映射：M19 已有 time.* 事件与 CRUD，缺「期间完整性治理」。事件溯源天然适配：`timesheet.submitted/approved/rejected` 事件 + **approved 即锁定该成员该期间**（409 拒绝再记/改/删，rejected 解冻可改），Owner 审批（复用成员角色），审批留痕走事件流（rebuild 一致）。

**AA.2 成员负载横切（OpenProject Resource planner / Team Planner）**

- [OpenProject 17.7](https://www.openproject.org/blog/resource-management-capacity-planning/) 新增 Resource management 模块：四视图容量规划、「理解负载 + 找到未分配工作」；[Team Planner](https://www.openproject.org/) 是周/双周日历拖拽分配 + **负载总览**。官方定位：[帮助组织计划容量、分配工作、跨团队均衡负载](https://www.openproject.org/docs/use-cases/resource-management/)——跨项目成员维度是资源管理的核心视角。
- 对本项目的映射：M23 组合总览是**项目维度**（行=项目五桶），M12 我的工作是**个人待办清单**；中间缺「管理者视角的成员横切」。`GET /portfolio/workload`（`_visible` 项目横切按成员聚合：活跃项/超期/近 7 天工时）纯投影零新表，与 roadmap/report 同构；前端「👥 负载」页行=成员。拖拽式 Team Planner 周历（按人重排期）留 backlog——本轮做只读负载视图（信息价值/实现成本比最高）。

**AA.3 打印视图（OpenProject PDF 报表 / Redmine #6280 缺口）**

- [OpenProject 14.1](https://www.openproject.org/blog/openproject-14-1-release/) Gantt 图 PDF 导出（A4/Letter/Tabloid 纸型）+[工作包 PDF 报表](https://www.openproject.org/docs/user-guide/work-packages/exporting/)（封面+目录+描述）——面向「向管理层呈现时间线/月报」；Redmine 的 [多 issue PDF 导出 #6280](https://www.redmine.org/issues/6280) 十余年未实现（仅当前页）；Taiga/Plane 只有数据导出（JSON/CSV）[无打印视图](https://community.taiga.io/t/follow-multiple-projects-at-once-main-dashboard/672)。
- 对本项目的映射：服务端 PDF 生成（Headless Chrome/报表库）成本高且引新依赖——**print CSS 路线**（`@media print` 隐藏导航/操作件 + 看板/列表/报表打印友好排版 + `window.print()` 按钮）零后端改动，浏览器「另存为 PDF」即得报表；这正对齐「最小可用 + 零新依赖」纪律。服务端报表 PDF 留 backlog。

**AA.4 M28 设计映射与验证纪律（沿用）**

- I86 工时锁定与审批：submit/approve/reject 事件 + approved 锁定期间（409）+ 审批页卡片。
- I87 成员负载横切：`/portfolio/workload` 投影聚合 + 「👥 负载」页。
- I88 打印视图：print CSS + 打印按钮（看板/列表/报表）；docs/12 §25 + 冒烟 34 于 I88 + 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M28 审阅。

**AA.5 M28 取舍**

M28 = **落地闭环三件套**：I86 工时锁定与审批（submit→approve 计薪冻结，Redmine 插件语义原生内建）/ I87 成员负载横切（`/portfolio/workload` 补 OpenProject resource 视角缺口）/ I88 打印视图（print CSS 对齐 OpenProject 报表呈现、零新依赖）+ docs/12 §25 + 冒烟 34 + M28 审阅，约 9 人日。按人拖拽周历（team planner 编辑面）、服务端报表 PDF、本体事件归档留 backlog。

## AB. M29 前置调研：效率与可观测——个人排期月历拖拽 / 看板卡片快捷编辑 / 运行聚合报表（2026-09-05）

> 目标协议触发：M28 审阅通过后开启。防重查：候选池六项逐一 grep——评论引用回复/多基线趋势/模板套用增强/字段直编/运行报表/月视图拖拽均无调研记录；M28 刚做的工时审批·负载·打印不重查。

**AB.1 个人排期月历与拖拽改期（OpenProject Calendar）**

- [OpenProject Calendar](https://www.openproject.org/docs/user-guide/calendar/)：月/周切换、工作包卡片**拖拽改期**（官方 changelog 明确语义：**左柄拖动改 start、右柄拖动改 finish**、拖动卡片整体平移）、**点击或拖选日期范围直接建工作包**；保存时自动顺延到下一个工作日（[admin guide](https://www.openproject.org/docs/system-admin-guide/calendars-and-dates/)）。
- 对本项目的映射：M20 拖拽改期落在**项目时间线**（条形图），个人视角缺「我的所有项目的有日期任务按日历排布」——`GET /my/work` 已聚合指派项，扩展携带 start/due 后即可出「我的日程」月历；拖拽落单 PATCH 复用 M14/M20 审计链；拖选范围快捷建任务（预填 start/due）对齐 OpenProject。工作日顺延留 backlog（无工作日历，M27 已论证）。

**AB.2 看板卡片快捷编辑（Kanboard 内联缺口 / WeKan 侧栏）**

- Kanboard **没有真正的卡片内联编辑**——编辑要走任务页或下拉菜单，社区多任务内联/批量编辑是长期诉求（[issue #3142](https://github.com/kanboard/kanboard/issues/3142)）；插件生态补卡片快捷按钮（edit/close/move/update date）；WeKan 用**侧栏面板**组织卡片属性 + 键盘快捷键（[docs](https://wekan.github.io/wekan-doc/user/Board-Administration.html)）。
- 对本项目的映射：M22 批量编辑覆盖「多选统一改」，M26 WIP 徽标覆盖「警示」；单卡片的优先级/执行者/日期/状态仍要打开抽屉才能改——看板卡片**行内快捷控件**（点卡片上的 ⚡ 弹出快捷编辑条：状态下拉/优先级/执行者/截止日，复用 patch_item 校验与审计）补齐高频微操作路径。

**AB.3 运行聚合报表（Langfuse 可观测语义）**

- Agent 可观测平台的标准面：每次运行的 latency、token、**cost、错误率**按项目/模型聚合（[Langfuse](https://langfuse.com/) MIT 开源可自托管、含 spend alerts；[LangSmith](https://www.langchain.com/langsmith/observability) 能力强但闭源 SaaS-only；[对比](https://www.datacamp.com/blog/langfuse-vs-langsmith)）。监控回答「指标变没变」，可观测回答「为什么变」（[LangChain 综述](https://www.langchain.com/resources/llm-observability-tools)）。
- 对本项目的映射：runs/spans 域已有运行与步骤数据（M5 起），但只有逐运行列表没有聚合面——replay provider 无真实 token/cost，不造假数；**可真实聚合的是**：运行数（按项目/角色/状态）、成功率、平均时长、Gate 挂起率、每运行步骤数（spans 计数）。`GET /runs/report` 纯投影聚合 + RunsPage 报表卡。token/cost 字段在 runs 载荷留位（接入真实 provider 后即有数）。

**AB.4 M29 设计映射与验证纪律（沿用）**

- I89 个人排期月历（/my/work 扩展日期 + 月历页拖拽改期/拖选建任务）。
- I90 看板卡片快捷编辑条（⚡ 直改状态/优先级/执行者/截止日，全走既有 PATCH 审计）。
- I91 运行聚合报表（`GET /runs/report` + RunsPage 报表卡；token/cost 载荷留位）；docs/12 §26 + 冒烟 35 于 I91 + 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M29 审阅。

**AB.5 M29 取舍**

M29 = **效率与可观测三件套**：I89 个人排期月历（OpenProject calendar 个人面 + 拖拽复用 M20 改期链）/ I90 看板卡片快捷编辑（补 Kanboard #3142 型内联缺口）/ I91 运行聚合报表（Langfuse 可观测语义的纯投影切片，token/cost 留位）+ docs/12 §26 + 冒烟 35 + M29 审阅，约 9 人日。评论引用回复、多基线趋势、工作日顺延、真实 token 成本接入留 backlog。

## AC. M30 前置调研：治理洞察——项目健康评分 / 健康趋势重放 / 评论引用回复（2026-09-05）

> 目标协议触发：M29 审阅通过后开启。防重查：健康评分/引用回复/健康趋势均无记录；多基线历史（M24 已做）、工作日顺延（M27 论证 backlog）、依赖图独立视图（时间线 M21 连线已覆盖核心面）不重查。

**AC.1 项目健康评分卡（CHAOSS 指标模型 / Taiga Iocane）**

- CHAOSS 发布了标准化的**开源项目健康指标模型**（Starter Model：活跃度、响应性、交付节奏等维度组合）；Taiga 内建 **Iocane 团队健康度量**（taiga.io）；WeKan 用户长期诉求主控面板（issue #4223——linked cards 之外没有自动聚合视图）。共同语义：**健康 = 多因子组合出单一可比数字**，而非让管理者自己看一堆原始计数。
- 对本项目的映射：组合总览（I72）给的是原始五桶/超期/工时计数——「哪个项目需要关注」仍要人脑综合。四因子加权评分（0-100）：**超期率**（overdue/active，40%）、**滞留率**（活跃超 14 天占比，20%）、**吞吐动量**（近 7 天 done/active，30%，上限截断）、**Gate 挂起率**（pending/active，10%）；纯投影可算（report 已有全部原料），`GET /portfolio/health` 出分 + 组合总览行内评分徽标（绿 ≥80 / 黄 60-79 / 红 <60）。

**AC.2 健康趋势：事件重放任意时点评分（事件溯源红利）**

- 健康分单点数字的追问永远是「比上周呢？」——投影表只存当前值，历史回溯需要事件重放（与 I85 燃尽同构：燃尽重放 status_changed，趋势重放**全项目项状态/日期事件**）。CHAOSS 模型强调健康是**趋势**而非快照。
- 对本项目的映射：`GET /projects/{id}/health/history?days=30`——事件重放 item.created/item.status_changed/item.updated（due_date 变化）重建每个周界时点的因子值 → 评分序列 → SVG 迷你趋势线（报表页健康卡内嵌）。零新表，rebuild 一致性由事件流天然保证。

**AC.3 评论引用回复（GitHub quote reply 语义）**

- GitHub 原生 **Quote reply**（选区引用 + r 快捷键 + 按钮）是讨论效率的标配；Redmine 核心无引用回复，靠 blockquote 语法 + 插件（Redmine Reply Button）补 UX 缺口；格式摩擦本身是 Redmine #15520 的核心抱怨。
- 对本项目的映射：M20 评论已渲染 GFM（marked+DOMPurify）——blockquote 渲染免费可用，缺的只是「❝ 引用」按钮：把原评论 body 逐行加 blockquote 前缀 + @作者 开头填入输入框并聚焦（存储仍是纯文本，M20 契约不变）。纯前端 + 现有渲染链。

**AC.4 M30 设计映射与验证纪律（沿用）**

- I92 项目健康评分：四因子加权 + `GET /portfolio/health` + 组合总览评分徽标。
- I93 健康趋势：事件重放周界评分序列 + 报表页健康卡 SVG 迷你趋势线。
- I94 评论引用回复：CommentsModal「❝」按钮（逐行 blockquote + @作者开头）；docs/12 §27 + 冒烟 36 于 I94 + 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M30 审阅。

**AC.5 M30 取舍**

M30 = **治理洞察三件套**：I92 项目健康评分（CHAOSS 多因子语义落地，管理面从「看数」到「看分」）/ I93 健康趋势（事件重放任意时点评分——事件溯源红利第三例）/ I94 评论引用回复（GitHub 语义、零后端）+ docs/12 §27 + 冒烟 36 + M30 审阅，约 9 人日。引用键盘快捷键、CHAOSS 全维度指标、依赖图独立视图（时间线连线已覆盖）留 backlog。

## AD. M31 前置调研：响应力——键盘优先操作 / 通知事件细分 / 响应性指标（2026-09-05）

> 目标协议触发：M30 审阅通过后开启。防重查：候选池六项逐一 grep——引用键盘快捷键（§AC.5 留 backlog，无调研记录）、通知偏好细分（M11 只做邮件/站内两级，事件类型粒度无记录）、多基线趋势（§AB 留 backlog 无记录）、CHAOSS 全维度（§AC.1 只取了 Starter 多因子语义）、依赖图独立视图（M21 时间线连线已覆盖，维持不查）、工时审批代理（I86 刚做，不查）。

**AD.1 键盘优先操作面（Linear / GitHub command palette / Dynatrace 规范）**

- Linear 是键盘优先 PM 工具的事实标准：⌘K 命令面板 + `C` 新建 issue + `?` 可搜索快捷键帮助浮层 + `G` 前缀页间导航（[Linear changelog](https://linear.app/changelog/2021-03-25-keyboard-shortcuts-help)、[Shortcuts.design](https://shortcuts.design/tools/toolspage-linear/)）；GitHub 命令面板同为 ⌘K 且支持自定义（[docs](https://docs.github.com/en/get-started/accessibility/github-command-palette)、[changelog](https://github.blog/changelog/2022-02-03-customizing-command-palette-keyboard-shortcuts-beta/)）；Dynatrace 的快捷键规划指南把 **⌘K / ? / j-k** 列为行业标准组合（[guide](https://developer.dynatrace.com/develop/guides/keyboard-shortcuts/plan-keyboard-shortcuts/)）。j/k 列表导航是 vim 血统的看板通行做法（GitHub 列表同款）。
- 对本项目的映射：⌘K 已有（M22 搜索入口 + I10 NL 命令），缺的是**发现性**与**列表内导航**——①`?` 快捷键帮助浮层（可搜索，穷举当前生效快捷键，权威清单从此有处可查）；②看板 j/k 选中卡片 + Enter 打开评论抽屉（不与卡片行内 ✕/⚡ 按钮抢焦点，输入框聚焦时自动让路）；③`C` 新建任务（看板/列表上下文，复用既有 CreateModal）。纯前端零后端。

**AD.2 通知偏好按事件类型细分（GitLab Custom 级别 / GitHub Custom watch）**

- GitLab 通知级别五档 watch/participate/mention/custom/disabled，其中 **Custom** = 逐事件类型开关（issues/MRs/comments…按项目设置）（[docs](https://docs.gitlab.com/user/profile/notifications/)）；GitHub 仓库级 Custom watch 同样是事件类型 checkbox（[docs](https://docs.github.com/subscriptions-and-notifications/get-started/configuring-notifications)）。共同语义：**噪声治理的最后一级是「按事件类型说不要」**——前面的档位只决定「因为什么收到」，Custom 决定「哪类不要」。
- 对本项目的映射：M11 的 user_prefs 只有 email_enabled 两级 + M18 per-item watch；扩为**事件类型 × 站内/邮件双通道开关**（item.status_changed / comment.created / mention / approval.requested / timesheet 待审类），`GET/PUT /me/notification-prefs`；投递统一收口在 **plan_notifications**（邮件与站内同走该闸门、逐事件查偏好）——GitLab #410008（「关了还发」）的教训 = 不在各投递通道各查一遍。

**AD.3 响应性指标（CHAOSS Responsiveness / Time to First Response）**

- CHAOSS Starter Model 四指标含 **Time to First Response** 与 Change Request Closure Ratio，维度族单列 **Responsiveness**（[Starter Model](https://www.chaoss.community/kb/metrics-model-starter-project-health/)、[维度族](https://www.chaoss.community/kbtopic/all-metrics-models/)）；I92 四因子覆盖了超期/滞留/吞吐/Gate，但**没有度量「人对人的响应速度」**——审批挂起多久有人理、评论发出多久有人回，恰是协作项目最被追问的数字。
- 对本项目的映射：事件流里原料齐全——**审批响应时长**（approval.requested → 同 Gate 的 granted/rejected 逐对配对，均值/中位/超 48h 占比）与**评论首响应时长**（comment.created → 下一条件非作者的 comment 或状态变更）；`GET /projects/{id}/responsiveness` 聚合输出 + 报表页「⏱ 响应力」卡（延续 I91 聚合/I93 重放范式，事件溯源红利第四例）。

**AD.4 M31 设计映射与验证纪律（沿用）**

- I95 键盘优先操作面：`?` 帮助浮层 + 看板 j/k 导航 + `C` 新建；纯前端，无新后端面。
- I96 通知偏好事件细分：notification_prefs 扩展（事件类型 × 双通道）+ plan_notifications 投递收口 + 设置 UI；docs/12 §28。
- I97 响应性指标：审批/评论首响应聚合端点 + 报表卡；**新增冒烟 37** 于 I97 + 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M31 审阅。

**AD.5 M31 取舍**

M31 = **响应力三件套**：I95 键盘优先（Linear 语义的操作发现性与导航面）/ I96 通知事件细分（GitLab Custom 的投递收口语义）/ I97 响应性指标（CHAOSS Responsiveness 落地）——主题统一「响应力」：**操作响应**（键盘）、**通道响应**（通知偏好）、**人对人响应**（指标）。+ docs/12 §28 + 冒烟 37 + M31 审阅，约 9 人日。引用键盘快捷键、多基线趋势、工作日顺延、CHAOSS 社区维度（贡献者成长类，AgentPM 无 contributor 演化语义）留 backlog。

## AE. M32 前置调研：引擎与入口——时间触发自动化 / 外部 intake 收件 / 列表分组聚合（2026-09-06）

> 目标协议触发：M31 审阅通过后开启。防重查：候选池 grep——引用快捷键/多基线趋势/工作日顺延/工时审批代理均无调研记录；依赖图独立视图维持不查。本轮三路新调研（时间触发规则 / 表格分组聚合 / 外部收件通道），选定 **M32 = 引擎与入口三件套**。

**AE.1 时间触发自动化（YouTrack On-schedule / Kanboard 插件语义）**

- AgentPM 规则引擎（M9）是**纯事件触发**（post-emit hook）——而同类工具的规则都有时间维度：YouTrack 的 **On-schedule** 规则按 cron 式调度扫描并升级逾期任务、通知负责人（[PVS-Studio 实践](https://pvs-studio.com/en/blog/posts/0853/)）；Kanboard 插件「列内停滞 N 天自动清 due」（[插件页](https://kanboard.org/plugins.html)）与「给无日期卡自动派日期」（[TaskAssignDateToUndated](https://github.com/dmorlitz/kanboard-TaskAssignDateToUndated)）；Kanban Tool 的 **Recurring Tasks** 按日/周/月定时自动建卡（[blog](https://kanbantool.com/blog/automating-cyclical-work-in-kanban-for-higher-efficiency/)）。
- 对本项目的映射：规则引擎加 **schedule 触发器**（规则声明 `trigger: "daily"`；扫描器线程复用 mailer 的后台线程模式，逐项目评估既有条件谓词 → 命中即走既有动作执行器：升优先级/移列/notify/**周期建卡**）——动作产生的真实事件（item.updated/automation.fired）回流事件流，投影与审计零新增概念。防重靠「每次扫描一条 `automation.swept` 心跳事件」幂等去重。

**AE.2 外部 intake 收件（Trello 板级邮箱 / Jira mail handler 的 HTTP 最小面）**

- Jira 内建 mail handler（POP/IMAP 轮询把邮件变 issue，[官方](https://support.atlassian.com/jira-cloud-administration/docs/create-issues-and-comments-from-email/)）+ JSM 表单门户；Trello 每板唯一邮箱地址、表单工具发邮件即建卡（[社区](https://trello.com/) / [r/trello 实践](https://www.reddit.com/r/trello/comments/k4p0vi/forms_submission_to_trello/)）；开源侧 Google Forms→Trello 脚本同理（[submit-googleforms-to-trello](https://github.com/kylepinecroft/submit-googleforms-to-trello)）。共同语义：**给容器一个免登录的「入口地址」，外部提交进来就是一等卡片**。
- 对本项目的映射：**intake 令牌 + 公开 JSON 端点**（Trello 邮箱语义的 HTTP 版，零 IMAP 基础设施）：Owner 生成/吊销项目级 intake token（投影表）；`POST /intake/{token}`（常量时间比较、字段白名单 title/desc/priority、actor=intake、复用 create_item 全校验）+ `/#/intake/{token}` 公开表单页（标题+说明两栏）。IMAP 邮件轮询留 backlog（重依赖且被 HTTP 端点覆盖 90% 场景）。

**AE.3 列表分组聚合（Airtable/NocoDB 组头统计语义）**

- 表格视图的分组+聚合是数据组织标配：Airtable group by 多级 + 组尾 count/sum 统计（社区公认效率标杆，[对比讨论](https://community.baserow.io/t/grouping-by-field-data/492?page=2)）；NocoDB 支持至多三级分组 + 组视图统计（[docs](https://nocodb.com/docs/product/tables/table-operations/group-by)、[社区](https://community.nocodb.com/t/summary-stats-not-showing-on-the-group-view/1458)）；Grist 用 summary table 表达聚合（[社区](https://community.getgrist.com/t/summary-tables-and-non-formula-columns/1156)）。
- 对本项目的映射：列表视图加 **group by**（复用 M6 字段分组的 fieldOptions 与 `?group=` 语义）+ **组头行**（该组计数 + spent_minutes 合计 + 折叠）——纯前端，数据全在已返回的 items 里；与 I79 渐进渲染兼容（分组作用于已显示行）。

**AE.4 M32 设计映射与验证纪律（沿用）**

- I98 时间触发自动化：schedule 触发器 + 扫描线程 + 心跳幂等 + 规则 UI 加触发器选择；单测（扫描命中/心跳防重/动作事件回流）。
- I99 外部 intake：intake token 投影 + 公开端点 + 公开表单页 + Owner 管理 UI；单测（token 鉴权/字段白名单/吊销 401/事件归账）。
- I100 列表分组聚合：group by 选择器 + 组头统计 + 折叠；vitest 聚合口径；**新增冒烟 38**（时间触发端到端/intake roundtrip/分组对账）于 I100 + 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M32 审阅。

**AE.5 M32 取舍**

M32 = **引擎与入口三件套**：I98 时间触发自动化（规则引擎的时间维度——YouTrack/Kanboard 语义）/ I99 外部 intake 收件（免登录入口地址——Trello/Jira 语义的 HTTP 最小面）/ I100 列表分组聚合（Airtable 组头统计语义）——主题统一「引擎与入口」：**引擎补节拍**（时间）、**容器加入口**（intake）、**数据给组织**（分组聚合）。+ docs/12 §29 + 冒烟 38 + M32 审阅，约 9 人日。IMAP 邮件轮询、多级分组、按组聚合排序、引用快捷键、多基线趋势留 backlog。

## AF. M33 前置调研：纵深——关键路径高亮 / 子任务进度汇总 / 工作项归档与回收站（2026-09-06）

> 目标协议触发：M32 审阅通过后开启。防重查：候选池 grep——引用快捷键/多基线趋势/工时审批代理/IMAP 轮询无调研记录；「关键路径」仅出现于验收语境与 OpenProject 排程讨论（无 CPM 算法记录）；工作项删除在 §Y.1（M26）留过「统一考量」backlog。

**AF.1 关键路径高亮（CPM 正逆传递）**

- 关键路径法（CPM）是排程科学的底座：**正向传递** ES/EF（`EF = ES + duration`）、**逆向传递** LS/LF（`LS = LF − duration`）、**Float = LF − EF**，float=0 的任务链即关键路径——任何一环延误直接顺延项目终点（[PMI](https://www.pmi.org/learning/library/critical-path-method-calculations-scheduling-8040)、[Wrike 公式](https://www.wrike.com/blog/critical-path-is-easy-as-123/)、[Asana](https://asana.com/resources/critical-path-method)）；ProjectManager/Smartsheet 都把关键路径渲染为 Gantt 上的红色链（[渲染](https://www.projectmanager.com/blog/critical-path-on-gantt)）。
- 对本项目的映射：M14 已有依赖图（depends_on + lag + auto_scheduled 级联）——CPM 只需在**同一张图**上做正逆两遍传递：`GET /projects/{id}/critical-path`（按已排期项的 start/due 迭代后继链，float=0 链输出）+ TimelinePage 关键链条形红框高亮 + 开关切。零新表、纯投影计算（事件溯源红利第五例——图即事件投影）。

**AF.2 子任务进度汇总（GitHub sub-issue progress 语义）**

- GitHub 原生 **sub-issue progress fields**：父 issue 自带「n/m 完成」进度字段、自动聚合（[官方](https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-parent-issue-and-sub-issue-progress-fields)、[sub-issues 发布](https://github.blog/engineering/architecture-optimization/introducing-sub-issues-enhancing-issue-management-on-github/)）；Jira 靠 automation 模板汇总 story points/状态到父任务（[模板](https://www.atlassian.com/software/jira/automation-template-library/sum-up-story-points)），首子任务开始→父转 in_progress 也是常见规则（[KB](https://support.atlassian.com/automation/kb/automation-rule-to-transition-a-parent-issue-to-in-progress-when-its-first/)）。
- 对本项目的映射：M24 子任务层级（parent_id）已存在但父任务**看不到子任务进度**——父卡/列表行加「子任务 n/m」徽标（done 子任务数/总子任务数，纯投影聚合、spent 合计同卡头）+ 时间线父条形上进度条。零后端（聚合在前端于已有 items 内完成）或可选 portfolio 口径。

**AF.3 工作项归档与回收站（软删除 + 保留期）**

- 现状格局：monday.com 有专门 Trash 区（[docs](https://support.monday.com/hc/en-us/articles/115005312729-The-trash-section)）、Azure DevOps 删除的工作项进 **Recycle Bin 可恢复**（[docs](https://learn.microsoft.com/en-us/azure/devops/boards/backlogs/remove-delete-work-items?view=azure-devops)）、Teamhood 删除项保留 30 天（[docs](https://teamhood.com/knowledge-base/best-practices/restoring-deleted-content/)）；**Jira 没有原生回收站**——删错只能整体回滚备份（[社区抱怨](https://community.atlassian.com/forums/Jira-questions/Is-it-possible-to-retrieve-deleted-tasks-from-a-Kanban-Board/qaq-p/971594)）；Vikunja 社区把软删除列为防数据丢失核心诉求（[请求](https://community.vikunja.io/t/add-soft-delete-and-restore-functionality-for-projects-and-tasks-to-prevent-irreversible-data-loss/4388)）。共同语义：**删除必须是可逆的软状态，回收站有入口有保留期**。
- 对本项目的映射：AgentPM 工作项**至今无法删除**（§Y.1 backlog「统一考量」）——`item.archived` / `item.restored` 显式事件 + items 投影 archived_at 列 + 看板/列表默认排除归档项 + 「🗑 回收站」抽屉（归档项列表 + 恢复按钮，事件溯源下恢复零成本、永不真删）。关系/子任务随归档悬置、恢复即复活。

**AF.4 M33 设计映射与验证纪律（沿用）**

- I101 关键路径：CPM 正逆传递 + `GET /projects/{id}/critical-path` + TimelinePage 红框高亮开关；单测（链计算/float 手算/lag 参与/环安全）。
- I102 子任务进度 rollup：父卡/列表行「子任务 n/m」徽标（含时间线进度条）；vitest 聚合口径。
- I103 工作项归档与回收站：archived/restored 事件 + archived_at 列迁移 + 回收站抽屉 + 默认排除；**新增冒烟 39**（关键路径手算对账/rollup 计数/归档恢复 roundtrip + rebuild 一致）于 I103 + 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M33 审阅。

**AF.5 M33 取舍**

M33 = **纵深三件套**：I101 关键路径高亮（时间纵深——排程科学补最后一块）/ I102 子任务进度汇总（层级纵深——GitHub sub-issue progress 语义）/ I103 工作项归档与回收站（数据纵深——软删除+可恢复，补「统一考量」backlog）+ docs/12 §30 + 冒烟 39 + M33 审阅，约 9 人日。硬删除（真删+保留期清理作业）、多级 rollup（孙任务向爷任务）、CPM 资源平衡、IMAP 轮询、引用快捷键、多基线趋势留 backlog。


## AG. M34 前置调研：时间关怀——工作日历跳休 / 到期邻近提醒 / 基线 S 曲线对比（2026-09-06）

> 目标协议触发：M33 审阅通过后开启。防重查：候选池 grep——引用快捷键（§AC/§AD/§AF 三轮留 backlog 无调研记录）、多基线趋势（§AB/§AF 留 backlog，M24 快照已有、时序对比无调研记录）、工作日顺延（M27 论证「无工作日历域」backlog，无调研记录）、工时审批代理（I86 刚做不查）、IMAP 轮询（§AE 留 backlog）均无调研记录。

**AG.1 工作日历与非工作日落点顺延（OpenProject 12.3 语义）**

- OpenProject 12.3「高级排期」：管理员在 Administration → Calendars and dates 全局定义**工作周 + 非工作日**（法定/本地节假日），**自动排期模式**的工作包计算 start/finish 时**跳过非工作日**，手排期（manual）完全不受影响（[系统管理文档](https://www.openproject.org/docs/system-admin-guide/calendars-and-dates/)、[12.3 发布博客](https://www.openproject.org/blog/openproject-12-3-release/)）；保存日期时**自动顺延到下一个工作日**（[admin guide](https://www.openproject.org/docs/system-admin-guide/calendars-and-dates/)）；用户级 Availability（个人休假+公司假日）是另一层（[账号设置](https://www.openproject.org/docs/user-guide/account-settings/schedule-and-availability/)），个人层留 backlog。
- 对本项目的映射：M14 自动排期（auto_scheduled）按**日历日**直算——M27 论证过「无工作日历域」backlog 本轮转正：`calendar.holiday_added`/`calendar.holiday_removed` 显式事件 + non_working_days 投影表（进 drop 清单）+ 设置页「📅 工作日历」管理卡（owner 加/删日期）；M14 传播的**落点顺延**辅助函数——后继 start = 前置 due+1+lag 与各项 due 若落在非工作日则顺延至下一工作日；手排期项零感知（OpenProject manual 语义）；工期保持日历日跨度不重算（比 OpenProject 工作日工期轻量、聚焦「截止日落在周六日」核心痛点）。

**AG.2 到期邻近提醒（Plane/Linear 语义——sweep 引擎的第一公民应用）**

- Linear：Issue Reminders（`H` 键任意时刻设「4pm」「next Tuesday」到点进 Inbox，[changelog](https://linear.app/changelog/2023-01-31-issue-reminders)）+ 到期邻近/逾期通知（[due dates 文档](https://linear.app/docs/due-dates)）+ email digest（[notifications](https://linear.app/docs/notifications)）；Plane：automations 对 assignee/subscriber 发「due date approaching」站内+邮件（[automations 文档](https://docs.plane.so/automations/overview)），社区仍在要更强的邮件提醒（[#7340](https://github.com/makeplane/plane/issues/7340)）；Taiga 至今**没有**到期通知、长年 feature request（[#27](https://github.com/kaleidos-ventures/taiga-front/issues/27)、[社区帖](https://community.taiga.io/t/no-email-notification-on-due-date-of-story/3481)）。共同语义：**到期提醒是调度引擎的第一公民应用**——Plane 直接做在 automations 里而非独立模块。
- 对本项目的映射：I98 已有每日 sweep ticker（run_daily_sweep + automation.swept 心跳幂等）+ I96 通知偏好闸门（pref_allows 双通道）——**内建到期提醒只是 sweep 的新增动作**：run_daily_sweep 对「due ∈ [today, today+N] 且未完成未归档且有 assignee」的项 emit `item.due_soon_notified`（投影器走 _notify(kind="due_soon")——NOTIFY_KINDS 五类扩六类、默认开）+ 邮件通道同闸门；**幂等天然成立**：sweep 每日至多一次 + 同一 sweep 内先查当日已通知集合；N 天窗口全局设置（默认 3）。零新引擎零新表（事件即审计、心跳保证节拍）。

**AG.3 基线 S 曲线对比（EVM PV/EV 双线 + SPI——事件溯源红利第六例）**

- EVM 标准语义：**PV**（计划值，按基线计划累计）、**EV**（挣值，按实际完成累计的计划工时）、**AC**（实际成本）；**S 曲线** = PV/EV 双线随时间累计图（形状缓 S），**SPI = EV/PV**（<1 落后 =1 持平 >1 超前），SV = EV−PV（[BVOP](https://bvop.org/define/earnedvaluemanagement.html)、[PMI](https://www.pmi.org/learning/library/earned-value-management-systems-analysis-8026)、[Xurrent——基线本质是快照](https://learning.xurrent.com/project_manager12)）；MS Project/ProjectManager 的 **Actual vs Baseline S-curves** 是基线对比的标准渲染（[ProjectManager](https://www.projectmanager.com/blog/s-curve-project-management)）；开源侧 OpenProject EVA 列表显示 work vs spent 与 progress（[功能页](https://www.openproject.org/collaboration-software-features/project-management-process/)），完整 S 曲线多靠外接 BI。
- 对本项目的映射：M24 baselines 快照已有（snapshot JSON 含每项 start/due/estimate_hours）+ I93 事件重放周界采样成熟——`GET /projects/{id}/baseline-curve?baseline_id=`：**PV 曲线**按周界采样累计基线项 estimate（按 due 时间分布：due≤采样日的项计入），**EV 曲线**事件重放 `item.status`→done 时点累计该基线内项的 estimate；双线 SVG 迷你图 + **SPI 手算卡**（末点 EV/PV，PV=0 诚实 None）+ 报表页「📈 S 曲线」卡（基线下拉选择）。零新表、纯投影+重放（**事件溯源红利第六例**——EV 即任意时点重放）。AC 第三线（spent 重放）与多基线并列对比留 backlog。

**AG.4 M34 设计映射与验证纪律（沿用）**

- I104 工作日历：calendar.holiday_added/removed 事件 + non_working_days 投影表 + M14 落点顺延辅助函数 + 设置页「📅 工作日历」卡；单测（周末顺延手算/节假日跨跳/删除恢复/手排期不动/rebuild 一致）。
- I105 到期提醒：sweep 动作 + item.due_soon_notified 事件 + NOTIFY_KINDS 第六类 due_soon + pref_allows 闸门 + 邮件通道；单测（N 天窗口边界/每日幂等/站内与邮件双闸/无 assignee 不发/rebuild）。
- I106 S 曲线：`GET /projects/{id}/baseline-curve` 端点 + 报表 SVG 双线 + SPI 手算；单测（PV 周界手算/EV 重放手算/SPI 空态/rebuild 一致）+ **冒烟 40**（跳休 roundtrip/提醒 roundtrip/S 曲线手算对账 + rebuild 一致）并入 I106 + M34 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M34 审阅。

**AG.5 M34 取舍**

M34 = **时间关怀三件套**：I104 工作日历跳休（排期关怀——M27 backlog 转正，OpenProject 落点顺延语义）/ I105 到期邻近提醒（人的关怀——Plane/Linear 语义，sweep 第一公民应用）/ I106 基线 S 曲线（趋势关怀——EVM PV/EV 语义，M24+I93 红利第六例）+ docs/12 §31 + 冒烟 40 + M34 审阅，约 9 人日。个人 Availability（休假层）、AC 第三线、多基线并列对比、IMAP 轮询、引用快捷键留 backlog。


## AH. M35 前置调研：通道与回复——IMAP 邮件转任务 / 常用回复 / 引用快捷键（2026-09-06）

> 目标协议触发：M34 审阅通过后开启。防重查：候选池 grep——Availability 休假层（§AG.1 仅留 backlog 无调研记录）、AC 第三线/多基线并列（§AG.5 仅留 backlog）、IMAP 轮询（§AE.2 仅留 backlog）、引用快捷键（§AC/§AD/§AF 三轮留 backlog）均无调研记录。

**AH.1 IMAP 邮件转任务（Redmine/Jira 邮件通道语义——intake 的邮箱入口）**

- Redmine：`rake redmine:email:receive_imap` cron 轮询邮箱，参数含 `--project`（路由目标）/`--tracker`/`--unknown-user`（未知发件人策略 ignore/accept/check 权限），**发件人邮箱必须匹配已有账号才能归账**（[官方 Wiki](https://www.redmine.org/projects/redmine/wiki/redminereceivingemails)、[配置指南](https://www.simplified.guide/redmine/incoming-email-configure)）；另有 `rdm-mailhandler.rb` Web Service 推送模式（绕开 IMAP 轮询）；Jira：POP/IMAP/Mail handler 轮询 + 项目级 vs 系统级 handler 决定路由与权限（[Atlassian 文档](https://confluence.atlassian.com/spaces/ADMINJIRASERVER0911/pages/1318890898)、[handler 作用域](https://community.atlassian.com/forums/Jira-Service-Management/Difference-between-project-and-system-mail-handlers/qaq-p/784380)）。共同语义：**轮询邮箱 → 发件人身份匹配归账（不匹配走降级策略）→ 规则路由到目标容器**。
- 对本项目的映射：Python 标准库 **imaplib** 零第三方依赖（与 SMTP 通道同构的 env 可选配置 `IMAP_HOST/IMAP_PORT/IMAP_USER/IMAP_PASS`，未配置即关闭）；ticker 线程轮询（I98 调度器同款，`scheduler_enabled` 开关复用）→ 每封未读邮件：`From` 邮箱匹配 `users.email` → 以该用户身份路由到**其可见的默认项目**（无匹配 → 降级 I99 intake 身份投公共表单项目）；主题=标题、正文=描述，复用 `create_item` 全校验链。与 I99 HTTP 端点互补：**HTTP 免登录入口 + 邮件被动入口**。多项目路由（subject 前缀 `[项目名]`）留 backlog。

**AH.2 常用回复（GitHub Saved Replies 语义——高频回复一键盘出）**

- GitHub：`Ctrl+.`（Mac `Cmd+.`）唤起 saved replies 面板、继续 `Ctrl+数字` 直选插入、输入即过滤（[官方文档](https://docs.github.com/en/get-started/writing-on-github/working-with-saved-replies/using-saved-replies)、[发布博客](https://github.blog/news-insights/saved-replies-keyboard-shortcuts/)）；社区实践把它当作 code review 标准化回复的核心效率工具（[Atomic Object](https://spin.atomicobject.com/github-saved-replies/)）。共同语义：**用户级常用语库 + 面板过滤 + 键位直选**。
- 对本项目的映射：saved_replies 用户级运行态表（缺省空、不进 drop 清单——同 notification_prefs 语义）+ `GET/POST/DELETE /me/saved-replies`（own-data，标题+正文 ≤2000）+ CommentsModal 「⌨ 常用回复」按钮与 `Ctrl+.` 唤起面板（输入过滤、↑↓ 选择、Enter 插入光标处）+ 评论框工具条「存为常用回复」（选中文本一键入库）。存储纯文本，渲染走既有 Markdown 管线零改动。

**AH.3 引用快捷键（I94 ❝ 的键位化——三轮 backlog 转正收尾）**

- 现状：I94 已做「❝」按钮引用回复（@作者+blockquote 预填）；GitHub 的 quote reply 有按钮 + `r` 快捷键双入口（§AC.1 调研过、键位一直留 backlog）；I95 SHORTCUTS 注册表（单一真源+isTypingTarget 让路）已为键位化铺好路。
- 对本项目的映射：看板 j/k 游标选中项后按 `R` → 直开 CommentsModal 并预填引用（复用 I94 引用预填函数）；CommentsModal 内 `Ctrl+Shift+R` 触发对原评论的 ❝；SHORTCUTS 注册表加条目 + `?` 浮层自动收录（零额外文案维护）。纯前端零后端。

**AH.4 M35 设计映射与验证纪律（沿用）**

- I107 IMAP 转任务：intake.py 或新 imap_in.py 域 + env 配置 + ticker 轮询 + 发件人匹配归账/降级 intake + 处理留痕（imap.seen 事件或邮件 Message-ID 幂等表）；单测（邮箱匹配归账/不匹配降级/Message-ID 幂等/未配置关闭/rebuild）。真实 IMAP 用 monkeypatch stub（同 I96 FakeSMTP 范式）。
- I108 常用回复：saved_replies 表 + own-data CRUD + CommentsModal 面板（过滤/直选/插入）+ 存为常用；单测（CRUD own-data 边界/超长 422/rebuild 保留——运行态表语义）。
- I109 引用快捷键：SHORTCUTS `R` 键位 + 游标联动 + 浮层自动收录；vitest 注册表断言 + **冒烟 41**（IMAP stub roundtrip/常用回复 CRUD+插入/引用快捷键预填 + rebuild 一致）并入 I109 + M35 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M35 审阅。

**AH.5 M35 取舍**

M35 = **通道与回复三件套**：I107 IMAP 邮件转任务（入口通道补全——Redmine/Jira 双先例，intake 邮箱版）/ I108 常用回复（回复效率——GitHub Saved Replies 语义）/ I109 引用快捷键+收尾（操作效率——I94 backlog 转正）+ docs/12 §32 + 冒烟 41 + M35 审阅，约 9 人日。多项目邮件路由、个人 Availability 休假层、AC 第三线、多基线并列对比留 backlog。


## AI. M36 前置调研：透明与容量——跨项目动态流 / 个人休假 / S 曲线扩展（2026-09-06）

> 目标协议触发：M35 审阅通过后开启。防重查：候选池 grep——Availability 休假层（§AG.1/§AH.5 仅留 backlog）、AC 第三线/多基线并列（§AG.5 仅留 backlog）、IMAP 多项目路由（I107 刚做主链路不查）均无调研记录；跨项目动态为本轮三路调研新发现。

**AI.1 跨项目动态流（OpenProject「My activity」语义——事件溯源红利第七例）**

- OpenProject：**My activity 页**聚合「你的全部最新动作与所参与项目的动态」（[官方文档](https://www.openproject.org/docs/getting-started/my-activity/)），另有跨项目 Overall activity 视图（[project lists](https://www.openproject.org/docs/user-guide/projects/project-lists/)）与项目内 activity 流（工作包新增/评论/状态变更，[activity 文档](https://www.openproject.org/docs/user-guide/activity/)）；Redmine 的 activity/journal 是同语义的经典实现。共同语义：**「我可见的项目里最近发生了什么」的单一聚合入口**——Linear Inbox 是通知态（推给个人），activity 是浏览态（回看全局）。
- 对本项目的映射：AgentPM 有 per-user 站内通知（M10）与项目内审计页（M22），缺**跨项目浏览态聚合**——事件流本身就是 activity feed：`GET /portfolio/activity`（复用 feed._visible 三层裁剪，扫可见项目的 item.created/status_changed/comment.created/milestone.*/approval.* 等白名单事件，按时间倒序 + actor/项目/类型过滤 + limit）+ 侧栏「📰 项目动态」页（时间线式：图标+事件摘要+项目名+相对时间，点击跳转）。零新表零重放——直接读 events（**事件溯源红利第七例：活动流免费**）。

**AI.2 个人 Availability 休假（Taiga 容量痛点 / Jira PTO 插件语义）**

- Taiga 有项目级周容量但「告诉 Taiga 某人 11 月只工作 13 天」是社区长年痛点（[capacity planning 帖](https://community.taiga.io/t/capacity-planning/2554)）；Jira 侧容量规划靠 HeroCoders/ActivityTimeline 等插件把**假期/病假/休假分类直接从容量中扣除**（[HeroCoders](https://www.herocoders.com/blog/pto-tracking-jira-capacity-planner)、[ActivityTimeline](https://activitytimeline.com/blog/jira-workload-capacity)）；OpenProject resource management 把 planned time off 作为资源计划的头等公民（[17.7 发布](https://www.openproject.org/blog/resource-management-capacity-planning/)、[用例文档](https://www.openproject.org/docs/use-cases/resource-management/)）。共同语义：**个人休假是日期段，容量与日程视图必须消费它**。
- 对本项目的映射：`user.time_off_started`/`user.time_off_cancelled` 显式事件 + user_time_off 投影表（user_id/start/end/reason，进 drop 清单）+ 设置页「🏖 我的休假」卡（own-data 登记日期段）+ **消费两端**：I87 `GET /portfolio/workload` 对休假中成员标「🏖 休假中」（活跃任务仍在但分母/标记体现）+ I89 我的日程月历叠加休假条。审批/Gate 流转不受休假影响（不做自动转派，转派规则留 backlog）。

**AI.3 S 曲线扩展：AC 第三线 + 多基线并列（MS Project 做不到的免费叠图）**

- MS Project 原生**不支持**多基线+EV+AC 单图叠加，社区标准工作流是「存多基线 → 导出 time-phased 数据 → Excel 手工叠图」（[Planning Planet 讨论](https://planningplanet.com/forums/microsoft-project/416271-s-curve-microsoft-project)、[Microsoft Learn Q&A「原生缺失」](https://learn.microsoft.com/en-us/answers/questions/5235196/)）；EVM 完整三线即 PV/EV/**AC**（实际成本=实际工时累计）（[monday.com S-curve](https://www.monday.com/blog/project-management/s-curve/)、[ProjectManager](https://www.projectmanager.com/blog/s-curve-project-management)）。
- 对本项目的映射：I106 端点扩展——**AC 第三线**：重放 timelog.time_logged 事件按采样日累计基线项的 spent_minutes（事件溯源下 AC 与 EV 同构免费）；**多基线并列**：`?compare=<baseline_id>` 参数返回第二组 PV 样本（两条基线 PV 同图对比「计划漂移了多少」）；报表卡三线图例 + 基线「对比」下拉。MS Project 要导 Excel 才能做的图，事件溯源下零导出直出。

**AI.4 M36 设计映射与验证纪律（沿用）**

- I110 跨项目动态流：reports.py `GET /portfolio/activity`（_visible + 事件白名单 + 过滤参数）+「📰 项目动态」页 + 侧栏入口；单测（_visible 裁剪/白名单/过滤/limit/rebuild 后事件序不变——事件即真相）。
- I111 休假：user_time_off 投影表 + 设置页卡 + workload 休假标记 + my/schedule 休假条；单测（登记 roundtrip/重叠 409/取消/workload 标记/rebuild 存活）。
- I112 S 曲线扩展：baseline-curve 加 ac 样本与 compare 参数 + 报表三线/双 PV；单测（AC 手算/compare 双 PV/rebuild 相等）+ **冒烟 42**（动态流对账/休假 roundtrip+标记/S 曲线三线手算 + rebuild 一致）并入 I112 + M36 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M36 审阅。

**AI.5 M36 取舍**

M36 = **透明与容量三件套**：I110 跨项目动态流（透明——OpenProject My activity 语义，事件溯源红利第七例）/ I111 个人 Availability 休假（容量——Taiga 痛点/Jira PTO 插件语义）/ I112 S 曲线扩展+收尾（对照——AC 第三线+多基线并列，MS Project 原生缺失项）+ docs/12 §33 + 冒烟 42 + M36 审阅，约 9 人日。休假自动转派、IMAP 多项目路由、动态流订阅 RSS 留 backlog。


## AJ. M37 前置调研：通道收尾——IMAP 主题路由 / 邮件回复转评论 / 动态流 Atom（2026-09-06）

> 目标协议触发：M36 审阅通过后开启。防重查：候选池 grep——IMAP subject 前缀路由（§AI.5/I107 仅留 backlog）、动态流 RSS（§AI.5 仅留 backlog）、休假自动转派（§AI.5 仅留 backlog）均无调研记录。行业面：Huly SaaS 停运转 self-host、Focalboard 进入维护模式、Plane 发布权限大改——均不改 AgentPM 功能路线。

**AJ.1 IMAP 主题路由（Jira Split Regex 的轻量版——`[项目名]` 前缀）**

- Jira Data Center 的 mail handler 有 **Split Regex** 字段（按正则切分回复膨胀），但「subject 正则路由到项目」原生能力有限，社区普遍靠 Email This Issue/JEMH 等三方应用做「正则匹配邮件属性 + 过滤/退信模板」（[Atlassian 社区](https://community.atlassian.com/forums/Jira-questions/Can-the-JIRA-Incoming-Mail-Handler-that-uses-regex-parse-HTML/qaq-p/623545)、[Meta-Inf 文档](https://docs.meta-inf.hu/email-this-issue/email-this-issue-for-jira-server-data-center/documentation/incoming-emails/next-generation-mail-handlers)）；另有「忽略特定地址/关键词」诉求（[社区](https://community.atlassian.com/forums/Jira-questions/Incoming-Mail-Handler-ignore-certain-address-or-keywords-when/qaq-p/831293)）。共同语义：**主题可携带路由信息，命中即定向，不命中走默认**。
- 对本项目的映射：I107 的默认项目路由保持，主题以 `[项目名]` 开头时**优先路由到该名称的可见项目**（发件人是其成员；非成员或项目不存在 → 落回默认项目路由，不静默丢信）；设置页「📮 外部收件」区提示前缀用法。零新表（路由是纯函数），正则留位。

**AJ.2 邮件回复转评论（Jira「replies become comments」语义）**

- Jira：新邮件建 issue，而**同主题的回复邮件变成该 issue 的评论**（[UWaterloo 解析](https://uwaterloo.ca/atlassian/blog/understanding-jiras-mail-handler-turning-emails-actionable)）；Cloud 版支持正文标记/分隔符过滤引用历史（[官方](https://support.atlassian.com/jira-cloud-administration/docs/create-issues-and-comments-from-email/)）。共同语义：**邮件线程与会话线合一**——回复不该生成新任务。
- 对本项目的映射：I107 处理邮件时先查 **In-Reply-To/References 头**是否指向本系统发出的 imap.message_processed 已见 Message-ID（或同主题且存在由邮件建出的任务）→ 命中则该邮件**不建新任务而是给对应任务发首条评论**（复用 I107 的 _attach_body）；纯标准库 email 头解析。imap_seen 记录 message→item 归属使线程链可回溯。

**AJ.3 动态流 Atom 订阅（feed_key 模式同构——M11 语义的全局活动版）**

- GitHub 私有活动 feed 需登录态/Token（[Stack Overflow](https://stackoverflow.com/questions/10730341/how-can-i-access-a-github-private-repository-rss-feed)）；GitLab 活动流是 Atom URL+**token 追加认证**且近期收紧了无 token 访问（[GitLab issue #433351](https://gitlab.com/gitlab-org/gitlab/-/issues/433351)）。共同语义：**订阅地址即凭证**（与 AgentPM users.feed_key / M11 Atom per-user key 完全同构）。
- 对本项目的映射：`GET /portfolio/activity.atom?key=`——复用 feed_key 认证（M11 同款 `_user_by_feed_key`）+ I110 的 _visible 裁剪与白名单聚合，手写 RFC 5545 式 Atom XML（I67 iCal 的零依赖先例）；动态页加「🔗 Atom」链接展示订阅地址。

**AJ.4 M37 设计映射与验证纪律（沿用）**

- I113 主题路由：imap_in.py `_route_message` 前置 `[项目名]` 解析（纯函数 + 成员校验）；单测（命中成员项目/非成员落默认/不存在落默认/无前缀不变/rebuild）。
- I114 回复转评论：In-Reply-To 头解析 + imap_seen 归属查询 + 转评论路径；单测（回复命中转评论/新主题建任务/Message-ID 幂等保持）。
- I115 动态 Atom：/portfolio/activity.atom?key= + feed_key 认证 + 动态页订阅链接；单测（key 认证 401/裁剪/XML 结构/rebuild 无影响——直读）+ **冒烟 43**（主题路由 roundtrip/回复转评论/Atom 订阅 XML 有效 + rebuild 一致）并入 I115 + M37 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M37 审阅。

**AJ.5 M37 取舍**

M37 = **通道收尾三件套**：I113 IMAP 主题路由（路由面——Jira Split Regex 轻量版）/ I114 邮件回复转评论（会话面——Jira replies-become-comments 语义）/ I115 动态流 Atom 订阅+收尾（订阅面——feed_key 同构，M11 全局活动版）+ docs/12 §34 + 冒烟 43 + M37 审阅，约 9 人日。休假自动转派、subject 正则全量路由、退信模板留 backlog。


## AK. M38 前置调研：层级与代位——多级进度 rollup / 休假代理转派 / 负载超载标记（2026-09-06）

> 目标协议触发：M37 审阅通过后开启。防重查：候选池 grep——多级 rollup（M33 §AF.5 仅留 backlog「孙任务向爷任务」）、资源平衡（M33 留 backlog 无调研记录）、休假自动转派（§AI.5/I111 仅留 backlog）均无调研记录。

**AK.1 多级进度 rollup（Jira Plans 逐级加权 + MS Project work-weighted 语义）**

- Jira Advanced Roadmaps：**Roll up values to parent issues**——日期与进度沿 Initiative→Epic→Story 层级逐级上卷，剩余估算加权（[Atlassian 文档](https://confluence.atlassian.com/jiraportfolioserver/rolling-up-values-to-parent-issues-968677334.html)、[progress 监控](https://confluence.atlassian.com/jiraportfolioserver/monitoring-progress-of-work-970614913.html)）；MS Project：**%Work Complete 按 work/工时加权**上卷，比 %Complete（工期加权）更准，Physical % Complete 完全不上卷（[ProjectPlan365](https://www.projectplan365.com/articles/percent-complete/)、[r/MSProject](https://www.reddit.com/r/MSProject/comments/1940rtu/the_age_old_question_percent_complete_based_on/)）。共同语义：**父级进度 = 子级的加权聚合，权重是估算量而非个数**。
- 对本项目的映射：I102 的 subtaskProgress 是「直接子任务 done 计数」单层——本轮扩展 rollup.ts：**递归沿 parent 链逐级上卷**（孙→子→父），进度权重改 **estimate_hours 加权**（无估算回退 1.0，与 I106 S 曲线同口径）；看板「🧩 n/m」徽标升级为加权百分比 + 时间线父条形沿用；vitest 固化递归口径（三层链/权重/环安全——parent 链理论无环但 rollup 加深度上限防御）。

**AK.2 休假代理转派（Jira automation + 「on leave until」字段语义）**

- Atlassian 官方 KB 两篇：用 automation + user properties（on leave until）**自动转派休假代理的 issue**（[KB-with-properties](https://support.atlassian.com/jira/kb/automatically-reassign-issues-of-agents-who-are-on-vacation-with-user-properties/)、[KB](https://support.atlassian.com/jira/kb/automatically-reassign-issues-of-agents-who-are-on-vacation/)）；Deviniti Assignment Rules 支持按人假期配置**在分配队列中自动跳过缺席者**（[Deviniti](https://deviniti.com/support/addon/cloud/assignment-rules/latest/rules/)）；Reddit 社区实践强调「**stand-in 转派、销假后转回原人**」（[r/jira](https://www.reddit.com/r/jira/comments/p3u4z3/how_do_you_guys_handle_vacation_replacement_for/)）。共同语义：**休假登记携带代理人，节拍任务负责转派与转回，全程留审计**。
- 对本项目的映射：I111 休假登记加可选 `delegate` 字段（代理人须同项目成员）+ I98 每日 sweep 扩展代位动作：休假首日把该成员**活跃未完成任务临时转给 delegate**（item.assigned 事件、payload 记 original_assignee），休假结束日自动转回——事件溯源下「转回」零成本；通知双通道照常（被转派人收 assigned 通知）。

**AK.3 负载超载标记（MS Project 自动 leveling 的反模式教训——检测而非自动改排）**

- MS Project 自动 leveling「把任务整体后移解决资源超载」，但社区公认它会**推出关键路径、恶化完成日期**（[GanttPRO](https://blog.ganttpro.com/en/resource-leveling-ms-microsoft-project/)、[Boyle 咨询的逻辑分析](https://boyleprojectconsulting.com/tomsblog/2016/01/05/logic-analysis-of-resource-leveled-schedules-ms-project/)）；MPUG 提出 **resource-critical path**（资源约束下的关键路径）概念；Aurora 直言「自动 leveling 可能高度低效——保证不超载 ≠ 高效排程」（[Aurora](https://www.aurorascheduling.com/blogs/why-resource-leveling-may-be-highly-inefficient/)、[MPUG](https://mpug.com/a-better-microsoft-project-workload-levelling-and-resource-critical-path)）。共同教训：**自动改排是反模式，透明检测才是正道**。
- 对本项目的映射：AgentPM **不做自动 leveling**（与 I104 手排期零感知一脉相承）——workload 端点加 `overloaded` 标记（活跃任务数超阈值，默认 5 可配）+ 负载页红色徽标提示人工均衡；与 I111 on_leave 徽标并列，负载页从「看数字」升级「看预警」。

**AK.4 M38 设计映射与验证纪律（沿用）**

- I116 多级 rollup：rollup.ts 递归版（per 父聚合直接子+继承子的加权进度）+ 看板徽标/时间线进度条升级；vitest（三层链/estimate 权重/无估算回退/深度防御）。
- I117 休假转派：time_off 加 delegate（同项目成员校验）+ sweep 代位动作（转派/转回、事件审计）+ 通知照常；单测（首日转派/payload 原人/末日转回/无 delegate 不动/rebuild）。
- I118 负载超载 + 收尾审阅：workload overloaded 阈值标记（config 可配）+ 负载页红色徽标；docs/12 §35；**冒烟 44**（三层 rollup 计数/转派转回 roundtrip/超载标记 + rebuild 一致）并入 I118 + M38 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M38 审阅。

**AK.5 M38 取舍**

M38 = **层级与代位三件套**：I116 多级进度 rollup（层级面——Jira Plans 逐级 estimate 加权，I102 单层升维）/ I117 休假代理转派（代位面——Jira KB 转派/转回语义，sweep 节拍）/ I118 负载超载标记+收尾（预警面——MS Project leveling 反模式的检测式解法）+ docs/12 §35 + 冒烟 44 + M38 审阅，约 9 人日。subject 正则全量路由、退信模板、自动 leveling（明确不做）留 backlog。

## AL. M39 前置调研：节奏与预测——Cycles 迭代 / 退信静默与过滤 / 完成日预测（2026-09-14）

> 目标协议触发：M38 审阅通过后开启。防重查：候选池 grep——subject 正则全量路由（§AJ.1 已有轻量版落地）、退信处理/邮件过滤关键词（§AJ.1 仅一句提及无调研记录）、Cycles 迭代（M27 §Z 留 backlog「Cycles」无调研记录）——本轮对后两者做完整调研。

**AL.1 Cycles 迭代时间盒（Plane Cycles + OpenProject 17.3 Sprints 与 Versions 分家）**

- Plane **Cycles**：「一段团队专注完成特定工作项的设定周期」即敏捷 sprint（[Plane Docs](https://docs.plane.so/core-concepts/cycles)），自带**燃尽图与未完成工作自动结转（auto-transfer/carryover）**（[Plane vs OpenProject](https://plane.so/blog/plane-vs-openproject-which-should-you-choose-in-2026)）；OpenProject 17.3 起把 **Sprints 从 Versions 里拆出来**成为独立概念——社区明确「sprint 不是改名的 version」：**迭代（时间盒）≠ 版本（发布/里程碑）**（[r/openproject](https://www.reddit.com/r/openproject/comments/1tukh3z/sprint_vs_version_differences_after_upgrade/)、[17.3 发布](https://www.youtube.com/watch?v=5SY55YGEtVE)、[agile 特性页](https://www.openproject.org/collaboration-software-features/agile-project-management/)）。共同语义：**迭代是按日期切片的工作容器，与里程碑（发布点）正交；周期结束未完成项显式结转而非静默堆积**。
- 对本项目的映射：AgentPM 有 milestone（发布点语义）但无迭代时间盒——补最小 Cycles 面：project.cycles 投影表（name/start/end 事件化）+ 工作项挂 cycle_id + 看板「周期」过滤下拉 + 周期结束次日 sweep 把未完成项**显式结转**到下一周期（cycle.carried_over 事件留审计——归属标记而非日期改排，与 I117/I118 检测式哲学一致，不碰 start/due）。

**AL.2 退信静默与邮件过滤（Jira suppression list + 标准 bounce 发件人约定）**

- Jira/JSM：收件服务器退信（bounce）后进入**抑制名单（suppression/bounce list）停止再投**，清除需人工介入（[Atlassian KB](https://support.atlassian.com/jira/kb/users-and-jsm-customers-not-getting-jira-cloud-emails-because-of-bounces/)、[Remove from bounce list](https://community.atlassian.com/forums/Jira-questions/Remove-email-address-from-the-bounce-list/qaq-p/2938434)、[Clear Bounce List](https://community.atlassian.com/forums/Jira-Service-Management/Clear-Bounce-List/qaq-p/2477365)）；ServiceNow 同构「监视/过滤已知退信地址」（[ServiceNow](https://www.servicenow.com/docs/r/xanadu/platform-administration/email-bounce.html)）；标准退信发件人约定 **MAILER-DAEMON@/POSTMASTER@**（[SuiteCRM 社区](https://community.suitecrm.com/t/email-bounce-handling/90499)）；Redmine 侧 rdm-mailhandler 的 email 关键词解析有已知局限（[论坛](https://www.redmine.org/boards/2/topics/18568)）、`--unknown-user=ignore` 即忽略式过滤（I107 已采）。共同语义：**退信是投递失败的既成事实 → 对该地址自动停投（可人工恢复），入站侧按地址/关键词可忽略**。
- 对本项目的映射：复用 I107 imap_in 的轮询接缝——MAILER-DAEMON/POSTMASTER 发来的退信 → 解析原始收件人 → users.email_notify 置 0 并**邮件静默**（站内照常，事件留审计，设置页可一键恢复）；入站过滤 = 可配的忽略地址/关键词清单（config 逗号分隔，命中即 ignore）——通道族（I107-I114）就此闭环「进得来、回得去、坏地址停得掉」。

**AL.3 完成日预测（Jira velocity chart + jira-agile-velocity 开源实现）**

- Jira velocity chart：按已完成 sprint 展示平均完成量，团队用它「预测消化剩余工作的速度」（[Atlassian 官方](https://support.atlassian.com/jira-software-cloud/docs/view-and-understand-the-velocity-chart/)）；开源 **jira-agile-velocity**：拉 Jira 完成点数 → 算周速率 → **外推项目完成日期**（[fgerthoffert/jira-agile-velocity](https://github.com/fgerthoffert/jira-agile-velocity)）；GitHub Projects 原生缺燃尽/速率图（[Discussion #38840](https://github.com/orgs/community/discussions/38840)）；社区对 committed vs completed 口径漂移的不满（[Atlassian 社区](https://community.atlassian.com/forums/Jira-questions/Issues-with-Jira-Backlog-Insights-Points-Completed-vs-Velocity/qaq-p/2965692)）提示**预测口径必须单一且可解释**。共同语义：**完成预测 = 近期速率的外推，速率口径透明、数据不足时诚实说不足**。
- 对本项目的映射：`GET /projects/{id}/forecast`——事件重放 done 首达（与 I85/I106 同一重放口径）算近 4 周周完成数**中位数**（抗毛刺）→ 剩余活跃项 ÷ 速率 = 预计完成日；活跃项逐条 due 对比预计进度给「风险」标记；数据不足（<2 周历史）诚实 None（SPI 先例）——纯投影零新表（事件溯源红利第八例），报表「🔮 完成预测」卡。

**AL.4 M39 设计映射与验证纪律（沿用）**

- I119 Cycles 迭代最小面：cycle 事件+投影（drop 清单）+ 项挂 cycle_id + 看板过滤下拉 + sweep 结转（carryover 事件审计）；单测（CRUD/挂载/结转/rebuild）。
- I120 退信静默与过滤：imap_in bounce 分支（MAILER-DAEMON/POSTMASTER + 原始收件人解析）+ email_notify 自动停投/恢复 + 忽略地址关键词清单；单测（退信静默/恢复/过滤命中）。
- I121 完成日预测 + 收尾审阅：forecast 端点（速率中位数外推 + 诚实 None）+ 报表预测卡；**冒烟 45**（结转 roundtrip/退信静默 roundtrip/预测手算 + rebuild 一致）并入 I121 + M39 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M39 审阅。

**AL.5 M39 取舍**

M39 = **节奏与预测三件套**：I119 Cycles 迭代最小面（节奏面——Plane Cycles/OpenProject Sprints 分家语义，迭代≠里程碑）/ I120 退信静默与邮件过滤（通道健壮面——suppression list 语义，复用 I107 接缝）/ I121 完成日预测+收尾（预测面——velocity 外推 + 诚实 None，事件溯源红利第八例）+ docs/12 §36 + 冒烟 45 + M39 审阅，约 9 人日。subject 正则全量路由（已有前缀版够用）、自动 leveling（明确不做）、digest 邮件（不做）留 backlog。

## AM. M40 前置调研：价值与可见性——工时成本与预算 / 工作项附件 / 依赖图视图（2026-09-14）

> 目标协议触发：M39 审阅通过后开启。防重查：候选池 grep——成本/预算/费率（无调研记录）、附件/attachment（无调研记录）、依赖图独立视图（M30 留 backlog，49 行仅 MVP 期「与依赖图联动」一句）均无完整调研记录。

**AM.1 工时成本与预算（OpenProject Budgets + Time and cost reporting）**

- OpenProject **Budgets 模块**：项目预算规划 planned labor/unit costs、对比 available vs spent（[Budgets 文档](https://www.openproject.org/docs/user-guide/budgets/)、[预算控制博客](https://www.openproject.org/blog/control-optimize-project-budget/)）；**Time and cost reporting**：人工成本 = **logged time × hourly rates**（费率按全局/角色/用户配置）， spent time 直接换算成本报表（[cost reporting](https://www.openproject.org/docs/user-guide/time-and-costs/reporting/)、[time tracking](https://www.openproject.org/collaboration-software-features/time-tracking/)、[cost tracking 单元成本](https://www.openproject.org/docs/user-guide/time-and-costs/cost-tracking/)）。共同语义：**工时是事实，成本是工时×费率的派生，预算是阈值线**——不另记一套"成本账"。
- 对本项目的映射：AgentPM 已有 item_time_entries（分钟×人×日）——补三个可配项即得成本面：users.hourly_rate（运行态，设置页自维护）+ projects.budget_hours（预算以**小时**计，避免货币单位纠缠）+ `GET /projects/{id}/cost-report`（按人 Σminutes×rate + 预算消耗比 + 超支预警）。纯投影零新表（工时事实已存，成本是查询派生）——报表卡 + CSV 同数。

**AM.2 工作项附件（Redmine 磁盘布局 + Jira DC 上传钳制）**

- Redmine：附件存 **files/ 磁盘目录**（DB 只存元数据，迁移痛点全在磁盘路径——[迁移讨论](https://www.redmine.org/boards/2/topics/47599)）；Jira DC：默认 **10MB/文件**上限可调（[配置文档](https://confluence.atlassian.com/adminjiraserver/configuring-file-attachments-938847851.html)），9.15 起支持格式 **allowlist/blocklist**（[Atlassian](https://support.atlassian.com/jira-cloud-administration/docs/configure-file-attachments/)）；API 两步式：先传文件得 token 再挂 issue（[Redmine 论坛](https://www.redmine.org/boards/1/topics/13984)、[ikuteam 指南](https://ikuteam.com/blog/add-attachment-to-jira)）。共同语义：**二进制进磁盘、元数据进库、大小钳制默认保守**。
- 对本项目的映射：工件仓（Git）之外补任务级文件——`item.attachment_added/removed` 事件 + attachments 投影表（drop 清单，rebuild 重建元数据；文件本体在 data_dir/attachments/{project}/ 事件之外，与工件 Git 仓同理）+ `POST /items/{id}/attachments`（multipart，默认 10MB 钳制）+ GET 下载 + 抽屉「📎 附件」区。两步式对单机自托管是过度设计，multipart 直传（Redmine 网页端同款）。

**AM.3 依赖图视图（Jira Plans dependencies map + OpenProject Relations tab）**

- Jira Advanced Roadmaps/Plans：**dependencies map**（图状）+ dependencies report（只读报表）双视图（[map](https://confluence.atlassian.com/jiraportfolioserver/displaying-the-dependencies-map-1005805794.html)、[report](https://confluence.atlassian.com/spaces/JIRASOFTWARESERVER/pages/1077915784/The+Dependencies+report+in+Advanced+Roadmaps)），跨项目依赖过滤是已知痛点（[社区](https://community.atlassian.com/forums/Advanced-Planning-in-Jira/Show-ONLY-cross-project-dependencies-in-Advanced-Roadmaps/td-p/2202699)）；OpenProject 走工作包 **Relations tab** 列表式（[官方](https://www.openproject.org/docs/user-guide/work-packages/work-package-relations-hierarchies/)）；[Quirk 综述](https://www.quirk.com.au/ultimate-guide-to-jira-dependency-graphs-reports-and-visualizations/)确认第三方都在补这块。共同语义：**依赖要一张"谁挡着谁"的图，阻塞关系按状态着色**。
- 对本项目的映射：M30 backlog 转正——AgentPM 已有 item_relations（KERNEL 四类）+ CPM float + 时间线连线，缺专用图：`🔗 依赖图` 页（分层布局，depends_on 边指向、done 灰/进行绿/**阻塞红**[上游未完成]、CPM 关键链琥珀描边）——纯前端读既有 relations/critical-path API，零后端改动。

**AM.4 M40 设计映射与验证纪律（沿用）**

- I122 工时成本与预算：users.hourly_rate 运行态列 + projects.budget_hours + cost-report 端点（按人/预算消耗/超支）+ 报表卡 + 设置页费率输入；单测（成本手算/预算比/rebuild）。
- I123 工作项附件：attachments 表 + multipart 上传钳制 + 下载 + 事件投影 + 抽屉 UI；单测（roundtrip/超限 413/越权 404/rebuild 元数据存活）。
- I124 依赖图视图 + 收尾审阅：前端分层图 + 状态着色 + 关键链描边；**冒烟 46**（成本手算/附件 roundtrip/依赖图数据契约 + rebuild）并入 I124 + M40 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M40 审阅。

**AM.5 M40 取舍**

M40 = **价值与可见性三件套**：I122 工时成本与预算（价值面——OpenProject Time and cost 语义，成本=工时×费率派生不另记账）/ I123 工作项附件（载体面——Redmine 磁盘+元数据语义，multipart 直传）/ I124 依赖图视图+收尾（可见面——Jira Plans dependencies map 语义，M30 backlog 转正）+ docs/12 §37 + 冒烟 46 + M40 审阅，约 9 人日。单元成本行项（差旅/设备）、多币种、附件格式白名单、跨项目依赖图留 backlog。

## AN. M41 前置调研：节奏治理——周期燃尽 / 审批超时提醒 / 审计导出（2026-09-14）

> 目标协议触发：M40 审阅通过后开启。防重查：候选池 grep——周期燃尽/燃尽 vs 燃上游（无调研记录，I119 留位）、审批 SLA/超时提醒（无调研记录）、审计导出（无调研记录）。

**AN.1 周期燃尽 + 范围线（Plane Cycles 燃尽 + Jira burnup 的 scope-change 教训）**

- Plane Cycles 自带**燃尽图**：剩余 vs 理想节奏（[Cycles 文档](https://docs.plane.so/core-concepts/cycles)）；Atlassian 官方：burnup 用「已完成 vs **总范围**」双线让 scope change 显性化——**燃尽线会掩盖范围变化**（完成 10 点+新增 10 点=线不动，[burnup 文档](https://support.atlassian.com/jira-software-cloud/docs/view-and-understand-the-burnup-chart/)、[brokenbuild](https://www.brokenbuild.net/blog/jira-burndown-chart-explained-from-basics-to-advanced-forecasting)、[Miro 对比](https://miro.com/agile/burnup-chart-vs-burndown-chart/)）；Azure DevOps 同样提示"燃尽线上翘=中途加范围"（[Microsoft](https://learn.microsoft.com/en-us/azure/devops/report/dashboards/burndown-guidance?view=azure-devops)）。共同语义：**周期内剩余量要配一条总范围线，范围漂移才藏得住猫腻**。
- 对本项目的映射：I119 的 cycles 补 `GET /cycles/{id}/burndown`——复用 I85 里程碑燃尽的 done 首达重放口径 + **burnup 双线**（remaining 递减线 + total scope 阶梯线[挂载/结转/新建都会抬线]）；周期卡/报表展示。纯事件重放零新表。

**AN.2 审批超时提醒（ServiceNow/Jira 审批 SLA 的 timer→reminder→escalate 模式）**

- ServiceNow：Flow Designer「pending 3 天发提醒」（[社区](https://www.servicenow.com/community/developer-forum/reminder-email-after-3-days-if-approval-is-still-pending-flow/m-p/3319392)）、审批 SLA 定时器+升级（[r/servicenow](https://www.reddit.com/r/servicenow/comments/12i615w/approval_sla_or_timer_for_reminders_escalations/)）；Jira JSM 用 automation 规则发审批提醒（[Atlassian 社区](https://community.atlassian.com/forums/Jira-Service-Management/How-to-create-the-automation-of-sending-an-approval-reminder/qaq-p/1579360)）；SailPoint 默认 90 天超时+可配提醒/升级（[文档](https://documentation.sailpoint.com/saas/help/requests/config_approval_settings.html)）；PeopleSoft 审批框架原生 notification/escalation manager（[Oracle](https://docs.oracle.com/en/applications/peoplesoft/peoplesoft-common/approval-framework/understanding-notification-escalation-manager.html)）。共同模式：**timer 检测 pending N 天 → 提醒审批人 → 超阈值升级 owner，全程幂等防骚扰**。
- 对本项目的映射：I98 sweep 家族第三员——`approval.pending_reminded`（pending 超 config `approval_reminder_days` 默认 3 天 → 提醒 owner[既有 approval 通知通道]；事件流当日幂等与 I105 同构）；响应力指标（I97）正好消费这批数据。M18 教训沿用：提醒是收口、事件是事实。

**AN.3 审计导出（Jira 原生 CSV + SOC2 保留基线）**

- Jira 原生 admin audit log **CSV 导出**按日期过滤（[Atlassian](https://support.atlassian.com/security-and-access-policies/docs/export-audit-logs/)、[合规导出指南](https://community.atlassian.com/forums/App-Central-articles/How-to-Export-Jira-Logs-for-Compliance-Purposes/ba-p/3134933)）；Redmine 无内建全量审计，靠插件补（[Auditlog](https://www.redmine.org/plugins/redmine_auditlog)、[Login Audit 2 流式 CSV](https://www.redmine.org/plugins/redmine_login_audit2)）；SOC2 保留期无硬规定——**90 天起步、12 个月常见**（[Konfirmity](https://www.konfirmity.com/blog/soc-2-logging-and-monitoring)、[Safeguard](https://safeguard.sh/resources/blog/how-to-meet-soc-2-audit-logging-requirements)）。共同语义：**审计页是给人看的，导出是给审计员的——admin only + 日期过滤 + CSV**。
- 对本项目的映射：AgentPM 事件流即全量审计（append-only、比 Redmine 插件还全），缺的只是导出——`GET /projects/{id}/audit.csv`（admin only、`?days=` 过滤、流式 CSV：id/ts/actor/type/agg/payload 摘要）。M12 CSV 导出同构，零新表。

**AN.4 M41 设计映射与验证纪律（沿用）**

- I125 周期燃尽：burndown 端点复用 I85 重放口径 + burnup 总范围线 + 周期区展示；单测（手算/rebuild）。
- I126 审批超时提醒：sweep `_remind_pending_approvals` + `approval.pending_reminded` 事件（当日幂等）+ 双通道 + config 天数；单测（窗口/幂等/决策后不提醒/rebuild）。
- I127 审计导出 + 收尾审阅：audit.csv admin 端点 + Audit 页导出按钮；**冒烟 47**（燃尽手算/提醒幂等/导出内容 + rebuild）并入 I127 + M41 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M41 审阅。

**AN.5 M41 取舍**

M41 = **节奏治理三件套**：I125 周期燃尽（节奏面——Plane Cycles 燃尽 + burnup 范围线，I85 口径参数化）/ I126 审批超时提醒（治理面——ServiceNow timer→reminder→escalate 模式，sweep 家族第三员）/ I127 审计导出+收尾（合规面——Jira 原生 CSV 语义，事件流即审计的最后一公里）+ docs/12 §38 + 冒烟 47 + M41 审阅，约 9 人日。审批升级链（多级 owner）、SOC2 保留期策略、全局审计导出留 backlog。

## AO. M42 前置调研：流量可见性——看板阻塞徽标 / 速率对比卡 / 收尾打包（2026-09-14）

> 目标协议触发：M41 审阅通过后开启。防重查：候选池 grep——阻塞徽标/blocked flag（无调研记录，I78 闭锁守卫与 I124 依赖图均未覆盖看板即时视觉）、速率对比图（§AL.3 只做项目级 forecast，无跨周期对比）、IntakePanel 隐藏与附件白名单（C 级/backlog 小项）。

**AO.1 看板阻塞徽标（Businessmap/Kanbanize 阻塞旗标 + LeanKit 可视化语义）**

- 看板方法的核心是「让问题在卡片上可见」：物理看板用红旗/贴纸标记 blocker，数字看板用 **flag/阻塞徽标**（[Businessmap 看板指南](https://businessmap.io/kanban-resources/getting-started/what-is-kanban-board)、[Planview LeanKit 词汇表](https://www.planview.com/resources/articles/kanban-glossary/)）；Jira 为受阻工作项提供 **flag 功能**（[Jira 视频教程](https://www.youtube.com/watch?v=qqVzURP_jL8)）。共同语义：**阻塞是一张卡的即时状态，必须在看板上一眼可见，而不是点开详情才知道**。
- 对本项目的映射：AgentPM 有 blocks 闭锁守卫（I78，422 拒绝）与依赖图（I124），但看板卡片上没有任何阻塞视觉——补齐：后端在 board/list 载荷派生 `blocked` 布尔（SQL EXISTS：存在未完结 blocks 上游或未完结 depends_on 前置），前端卡片/列表行红色「🚧」徽标。纯派生零新表。

**AO.2 速率对比卡（Jira velocity chart：committed vs completed 双柱 + 平均线）**

- Jira velocity chart：每个 sprint **committed（灰柱）vs completed（绿柱）**双柱对比 + 平均速率趋势线，sprint 越多预测越准（[官方文档](https://support.atlassian.com/jira-software-cloud/docs/view-and-understand-the-velocity-chart/)、[Report of the Week](https://community.atlassian.com/forums/App-Central-articles/3-Report-of-the-Week-Sprint-Velocity-Chart/ba-p/2836184)、[Tempo](https://www.tempo.io/blog/velocity-chart)）；跨团队聚合要三方工具（[BrokenBuild benchmarking](https://www.brokenbuild.net/examples/benchmarking-velocity-chart)）；I121 的 forecast 已用中位数速率做外推，但**没有按周期的速率对比视图**——「哪个周期掉速了」不可见。
- 对本项目的映射：`GET /projects/{id}/velocity`——复用 I125/I121 的重放口径按周期聚合：committed=周期首个有范围日的 total（I125 承诺日锚点同款），completed=周期窗口内 resolved 数；已完结周期列表 + 双柱 SVG + 平均线；数据不足诚实空。纯事件重放零新表（报表族第九次免费）。

**AO.3 收尾打包（C 级小项清账）**

- IntakePanel 非 owner 隐藏（M38 审阅 C 级：渲染但 403 的 console 噪声）；附件格式白名单（M40-I123 留位：`attachment_allowed_ext` config，逗号分隔，空=全放行——Jira 9.15 allowlist 语义）；审批升级链最小面（M41-I126 留位：pending 超 reminder_days×2 → 同事件升级提醒 admin，ServiceNow escalate 语义）。
- 对本项目的映射：三个小项一次清账——前两个是 config/UI 小改，升级链是 I126 事件的第二接收人扩展（payload 加 escalated 标记），零新表。

**AO.4 M42 设计映射与验证纪律（沿用）**

- I128 看板阻塞徽标：board/list 载荷派生 blocked + 卡片/列表「🚧」红徽标 + deps 页只看被阻塞互链；单测（blocked 派生矩阵/守卫联动）。
- I129 速率对比卡：velocity 端点（按周期 committed/completed 双柱+平均线）+ 报表卡；单测（手算/空周期诚实/rebuild）。
- I130 收尾打包 + 冒烟 48：IntakePanel 隐藏 + 附件白名单 + 审批升级链；**冒烟 48**（阻塞派生/速率手算/升级链 roundtrip + rebuild）并入 I130 + M42 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M42 审阅。

**AO.5 M42 取舍**

M42 = **流量可见性三件套**：I128 看板阻塞徽标（即时面——Businessmap 阻塞旗标语义，I78 守卫的视觉半边）/ I129 速率对比卡（趋势面——Jira velocity chart committed vs completed 双柱，跨周期对比）/ I130 收尾打包+冒烟 48+审阅（C 级清账：IntakePanel 隐藏+附件白名单+审批升级链）+ docs/12 §39 + 冒烟 48 + M42 审阅，约 9 人日。跨项目依赖图（需跨项目关系模型，V2 级）、多币种、digest 邮件留 backlog。

## AP. M43 前置调研：交付闭环——风险登记册 / 项目收尾清单 / 完成自动重建（2026-09-14）

> 目标协议触发：M42 审阅通过后开启。防重查：候选池 grep——风险登记册/risk register（无调研记录）、项目收尾/closure checklist（无调研记录）、完成自动重建（I98 recurring 是按日历建卡，「完成重开」语义无调研记录）。

**AP.1 风险登记册（PMBOK 概率×影响矩阵 + OpenProject 原生风险模块）**

- PMBOK：风险登记册是识别→分析→应对→监控的载体，**风险分 = 概率 × 影响**，用概率/影响矩阵可视化排序（[PMI](https://www.pmi.org/learning/library/risk-analysis-project-management-7070)、[PMBOK 六过程](https://www.projectengineer.net/project-risk-management-according-to-the-pmbok/)、[7 步指南](https://projectmanagementacademy.net/resources/blog/risk-register-in-project-management/)）；OpenProject 有**原生 risk 工作包类型**与 likelihood/impact 内建类别（[官方文档](https://www.openproject.org/docs/use-cases/risk-management/)）；Jira 靠 SoftComply 等应用补（[2025 对比](https://softcomply.com/best-jira-risk-register-plugins/)）；SimpleRisk 开源独立实现（[官网](https://www.simplerisk.com/blog/simplerisk-free-and-open-source-vs-fully-featured-platform)）。共同语义：**风险是一等公民条目：概率×影响打分排序、有应对措施与责任人、周期性复审**。
- 对本项目的映射：`risk` 域事件（risk.identified/mitigated/closed）+ risks 投影表（title/probability[1-3]/impact[1-3]/response/owner/review_date，进 drop 清单）→ 风险分 = p×i 自动排序；「⚠ 风险登记册」页（矩阵热力 + 列表）+ 工作项可关联 risk_id；PMBOK 落地的最后一块核心知识域。

**AP.2 项目收尾清单（PMBOK Closing Process Group + closeout checklist）**

- PMBOK **Closing Process Group** 是常被忽略的第五过程组：确认交付达标、正式验收、合同/采购收尾、经验教训、释放资源、收尾报告（[PMI](https://www.pmi.org/learning/library/importance-of-closing-process-group-9949)、[7 步清单](https://www.projectmanager.com/blog/project-closure)、[closeout checklist](https://www.projectmanagement.com/checklists/268528/project-closeout-checklist)、[Miro 6 步](https://miro.com/project-management/project-closure-checklist/)）。共同语义：**收尾是可检查的清单动作，不是「大家散了吧」**。
- 对本项目的映射：项目收尾清单端点 `GET /projects/{id}/closure-checklist`——纯投影核对：活跃项=0、pending 审批=0、全部 Gate 达成、工时已审批、无过期风险 → 全绿才允许 `project.completed` 事件（项目状态 completed，区别于 archived 归档）+ 收尾报告数据（工期/成本/吞吐汇总）+ 项目列表徽标。清单不过则逐项列差。

**AP.3 完成自动重建（YouTrack reset workflow 语义）**

- YouTrack 用 workflow 规则实现「任务完成后自动重置/重建下一期」（[默认 workflows](https://www.jetbrains.com/help/youtrack/cloud/default-workflows.html)、[workflow 示例](https://yt-cli.readthedocs.io/en/latest/workflows.html)）；n8n 社区同样在问「workflow 完成后自动重启」（[r/n8n](https://www.reddit.com/r/n8n/comments/1q2vrwj/how_to_automatically_restart_workflow_once/)）。共同语义：**周期性任务以「完成」为节拍而非「日历」——上一期完成触发下一期生成**。
- 对本项目的映射：I98 recurring 已是日历节拍（create_recurring 按日建卡）；补「完成节拍」：任务带 `recurrence_days` 字段 → 完成时 sweep 内建动作在完成日+N 重建同概念新卡（item.created 真事件、payload 记 respawn_of 审计链）——sweep 家族第四员，与日历节拍互补（周会/月报/巡检类任务的真实节奏）。

**AP.4 M43 设计映射与验证纪律（沿用）**

- I131 风险登记册：risk 事件+投影+风险分排序+登记册页+项关联；单测（打分/生命周期/rebuild）。
- I132 项目收尾清单：closure-checklist 端点（五项核对）+ project.completed 事件与徽标 + 收尾报告数据；单测（全绿才放行/差项列出/rebuild）。
- I133 完成自动重建 + 收尾审阅：recurrence_days 字段 + sweep respawn（payload 记 respawn_of）+ 任务卡徽标；**冒烟 49**（风险打分/收尾清单/重建 roundtrip + rebuild）并入 I133 + M43 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M43 审阅。

**AP.5 M43 取舍**

M43 = **交付闭环三件套**：I131 风险登记册（风险面——PMBOK p×i 矩阵 + OpenProject 原生模块语义，核心知识域补缺）/ I132 项目收尾清单（闭环面——PMBOK Closing Process Group，completed 区别于 archived）/ I133 完成自动重建+收尾审阅（节拍面——YouTrack reset 语义，完成触发而非日历触发，sweep 家族第四员）+ docs/12 §40 + 冒烟 49 + M43 审阅，约 9 人日。定量风险分析（EMV/蒙特卡洛）、风险升级链、跨项目风险留 backlog。


## AQ. M46 前置调研：LLM 流式输出 / 多币种 / 深色模式与主题 token 化（2026-09-19）

> 目标协议触发：M45（用户指令轮）完成后开启。防重查：候选池 grep——多币种/currency（§AM.5、§AO.5 两次仅留 backlog 无调研记录）、Cycles 多周期并列对比（§AN.3 只做单周期燃尽+burnup，I129 velocity 已覆盖跨周期 committed vs completed；本轮确认 Plane 无原生跨周期并列视图，该候选降级）、LLM 流式/逐 token（§B AgentScope 只一句「事件总线实时流式」，无落地调研）、深色模式/dark mode（无调研记录）、record 录制件回放（**M44 已顺手实现**：replay_templates `_recorded(key)` 优先于手写模板消费 recordings.yaml，候选池该项闭环，仅留 key 无上下文指纹的小改进）。本轮三路新调研（LLM 流式输出 / 多币种 / 深色模式），选定 **M46 = 流式与主题三件套**。

**AQ.1 LLM 流式输出（LangGraph streaming + FastAPI SSE 语义）**

- 行业模式：LangGraph 生产级流式三形态——节点更新/进度事件/**token 逐字**（`astream_events` 或 `messages` streaming mode），async FastAPI 端点包 `StreamingResponse(text/event-stream)` 逐 token 吐 SSE，前端 `useStream` 消费（[focused.io 生产指南](https://focused.io)、[LangChain 官方 streaming 文档](https://docs.langchain.com)、[astream_events 实战](https://abstractalgorithms.hashnode.dev)、[FastAPI SSE 教程](https://blog.gopenai.com)）；AgentScope 2.0 同样以事件总线做实时流式（§B）。共同语义：**流式是传输层优化，不是数据模型变更——完整消息仍是唯一落库真相**。
- 对本项目的映射：**token 增量走瞬态广播、不入事件库**——逐 token 若全量 emit 会制造数千事件/次 run，炸事件表体积且破坏 live==replay 的可承受性（事件溯源不变量优先于流式体验）。形态：provider 流式读 chunk → `event_bus.publish` 瞬态事件（`run.token_delta`，不 emit 不落库）→ 前端经现有 `/api/stream` SSE 通道增量渲染 assistant 消息，`message.created` 仍是唯一持久化终点；replay/record provider 无流式语义，诚实直返完整文本（与 M29 诚实零 token 同款纪律）。事件溯源红利：SSE 广播基础设施 M10/M15 已建，本次零新通道。

**AQ.2 多币种（Tempo Financial Manager 汇率表语义）**

- 行业：Tempo Financial Manager（原 Cost Tracker）是 Jira 成本跟踪标杆，**显式汇率配置**——全局设置里 per-currency 汇率表，多币种成本统一换算基准币展示（[Tempo 汇率文档](https://help.tempo.io)、[Marketplace](https://marketplace.atlassian.com)）；OpenProject **无原生多币种**，成本锁单一系统币种，社区以「统一基准币/外导财务工具」绕行（[openproject.org](https://www.openproject.org)）。共同语义：**成本记录不锁币种、展示归一基准币——汇率是手工配置的可审计数据，不是实时外呼**。
- 对本项目的映射：I122 成本=工时×费率派生不另记账的语义保持；轻量版三层——settings 基准币种（默认 CNY）+ 手工汇率表（YAML 配置、零外部 API 依赖、可测）+ users/projects 可选 currency 字段；cost-report 按基准币汇总并披露汇率来源，未配汇率的币种诚实标注「未折算」。多币种金额继续不进事件 payload（I122 语义：费率是运行时列）。

**AQ.3 深色模式与主题 token 化（Tailwind 双主题语义）**

- 行业：现代 PM 工具（Huly/Plane/Linear）均默认提供暗色主题，实现一致——**设计 token 层（CSS 变量）+ `prefers-color-scheme` 媒体查询/`.dark` 类双策略**，组件只引用 token 不写死色值（Tailwind dark mode 官方双策略）；PWA 需同步 `theme-color` meta 与 manifest 背景色，否则安装后状态栏与内容割裂。
- 对本项目的映射：M45 审计确认 index.css 只有亮色 token、`theme-color` 却是深色（割裂实证）。三层修复——index.css 补 `.dark` 变量组 + `prefers-color-scheme` 跟随系统 + 手动切换（localStorage 记忆、html class 切换）；M45 审计列出的 40+ 处硬编码调色板（red-500/dan、indigo/acc 漂移）择要映射回 ok/warn/dan/acc token；theme-color 双值（media 分亮暗）。

**AQ.4 M46 设计映射与验证纪律（沿用）**

- I138 LLM 流式输出：provider `stream=True` chunk 读取 + bus 瞬态广播（不落库）+ ConversationView 逐字渲染 + replay/record 诚实非流式；单测（瞬态事件不入库/完整消息仍落库/replay 直返）。
- I139 多币种轻量版：基准币种+汇率表+currency 字段+cost-report 换算汇总；单测（换算/未配汇率披露/rebuild）。
- I140 深色模式+token 化+收尾：双主题 token 组+系统跟随+手动切换+硬编码色择要归位+theme-color 双值；**冒烟 51**（流式瞬态/币种换算/主题切换）并入 I140 + M46 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M46 审阅。

**AQ.5 M46 取舍**

M46 = **流式与主题三件套**：I138 LLM 流式输出（体验面——LangGraph streaming 语义，「完整消息是唯一落库真相」的流式纪律）/ I139 多币种轻量版（价值面——Tempo 汇率表语义，手工汇率零外呼，I122 派生成本语义延续）/ I140 深色模式+token 化+收尾审阅（显示面——双主题 token + M45 审计硬编码色归位 + theme-color 割裂修复）+ docs/12 §41 + 冒烟 51 + M46 审阅，约 9 人日。Cycles 多周期并列视图（Plane 无原生、I129 已覆盖跨周期对比，价值降级）、record 录制件上下文指纹、对话多轮上下文压缩、角色温度/模型分档留 backlog。









## AR. M47 前置调研：上下文压缩 / 单元成本行项 / 跨项目依赖（2026-09-21）

> 目标协议触发：M46 完成后开启。防重查：候选池 grep——跨项目依赖（§AM.4 仅项目内依赖图 + §AM.5/§AO.5 两次留 backlog「需跨项目关系模型 V2 级」，无建模调研）、单元成本行项（§AM.5 仅一句留 backlog）、上下文压缩（§B 69 行仅 AgentScope「三事件锁」一句语义，无落地调研）、温度/模型分档（无调研记录）。本轮三路新调研（LLM 上下文压缩 / 单元成本行项 / 跨项目依赖），选定 **M47 = 深度与协同三件套**。

**AR.1 LLM 对话上下文压缩（LangGraph SummarizationNode 语义）**

- 行业：长对话超上下文窗口的通行解是**压缩而非丢弃**——LangGraph `SummarizationNode`/pre-model hook：超限前用一次 LLM 调用把旧消息折叠成摘要，原存储不动（[LangChain short-term memory 文档](https://docs.langchain.com)、[Context Management for Deep Agents](https://www.langchain.com)、[memory 深度文](https://pub.towardsai.net)、[分层策略：trim→summarize→retrieve](https://www.dailydoseofds.com)）；AgentScope 2.0 把 compaction 做成**可选能力缝**：`start/summary/end` 三事件锁进轨迹，压缩不产生「假完成」（§B）。共同语义：**压缩是读路径（prompt 组装）优化——存储原文永不改，压缩产物可观测、可审计**。
- 对本项目的映射：M46 实测 prompt 组装的 `_context` 把 run 起后的**全部注入约束无限制列举**（多轮打断→注入场景线性膨胀，真实 glm-5.3 一次 run 已 37k output tokens）——这就是爆炸点。落点=读路径：constraints/instruction 超过字符预算（配置化，默认约 8k chars≈2k tokens）时，早期约束折叠为一行摘要（保底**规则摘要**：计数+首尾条原文；配置了真实模型时可选 LLM 摘要，走 ui_agent_model 廉价档）；span 记 `apm.context_chars/budget/compressed` 观测。**存储原文一字不动**——压缩产物不落事件库（与 I138 瞬态广播同一纪律），rebuild 永不复制压缩。

**AR.2 单元成本行项（OpenProject Budget 双轨语义）**

- 行业：OpenProject Budget 模块把项目成本分**双轨**——labor（工时×费率，I122 已有）与 **material/unit costs**（行项：自定义成本类型×单价，如差旅/设备/采购；[官方预算文档](https://www.openproject.org)、[TechRepublic 配置指南](https://www.techrepublic.com)）；两轨同池进预算对比（planned vs actual 分 labor/material 列）。共同语义：**行项是一等记录（谁/何时/多少/花在哪个工作项），不是工时的附属品**。
- 对本项目的映射：新 expense 域——`expense.recorded/deleted` 事件 + expense_entries 投影表（description/qty/unit_price/currency/spent_on/vendor/可选 item_id，进 drop 清单）+ 金额不锁币种（I139 汇率表折算基准币，同一口径）；cost-report 合并双轨：labor 与 expense 分区小计 + 合计与 budget_hours 预算消耗并排（预算仍以小时计，费用行以基准币并列展示，不混算——诚实披露两口径）；前端报表卡分区 + 工作项详情费用行列表。

**AR.3 跨项目依赖（OpenProject 跨项目 relations 语义）**

- 行业：OpenProject **原生支持跨项目 relations**——管理设置开关（Administration → Work packages）允许跨项目建关系，关系类型同集（relates/blocks/precedes-follows/derived），**跨项目 Gantt** 靠 follows/precedes 在多项目时间线上联动排期（[work package relations 文档](https://www.openproject.org)、[跨项目引用](https://www.openproject.org)、[跨项目里程碑依赖](https://workspace.pm)）；Jira Plans dependencies map 同样以跨项目过滤为核心场景（§AM.4）。共同语义：**关系跟着工作项走、不跟着项目走；可见性由双方项目共同决定；排期传播跨项目沿关系链生效**。
- 对本项目的映射：现状 `post_relation` 对跨项目显式 422（「cross-project relations not supported」）+ item_relations 投影单 project_id。落点三层——①建模：放开 422，事件仍聚合在 from_item 项目（append-only 单写者不变），投影 to_item 允许跨项目 id；②可见性：建关系需双方项目可读（viewer 亦可读不可写，写仍是 from 侧项目门禁），依赖图/关系列表渲染时过滤对当前用户不可见的一侧（退化为「外部依赖」占位节点）；③排期：I44 传播与 I83 lag 对齐跨项目沿关系生效（工作日历取各自项目配置）。依赖图（I124）与关键路径（I102）跨项目渲染。

**AR.4 M47 设计映射与验证纪律（沿用）**

- I141 上下文压缩：预算配置+规则折叠保底+可选 LLM 摘要+span 观测；单测（阈值折叠/原文不动/rebuild 无影响/预算内零行为）。
- I142 单元成本行项：expense 域事件+投影+校验（qty>0/price≥0/ISO 币种）+cost-report 双轨+前端分区；单测（CRUD/币种折算/双轨合计/rebuild）。
- I143 跨项目依赖：放开 422+可见性双检+排期传播跨项目+依赖图跨项目渲染（不可见侧占位）；单测（跨项目建链/可见性过滤/传播联动/rebuild）。
- **冒烟 52**（压缩预算/双轨成本/跨项目依赖链）并入 I143 收尾 + M47 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M47 审阅。

**AR.5 M47 取舍**

M47 = **深度与协同三件套**：I141 LLM 对话上下文压缩（深度面——LangGraph SummarizationNode 语义，「压缩是读路径优化，存储原文永不改」）/ I142 单元成本行项（价值面——OpenProject Budget 双轨，expense 一等记录+I139 汇率口径延续）/ I143 跨项目依赖+收尾审阅（协同面——OpenProject 跨项目 relations，「关系跟着工作项走」）+ docs/12 §42 + 冒烟 52 + M47 审阅，约 9 人日。角色温度/模型分档、record 录制件上下文指纹、跨项目关系类型扩展（derived/includes）、M45/M46 工程债（engine `_exec_lock` run 粒度化/_active_runs 清理/看板列渐进渲染）留 backlog。


## AS. M48 前置调研：模型分档与降级 / 周期回顾包 / 并发治理（2026-09-21）

> 目标协议触发：M47 完成后开启。防重查：候选池 grep——温度/模型分档（§AQ/§AR 两次留 backlog，无调研记录）、Cycles 多周期并列（§AQ 已确认 Plane 无原生 + I129 覆盖跨周期对比，**维持降级不重查**）、record 录制件指纹（§AQ 定性「小改进」并入本轮分档迭代，不独立立项）、回顾会议/retrospective（§B Leantime 仅「回顾」一词，无落地调研）、并发/锁粒度（工程债非调研项，但本轮补行业模式）。本轮三路新调研（模型分档与降级 / 周期回顾包 / 并发治理），选定 **M48 = 调度与治理三件套**。

**AS.1 角色模型分档与 cascade 降级（model routing + cascade 语义）**

- 行业：model routing=把每类查询路由到能胜任的最便宜模型（研究口径 **2-4× 成本降**而质量不损）；model cascade=**cheap-first、失败按档升级**（[routing/cascade 统一框架](https://openreview.net)、[NeuralTrust 路由指南](https://neuraltrust.com)、[TrueFoundry 成本感知路由](https://www.truefoundry.com)、[路由技术综述](https://www.getmaxim.ai)）。共同语义：**档位是显式配置（cheap/standard/reasoning 三档），运行时按档取模型名；失败沿档升级要留痕（degraded 可观测），绝不静默换档**。
- 对本项目的映射：已有零散档位（`ui_agent_model` 廉价档、角色 `model.name`、I141 摘要走廉价档）——升级为**三档体系**：config `APM_MODEL_CHEAP/STANDARD/REASONING`（STANDARD 缺省回落 llm_model）+ 角色 YAML `model.tier: cheap|standard|reasoning`（显式 `model.name` 仍最高优先）+ **cascade 降级**：主档 LLMError（限流/5xx/超时）时向上一档重试一次，span 标 `apm.model_tier/model_degraded`，run 照常不 fail。**档位语义诚实**：降级只在错误路径，正常路由永不静默换模型。

**AS.2 周期回顾包（retrospective data pack 语义）**

- 行业：回顾（retrospective）是 Scrum 五步仪式的收口，工具趋势是把**数据支撑内建**进仪式（velocity 趋势=「团队容量的速度表」（[Atlassian](https://www.atlassian.com)）、analytics 面板把交付模式变成规划信号（[Axify](https://axify.io)）；2026 调研（419 工程师/PM）指出的最大缺口恰是**回顾洞察 → 跟进落地**（[Easy Agile Trends](https://www.easyagile.com)、[五步回顾实践研究](https://arxiv.org)）。共同语义：**回顾需要一份现成的数据包——周期口径对齐、拖入项显性、改进项可追踪**。
- 对本项目的映射：M39-M42 已散落全部素材（velocity/forecast/burnup/carryover/responsiveness/blocks）——缺一个**仪式出口**。落点：`GET /cycles/{id}/retrospective` 纯投影聚合——完成数/承诺完成率（对 I129 口径）、结转拖入清单（I119 carryover）、超期新增、人机 run 参与度、top 阻塞依赖（blocks 计数排序）、与前周期速率对比；前端周期卡「📋 回顾」入口 + 打印友好。改进项转任务（retro action item → item）留 backlog。

**AS.3 并发治理（per-run lock + 泄漏清理，工程债+行业模式）**

- 行业：instance-wide 锁会把「配置的并发」变成「实际串行」——LangGraph `AsyncPostgresSaver` 用实例级 `asyncio.Lock` 包连接池即翻车（**configured capacity ≠ effective concurrency**）；正解=锁/信号量按**真正需要互斥的边界**划分（[Python sync 原语](https://docs.python.org)、[asyncio 信号量对齐速率限制](https://rednafi.com)）；并行分支的中断/取消要用结构化并发处理（[LangChain 论坛](https://forum.langchain.com)）。共同语义：**互斥边界=共享可变状态的范围，不是「图实例」或「进程」**。
- 对本项目的映射：M45 审计 M8/L1 两笔工程债一次清——①`engine._exec_lock` 全局 threading.Lock 让所有 run 串行（一个挂起 LLM 调用阻塞全实例约 9 分钟）→ **按 conversation_id 分锁**（同对话的 run 天然互斥防状态竞争；不同对话并行；SQLite 写已由 `db.tx` 全局锁保护、LLM 长 IO 不持锁，安全）；②`_active_runs` 字典只进不出 → run 终态时 pop（终态判定复用 runkeeper 状态机）。看板列渐进渲染（前端显示债）并入收尾迭代。

**AS.4 M48 设计映射与验证纪律（沿用）**

- I144 模型分档：三档配置+tier 解析[显式 name 优先]+cascade 单次降级+span 观测；单测（tier 解析/降级链/降级留痕/replay 不受影响）。
- I145 周期回顾包：聚合端点（完成率/拖入/超期/run 参与/blocks top/速率对比）+前端入口；单测（口径对齐 I129/空周期诚实/rebuild 一致）。
- I146 并发治理+收尾：per-conversation 锁 + _active_runs pop + 看板列渐进渲染 + **冒烟 53**（分档降级/回顾包/并行 run）+ M48 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M48 审阅。

**AS.5 M48 取舍**

M48 = **调度与治理三件套**：I144 角色模型分档与 cascade 降级（成本面——routing/cascade 语义，「降级只在错误路径，永不静默换档」）/ I145 周期回顾包（仪式面——回顾数据包内建，堵「洞察→跟进」缺口）/ I146 并发治理+收尾审阅（性能面——per-conversation 锁取代全局串行 + 内存泄漏清理 + 看板列渐进渲染）+ docs/12 §43 + 冒烟 53 + M48 审阅，约 9 人日。Cycles 多周期并列（维持降级）、改进项转任务、record 录制件上下文指纹（并入 I144 顺手做 key 加 context 短哈希）、关系类型扩展留 backlog。


## AT. M49 前置调研：回顾行动项落地 / 状态报告自动生成 / 关系类型扩展（2026-09-21）

> 目标协议触发：M48 完成后开启。防重查：候选池 grep——改进项转任务（§AS.1/AS.5 两次留 backlog，痛点证据已在 M48 调研确立——「回顾洞察→跟进」是行业最大缺口，无落地调研）、项目状态报告自动生成（**无任何调研记录**，本轮新发现方向）、关系类型扩展（§B 49 行仅受控枚举一句 + §AS.3 搜索结果一句带过 OpenProject 关系族，无落地调研）；Cycles 多周期并列（维持降级）、subject 正则全量路由/digest 邮件（维持「除非用户要求」）。本轮三路新调研（行动项落地 / 状态报告自动化 / 关系类型扩展），选定 **M49 = 闭环与表达三件套**。

**AT.1 回顾行动项落地（immediate conversion 语义）**

- 行业共识高度收敛：**立即转换**——回顾会不散场，直到 top 1-2 项变成受追踪的 issue（[Easy Agile](https://help.easyagile.com) 的 Action 列直接建 Jira issue、[Atlassian 社区](https://community.atlassian.com)）；每项**单一 owner + 明确 due**（[Neatro](https://www.neatro.io)）；每周期限 1-3 项防疲劳、下届回顾开场先过上一届行动项（[Retromat](https://retromat.org)、[Kollabe](https://kollabe.com)）。共同语义：**行动项不是会议纪要的一行字，是带 owner/截止的受追踪工作项；生成动作发生在回顾现场**。
- 对本项目的映射：I145 回顾包已有全部数据——落点三层：①retrospective 响应加 `action_items`（title/owner/due，回顾现场填写）；②`POST /cycles/{id}/action-items` 批量转工作项——item.created 真事件，payload 记 `retro_of: cycle_id` 审计链（同 I133 respawn 模式），owner→assignee_id、due→due_date；③已转换的项在回顾响应中标注 item_id（防重复生成）；下届回顾自动带出上届未结行动项（开场过账）。**不加新表**：转换关系走事件 payload 审计链。

**AT.2 项目状态报告自动生成（status report as artifact）**

- 行业：两条路线——模板化周报（[TeamGantt 模板](https://www.teamgantt.com)、[Monday 自动汇编](https://monday.com)）与 AI 草稿（[Dart](https://www.dartai.com)、[KnowledgeHut](https://www.knowledgehut.com)）；报告骨架共识：**总体健康结论 → 本期完成/下期计划 → 风险与阻塞 → 指标（进度/工时/预算）**；Monday 的形态是「平台已有数据自动汇编成草稿，人只做润色与结论」（[Virtosoftware](https://www.virtosoftware.com)、[ClickUp 综述](https://clickup.com)）。共同语义：**报告是平台数据的汇编视图，人补充判断——生成要落在可版本化、可分发的载体上**。
- 对本项目的映射：`POST /projects/{id}/status-report` 生成 Markdown 状态报告，**作为工件写入项目 git 内容仓**（天然继承版本史/diff/审计，零新表）——这是「工件入 git」架构的红利。骨架：健康分与趋势 → 阶段/Gate 进度 → 本期完成/进行中/超期 → 待审 Gate → 工时与预算消耗（labor/expense 双轨 I142 口径）→ 风险 open 数 → 下期建议要点（由数据推导的客观条目）。可选 `?ai_summary=true` 时用 ui_agent_model 生成人话摘要段（失败降级纯数据版——同 I141 降级纪律）。手动触发优先；周期性自动生成（sweep 家族第五员）留 backlog。

**AT.3 关系类型扩展（OpenProject 关系族补全）**

- 行业：OpenProject 关系族为 relates/duplicates/blocks/precedes-follows/derived/includes（[官方 FAQ](https://www.openproject.org)）——其中 **duplicates=重复项互指**、**includes=包含**属「标注型关系」（无排期/闭锁副作用），derived 的进度派生传播是最重的一档。共同语义：**受控枚举扩档是低风险增量——标注型关系只影响可视化与检索，不触碰排期/闭锁守卫**。
- 对本项目的映射：内核 KERNEL_RELATIONS 现有 depends_on（排期语义）/blocks（闭锁语义）/relates_to 等——补 **duplicates**（重复项互指：可视化连线+互相提示）与 **includes**（包含：聚合计数展示）；两者均为标注型，不进排期传播与 blocks 闭锁守卫；依赖图/关系列表/时间线连线自然支持（relation_type 透传渲染）。derived 的进度派生传播（最重档）留 backlog——与 I116 rollup 语义重叠需单独论证。

**AT.4 M49 设计映射与验证纪律（沿用）**

- I147 行动项落地：action_items 填写+批量转任务+审计链+去重标注+上届带出；单测（转换/去重/owner-due 映射/rebuild）。
- I148 状态报告：POST 生成 Markdown 工件入 git+模板骨架全数据分区+可选 AI 摘要降级；单测（工件落盘/分区数据正确/重复生成=新版本/rebuild）。
- I149 关系类型扩展+收尾：duplicates/includes 枚举+渲染透传+图表配对色 token 化 + **冒烟 54**（行动项转任务/状态报告工件/新关系类型 roundtrip）+ M49 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M49 审阅。

**AT.5 M49 取舍**

M49 = **闭环与表达三件套**：I147 回顾行动项落地（闭环面——immediate conversion，「行动项是受追踪工作项不是纪要字」）/ I148 状态报告自动生成（表达面——报告=平台数据汇编入 git，可选 AI 润色）/ I149 关系类型扩展+图表色收尾审阅（表达面——受控枚举低风险扩档）+ docs/12 §44 + 冒烟 54 + M49 审阅，约 9 人日。derived 进度派生传播、Cycles 多周期并列（维持降级）、subject 正则全量路由/digest 邮件（维持不做除非要求）、周期性自动状态报告（sweep 第五员）留 backlog。

## AU. M50 前置调研：周期性自动状态报告 / 父子进度上卷裁决 / 2026 AI 报告特性（2026-09-21）

> 目标协议触发：M49 完成后开启。防重查：候选池 grep——周期性自动状态报告（§AT.2 明确留 backlog「sweep 家族第五员」且 I148 手动版已落地，无落地调研）、derived 进度派生传播（§AT.3 留 backlog「与 I116 rollup 重叠需论证」，本轮补行业调研后裁决）、Cycles 多周期并列（维持降级）、subject 正则全量路由/digest 邮件（维持不做除非要求）。本轮三路新调研（周期性报告调度 / 父子进度上卷 / 2026 AI 报告特性扫描），选定 **M50 = 周期性自动状态报告**。

**AU.1 周期性自动状态报告（scheduled digest 语义）**

- 需求证据：Plane GitHub issue #5861 明确请求「每日更新 + 每周状态报告仪表盘」——周期性 digest 是开源工具被反复要而普遍没有的能力（[Plane](https://plane.so)、[GitHub #5861](https://github.com/makeplane/plane/issues/5861)）；OpenProject 以「一段时间内项目发生了什么变化」为总览核心卖点（[OpenProject](https://www.openproject.org)）；2026 年「自动状态更新」成为各家内核能力（[Tommaso Ricci 2026 综述](https://www.tommasomariaricci.com/blog/ai-for-project-management-guide)：AI 监控任务完成/识别延迟/自动更新状态；[Microsoft Planner](https://www.microsoft.com/en-us/microsoft-365/planner/project-management-ai) AI 跟踪状态并发提醒；[Lark](https://www.larksuite.com/en_us/blog/ai-project-management-tools) AI 从任务评论自动生成周度干系人更新）。共同语义：**报告的价值在「准时发生」而非「手动可触发」——digest 与其说是一个功能，不如说是一个节律；节律的正确实现 = 幂等调度 + 事实化心跳**。
- 对本项目的映射：I148 手动版已落地，M50 把它变成 sweep 第七员——`run_daily_sweep` 加 `report_status_weekly` pass：ISO 周一（config `weekly_report_day`，0 关闭）对每个活跃项目生成状态报告；幂等 = `artifact.report_generated` 事件 payload 记 `source:"weekly"` + ISO 周键，扫到本周已生成即跳过（同 `automation.swept` 心跳模式，零新表）；重构 `generate_status_report` 出 `_collect_status_metrics`（数据收集）+ `_render_status_lines`（渲染）两层，手动端点与 sweep pass 共用同一汇编核；`automation.swept` payload 加 `reported` 计数。AI 摘要 sweep 版默认关（成本纪律），手动版不受影响。

**AU.2 父子进度上卷（derived 语义裁决）**

- 行业：原生 Jira **不做**父子 %done 上卷——Atlassian 生态靠插件补位：Ricksoft WBS Gantt-Chart 按子任务估算加权计算父进度、ProSchedule 用「Jira Field 法」从链路字段自动计算（[Atlassian 社区](https://community.atlassian.com)、[Ricksoft 文档](https://ricksoft-support.atlassian.net)）；OpenProject 把 derived 列为关系族最重一档。共同语义：**进度上卷不是「读个数字」，是加权策略（子任务均权 vs 估算加权 vs 工时加权）+ 重算时机（子项变更即传播 vs 读时计算）+ 环路治理三件事一起**。
- 裁决：**维持 backlog 不立项**。理由：I116 已有 contains 聚合、I149 includes 计数展示，读时聚合覆盖「父项看子项进度」八成场景；写时传播（derived）与 I116 rollup 语义重叠、加权策略无用户输入前属过度设计——本轮证据（连原生 Jira 都不做写时上卷、留给插件层）反而支持维持 backlog 的行业选择。

**AU.3 2026 AI 报告特性扫描（新发现方向）**

- 2026 趋势三件套收敛为标配：自动状态更新 / AI 生成摘要 / 风险预测（[ClickUp 综述](https://clickup.com)、[Lark](https://www.larksuite.com/en_us/blog/ai-project-management-tools)、[Microsoft Planner](https://www.microsoft.com/en-us/microsoft-365/planner/project-management-ai)、[Productive](https://productive.io/blog/ai-project-management-tools) 全部捆绑）；AgentPM 对应现状：手动报告 AI 摘要段（I148）✓、周期性自动报告（本轮 I150）✓、风险登记册（M42）+ 速率 forecast（M41）✓——三件套对齐后无新缺口；Lark 式「从评论抓取生成」属增强档留 backlog。

**AU.4 M50 设计映射与验证纪律（沿用）**

- I150 sweep 周期报告 pass：汇编核重构（collect/render 分层）+ 第七员 pass + 按项目按 ISO 周幂等 + payload 指标与 `reported` 计数；单测（重构后手动版不变/周一触发/同周幂等/开关关闭/非活跃跳过/计数对账）。
- I151 通知与前端入口：owner 通知（新 kind `report_weekly` 入 NOTIFY_KINDS 白名单）+ ReportsPage「最近报告」列表（artifact.report_generated 事件过滤）+ 直开工件；单测（通知白名单/owner 定向/偏好关时不发）。
- I152 环比对比：weekly payload 携带结构化指标，下期读上期算 Δ（完成度/超期/费用），报告加「环比」分区；单测（首期无环比/第二期 Δ 正确/rebuild 一致）。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M50 审阅 + **冒烟 55**（周期报告 roundtrip：sweep→报告工件→通知→环比）。

**AU.5 M50 取舍**

M50 = **周期性自动状态报告**：I150 sweep 周期报告 pass（节律面——「报告的价值在准时发生」，幂等心跳零新表）/ I151 通知与前端入口（分发面——owner 通知 + 最近报告列表）/ I152 环比对比 + **冒烟 55** + M50 审阅，约 9 人日。derived 进度派生传播（本轮裁决维持 backlog：连原生 Jira 都不做写时上卷，读时聚合已覆盖主场景）、AI 评论抓取摘要（增强档）、Cycles 多周期并列（维持降级）留 backlog。


## AV. M51 前置调研：评论语料段 / 周报 digest 邮件 / 2026 自托管 AI 扫描（2026-09-21）

> 目标协议触发：M50 完成后开启。防重查：候选池 grep——AI 评论抓取周报摘要（§AU.3/AU.5 仅留 backlog「增强档」一句，无落地调研）、周报 email 分发（**无任何调研记录**——M11 email 通道已有但正文单行 summary，report_weekly 走两通道，报告正文从未进邮件）、Cycles 多周期并列（维持降级）、derived 进度上卷（M50 已裁决维持）、subject 正则全量路由（维持不做除非要求）。本轮三路新调研（评论语料摘要 / 邮件分发模式 / 2026 自托管 AI 扫描），选定 **M51 = 周报深化与分发三件套**。

**AV.1 评论语料→周报摘要（activity digest 语义）**

- 行业实现范式收敛为三步：**拉活动数据 → LLM 汇总 → 定时分发**（[Asana 论坛需求帖](https://forum.asana.com)：按日/周汇总我被指派/我更新/我完成的；[DailyBot](https://www.dailybot.com)：从工具已发出的信号起草站会，**人是编辑**；[oscorm](https://oscorm.com)：成员签到由 AI 汇成周报）。关键定性：**语料段（谁在做什么）与叙事段（AI 润色判断）是两层——语料层确定可测、零模型；叙事层才需要 LLM，且失败必须可降级**。
- 对本项目的映射：I150 周报已有指标骨架、缺「人话素材」——补**「本期动态」确定语料段**（comment.created 近 7 天按工作项分组：作者+摘要预览，最多 8 条+计数溢出行，纯投影零模型）；AI 叙事段走 config `weekly_report_ai`（默认关——延续 I150「定时任务不花没人要的 token」纪律），失败降级纯语料版（同 I148 降级纪律）。

**AV.2 周报邮件分发（scheduled delivery 混合模式）**

- 行业主流=定时生成+邮件分发，形态三分：附件（Workday/Ninja Forms/Bluerithm 的 PDF/Excel）、内联 HTML 摘要、链接；[Google Data Studio](https://docs.cloud.google.com/data-studio/schedule-automatic-report-delivery) 的混合式（PDF 附件+首页内联预览）最完整；[Asana 论坛](https://forum.asana.com)用户请求把超期聚合进一封周 digest（[AnnounceKit](https://announcekit.app) digest 语义：一封定时邮件捆住多批更新）。共同语义：**邮件正文必须自含结论（不必点开也知道好坏），链接只负责取证**。
- 对本项目的映射：M11 email 通道对 report_weekly **已天然生效**（NOTIFY_EVENTS 含 notification.sent + per-kind email 偏好门 + FakeSMTP 测试件齐全）——增量只在正文：`notification.sent` payload 加 `digest` 纯文本字段，mailer `enqueue` 透传、`_send` 有 body 用 body（对非周报事件零影响）——digest=总体健康三行+环比一行+工件路径，正文自含结论。

**AV.3 2026 自托管 AI 扫描（新发现方向）**

- [Plane vs OpenProject 2026 对比](https://plane.so)：OpenProject 截至 2026-02 **无任何生产级 AI 特性**；Plane AI 商业自托管版按 M50 调研 2026-03 发布（BYO OpenAI/Anthropic key），并主打 air-gapped 部署——AgentPM 的「自托管+BYO-key+事件溯源审计」路线与 Plane 商业化方向一致且在开源侧领先（[Orangescrum 2026 综述](https://blog.orangescrum.com)佐证两强格局）。**无新功能缺口**；Plane 渐进闭源化趋势不改 AgentPM 路线。

**AV.4 M51 设计映射与验证纪律（沿用）**

- I153 评论语料段：`_activity_lines`（comment.created 近 7 天按项分组+计数溢出）+ `weekly_report_ai` 开关+AI 失败降级；单测（语料分组/溢出行/降级/开关关时零外呼）。
- I154 digest 邮件：payload.digest 字段+mailer enqueue 透传+_send body 分支；单测（FakeSMTP 正文断言/非周报单行不变/email 偏好门仍生效）。
- I155 冒烟 56+审阅：评论→周报语料段→digest 邮件→偏好门 roundtrip。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M51 审阅 + **冒烟 56**。

**AV.5 M51 取舍**

M51 = **周报深化与分发三件套**：I153 评论语料段（素材面——语料/叙事两层，语料层确定可测）/ I154 digest 邮件（分发面——正文自含结论，链接只管取证）/ I155 冒烟 56+审阅，约 9 人日。Cycles 多周期并列（维持降级）、derived 进度上卷（M50 裁决维持）、subject 正则全量路由（不做除非要求）留 backlog。


## AW. M52 前置调研：报告附件形态 / 周报订阅制 / 2026 秋季特性扫描（2026-09-21）

> 目标协议触发：M51 完成后开启。防重查：候选池 grep——周报附件形态（§AV.2 仅「附件/内联/链接三形态」一句带过，无落地调研与技术选型）、报表订阅制（**无任何调研记录**——Jira filter/dashboard subscription 未查过，GitLab 缺口未确认）、Cycles 多周期并列（维持降级）、derived 上卷（M50 已裁决维持）、subject 正则全量路由（维持不做除非要求）。本轮三路新调研（服务端 PDF 选型 / 报告订阅语义 / 2026 秋季特性扫描），选定 **M52 = 周报分发完备三件套**。

**AW.1 报告附件形态（PDF 依赖裁决 + Markdown 附件）**

- 技术选型证据：Python 服务端 HTML→PDF 三路线——[Playwright](https://pdf4.dev) 渲染快（~42ms）但**捆绑整浏览器**部署重；[WeasyPrint](https://www.nutrient.io) 部署轻但**依赖系统 Pango/Cairo**（[Windows 安装痛](https://github.com/Kozea/WeasyPrint)是高频 issue，本项目开发/演示在 Windows）；[wkhtmltopdf 已停止上游维护](https://pdfbolt.com)（legacy 避雷）。共同结论：**PDF 服务端转换的依赖重量与「打印即得」的价值不成比例**。
- 裁决：**不引服务端 PDF 依赖**。人的 PDF 路径维持 I88 打印 CSS（浏览器「另存为 PDF」）；机器分发路径补**Markdown 附件**（EmailMessage.add_attachment 零新依赖）——Google Data Studio 混合式（附件+内联摘要）以「.md 附件+digest 内联」形态闭环；附件名带周键（`weekly-report-2026-W39.md`）。

**AW.2 周报订阅制（filter/dashboard subscription 语义）**

- 行业：[Jira filter subscription](https://www.atlassian.com)——保存的 JQL 按日程跑、结果邮件发给你或组（订阅对象是「查询结果」）；[Jira dashboard subscription](https://support.atlassian.com)——定时邮件送 dashboard 的 **PDF/CSV 副本**（订阅对象是「视图快照」，收件人自选任意人）；**GitLab 原生无定时报告订阅**（社区多年 feature request）——OSS 真空区实证。共同语义：**订阅=「人 × 项目 × 通道」的自选关系，收件人不再由角色（owner）单方面决定**。
- 对本项目的映射：M50 周报收件人硬编码 owner——补**订阅事件对** `report.subscribed/report.unsubscribed`（payload 记 user_id，投影 report_subscribers 表进 drop 清单）+ `POST/GET/DELETE /projects/{id}/report-subscription`（仅项目成员可订——读权限门）+ sweep 收件人 = **owner ∪ 订阅者去重**；前端 Reports 页「🔔 订阅周报」开关；per-kind 偏好门（report_weekly）对订阅者同样生效——订阅解决「发给谁」，偏好解决「怎么发」。

**AW.3 2026 秋季特性扫描（新发现方向）**

- [OpenProject 17.7](https://www.openproject.org)（2026-08）新资源管理模块（容量/人员规划）——AgentPM M28 个人负载 + I111 休假覆盖个人面，跨项目资源规划是更大队形，留 backlog 观察；[Plane v3.0](https://plane.so)（2026-07）桌面应用+治理+AI 深化、Taiga 6.10 项目归档（AgentPM M22 已有）——**无新功能缺口**；2026 主题（AI 自动化/个性化/工作流柔性）与既有路线一致。

**AW.4 M52 设计映射与验证纪律（沿用）**

- I156 周报 Markdown 附件：notification.sent payload 加 `path` + mailer `_send` 工作线程读 git 内容 add_attachment[零阻塞写路径]；单测（FakeSMTP iter_attachments 断言文件名与内容/非周报无附件/git 缺文件降级仅 digest）。
- I157 周报订阅：事件对+投影表+三端点+成员门+sweep 收件人并集去重+前端开关；单测（订阅 roundtrip/非成员 403/owner 与订阅者去重/退订后不再收/rebuild 复现）。
- I158 冒烟 57+审阅：订阅→sweep→订阅者收附件邮件→偏好关断→退订 roundtrip。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M52 审阅 + **冒烟 57**。

**AW.5 M52 取舍**

M52 = **周报分发完备三件套**：I156 Markdown 附件（形态面——混合式闭环，PDF 依赖裁决不引入）/ I157 周报订阅（受众面——收件人从角色单方扩到自选，OSS 真空区）/ I158 冒烟 57+审阅，约 9 人日。服务端 PDF 转换（依赖裁决不引入）、Cycles 多周期并列（维持降级）、derived 上卷（M50 裁决维持）留 backlog。


## AX. M53 前置调研：digest 邮件 HTML 化 / 跨周资源面 / 交易邮件设计细节（2026-09-21）

> 目标协议触发：M52 完成后开启。防重查：候选池 grep——digest 邮件 HTML 模板化（§AV.2 仅「内联 HTML 摘要」一句带过，无技术调研）、跨项目资源规划（§AW.3 仅「留 backlog 观察」一句，OpenProject 17.7 细节未查）、Cycles 多周期并列（维持降级）、derived 上卷（已裁决维持）、subject 正则全量路由（维持不做除非要求）。本轮三路新调研（HTML 邮件工程共识 / 资源规划对照 / 交易邮件设计细节），选定 **M53 = 分发呈现与资源面三件套**。

**AX.1 digest 邮件 HTML 化（multipart/alternative 语义）**

- 工程共识（[Sitepoint](https://www.sitepoint.com)/[WooCommerce 开发文档](https://developer.woocommerce.com)/[markaplugin](https://markaplugin.com)）：**table 嵌套布局而非 div**（Outlook 桌面版等老客户端 CSS 支持差，table 是唯一跨客户端一致方案）、**关键 CSS 全内联**（Gmail 等剥离/忽略 head 样式）、单元格显式宽度、移动优先；**发送 multipart/alternative 双 part**（[Campaign Monitor 共识](https://www.campaignmonitor.com)——HTML 与纯文本并存由客户端自选，兼容性/可达性/送达率三赢；纯文本部分必须是真正可读的 digest 而非自动转储）。共同语义：**HTML 是呈现增强，纯文本是可达性底线——两者共存而非二选一**。
- 对本项目的映射：I154 的纯文本 digest 恰好就是那个「真正可读的纯文本 part」——补 HTML part 即可：`EmailMessage.add_alternative(html)` 零新依赖；HTML=table 布局+内联样式的周报卡（标题+周键、指标行配状态徽标色[超期红/风险琥珀/完成绿]、环比行、CTA「查看全文」按钮链到站内 Reports 页）。

**AX.2 跨周资源面（OpenProject 17.7 Resource planner 轻量化）**

- [OpenProject 17.7](https://www.openproject.org)（2026-08）：Resource planner 时间轴可视化**每用户已分配工作 vs 剩余容量**随时间变化、按实际容量规划、一处跨项目分配人员。重模式三件套：时间轴 UI+容量模型（工时/天）+显式分配记录——对「人 directs」定位过重（分配是另一种计划层，与 AgentPM「指派即分配」哲学冲突）。
- 轻量裁决：**只做「读视图」不做「分配层」**——按人 × 未来两周（本周+下下周）的到期负载热力（活跃工作项按 due_date 落桶、estimate_hours 求和、休假覆盖标灰），纯投影零新表零新计划概念；跨项目天然（items 全局查，前端组合负载页入口）。显式容量/分配层留 backlog（需用户先表达「要排人」的需求）。

**AX.3 交易邮件设计细节（层次/徽标/CTA）**

- [Postmark 2026 交易邮件 15 条](https://postmarkapp.com)/[iContact](https://www.icontact.com)：**信息层级**——最重要的结论放最前（周报=总体判断先行）；状态用色块徽标强化（红=超期、琥珀=风险、绿=健康）；CTA 按钮单一明确（「查看全文」一个动作，不堆链接）。对 I159 HTML 模板的直接约束：结论行前置、三色徽标、单 CTA。

**AX.4 M53 设计映射与验证纪律（沿用）**

- I159 digest 邮件 HTML part：`_digest_html()` 纯函数（digest 字符串+指标→table HTML）+ mailer `_send` add_alternative[HTML 生成失败降级纯文本不失败]；单测（FakeSMTP html part 断言含徽标与 CTA/纯文本 part 仍在/非周报邮件无 html part）。
- I160 跨周资源热力：workload 端点扩展 per-member 两周桶（due 桶+est_hours+on_leave 覆盖）+ WorkloadPage 热力卡；单测（桶归属含跨周边界/休假标灰/estimate 求和口径）。
- I161 冒烟 58+审阅：HTML 邮件→资源热力→偏好门 roundtrip。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M53 审阅 + **冒烟 58**。

**AX.5 M53 取舍**

M53 = **分发呈现与资源面三件套**：I159 digest 邮件 HTML 化（呈现面——multipart/alternative，纯文本底线保留）/ I160 跨周资源热力（资源面——只做读视图不做分配层，OpenProject 17.7 轻量化）/ I161 冒烟 58+审阅，约 9 人日。显式容量/分配层（需用户先表达排人需求）、Cycles 多周期并列（维持降级）、derived 上卷（已裁决维持）留 backlog。


## AY. M54 前置调研：自定义关注规则 / 通知规则架构范式 / 2026 末扫描（2026-09-21）

> 目标协议触发：M53 完成后开启。防重查：候选池 grep——订阅规则泛化（I157 只调研了「周报订阅」特例，「人×项目×事件类型」通用 watch 规则与 Jira filter subscription/GitHub custom watch 对照**无调研记录**）、显式容量分配层（M53 轻量裁决留口子，需用户先表达排人需求——维持默认不做）、Cycles 多周期并列（维持降级）、derived 上卷（已裁决维持）、subject 正则全量路由（维持不做除非要求）。本轮三路新调研（订阅规则产品语义 / 事件订阅架构范式 / 2026 末扫描），选定 **M54 = 自定义关注三件套**。

**AY.1 订阅规则产品语义（watch=用户自建的「谁在什么事件上被通知」）**

- 三家对照：[Jira filter subscription](https://support.atlassian.com)——保存的过滤器按日程跑、结果邮件化（可「无结果也发」），且**默认只在结果最近有变化时发**（反空/反重复是内建纪律）；[GitHub Custom watch](https://docs.github.com)——按仓库×**事件类型**自选（releases/issues/PRs/discussions），触发器与通道分离；[Linear](https://linear.app/docs/notifications)——**按通道**（Desktop/Mobile/Email/Slack）×事件类别独立配置。四条设计共识（[Adobe](https://blog.adobe.com)/[Toptal](https://www.toptal.com)）：**触发器与通道分离、相关性默认、空/重复抑制、用户可控**。
- 对本项目的映射：现有通知面是「角色推导收件人」（指派/owner/参与者），I157 是「周报」单事件特例——补**用户自建 watch 规则**：`人 × 项目 × 事件类型`（白名单内，可带条件），触发走 notification.sent 既有双通道（站内+邮件+偏好门全复用）——「发给谁」由 watch 决定，「怎么发」仍由 I96 偏好决定，语义正交不重造。

**AY.2 事件订阅架构范式（subscription-side filter rules）**

- [Azure Service Bus Topic Filters](https://learn.microsoft.com)：pub/sub 的订阅侧过滤规则——每个订阅者注册自己的过滤表达式（对事件属性求值），broker 侧匹配投递；与「每类事件硬编码收件人」相对，是**通用可配置通知**的标准形态。共同语义：**规则是数据不是代码**——匹配逻辑对事件 payload 求值，规则增删不改事件流。
- 对本项目的映射：事件溯源天然适配——watch 规则本身就是事件（`watch.added/removed` + 投影表进 drop 清单，同 I157 范式）；消费端用 **post-emit hook**（mailer.enqueue 同款机制）对每个事件求值匹配规则→命中即 emit `notification.sent`（kind=`watch`）——投影器做偏好门、mailer 做邮件门，双通道零新通道。防循环：watch 规则匹配白名单不含 `notification.sent` 自身。

**AY.3 2026 末扫描（新发现方向）**

- 2026 Q3-Q4 无具体厂商新缺口信号（Epicflow/Atlassian/TechPlusTrends 等均为趋势综述：Agentic AI 从被动软件转向自主代理）——AgentPM 的「人 directs、Agent executes + 事件溯源审计」正是该方向的工程化形态；watch 规则把「人想被通知什么」也从硬编码变成用户可配置，与趋势同向。无新功能缺口。

**AY.4 M54 设计映射与验证纪律（沿用）**

- I162 watch 规则域：`watch.added/removed` 事件对 + watch_rules 投影表（drop 清单）+ CRUD 三端点（own-data+成员门）+ 可订阅事件类型白名单（item.*/approval.*/comment.*/risk.*/expense.*/artifact.report_generated 等，显式排除 notification.sent/email.*）+ post-emit hook 匹配消费[actor 自事件抑制/命中去重]；单测（roundtrip+rebuild/非成员 403/白名单外 422/命中发 watch 通知/自事件抑制）。
- I163 偏好门+前端管理：NOTIFY_KINDS 加 `watch: 自定义关注` + 铃铛偏好浮层「👁 项目关注规则」管理区（跨项目列表+事件类型下拉+增删）；单测（偏好关断双通道/多规则命中单份）。
- I164 冒烟 59+审阅：建规则→触发事件→站内+邮件→偏好关断→删规则 roundtrip。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M54 审阅 + **冒烟 59**。

**AY.5 M54 取舍**

M54 = **自定义关注三件套**：I162 watch 规则域（规则=数据不是代码，事件溯源范式第七例）/ I163 偏好门+前端管理（触发器与通道分离的 Linear 语义）/ I164 冒烟 59+审阅，约 9 人日。显式容量/分配层（默认不做除非用户要求）、订阅日程化（filter subscription 的定时批次面——AgentPM 已有 sweep 节律，暂无第二批过滤需求）、Cycles 多周期并列（维持降级）、derived 上卷（已裁决维持）留 backlog。


## AZ. M55 前置调研：watch 条件化 / 通知降噪 / 疲劳面证据（2026-09-21）

> 目标协议触发：M54 完成后开启。防重查：候选池 grep——watch 条件化（condition_json M54 已落库但**未消费**，payload 条件匹配[Azure Service Bus rule 第二半]无调研记录）、通知合并/频次治理（**无任何调研记录**）、显式容量分配层（维持默认不做）、Cycles 多周期并列（维持降级）、derived 上卷（已裁决维持）。本轮三路新调研（条件过滤产品现状 / 降噪工程范式 / 疲劳面证据），选定 **M55 = 关注精修与降噪三件套**。

**AZ.1 watch 条件化（subscription-side payload filter）**

- 产品现状：**Jira 订阅与 GitHub watch 原生都不支持按用户的细粒度 payload 条件**——业界靠中间件补位（[AWS CodeBuild webhook filter groups](https://docs.github.com)、[Harness 的 payload/header/branch JEXL 条件 AND 组合](https://developer.harness.io)）；[Keboola 实战文](https://www.keboola.com)直言 GitHub 通知过滤「the hard way」要自建管道。共同语义：**条件是订阅规则的一部分，匹配发生在投递侧**。
- 对本项目的映射：AgentPM 事件 payload 是结构化 JSON——条件可**原生**支持而无需中间件（事件溯源红利第九例）：`condition_json` = 扁平 dict（payload 顶层字段→期望值，全等匹配，≤5 键），hook 内全部命中才投递；`{"status_group":"done"}` 即「只关注完成」。无 JEXL/表达式引擎（过度设计），扁平等值已覆盖「只看完成/只看新建/只看某指派」八成诉求。

**AZ.2 通知降噪（source filter + display bundling 两层）**

- 工程范式：[Knock 批量引擎](https://www.knock.app)/[Novu digest](https://novu.co)——定时窗口聚合多事件为一封；[Courier 通知中心](https://www.courier.com)——**展示层 bundling 是降噪性价比最高的修复**（同类重复折叠为一行「Maya 和 8 其他人」）；[Sentry 反噪三招](https://blog.sentry.io)——**条件逻辑放源头**（只在满足条件时产生告警）胜过事后静音。
- 对本项目的映射：两层各取一半——**源头层**=I165 条件化（不匹配就不产生事件）；**展示层**=站内铃铛对连续同类 watch 通知折叠为一行带计数（纯前端，事件流不动，rebuild 语义不变）；不做定时窗口 digest（AgentPM 已有周报 digest 节律，第二套窗口属重复建设）。

**AZ.3 疲劳面证据（新发现方向）**

- 2026 年疲劳叙事收敛（[MeisterTask](https://www.meistertask.com)/[SupportBench](https://www.supportbench.com)）：疲劳来自「多工具各自 streams + 差过滤」，解方是**审计+条件化+静音规则**而非全关（[Wrike 反面观点](https://www.wrike.com)：配置得当的通知反而穿透噪声）——与 M54/M55 路线（用户可控 watch + 条件 + 偏好矩阵九员）完全同向。无新功能缺口。

**AZ.4 M55 设计映射与验证纪律（沿用）**

- I165 watch 条件化：POST 校验 condition_json（扁平 dict/≤5 键/值为原始类型）+ hook 匹配（全等、空条件=全匹配）+ 前端条件字段/值可选输入与规则行条件徽标；单测（条件命中/不命中/坏条件 422/rebuild 复现）。
- I166 铃铛降噪折叠：bell 列表连续同 kind+同项目 watch 折叠一行「N 条动态」（纯函数分组 + vitest）；不触碰事件流与已读语义（折叠行点开=逐条已读不变）。
- I167 冒烟 60+审阅：条件 watch（done 命中/in_progress 不命中）→降噪折叠→偏好门 roundtrip。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M55 审阅 + **冒烟 60**。

**AZ.5 M55 取舍**

M55 = **关注精修与降噪三件套**：I165 watch 条件化（源头层——事件溯源红利第九例：结构化 payload 原生条件无需中间件）/ I166 铃铛降噪折叠（展示层——性价比最高修复，事件流零改动）/ I167 冒烟 60+审阅，约 9 人日。定时窗口 digest（与周报节律重复）、JEXL 表达式引擎（过度设计）、显式容量分配层（默认不做）、Cycles 多周期并列（维持降级）、derived 上卷（已裁决维持）留 backlog。

## BA. M56 前置调研：watch 规则导入导出 / 静默时段 / 2026 秋季扫描（2026-09-26）

> 目标协议触发：M55 完成后开启。防重查：候选池 grep——watch 摘要批量投递（跨事件窗口聚合 M55 §AZ.2/§AZ.5 已裁决「与周报节律重复→不做」，**维持不重查**）、watch 规则导入导出/团队共享关注模板（**无任何调研记录**）、显式容量分配层（维持默认不做）、Cycles 多周期并列（维持降级）、derived 上卷（已裁决维持）、静默时段/免打扰窗口（**无调研记录**——本轮新方向）。本轮三路新调研（规则模板共享与导入导出 / 静默时段与免打扰范式 / 2026 秋季扫描），选定 **M56 = 关注共享与免打扰三件套**。

**BA.1 watch 规则导入导出（团队共享关注模板）**

- 产品现状：**Jira 没有内建的过滤器/订阅导出导入机制**——[Manage filters](https://support.atlassian.com/jira-software-cloud/docs/manage-filters) 只覆盖分享/订阅/复制/收藏；跨实例迁移要靠 Data Center 的 SearchRequest 表 admin 工具（[社区实践](https://community.atlassian.com/forums/Jira-Service-Management/Custom-Subscription-for-a-Filter/qaq-p/3209177)）；订阅在标准导出中不存活，连「限制谁能收订阅邮件」都还是未解需求（[JSWSERVER-21837](https://jira.atlassian.com/browse/JSWSERVER-21837)）。业界最接近「团队共享通知模板」的是**共享过滤器（模板层）+ 个人订阅（配置层）**两层：过滤器可分享给组/项目、订阅永远是个人的——分享的应该是配置模板而不是订阅本身。
- 对本项目的映射：watch 规则本身是事件溯源的数据——导出=own-rules 序列化为**项目无关模板**（去重后的 `{event_type, condition}` 对数组，剥离 user/project 才能跨项目复用）；导入=复用既有校验链（WATCHABLE 白名单+`_serialize_condition`）+「缺则补、在则跳过」的模板应用语义（投影 ON CONFLICT DO NOTHING 已内建，个人改过的条件不被模板覆盖）→ `{imported, skipped}` 对账返回；成员门复用 `_require_member`。**AgentPM 超越 Jira 的点：导出导入内建开箱（Jira 要 admin 工具挖表），且规则是事件、rebuild 可复现。**

**BA.2 静默时段（quiet hours / 免打扰窗口）**

- 产品范式：Slack 支持个人 DND 日程 + 管理员工作区默认免打扰时段（[Configure your Do Not Disturb schedule](https://slack.com/help/articles/214908388)）；GitHub/Linear 经 Slack 路由的告警同样被日程静默（跨入站源一致生效是共识诉求）。设计共识五条：**按用户日程（如 22:00–08:00）、管理员默认+个人可调、优先级突破（@mention 可穿透）、免打扰期排队/汇总投递、跨入站源一致生效**。
- 对本项目的映射（与 M55「不做第二套定时窗口」裁决不冲突）：静默时段是**通道投递门**不是内容报告——窗口内邮件推送静默、站内照发（铃铛就是应用内实时面，Slack DND 同语义；事件流零改动）。两层例外：**mention 突破**（急迫性最高，I96 已有 mention 不可关断的同族纪律）与 **digest 类邮件不重复抑制**（周报 digest 本身已是批量窗口，再被静默等于白做——payload 带 digest 体即豁免）。落点：mailer.enqueue 既有门链（kind 偏好→邮箱地址→总开关）加第四道**时刻门**；`users.quiet_start/quiet_end` 运行态列（email_notify/hourly_rate 同族：轻量 ALTER 迁移+own-data 端点）；不做「免打扰期排队+退出汇总投递」（那即定时窗口，M55 已裁决不做）。

**BA.3 2026 秋季扫描**

- 三家均无 9 月具体缺口信号：趋势综述确认 AI 特性铺满 agile 工具（[Simpliaxis 2026 agile 工具综述](https://www.simpliaxis.com)：自动门票摘要已成标配）；Jira 走 MCP agent 连接（AI 经 MCP 直接读写 Jira 数据，[LinkedIn 实践](https://www.linkedin.com)）；OpenProject 仍是自托管治理选位（[Sharkly human-agent teams 对照](https://sharkly.ai)：Linear 最快/Plane 与 OpenProject 自托管）。「human-agent teams」叙事与 AgentPM「人指挥 Agent 执行+事件溯源审计」同向。无新功能缺口。

**BA.4 M56 设计映射与验证纪律（沿用）**

- I168 watch 规则导入导出：`GET /watch-rules/export`（own 模板：去重后 `{event_type, condition}` 数组）+ `POST /projects/{id}/watch-rules/import`（校验+缺补在跳+对账 imported/skipped）+ 前端铃铛偏好浮层「导出/导入模板」（下载 JSON blob/文件选择解析后应用到所选项目）；单测（导出模板形状/导入 roundtrip/坏模板 422/非成员 403/重复导入跳过对账/rebuild 复现）。
- I169 静默时段：`users.quiet_start/quiet_end`（HH:MM，空=关；跨午夜窗口 start>end 合法；start==end 视为关闭）+ `GET/PUT /me/quiet-hours`（格式校验 422）+ mailer 时刻门（窗口内非 mention 非 digest 邮件跳过——站内照发、事件照发）+ 前端铃铛偏好浮层起止输入；单测（窗口判定纯函数含跨午夜/边界、mention 与 digest 突破、窗口外正常投递、站内不受影响）。
- I170 冒烟 61+审阅：导出→导入 roundtrip→静默窗口内邮件静默站内照发→mention/digest 突破→窗口外恢复。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M56 审阅 + **冒烟 61**。

**BA.5 M56 取舍**

M56 = **关注共享与免打扰三件套**：I168 watch 规则导入导出（团队模板——Jira 无内建导入导出，AgentPM 内建+事件可重放）/ I169 静默时段（通道投递门——Slack DND 语义，mention 与 digest 突破）/ I170 冒烟 61+审阅，约 9 人日。免打扰期排队汇总投递（即定时窗口，M55 已裁决不做）、管理员默认 DND（单实例个人工具无组语义，个人时段已覆盖）、显式容量分配层（默认不做）、Cycles 多周期并列（维持降级）、derived 上卷（已裁决维持）留 backlog。

## BB. M57 前置调研：watch 规则编辑与暂停 / 资产信任信号 / 2026 Q4 扫描（2026-09-27）

> 目标协议触发：M56 完成后开启。防重查：候选池 grep——watch 规则 PATCH 编辑与暂停恢复（**无调研记录**——M55 坑位记录了「改条件需删了重加的 409 语义诚实」，产品化方向未查过行业语义）、多节律报告/daily digest（M55 §AZ.5 已裁决「不做第二套定时窗口」——维持不重查，重提需新证据）、资产库/模板域深化（**M7（I23-I25 模板中心）后未再调研**，30+ 迭代空白）、新特性扫描（照例）、显式容量分配层（维持默认不做）、Cycles 多周期+derived（维持）。本轮三路新调研（自动化规则开关与编辑语义 / 资产注册表信任信号 / 2026 Q4 扫描），选定 **M57 = 治理收口与资产洞察三件套**。

**BB.1 watch 规则编辑与暂停（in-place edit + paused state）**

- 产品现状：**二元开关 + 配置保留 + 可恢复**是自动化规则的通用开关语义——[Zapier 的 Zap on/off toggle](https://help.zapier.com)（关掉不删配置，社区常见「批量编辑前先关掉一批 Zap」）；[GitHub Actions 的 Disable workflow](https://docs.github.com)（菜单项禁用→横幅态+一键恢复，API `PUT .../workflows/{id}/disable`）；IFTTT Applet 卡片直翻开关。编辑侧三家皆支持**就地修改**（Zapier 编辑器/GitHub 工作流文件），从不要求「删了重建」。
- 对本项目的映射：M55 记录的「同 (project,event_type) 改条件需删了重加（409 引导）」是主键约束下的诚实兜底，但行业语义是**就地编辑 + 暂停态**——`PATCH /projects/{id}/watch-rules/{event_type}`（body {condition?, paused?}，走白名单+条件校验复用）emit 单一 `watch.updated` 事实（payload 带全量 condition_json+paused，投影 upsert 整行——重建可复现，暂停/恢复/改条件都有审计链）；hook 投递侧跳过 paused 规则；前端规则行加 ⏸/▶ 切换与条件就地编辑。**暂停≠删除**：配置原样保留，事件流零改动。

**BB.2 资产信任信号（registry trust signals 的组织内翻译）**

- 产品现状：npm 包页是**注册表信任信号的金标准**——最新版本、**last published 时间**、README 渲染、仓库链接、弃用横幅（[npmjs.com](https://www.npmjs.com)）；健康度评估工具（[pkgpulse](https://www.pkgpulse.com)）把用户实际判断依据形式化为：**周下载趋势、维护活跃度、源码可查、弃用状态**。私有模块注册表（[GitLab Terraform Module Registry](https://gitlab.com)/[Firefly](https://docs.firefly.ai)/[Harness IaCM](https://developer.harness.io)）同样以集中、版本化、可发现为核心，用量导出支撑采纳追踪。
- 对本项目的映射：资产库是「组织记忆」，但**复用是否发生**目前不可见——`asset.consumed/asset.linked` 事件早已入流（M6 起），缺的是读侧洞察：`GET /assets/insights` 纯投影（per-asset 消费计数/最近消费时间/published 时长/来源项目；**零消费且久未更新的资产清单**=候选弃用面）+ AssetsPage 洞察卡（使用 Top/久未复用两分区+「久未复用」徽标）。弃用流程已有（asset.deprecated），不新增写路径——**事件溯源红利第十例：使用遥测零埋点，投影即得**。

**BB.3 2026 Q4 扫描**

- [Atlassian 2026 年 9 月发布](https://techgig.com)：AI-native Jira——**Teamwork Graph**（链接工作/团队/目标/代码/知识）与 **Agentic loops in Jira**（代理循环执行工作项）+ @Jira Slack 自然语言操作；Linear/Plane 无 Q4 具体缺口信号。Teamwork Graph=跨实体事件图、Agentic loops=人监督下的代理执行——与 AgentPM「事件溯源图 + 角色 Agent 运行时 + Gate 审批」**完全同向**，无新功能缺口；反向确认了本体/事件内核路线的先手性。

**BB.4 M57 设计映射与验证纪律（沿用）**

- I171 watch 规则编辑与暂停：`PATCH /projects/{id}/watch-rules/{event_type}`（条件复用 `_serialize_condition` 校验·paused: bool 可选）+ `watch.updated` 事件与投影 upsert（drop 清单已含 watch_rules，rebuild 复现）+ `_on_event` 跳过 paused 规则 + 前端规则行 ⏸/▶ 与「✎ 改条件」就地编辑；单测（PATCH 条件生效[旧条件不再匹配/新条件命中]/暂停静默与恢复投递/未订 404/坏条件 422/rebuild 复现含 paused 态）。
- I172 资产使用洞察：`GET /assets/insights` 纯投影（events 流聚合 consumed/link 计数与最近时间·published 时长·零消费清单）+ AssetsPage 洞察卡（使用 Top/久未复用+徽标）+ vitest 无新组件断言走 API 单测（投影计数/rebuild 一致/空态诚实）。
- I173 冒烟 62+审阅：改条件→旧静默新命中→暂停→恢复→洞察计数与久未复用清单 roundtrip。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M57 审阅 + **冒烟 62**。

**BB.5 M57 取舍**

M57 = **治理收口与资产洞察三件套**：I171 watch 规则编辑与暂停（就地编辑+暂停态——Zapier/GitHub Actions 通用语义，修 M55 的 409 坑）/ I172 资产使用洞察（registry 信任信号的组织内翻译——投影即得零埋点）/ I173 冒烟 62+审阅，约 9 人日。多节律报告/daily digest（M55 已裁决维持不做）、资产评分/星级（单实例无社区语义，使用计数已够）、显式容量分配层（默认不做）、Cycles 多周期并列（维持降级）、derived 上卷（已裁决维持）留 backlog。

## BC. M58 前置调研：agent 动态关注 / CI 通知纪律 / 2026-27 前瞻（2026-09-27）

> 目标协议触发：M57 完成后开启。防重查：候选池 grep——run.* 生命周期事件入 watch 白名单（**无调研记录**——WATCHABLE_EVENTS 自 M54 定格为 13 类，agent 运行完成/失败尚不可关注）、站内跨 kind 合并摘要（M55 已做同 kind 折叠——维持「需新证据才重提」）、新特性扫描（照例）、显式容量/Cycles 多周期/derived/多节律报告（均已裁决维持）。本轮三路新调研（agent 状态通知产品语义 / CI 流水线通知纪律 / 2026-27 前瞻），选定 **M58 = 关注 agent 动态三件套**。

**BC.1 agent 动态关注（run lifecycle events → watch）**

- 产品现状：agent 编排产品的通知时刻收敛于三点——**完成、失败、等待人介入**。[Superset](https://github.com/superset-sh)（编排 100+ 编码 agent）以「agent finish 即通知」为核心卖点；[Solo](https://soloterm.com) 跟踪 agent 状态机（working/idle/**waiting for permission**/error-blocked）并在状态变化时提醒；[Devin subagents](https://cognitionai.mintlify.app) 在子代理完成后汇报、权限请求即暂停等待批准；[Smithers](https://smithers.sh) 的审批门把 run 挂起到盘上等人应答（分钟或天级）。
- 对本项目的映射：`run.succeeded` / `run.failed` 入 WATCHABLE 白名单（13→15 类）——agent 完成是交付时刻（Copilot/Superset 均通知完成），失败必响；**run.interrupted 不入白名单**：Gate 挂起已有 approval.requested 通知面（I96 偏好门第九员 watch 亦已覆盖），双份通知违背 M55 降噪路线。噪声面排除：run.requested/started/tokens_recorded/span_* 是记账与过程面（M44 纪律：token 记录不进通知）。自抑制天然成立（run 事件 actor=runtime:{run_id} 系统态，不触发 actor 相等抑制——发起人正是最该收到完成通知的人，CI 语义「路由给触发者」）。

**BC.2 CI 通知纪律（failure-first + actionable context）**

- 工程共识：**失败必响、成功静默**（[GitHub Actions `if: failure()`](https://www.gitnotifier.com) / [CircleCI Slack orb `basic_fail_1`](https://circleci.com/developer/orbs/orb/circleci/slack)）——成功通知制造警报疲劳；例外是**部署/交付型成功值得通知**（production deploy success）；通知必须**带可行动上下文**（job 名/分支/commit/日志链接）；**路由给对的人**（触发者/breaking-change owner 而非整频道）。
- 对本项目的映射：watch hook 对 run.* 事件生成**带上下文的摘要**——failed 带 error 首行、succeeded 带 outcome/工件路径（CI「可行动上下文」共识），用户以 watch 条件化自行裁决成功是否通知（I165 的 payload 条件天然支持 `{"outcome": ...}` 匹配——订阅侧过滤仍在投递位）；通知点击**直达 run**（notification.sent payload 透传 run_id，铃铛跳转——「日志链接」语义）。

**BC.3 2026-27 前瞻**

- Agentic AI 支出 2026 $206.5B→2027 $376.3B（[biz4group](https://www.biz4group.com)）；Gartner 预测 2026 末 40% 企业应用内嵌任务型 agent（2025 不足 5%）；全球 ~41% 新代码由 AI 生成、92% 美国开发者日用 AI 助手——**「AI 技术债清算」叙事**推高人工评审/审批需求（[Citrusbug](https://www.citrusbug.com)）；HITL 审批门成为企业合规标准模式（SOX 控制面）。**有界自主（bounded autonomy）= 行业收敛模型**——AgentPM「人 directs、Agent executes、Gate 审批」正是该形态的工程化；run 可关注补上「人监督 agent」的最后一环：通知面。无新功能缺口，方向强确认。

**BC.4 M58 设计映射与验证纪律（沿用）**

- I174 run 生命周期入白名单：WATCHABLE_EVENTS 加 `run.succeeded`/`run.failed` + hook 摘要分支（failed 带 error 首行 80 字/succeeded 带 outcome 或工件路径）+ AppShell WATCHABLE 标签表同步 15 类；单测（成功/失败入站通知/白名单外 run.started 422/条件化 `{"outcome":...}` 匹配/自抑制不误伤[发起人收到]/rebuild）。
- I175 通知直达与一键关注：watch hook 对 run.* 通知 payload 透传 `run_id` + GET /notifications 解析 ref 链透出 run_id + 前端铃铛 watch 通知点击跳 run 详情 + RunsPage「👁 关注 agent 动态」开关（一键幂等建/删 run.succeeded+failed 规则对）；单测（payload 透传/GET 透出/开关幂等 roundtrip）。
- I176 冒烟 63+审阅：发起 run→succeeded 通知直达→failed 通知→条件化静默→一键关注/退订 roundtrip。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M58 审阅 + **冒烟 63**。

**BC.5 M58 取舍**

M58 = **关注 agent 动态三件套**：I174 run 生命周期入白名单（完成/失败=agent 版 notify-worthy moments，行业三点收敛去其一一Gate 已有）/ I175 通知直达与一键关注（CI 可行动上下文+日志链接语义的组织内翻译）/ I176 冒烟 63+审阅，约 9 人日。run.interrupted 入白名单（与 approval.requested 双份——M55 降噪违背）、站内跨 kind 合并（需新证据）、过程事件入白名单（requested/started/tokens/span=记账面）、显式容量、Cycles 多周期、derived、多节律报告留 backlog。

## BD. M59 前置调研：「等待我」行动聚合 / 模板包升级溯源 / 2027 前瞻（2026-09-27）

> 目标协议触发：M58 完成后开启。防重查：候选池 grep——run 域「等待我」行动聚合（**无专项调研**——M12「我的工作」是任务视角[分配给我的]，审批中心是单域视角；「按谁需要行动聚合」的行动视角未查过）、watch 邮件摘要化（接近 M55 已裁决的「第二套定时窗口」——维持需新证据）、本体/模板域刷新（**M7 后 30+ 迭代空白**——pack 版本/升级/实例溯源语义未查过）、新特性扫描（照例）、显式容量/Cycles/derived/多节律报告/站内跨 kind 合并（均维持）。本轮三路新调研（行动聚合收件箱范式 / 模板市场升级语义 / 2027 前瞻），选定 **M59 = 行动聚合与包治理三件套**。

**BD.1 「等待我」行动聚合（action-required 视角）**

- 产品范式：Linear Inbox 是「需要我处理」队列的 canonical 形态——按**谁需要行动**聚合（review request/assignment/mention），而非按事件类型；GitHub notifications 有 `reason:review-requested` 过滤器、Jira 有「pending my approval」视图——**行动视角与任务视角（My page「分配给我」）是两套正交面**：前者回答「什么在等我动手」，后者回答「我名下有什么」。
- 对本项目的映射：`GET /my/attention` 纯读投影，三分区——**待我审批**（我任 owner 的项目内 pending approvals——decider 语义即 owner，与 I96 approval 通知收件人同口径）、**等我恢复的运行**（我可见项目内 interrupted runs——Gate 语义即等人）、**我的临期项**（assignee=me 且 due≤3 天未完成）；每分区计数+清单。前端 MyWorkPage 顶部「⏳ 等待我」卡，分区点击跳对应页（审批中心/Runs/我的工作）。审批中心与 Runs 页不动——聚合面只做「跨域入口」，不做第二套操作面（YAGNI）。

**BD.2 模板包升级溯源（marketplace update 语义的组织内翻译）**

- 产品范式：[VS Code 扩展市场](https://code.visualstudio.com)的核心生命周期语义=**版本化+更新可见**（"Show Extension Updates"）；[Obsidian 社区插件](https://github.com/obsidianmd/obsidian-releases)有提交+治理流程；两者的共同本质：**实例与模板版本解耦后，「谁还跑在旧版」成为一等可见信息**。
- 对本项目的映射：pack 已有 version（本体版本，M4 起版本化），但**实例化时刻的版本未记录**——`project.created` payload 增量加 `ontology_version`（旧实例无此键→诚实显示「早期实例」）；`GET /template-packs/{name}/usages` 从事件流聚合实例项目清单（名称/出生版本/当前 pack 版本对比/活跃状态）+ 模板中心「实例 N·落后 M 版」徽标。**升级影响面可见化**：重导入升版本后，一眼看出哪些项目出身旧版——不做自动迁移（本体演进是人工治理决策，M4 纪律），只做可见性。

**BD.3 2027 前瞻**

- Gartner 预测 **2027 年 40%+ agentic AI 项目将被取消**（[mtm.video](https://www.mtm.video)）——洗牌期将至，失败归因于「混沌环境+无标准」；Kanbanchi 2026-27 诚实评估（[Kanbanchi](https://kanbanchi.com)）：AI 擅长例行任务管理（建任务/改状态/提醒/分发/总结），人聚焦高价值——**增强而非替代**。对本项目的含义：幸存者画像=**标准化+可审计+人指挥**——AgentPM 的本体类型系统/事件溯源审计/Gate 治理正是该画像的三支柱；40% 取消率的反面恰是工程化管理系统的机会面。无新功能缺口，路线强确认。

**BD.4 M59 设计映射与验证纪律（沿用）**

- I177 「等待我」行动聚合：`GET /my/attention`（三分区计数+清单，可见性门与审批中心/Runs/MyWork 同口径）+ MyWorkPage「⏳ 等待我」卡（分区点击跳转）+ api.ts getMyAttention；单测（三分区各命中与不命中/owner 才见审批/非成员不见/rebuild 一致/空态诚实）。
- I178 模板包实例溯源：project.created payload +ontology_version（增量键）+ `GET /template-packs/{name}/usages`（实例清单：项目名/出生版本/落后 badge）+ 模板中心 pack 卡「实例 N」入口；单测（usages 聚合正确/早期实例无版本键的诚实显示/多实例排序/rebuild）。
- I179 冒烟 64+审阅：三分区聚合 roundtrip→pack 实例两项目+版本对比→docs 收口 + M59 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M59 审阅 + **冒烟 64**。

**BD.5 M59 取舍**

M59 = **行动聚合与包治理三件套**：I177 「等待我」行动聚合（Linear Inbox 行动视角——与 MyWork 任务视角正交）/ I178 模板包实例溯源与升级影响（VS Code/Obsidian update 语义翻译——可见性不做自动迁移）/ I179 冒烟 64+审阅，约 9 人日。watch 邮件摘要化（第二套定时窗口需新证据）、审批页/Runs 页重构（聚合面只做入口）、显式容量、Cycles 多周期、derived、多节律报告、站内跨 kind 合并留 backlog。

## BE. M60 前置调研：备份恢复演练 / 组合健康趋势 / 健康分模型对照（2026-09-27）

> 目标协议触发：M59 完成后开启。防重查：候选池 grep——备份/恢复（**§L.3 裁决「NDJSON 仅补充、备份走 DB 层」后一直留 backlog**——docs/11 有手工命令无工具无演练）、角色市场/角色版本化（无记录——单实例 YAML 治理偏过度设计，**降级不查**）、组合健康趋势（M23 组合总览是当前态聚合·M30 健康史按项目——**跨项目趋势对比无调研**）、健康分模型刷新（M30 建分后未对照行业框架）、新特性扫描（BC.3/BD.3 连续两轮同向结论，边际价值低——本轮并入健康分对照）。本轮三路新调研（SQLite 自托管备份工程共识 / 组合层流指标 / DORA 与 Flow 框架对照），选定 **M60 = 运维韧性与组合洞察三件套**。

**BE.1 备份/恢复演练（「备份会自己跑，演练是为了证明恢复有效」）**

- 工程共识：**绝不直接拷贝活库文件**——WAL 模式下直接 cp 会丢未 checkpoint 的帧（[Slipway](https://docs.sailscasts.com)/[Drupal](https://www.drupal.org)：用在线备份 API[`sqlite3_backup_*`/`.backup`/`VACUUM INTO`]取一致性快照）；自托管标配 Litestream 做 WAL 连续流复制到对象存储（[SSDNodes](https://www.ssdnodes.com)），但单机场景「备份命令+定期演练」已够（[Kazma DR 文档](https://kazma.ai)：**"backups run themselves; the drill exists to prove the RESTORE still works"**）；[2026 WAL 生产指南](https://www.kunalganglani.com)把 restore drill 列为标配交付物。
- 对本项目的映射：`tools/backup.py`（apm.db 走 sqlite3 backup API + `content/` 打包 + `ontologies/` 打包 + manifest.json[版本/时间/文件清单] → 单 zip）与 `tools/restore.py`（解包到目标 data dir + 完整性校验）；**冒烟演练闭环**：备份→清空→恢复→rebuild→项目可读断言——「演练证明恢复有效」的直接工程化。Litestream 不引入（单机手动档，docs/11 补充连接说明）。APM_DATA_DIR 感知（演示隔离纪律自然兼容）。

**BE.2 组合健康趋势（跨项目流指标对照）**

- 产品现状：**Jira 原生做不了跨项目指标**——对照需 Atlassian Analytics（Premium/Enterprise）或第三方（[Grandia](https://grandiasolutions.com)/[Broken Build](https://brokenbuild.net)）；组合层标准指标集=**中位周期时间、吞吐、WIP、阻塞占比**（[Umbrex R&D 流指标手册](https://umbrex.com)）；SAFe 语境加 PI 可预测性（[Savah](https://www.savahapp.com)）；专门流分析工具（[Businessmap](https://businessmap.io)）卖的就是 CFD+周期散点+吞吐。
- 对本项目的映射：`GET /portfolio/health-trend` 纯投影——可见项目的健康史对齐采样（每项目近 N 周分数序列+方向箭头）+ **组合中位线**；每项目附流指标三件：**中位完成周期**（item.created→done 事件对中位天数）、**近 4 周吞吐**（done 计数/周）、**当前 WIP**（in_progress 计数）——Flow Framework 三指标原生可算（事件溯源红利第十二例：流指标=事件对投影，零埋点）。Dashboard 组合卡加趋势行。原生 Jira 的缺口恰是 AgentPM 事件内核的免费午餐。

**BE.3 健康分模型对照（DORA/Flow 框架校验）**

- 框架基线：DORA 四键（部署频率/变更前置时长/变更失败率/恢复时长）是首个实证交付性能框架（[coderbuds](https://coderbuds.com)）；Flow Framework 四指标（周期/WIP/流效率/吞吐）与 DORA/SPACE 互补（[targetboard](https://targetboard.ai)）；2026 研究（[levitation](https://levitation.in)）：240 团队 75% 在引入 AI 后 DORA 指标下滑——**AI 加速产出但不天然加速健康**，治理与队列管理才是杠杆。
- 对本项目的映射：M30 健康分五因子（完成率/超期/Gate 挂起/吞吐/工时记账）已覆盖 Flow 三指标的健康面与滞后面——本轮以 BE.2 的流指标**并排呈现**（健康分=结论，流指标=归因入口），不改分模型（无证据支持改权重）；「AI 后 DORA 下滑」研究反向确认 AgentPM「人在环+审计」路线：agent 加速必须配治理面板。健康分模型刷新留待有数据证据时再议。

**BE.4 M60 设计映射与验证纪律（沿用）**

- I180 备份/恢复演练：tools/backup.py（sqlite3 backup API→临时一致库+content/ 仓 zip+ontologies/ zip+manifest.json→单 zip 产物）+ tools/restore.py（解包校验 manifest→落目标 APM_DATA_DIR）+ docs/11 补「演练三步」段；冒烟含演练闭环（备份→清空→恢复→rebuild→断言项目与工件可读——live==replay 纪律的灾备版）。
- I181 组合健康趋势：`GET /portfolio/health-trend`（可见项目健康史采样对齐+组合中位线+方向）+ per-project 流指标（中位完成周期/近 4 周吞吐/WIP）+ Dashboard 组合卡趋势行 + api.ts；单测（趋势对齐/中位线/流指标算术/不可见项目不泄漏/rebuild 一致）。
- I182 冒烟 65+审阅：演练闭环 roundtrip→组合趋势与流指标 roundtrip + docs 收口 + M60 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M60 审阅 + **冒烟 65**。

**BE.5 M60 取舍**

M60 = **运维韧性与组合洞察三件套**：I180 备份/恢复演练工具（在线备份 API+演练闭环——灾备版的 live==replay）/ I181 组合健康趋势与流指标（Jira 原生缺口的事件内核免费午餐——健康分=结论流指标=归因）/ I182 冒烟 65+审阅，约 9 人日。Litestream 连续复制（单机手动档够用，docs/11 留连接说明）、角色市场/角色版本化（单实例 YAML 治理过度设计）、健康分权重刷新（无数据证据不动）、显式容量、Cycles 多周期、derived、多节律报告、站内跨 kind 合并、watch 邮件摘要化留 backlog。

## BF. M61 前置调研：事件表体积观测 / 移动端响应式审计 / 会话搜索与导出（2026-09-27）

> 目标协议触发：M60 完成后开启。防重查：候选池 grep——事件表体积/归档（**§K.3 已裁决「归档=导出非删除」且导出/导入/备份工具齐备[M13-I43/M14-I45/M60-I180]，但「体积观测端点」与增长认知从未落地**）、移动端响应式（§N.2 调研过 PWA 路线[M15 选 responsive-first]，**但 M15 之后 10+ 新页/新卡从未过 375px 审计——审计刷新非重复调研**）、会话搜索/导出（§D 调研过轨迹数据模型[Langfuse/OpenInference]，**但会话消息既不可搜索也不可导出——产品化缺口非模型缺口**）、新特性扫描（BC.3/BD.3/BE.3 三轮同向，边际价值趋零，并入维持项）。本轮三路新调研（事件溯源长期运行成长治理 / 移动端审计缺口基线 / 对话历史搜索的 UX 共识），选定 **M61 = 治理观测与轨迹可寻三件套**。

**BF.1 事件表体积观测（事件溯源长期运行的「先测后治」）**

- 行业共识（[Event-Driven.io Marten snapshots](https://event-driven.io)/**[Kurrent/EventStoreDB](https://kurrentdb.kurrent.io)**/[CodeOpinion](https://codeopinion.com)）：成长治理三板斧=**短流优先**（按时间窗切流）→ **快照**（每 N 事件一拍，非每操作）→ **截断**（`$tb` truncate-before 元数据在快照后剪掉流前缀，剪掉的部分进冷存储归档）。同向告诫：**快照是优化不是默认**——读侧扩展靠投影/read model 解决，别过早优化（[EventSourcingDB docs](https://docs.eventsourcingdb.io)）；[Microsoft Learn Cosmos DB 事件仓 housekeeping](https://learn.microsoft.com)同构：有快照后只需快照之后的事件做 rehydrate。
- 对本项目的映射：AgentPM 是**单一全局事件流**（非 per-aggregate 流），且 live==replay 不变量意味着**任何删除都断链**（§K.3 裁决不变）——三板斧的「截断/快照」对我们**不适用**：整库即流，M60 的 zip 备份就是快照形态，rebuild 就是 rehydrate。真正缺的是**观测**：没有端点能回答「事件表现在多大、什么类型在涨、最老的事件多老」——这是「先测后治」的第一步，也是拒绝过早优化的证据基线。`GET /system/event-store-stats` 纯读（总事件数/库体积/按 agg_type×event_type 分布/最早最晚时间戳），不改任何数据；治理动作（若未来需要）=既有导出+备份组合，无新机制。

**BF.2 移动端响应式审计刷新（375px 成为默认下限之后）**

- 审计基线（[Polypane overlooked breakpoints](https://polypane.app)/[NN Group breakpoints](https://www.nngroup.com)/[BrowserStack 2025](https://www.browserstack.com)）：**375px 成为大家「开始测试」的宽度，320px 设备被系统性忽略**——审计缺口是小屏本身；2026 事实标准断点 480/768/1024/1440（[RedefineWeb](https://redefineweb.com)）。企业仪表盘常见失败面（[pirateskills](https://pirateskills.com)/[skills.rest Dashboard Mobile System-First](https://skills.rest)）：**导航与内容重叠、表格/图表横向溢出、按钮出屏、字号过小**；系统优先审计法=先审共享壳层（shell/header），再把「必须移动原生」的组件（导航）单独分档。
- 对本项目的映射：M15 选 responsive-first（Tailwind 断点）后，**新增 10+ 页/卡从未过小屏审计**（MyWork 等待我卡/Templates PackDrawer 实例区/Assets 使用洞察/Dashboard 组合趋势列/WatchRules/QuietHours/Runs WatchAgentToggle/通知折叠组…）；已知风险点=固定宽度行（如 Dashboard `w-32` 项目名列在 375px 挤压溢出）。审计动作=壳层（AppShell 侧栏）+新卡片逐页 375px 检查，修复最差三处（横向溢出/固定宽/表单挤压），**不做** PWA/原生 App（§N.2 裁决维持）。

**BF.3 会话搜索与导出（「被遗忘的对话问题」的组织内解法）**

- UX 共识：ChatGPT 侧栏搜索只匹配**标题+少量元数据**、Claude 只匹配标题——内容级检索两家都弱，长历史里知识持续流失（**[The forgotten conversation problem, UX Collective](https://uxdesign.cc/the-forgotten-conversation-problem-in-ai-chat-4d3d0c3ea525)**）；专门的[对话历史搜索模式库](https://aiuxplayground.com/pattern/conversation-search)总结为：按关键词/日期/项目/标签过滤，命中后**跳转定位到消息**；社区为「搜导出的 Claude 历史」专门造工具（[Reddit r/ClaudeAI](https://www.reddit.com/r/ClaudeAI/comments/1hxwdx3/i_made_a_tool_to_search_through_claude)）——第三方补位即需求实证；数据导出（JSON 全量）被视为对抗锁定（[MacStories](https://www.macstories.net/linked/claudes-chat-history-and-app-integrations-as-a-form-of-lock-in)）。
- 对本项目的映射：AgentPM 对话/消息**全是事件**（conversation.message 等）却接不进 ⌘K——`/search` 只索引 items+comments（M22-I68）。消息表已有投影，FTS 索引加一张 `messages_search`（CJK bigram 复用 `_bigrams`）+ `@on("conversation.message")` 投影器（注册在消息投影器之后）= 事件溯源红利第十三例；导出走**会话 Markdown 转写**（人读优先，与 NDJSON 机器导出互补——GitLab 审计事件「DB 留存+流式外送」的组织内语义）。搜索可见性沿用 `_visible` 项目裁剪（与 items/comments 同口径）。

**BF.4 M61 设计映射与验证纪律（沿用）**

- I183 事件表体积观测：`GET /system/event-store-stats`（COUNT/页数→字节/agg_type×event_type GROUP BY/最早最晚 ts）+ 系统面板卡（admin 可见——与 rebuild 同域）+ 单测（计数对账/分布行/空库不炸）。
- I184 会话搜索与导出：schema 加 `messages_search` FTS + `_reindex_message` + `@on("conversation.message")` + `/search` types 加 conversations（`_visible` 裁剪）+ `GET /conversations/{id}/export`（Markdown 转写含角色/时间/actor）+ 前端（⌘K 结果含会话命中行跳转；会话详情导出按钮）+ 单测（中文 bigram 命中/不可见项目不泄漏/转写含 actor 与 parent 结构/rebuild 一致）。
- I185 移动端审计刷新+冒烟 66+审阅：AppShell+新卡片 375px 审计，修复最差三处；冒烟 66（体积观测 roundtrip→会话中文搜索命中→导出含结构）+ 全量回归 + docs 收口 + M61 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M61 审阅 + **冒烟 66**。

**BF.5 M61 取舍**

M61 = **治理观测与轨迹可寻三件套**：I183 事件表体积观测（先测后治——拒绝过早优化的证据基线）/ I184 会话搜索与导出（被遗忘对话问题的组织内解法——红利第十三例）/ I185 移动端审计刷新+冒烟 66+审阅，约 9 人日。事件流截断/快照（破坏 live==replay，§K.3 裁决维持——观测替治理）、PWA/原生 App（§N.2 裁决维持）、320px 极小屏专项（375px 为审计基线，320 留证据）、会话跨项目聚合视图（`_visible` 口径已覆盖，单独视图无增量）、消息级全文高亮定位（跳转会话详情已够，N=1 证据不足）留 backlog。

## BG. M62 前置调研：端点性能观测 / watch 规则渠道偏好 / Agent 用量聚合（2026-09-27）

> 目标协议触发：M61 完成后开启。防重查：候选池 grep——端点性能观测（**§M25 只调研过分页扩展[keyset]，M48-I146 做过并发治理[修锁不测延迟]，M61-I183 观测的是数据体积不是耗时——端点延迟观测无记录**）、watch 规则渠道偏好（pref_allows 矩阵自 I96 是 kind×channel 全局档，**规则级覆盖无调研无实现**）、审批中心刷新（§AN.2 已调研 SLA/超时[I126 timer→reminder→escalate]+M42 升级链清账，批量审批 M2 即有——**刷新缺研究增量，降级不查**）、Agent 用量聚合（§Q/M44 调研过 Langfuse 标准面[latency/token/cost/错误率按项目模型聚合]，**但组合级聚合端点从未建——runs 投影已记账[tokens/estimated_cost_usd]只差读侧**）。本轮三路新调研（FastAPI/SQLite 延迟观测实践 / 通知路由的渠道选择 UX / LLM spend 分析面），选定 **M62 = 性能观测与用量聚合三件套**。

**BG.1 端点性能观测（「先测后治」的延迟版——BF.1 姊妹题）**

- 工程共识（[FastAPI Middleware](https://fastapi.tiangolo.com)/[FastAPI Observability Lab](https://pub.towardsai.net)/[TDS Observability](https://tds.s-anand.net)）：中间件「before/after 每个请求都跑」是**请求计时/慢请求日志的标准位**——`time.perf_counter()` 包 `call_next`，超阈值（如 500ms）落慢日志；p95/p99 由聚合侧算（Prometheus histogram 语义），单机不引 Prometheus 则聚合入内存环形桶或落日志。SQLite 侧（[Stackademic WAL 笔记](https://blog.stackademic.com)/[chat2db 低延迟清单](https://chat2db.ai)）：审计套路=`EXPLAIN QUERY PLAN` 看 **SCAN（全表扫）vs SEARCH ... USING INDEX**；OR 无法合并双索引时改写 UNION；热端点 WHERE/ORDER BY 列补覆盖索引，schema 变更后复查。
- 对本项目的映射：`GET /system/slow-endpoints`（内存环形桶 per 路径计数+均值+最大耗时，超阈值样本保留——零依赖零新表，纯内存观测面）+ ASGI 计时中间件（读侧埋点不进事件流——**延迟遥测是运行时数据不是领域事实，入流会污染 live==replay**，与 token_delta 瞬态广播同理[M46 裁决]）；SQLite 索引审计=开发侧一次性动作（对热点查询跑 EXPLAIN QUERY PLAN，补缺失索引入 schema），不做在线分析器。

**BG.2 watch 规则渠道偏好（规则级路由的渠道选择）**

- 产品语义（[Jira+Slack 多条件路由](https://community.atlassian.com/forums/Automation-questions/Jira-Slack-Multiple-Notification-Conditions/qaq-p/1856886)/[Troopr Jira 通知指南](https://www.troopr.ai/post/jira-notifications-in-slack)/[PullNotifier GitHub 对比](https://pullnotifier.com/github-slack-integration)）：主流 UX 三型=**渠道内订阅管理**（`/github subscribe` 在频道里跑——Slack 语义，AgentPM 无第三方渠道不适用）、**自动化规则+目的地**（Jira Automation：条件→渠道，规则即路由）、**事件类型/过滤器路由**；常见痛点=规则重叠、跨实体错路由（[GitHub 社区 #196194](https://github.com/orgs/community/discussions/196194)）。Slack 自己的 per-channel preferences（[设置文档](https://slack.com/help/articles/218551037-Set-your-notification-preferences)）是「按会话覆盖全局」的母型。
- 对本项目的映射：watch_rules 加 `channels` 列（NULL=跟随全局 pref_allows kind×channel 档[I96 语义不变]；`["inapp"]`/`["email"]`/双值=规则级覆盖）——**单事实携带全量新态**：watch.updated 事件已整行 upsert[I171]，payload 加 channels 即向后兼容（缺键=跟随全局，旧库事件自然兼容）；hook 投递侧查规则行内覆盖、无则回退 pref_allows；前端规则行加渠道多选片（站内/邮件）。**不做** 多目的地分发（一规则多渠道=复制通知，Jira Automation 语义在 N=1 单机是负担）。

**BG.3 Agent 用量与成本聚合（Langfuse spend 面的组织内翻译）**

- 平台现状（[Langfuse 自托管](https://langfuse.com)/[deeplake 对比](https://deeplake.ai)/[pyimagesearch RAG 可观测](https://pyimagesearch.com)）：Langfuse[MIT 自托管]提供 trace 级 token/成本聚合仪表盘（价格表自动算 cost，按 user/agent/model 过滤）；OpenLLMetry=OTel 埋点层喂给后端；轻量替代=dsh-suite 类专用 cost/token 聚合看板+预算告警。共同语义：**spend 面回答「钱花在哪类工作上了」**。
- 对本项目的映射：**runs 投影自 M44 已记账**（total_input_tokens/total_output_tokens/estimated_cost_usd/agent_role/status/started_at）——`GET /portfolio/agent-usage` 纯读聚合（按 agent_role × 可见项目 GROUP BY：run 数/完成率/token 总量/成本合计/近 30 天窗口），**红利第十四例：账本事件已入流，聚合即得零埋点**；前端 Workload 页加「🤖 Agent 用量」卡（Top 角色行+成本+token）。**不做** 逐 run 明细第二入口（Runs 页已在）、预算告警（无消耗证据，N=1）、模型价格表管理（estimated_cost_usd 已在 run 落账时算好[M44]）。

**BG.4 M62 设计映射与验证纪律（沿用）**

- I186 端点性能观测：ASGI 计时中间件（perf_counter 环形桶 per 路径，阈值默认 500ms 可配）+ `GET /system/slow-endpoints`（admin 门）+ SQLite 索引审计（热点查询 EXPLAIN QUERY PLAN 核对，补缺失索引）+ 前端系统卡（Top 慢端点行）+ 单测（中间件计时/桶聚合/空态/慢样本保留/admin 403）。
- I187 watch 规则渠道偏好：watch_rules.channels 列（ALTER 迁移）+ WatchPatchIn.channels 校验[NULL/空/双通道白名单] + hook 投递侧覆盖回退 pref_allows + watch.updated payload +channels + GET /watch-rules 透出 + 前端规则行渠道片 + 单测（覆盖生效/回退全局/旧库缺键兼容/坏值 422/rebuild）。
- I188 Agent 用量聚合+冒烟 67+审阅：`GET /portfolio/agent-usage`（agent_role×项目聚合，_visible 口径）+ WorkloadPage「🤖 Agent 用量」卡 + 冒烟 67（慢端点观测 roundtrip→渠道覆盖与回退→用量聚合对账 runs 记账）+ 全量回归 + docs 收口 + M62 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M62 审阅 + **冒烟 67**。

**BG.5 M62 取舍**

M62 = **性能观测与用量聚合三件套**：I186 端点性能观测（延迟遥测运行时数据不进事件流——瞬态广播同理）/ I187 watch 规则渠道偏好（规则级覆盖回退全局——单事实携带全量新态）/ I188 Agent 用量聚合+冒烟 67+审阅（红利第十四例：runs 记账的读侧免费午餐），约 9 人日。Prometheus/Grafana 外导（单机内存桶够用）、慢请求全量落事件流（污染 live==replay）、多目的地分发、逐 run 用量第二入口、预算告警、模型价格表管理、审批中心刷新（SLA/升级链 M41/M42 已清账）留 backlog。

## BH. M63 前置调研：自动化触发 Agent 运行 / 项目级通知降级 / 工作项检查清单（2026-09-27）

> 目标协议触发：M62 完成后开启。防重查：候选池 grep——**工作项批量操作[上轮候选池误判：§U.3 (M22) 已完整调研且 I70 已建 batch-patch 端点——勾选批量条+逐事件逐项结果，候选作废]**、自动化触发 Agent 运行（ACTION_TYPES 六动作 assign/set_priority/set_field/set_status/notify/create_recurring——**无 agent 动作；编排只能靠人点「让 Agent 执行」或依赖链接续，规则面缺口**）、项目级通知降级（§Q/M44 调研过 watch/pref 语义但都是 opt-in 面与全局档——**opt-out 的「参与即响」降级无调研**）、工作项检查清单（schema 无 checklist；I67 只做评论清单项转子任务——**item 行内清单域缺失**）。本轮三路新调研（工作流自动化触发 agent 的防环共识 / GitHub-Slack 通知分档语义 / GitHub tasklist→sub-issues 演化），选定 **M63 = 编排与降噪三件套**。

**BH.1 自动化触发 Agent 运行（规则面补上 agent 动作——防环是第一设计约束）**

- 工程共识（[Zapier Agents 意外活动](https://help.zapier.com/hc/en-us/articles/45697420326285-Zapier-Agents-unexpected-activity-usage)/[n8n AI Agent 节点](https://www.cyberclick.net)/[n8n 防环实践](https://nirajiitr.com)）：**反馈环是自动化×agent 组合的头号事故源**——「agent 触发的写回恰恰是它自己监听的数据」；共识防环五件套=**自家写回不打标不触发**（"modified by automation" 标签/过滤）→ **硬迭代上限**（IF+Wait 封顶重试）→ **Error Trigger 兜底**（失败走告警而非静默重试）→ **不可逆动作前 HITL 审批** → 重复动作间限速（[n8nlab 安全清单](https://n8nlab.io)）。
- 对本项目的映射：ACTION_TYPES 加第七动作 `run_agent`（payload: agent_role + instruction ≤200 字；目标=event 关联的工作项，无项则 422——自动化挂在工作项上而非凭空开跑）；**防环三闸**：①触发白名单不扩（run.requested 等 run.* 永不入 TRIGGERS——watch 先例）②**agent 运行自身产生的事件[actor_id 前缀 runtime:]不触发 dispatch**——agent 写回是自动化的果不是因，加了它才可能成环（现有 guard 只挡 actor_type=automation）③**每规则每日硬上限**（当日该规则触发的 run 计数 ≥3 拒发——计数走事件查询零新表）。治理不降级：自动化触发的 run 与手点同链——Gate 照挂、审批照走、token 照记账（HITL 语义天然内建）。

**BH.2 项目级通知降级（GitHub watch 三档的组织内取两档）**

- 产品语义（[GitHub Docs 配置通知](https://docs.github.com/subscriptions-and-notifications/get-started/configuring-notifications)/[Slack 频道级设置](https://slack.com/help/articles/360056534254-Manage-notifications-for-specific-channels-and-direct-messages)/[社区讨论 #66334](https://github.com/orgs/community/discussions/66334)）：GitHub 仓库级 watch 三档=**All Activity / Participating & @mentions / Ignore**（仓库档覆盖全局默认；Ignore 连 @mentions 都吞）；Slack 频道级=覆盖全局+静音（可细到「静 @here 留 @user」）。共同痛点：参与即订阅太宽（评论一次就永久订阅），**缺的是 opt-out 一档而非 opt-in**。
- 对本项目的映射：project_members 加 `notify_level` 列（NULL=默认参与即响[现状]；`mentions_only`=**参与类通知静音**——comment 参与面/item 状态参与面不响；**mention/assignment/approval.requested/due_soon/watch 规则照常**——治理必达与显式订阅不静音）。**GitHub 的 Ignore 档不取**：连提及都吞会让审批漏接（approval 不该能被静音），取 Slack「保留直接提及」语义；All Activity 档即现状（参与者自动订阅已是最宽）。事件=`project.member_notify_level`（成员域第四事件，投影整行更新——单事实携带全量新态）；门插在 plan_notifications 的参与类分支。

**BH.3 工作项检查清单（GitHub tasklist→sub-issues 演化的反教训）**

- 产品语义（[GitHub About tasklists](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/about-tasklists)/[Adding sub-issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues)/[HN 讨论](https://news.ycombinator.com/item?id=42725692)）：GitHub 正把 Markdown tasklist 收敛为 **sub-issues 层级**（清单项一键转子 issue）；社区反馈分化——sub-issue 列表丢失了「同屏勾选的轻量感」（[讨论 #151832](https://github.com/orgs/community/discussions/151832)）。教训：**清单的价值在轻量（不打断、同屏勾），转实体是有重量的一步**。
- 对本项目的映射：items 加 `checklist` TEXT 列（JSON 数组 [{text, done}]，上限 20 项/单项 ≤200 字）；事件=`item.checklist_updated`（**整列覆盖**——custom_fields 整列覆盖纪律同款，payload 携带全量新清单）；投影=直接写列；UI=工作项抽屉清单区（添加/勾选/删除/进度 n/m）+ 看板卡「✓n/m」进度徽标（有清单才显示）。**不做**：清单项转子任务/独立实体（I67 extracted_tasks 已覆盖「升级」面——评论清单转 task；checklist→task 转换同款留 backlog）、清单进度影响完成率口径（advisory only——健康分不认它）。

**BH.4 M63 设计映射与验证纪律（沿用）**

- I189 自动化 run_agent：ACTION_TYPES +7、校验（role 存在/instruction ≤200/有关联 item）+ dispatch 分支（经 orchestrator 起 run·payload 标 origin=rule id）+ 防环三闸（TRIGGERS 不扩/runtime:* actor 不触发/每规则每日 ≤3 次）+ 自动化面板动作选项 + 单测（起 run 成功/无项 422/agent 写回不再触发/日上限/审批链保留）。
- I190 项目级通知降级：project_members.notify_level 列（ALTER）+ `project.member_notify_level` 事件+投影 + 成员门端点 PATCH /projects/{id}/members/{uid}/notify-level（owner 或本人）+ plan_notifications 参与类分支查档 + 成员面板档位切换 + 单测（mentions_only 静参与留提及/默认不变/rebuild 一致/非本人非 owner 403）。
- I191 检查清单+冒烟 68+审阅：items.checklist 列（ALTER）+ `item.checklist_updated` 事件+投影[整列覆盖] + PATCH 端点 + 抽屉清单区+看板卡进度徽标 + **冒烟 68**（run_agent 触发→防环→降级档 roundtrip→清单 roundtrip）+ 全量回归 + docs 收口 + M63 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M63 审阅 + **冒烟 68**。

**BH.5 M63 取舍**

M63 = **编排与降噪三件套**：I189 自动化 run_agent（防环三闸——反馈环是自动化×agent 头号事故源）/ I190 项目级通知降级（GitHub 三档取两档——Ignore 连提及都吞过于激进）/ I191 检查清单+冒烟 68+审阅（轻量勾选不做实体转换——GitHub 收敛教训反向指导），约 9 人日。触发白名单扩 run.*、Ignore 完整档、清单转子任务、清单进健康分、Slack 式 @here 细分静音留 backlog。

## BI. M64 前置调研：run 重试对比 / ⌘K 搜索深化 / 清单转子任务（2026-09-28）

> 目标协议触发：M63 完成后开启。防重查：候选池 grep——run 重试对比（**§A LangGraph「interrupt→resume/time travel」已调研，M4 建了 retry-from-checkpoint，但「重试链可视化+前后 diff」从未调研从未建**——OpenHands 把重试当独立 rollout 事后比，AgentPM 有 checkpointer 天然能做成链）、⌘K 搜索深化（**§U.1 (M22) 调研过全局搜索形态，M61 补 conversations 类型；facet 过滤/最近搜索/模糊导航无调研**）、清单转子任务（**BH.5 明示「证据足时再做」：I67 已建评论面转子任务链[extracted_tasks+渲染替换+409 幂等]，item 行内 checklist[M63]→task 是同构缺口，防重查证实无既有调研无实现**）、运行时间线增强（M4 已有 span 树+甘特+人机时间线，§D 轨迹模型已调研——**缺增量，降级不查**）。本轮三路新调研（LangGraph time-travel vs OpenHands 重试语义 / Cmd-K palette 设计模式 / 清单转实体的 hover 误触证据），选定 **M64 = 溯源与升级三件套**。

**BI.1 run 重试对比（「重跑后哪里变了」——checkpoint 语义的可视化）**

- 产品语义（**[LangGraph time travel](https://forum.langchain.com)**/[rpabotsworld 教程](https://rpabotsworld.com)/[OpenHands 评估](https://www.openhands.dev)）：LangGraph 是**确定性 checkpoint resume**——`get_state_history()` 取历史、从任意 checkpoint 重放、`update_state()` 可在续跑前改状态（fork 历史）；OpenHands 则把重跑当**独立 rollout** 事后比（多尝试 60.6%→66.4%），对比靠轨迹 JSONL。两派共识：**重试的可视价值在「与上次差在哪」**——不是第二份独立日志，而是带血缘的对照。
- 对本项目的映射：M4-I13 的 `run.retried_from_checkpoint` 事件已是链锚（payload.original 指向原 run）——`GET /runs/{id}/retry-lineage` 纯读投影（沿 original 回溯整链 + 每环 status/step 数/token/时长/产出工件），**红利第十五例：链事实已在流中，投影即得**；Runs 页重试卡片显示「↳ 重试自 run_xxx」+ 点击开对比抽屉（两列并排：状态/token/步骤数/工件列表——**diff 的是标量与清单不是正文**，正文在各自轨迹页）。**不做** state 编辑续跑（update_state 语义——Gate 审批已是人在环编辑点，第二编辑面属重复）、跨链合并视图（一条链一个抽屉）。

**BI.2 ⌘K 搜索深化（Linear/Raycast 式 palette 的三件补课）**

- UX 模式（**[setproduct.com palette 解剖](https://www.setproduct.com)**[Linear/Raycast/Vercel 十例拆解]/[VS Code docs](https://code.visualstudio.com)）：power-user palette 三标配=**模糊匹配**（fuzzy subsequence，非全等子串）、**recents 置顶**（最近命令/搜索默认浮出、可清空）、**前缀分域**（`>` 命令、`@` 人、`#` scope——一个入口多层语义）；常见失败态=空态无 recents、加载无骨架、无结果无「转全局搜索」出口。
- 对本项目的映射：⌘K 结果已含 items/comments/conversations/资产导航（M22/M61 累积），本轮补三件：①**recents 置顶**（最近 5 条搜索词 localStorage 本地存——搜索行为是个人 UI 态不进事件流，与 perf 遥测同理）；②**结果页 facets**（/search 返回已有 project 维度——前端按项目聚合 chips 过滤，零后端改动）；③**空态转出口**（无结果时一键「以 'q' 跳全局搜索」——palette 死角的 Linear 语义）。**不做** 前缀分域（单机 N=1 无多人 @ 语义，`#` 与既有「搜索 'x'」指令重叠）、服务端 fuzzy（FTS bigram 已够，前端子序列过滤导航项即可）。

**BI.3 清单转子任务（BH.5 的证据续期——hover 误触是 documented 反例）**

- UX 证据（**[GitLab #363613](https://gitlab.com)**：hover「Convert to Work Item」太易误触成社区长期抱怨/[Linear](https://linear.app)：选中清单 Cmd+Shift+O 批量转子 issue/[Atlassian Tick](https://community.atlassian.com)：清单项一键转 issue 解决复制粘贴)/[WCAG 1.4.13](https://www.w3.org)：hover 内容易意外触发与不可发现)——共识=**转换必须是显式低频动作**：hover 可发现但不可易触，转换后原位留痕可跳转。
- 对本项目的映射：与 I67 评论面转子任务**同构同链**——`POST /items/{id}/checklist/extract`（body: index；checklist 项 → 创建 task 概念工作项[标题=项文本] + `extracted_tasks` 复用[加 item_id 维度·同 item 同文本 409 幂等·与 comment 面共表] + checklist 项标记 `extracted: item_id`[整列覆盖纪律]）；UI=清单行 hover 出「→任务」（显式点击非 hover 直转·GitLab 教训）+ 卡片徽标不变；**不做** 批量选中转换（Linear Cmd+Shift+O——单机 N=1 频次不足）、转换后自动勾选（原始意图保留——done 与 extracted 正交）。

**BI.4 M64 设计映射与验证纪律（沿用）**

- I192 run 重试对比：`GET /runs/{id}/retry-lineage`（链回溯+每环标量）+ runs 投影不加列（链沿事件查）+ Runs 页「↳ 重试自」徽标与对比抽屉（两列并排标量/工件清单 diff）+ 单测（链回溯完整/多级链/diff 标量正确/无链单环 404 语义/rebuild 一致）。
- I193 ⌘K 搜索深化：palette recents（localStorage·上限 5·可清空）+ 结果页项目 facets（纯前端聚合）+ 空态转全局搜索出口 + 单测/组件测试（recents 读写/去重/上限——vitest 侧）。
- I194 清单转子任务+冒烟 69+审阅：`POST /items/{id}/checklist/extract`（index → create_item 全校验链 + extracted_tasks 复用加 item_id 维度 + 409 幂等 + checklist 项标记 extracted）+ 清单行「→任务」显式按钮 + **冒烟 69**（重试链 roundtrip→palette recents 语义→清单转任务 roundtrip+rebuild）+ 全量回归 + docs 收口 + M64 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M64 审阅 + **冒烟 69**。

**BI.5 M64 取舍**

M64 = **溯源与升级三件套**：I192 run 重试对比（checkpoint 血缘可视化——红利第十五例）/ I193 ⌘K 搜索深化（recents/facets/空态出口——palette 三标配）/ I194 清单转子任务+冒烟 69+审阅（BH.5 证据续期——显式点击防 hover 误触，与 I67 同构同链），约 9 人日。update_state 编辑续跑、跨链合并视图、前缀分域、服务端 fuzzy、批量选中转换、转换后自动勾选、运行时间线增强（M4 面已够）留 backlog。

## BJ. M65 前置调研：运行分叉 / 看板泳道 / 计划快照对比（2026-09-28）

> 目标协议触发：M64 完成后开启。防重查：候选池 grep——运行分叉（**§A LangGraph update_state「续跑前改状态」已调研但只留概念；对话树 parent_conversation_id 自 MVP 就有血缘存储；M64-I192 做了链对比后「从历史点分叉新支线」的执行面缺口显形——无实现无专项调研**）、看板泳道（**§A 记录 Taiga/Kanboard 泳道+WIP 语义，M24-I76 做的是时间线泳道避让不是看板——看板已有 group_by 单维[saved_views 白名单]但无第二维交叉，防重查证实无专项调研**）、回收站审计刷新（**M33-I103 已建 item.archived/restored+回收站抽屉——候选作废**，防重查纪律第三次自证）、邮件路由增强（**M37-I113/I114 已建主题路由+回复转评论——作废**）。本轮三路新调研（Git 分支模型对 agent 运行的隐喻迁移 / 看板泳道与 WIP 的看板语义 / 基线对比与计划快照），选定 **M65 = 编排纵深三件套**。

**BJ.1 运行分叉（从 checkpoint 开支线——Git branch 的 run 域翻译）**

- 产品语义（[LangGraph time travel](https://forum.langchain.com)/[rpabotsworld](https://rpabotsworld.com)/[OpenHands](https://www.openhands.dev)）：LangGraph 的 update_state 允许**从任意 checkpoint 改状态续跑**——原 run 不动、分叉出平行历史（fork 语义）；Git 的 branch 是同构隐喻：主线保留、支线试验、好结果合回。OpenHands 则每次 rerun 都是独立 rollout（无血缘）。共识=**试验性重跑需要分支而非覆盖**。
- 对本项目的映射：`POST /runs/{run_id}/fork`（body: instruction 可选≤500 字——分叉时的修正指令）——以原 run 的 conversation+item+role+instruction 为底**开新 run**（start_run 标准链·新 run_id·payload 加 `forked_from: run_id`），原 run 及其 lineage 不动；retry-lineage 扩展为**树感知**（沿 retried_from_checkpoint 与 forked_from 双边回溯，`GET /runs/{id}/lineage` 保留 retry 线性语义、新 `?tree=1` 返回分叉树）。防环沿用 M64 guard。**不做** state 级编辑续跑（update_state 需 checkpointer state 序列化——SqliteSaver 已有但暴露 state 编辑面是治理决策，Gate 审批已是人在环编辑点）、分叉自动合并（合并=人看对比抽屉后采纳，无自动写回）。

**BJ.2 看板泳道（第二分组维度——Taiga/Kanboard 的看板语义）**

- 产品语义（[Taiga](https://taiga.io)/[Kanboard docs](https://kanboard.org)）：泳道=列（status）之外的**行维度**（按 assignee/feature/优先级切行），列×行交叉定位瓶颈；Kanboard 泳道+列 WIP 双限是看板法标配。共同痛点=纯列视图多人同项目时「谁在做什么」要靠卡片头像扫读。
- 对本项目的映射：`get_board` 已支持 `group_by` 单维（M6-I21：状态生命周期或 `field:<id>`）——本轮加**第二维 `swimlane_by`**（`assignee_id`/`feature_id`/`priority` 白名单三选一，None=无泳道）；投影零改动（纯读分组），前端看板列内按泳道小标题分行（行头显示维度值+计数）；saved_views 定义加 swimlane_by 键（视图持久化白名单扩一键）。**不做** 泳道级 WIP 限制（自动化里 set_status 闭锁已有阻塞语义，WIP 计数告警无证据）、跨项目泳道（board 单项目域）。

**BJ.3 计划快照对比（多基线存了，横向对比没做）**

- 产品语义（MS Project 多基线/[OpenProject baseline diff](https://www.openproject.org)）：多基线的价值不在存而在**比**——任意两条基线并排看「计划如何漂移」；M24-I76 已做多基线存储+切换显隐+拖拽幽灵，但「基线 A vs 基线 B」的横向对比表未建。
- 对本项目的映射：`GET /projects/{id}/baselines/compare?a=&b=`——两条基线的 item 级 diff（日期偏移/新增消失项计数）+ TimelinePage「📊 对比」入口选两条基线出对比抽屉。baselines 投影自 M24 未动——纯读聚合。**不做** 三条以上对比（两两对比已覆盖诊断语义）、基线自动diff报告（周报已有偏差面 I127）。

**BJ.4 M65 设计映射与验证纪律（沿用）**

- I195 运行分叉：`POST /runs/{id}/fork`（forked_from 血缘+标准 start_run 链）+ lineage 树感知（双边回溯）+ Runs 页「⑂ 分叉」按钮与指令输入 + 单测（分叉 run 创建且原 run 不动/forked_from 在事件与投影可见/树回溯含支线/rebuild 一致/防环 guard 覆盖 forked 事件）。
- I196 看板泳道：get_board + swimlane_by（白名单校验·None 兼容）+ 前端列内泳道行渲染 + saved_views 白名单+1 键 + 单测（assignee 分行/feature 分行/None 无泳道/视图存取 roundtrip/rebuild 无涉——纯读）。
- I197 基线对比+冒烟 70+审阅：`GET /projects/{id}/baselines/compare`（两两 item 级 diff：日期偏移/新增/消失）+ TimelinePage 对比入口+抽屉 + **冒烟 70**（fork 分叉→树回溯→泳道分组→基线对比）+ 全量回归 + docs 收口 + M65 审阅。
- 验证纪律：每迭代只跑相关测试；全量收敛至 M65 审阅 + **冒烟 70**。

**BJ.5 M65 取舍**

M65 = **编排纵深三件套**：I195 运行分叉（checkpoint 支线——Git branch 隐喻的 run 域翻译）/ I196 看板泳道（第二分组维度——列×行交叉定位瓶颈）/ I197 基线对比+冒烟 70+审阅（多基线的价值在比不在存），约 9 人日。state 级编辑续跑、分叉自动合并、泳道 WIP 告警、跨项目泳道、三条以上基线对比、回收站审计刷新（M33 已建）、邮件路由增强（M37 已建）留 backlog。
