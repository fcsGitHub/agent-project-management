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
