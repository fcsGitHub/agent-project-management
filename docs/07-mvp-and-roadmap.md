# 07 · MVP 最小实现与扩展路线

> v0.2：按评审意见扩充——功能/对话层级、提示词分层、NL 命令（L1 级）、本体模块进入 MVP；相应调整任务拆解与验收脚本。功能完备性以 03 §5 核对表为准。
> v0.3：资产库最小闭环（三库 + 沉淀 + FTS 检索 + Agent 资产工具）进入 MVP（09 §9）。

## 1. MVP 目标与边界

**一句话**：单人 docker 一键起，跑通「一句话需求 → PRD → 任务分解 → Agent 开发 → 审批验收 → 发布说明」全闭环；全程以**项目→功能→对话**导航，对话随时可打断/恢复，提示词分层可见可编辑，可用自然语言驱动页面，轨迹可查可审计；**值得复用的工件可沉淀为组织资产并在新项目中被 Agent 检索复用**。

### 1.1 MVP 明确包含（In Scope）

| 模块 | MVP 内容 |
| --- | --- |
| 项目/功能 | 项目 CRUD（双模板）、功能 CRUD 与功能页（看板切片/对话列表/工件切片三 Tab）、里程碑只读展示 |
| **对话**（v0.2） | 消息树持久化（刷新/重启无损）、打断/继续/挂起、执行中发送消息=打断+注入、起草/执行/评审/临时四类对话 |
| **提示词分层**（v0.2） | L1-L4 分层查看（上下文抽屉）、L1 宪章与 L3 指令编辑 + 版本史（存 Git prompts/） |
| **本体**（v0.2） | 内置 software-dev 与 generic 两套；本体页只读浏览 + 校验状态；YAML 手工定制路径（改文件重载） |
| **资产库**（v0.3） | 三库（产品/测试/文档，本体 libraries 注册）；工件「沉淀为资产」+ 入库评审 Gate（asset_review）；资产页（库 Tab/过滤/FTS5 全文检索）；Agent 工具 search_assets/read_asset/link_asset；来源链/引用链记录与展示 |
| 工作项 | CRUD、状态机（本体 lifecycle 驱动五桶）、依赖 contains/depends_on/produces/consumes、指派（人/Agent 角色） |
| 看板 | 看板 + 列表两视图、卡片内联批准、多选批量「让 Agent 做」、按功能切片 |
| Agent 角色 | 4 个：PM-Agent、Planner-Agent、Dev-Agent、Release-Agent（YAML 定义）；QA/Architect 角色文件就绪但不挂默认模板 |
| 运行时 | LangGraph 编排、SQLite checkpointer、interrupt/审批/resume、失败重试（Run 级）、崩溃合成事件配平（dsh 模式） |
| 审批 | Gate（PRD/计划/代码/发布）+ dangerous 工具审批 + 批量批准 + 修改后恢复；fail-closed + 单次授权 |
| **NL 命令**（v0.2） | ⌘K 自然语言模式 L1 级：导航/过滤/选择/批量审批；只读直执、写操作预览确认、可撤销、事件审计 |
| 工件 | 内容仓（Git）、PRD/WBS/发布说明落盘、内置 Markdown 编辑器（人的修改也成 commit） |
| 轨迹 | span 落库（OTel 对齐 + apm.* 扩展）、对话内步骤行、Run 抽屉（左树右甘特 + 人机交织时间线）、Graph 节点角标联动 |
| 审计 | 事件流查询：过滤/展开 payload/导出 CSV |
| 实时 | SSE 推送（对话流式、看板、审批徽标、活动流） |
| 部署 | docker-compose；`.env` 配 LLM key（OpenAI 兼容协议；UI-Agent 可单独配小模型） |

### 1.2 MVP 明确不做（Out of Scope → 见扩展路线）

多用户/权限、多租户、甘特图、日历、泳道与 WIP、保存的自定义视图、规则引擎（auto-approve 仅三个固定开关）、时间/成本报表、Wiki/聊天、代码沙箱执行（Dev-Agent 产出以补丁/diff 交付）、Webhook、OTel 导出、移动端、**对话分叉/树状多枝**（V1.2）、**上下文自动压缩**（V1.2，三事件锁）、**NL L2/L3 级与语音**（V1.3/V2）、**本体表单编辑器**（V1.2）、**QA/缺陷回流闭环**（V1.2）、**资产增强**：沉淀建议（V1.2）、语义检索（V1.3）、fork-diff 与标签本体治理（V2）、资产市场（V3）。

> 判断标准：每一项都被追问"没有它闭环断吗？"——不断则出 MVP。但评审要求的四个新能力（对话层级/提示词分层/NL L1/本体双内置）已证明是闭环的**结构组成部分**，故入 MVP。

## 2. Agent 角色定义（YAML，声明式可扩展）

```yaml
# agents/pm-agent.yaml —— 新增角色零后端代码（借鉴 CrewAI/ChatDev 2.0）
id: pm-agent
display_name: 产品经理 Agent
concepts: [requirement, feature]            # 适配的本体概念（08），非软件项目可复用角色
model: { provider: openai_compat, name: gpt-4.1-mini, temperature: 0.3 }
system_prompt_file: prompts/roles/pm-agent.md   # 提示词 L4，Git 版本化
tools: [read_artifact, write_artifact, search_web]   # 白名单；权限级别随工具自带
output:                                            # 产出契约（CrewAI expected_output 思想）
  artifact: artifacts/prd.md
  schema: schemas/prd.schema.json                  # 结构校验，失败自修一次
  on_complete: request_gate_approval               # 完成即挂 Gate
limits: { max_steps: 12, max_tokens_per_run: 60000 }
```

运行时加载 YAML → 组装 LangGraph 子图（节点：analyze → draft → self_check → gate）。**UI-Agent 单独一类**：不产出工件、只调应用 API（工具=页面动作），模型可配置为小模型（见 06 §5.2）。

### 2.5 前端开源复用清单（v0.3 增，落实"尽量复用开源"）

> 评审 Demo（demo.html）的视觉与交互即按下列组件的设计语言绘制（对标 Linear / Plane / Huly），正式实现不做视觉自研，只写业务胶水。均为 MIT/ISC 许可，可商用。

| 复用组件 | 覆盖 | 备注 |
| --- | --- | --- |
| **shadcn/ui**（Radix 原语 + Tailwind） | 按钮/对话框/抽屉/下拉/表格等全部基础组件 | 源码拷贝式引入，深度可改；zinc 中性色 + 单强调色体系 |
| **lucide-react** | 全套线性图标 | Demo 内嵌同款 SVG path |
| **cmdk** | ⌘K 命令面板（命令 + 自然语言双模式） | 06 §5 的交互载体 |
| **React Flow（@xyflow）** | 项目图 DAG / Gate 节点 / 角标联动 / V1.2 编辑 | 替代自研 SVG 图编辑器 |
| **Sonner** | Toast 通知（操作回显/撤销入口） | — |
| **TanStack Query + Router + Table** | 数据层（SSE 增量更新）/ 路由 / 审计表格 | URL 即状态配合 Router 实现 |
| **react-markdown + shiki** | 工件/资产正文渲染与代码高亮 | diff 视图用 react-diff-view（候选） |
| 后端沿用 §5 选型 | FastAPI / LangGraph / SQLite→PG / Git | 免协议层，直接组合 |

自研范围收敛为三块：事件内核（事件表 + 投影器）、图编排胶水（Orchestrator 状态机）、以及上述组件之上的业务页面组装。

## 3. API 概要（API-first，页面与 NL 共用同一 API）

```
POST   /api/projects / GET /api/projects/{id}/graph
POST   /api/projects/{id}/features            建功能（含简报初稿）
GET    /api/features/{id}?include=items,conversations,artifacts
POST   /api/conversations                     {feature_id, kind, instruction, item_id?}
GET    /api/conversations/{id}/messages       消息树
POST   /api/conversations/{id}/messages       发消息（执行中=打断+注入）
POST   /api/conversations/{id}/interrupt      打断
POST   /api/conversations/{id}/resume         {instruction?} 继续或带新指令继续
GET    /api/conversations/{id}/context        提示词分层（L1-L4 + 合并预览）
PUT    /api/conversations/{id}/context/{level} 编辑提示词层（L1/L3；L2 V1.1）
POST   /api/ui_commands                       {utterance, page_state} → NL L1（预览/确认）
PATCH  /api/items/{id}   POST /api/items/{id}/relations
POST   /api/runs  POST /api/runs/{id}/retry   GET /api/runs/{id}/spans|timeline
GET    /api/approvals?status=pending  POST /api/approvals/{id}/decision
GET    /api/events  GET /api/stream           SSE
GET    /api/projects/{id}/ontology            本体（只读）+ 校验状态
GET    /api/assets?library=&kind=&q=&tag=     资产检索（FTS + 元数据过滤）
POST   /api/assets                            沉淀为资产（draft；payload 含来源工件/commit）
POST   /api/assets/{id}/submit_review         提请入库评审（asset_review Gate）
GET    /api/assets/{id}                       详情（版本史/来源链/引用链）
POST   /api/assets/{id}/link                  引用登记（项目/工件/对话）
POST   /api/system/rebuild-projections
```

## 4. 实现拆解与工作量（单人估算，v0.2 调整）

| # | 任务 | 依赖 | 估时 |
| --- | --- | --- | --- |
| 1 | 骨架：FastAPI + SQLite + 事件表 + 投影器 + rebuild | — | 3d |
| 2 | 工作项域 + **本体服务**（YAML 加载/校验/类型注册，双内置本体） | 1 | 4d |
| 3 | **功能域 + 对话域**：消息树/打断恢复/挂起/上下文分层组装与版本 | 1 | 5d |
| 4 | 内容仓：Git 集成 + 工件 API + prompts/ 编辑 | 1 | 2d |
| 5 | Agent Runtime：LangGraph 接入、YAML 角色加载、4 角色提示词、工具层权限、崩溃配平 | 1 | 5d |
| 6 | Orchestrator：图状态机、就绪调度、Gate→审批、失败降级 | 2,5 | 4d |
| 7 | 审批域：决策 API、批量、edit_and_resume、fail-closed | 6 | 3d |
| 8 | 轨迹域：span 埋点（OTel+apm.*）、查询 API、节点锚点注入 | 5 | 2d |
| 9 | **NL 命令层（L1）**：UI-Agent + 页面动作工具注册 + 预览/确认/撤销 + ui_command 事件 | 1 | 3d |
| 10 | SSE 总线 + 前端骨架（布局/路由/数据层） | 1 | 3d |
| 11 | 前端：Dashboard/功能页/对话视图/Board/Runs 抽屉/审批中心/审计/本体页 | 10 | 9d |
| 12 | Graph 视图（React Flow 只读 + 编辑 + 节点角标联动） | 10 | 4d |
| 13 | docker-compose、种子数据、端到端冒烟脚本 | 全部 | 2d |
| 14 | 打磨：空状态/快捷键/⌘K/引导 | 11 | 3d |
| 15 | **资产域**：资产仓 Git + assets/asset_links 投影 + FTS5 索引、沉淀表单与 asset_review Gate、资产页、Agent 三工具 | 2,4,11 | 4d |

合计约 7.5 周（一人）；里程碑：**M1 数据层+本体+对话域（#1-5）→ M2 编排+审批+轨迹+NL（#6-10）→ M3 前端完整+资产域+部署（#11-15）**。执行与审阅计划、迭代切分与进度状态见 10（开发计划分册）。

**验收冒烟脚本**（定义"闭环完成"）：
1. 创建项目（software-dev 本体）→ 断言功能/对话自动创建；
2. PRD 审批出现 → **先打断 PM-Agent 对话、补充一句约束、继续** → 批准 → 断言 PRD 含补充约束；
3. 12 任务生成 → NL 命令"只看高优先级任务" → 断言过滤生效并落 ui_command 事件；
4. 批量启动 → 打断其中一个 → 恢复 → 断言 awaiting_review → 批量批准；
5. release-notes 工件存在 → 审计页可查全部事件 → **用 generic 本体建第二个项目**走通三阶段轻流程；
6. **沉淀登录回归套件到测试库（走 asset_review Gate）→ 第二项目中 QA-Agent `search_assets("登录 回归")` 命中并 link → 资产页可见双向链**；
7. `rebuild-projections` 后状态一致；服务重启后对话无损恢复。

## 5. 扩展路线

| 版本 | 主题 | 关键项 |
| --- | --- | --- |
| **V1.1** | 多人协作 + 上下文完善 | 用户/角色/会话、审批路由、通知；L2/L4 提示词编辑、有效提示词合并预览、审批「转对话」 |
| **V1.2** | 会话深化 + 测试域 + 本体/资产编辑 | 对话分叉树（血统）、上下文自动压缩（三事件锁）、跨对话搜索；QA-Agent 全量 + 缺陷回流；本体表单编辑器 + 第三套内置本体；功能小图；**资产沉淀建议（Gate 附加 + 复盘挖掘）、prompt-template 资产接入对话模板、库维护者** |
| **V1.3** | 可观测与 NL/检索升级 | OTel 导出 → 自托管 Langfuse、费用报表、checkpoint time-travel UI；NL L2 级（指派/启动/打断）；**资产语义检索（向量）** |
| **V2** | 编排与自动化 | 规则引擎（触发+条件+动作）、保存视图/泳道/WIP/甘特、代码沙箱（Docker）开放命令执行、NL L3 复合意图 + 语音、Webhook + 开放 API；**资产 fork-diff 比较、supersede 链可视化、标签本体治理** |
| **V3** | 规模化与生态 | PostgreSQL/多租户、组织级 RBAC、SIEM 对接、角色与本体模板市场、Agent 团队模式（leader-worker）；**资产市场（与本体模板市场合并）** |

可扩展性论证（新增两条）：

5. 新本体 = 新 YAML（+可选新角色包），内核类型系统不变；
6. NL 能力分级独立演进：L1→L3 只改 UI-Agent 的工具注册与提示词，不动应用 API。

## 6. 主要风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| LLM 产出质量不稳（PRD/WBS 不可用） | 核心价值不成立 | 产出 schema 校验+自检重写；人可"修改后恢复"；提示词模板进内容仓可迭代 |
| **NL 误解析执行错操作** | 用户信任受损 | 只读直执/写操作预览确认/dangerous 二次确认；解析失败降级为候选列表；全量事件可撤销可审计 |
| **上下文分层组装复杂（L1-L4 叠加）** | Agent 行为难预期 | 有效提示词合并预览（可见即可控）；层间 token 预算硬限制；版本史可回滚对照 |
| Dev-Agent 代码质量（无沙箱不能验证） | 代码任务体验打折 | MVP 明确以"补丁+评审"交付；沙箱列 V2 |
| 事件表膨胀 | 查询变慢 | 投影索引承担查询；事件表只追加+分页；归档策略 |
| LangGraph API 变动 | 运行时耦合 | Orchestrator 与 Runtime 间内部接口隔离；压缩/审批/持久化走能力缝 |
| 审批疲劳（pending 太多） | 协作退化为排队 | 批量审批 + 三档放权 + awaiting 时间可视化 |
| **资产库腐化（陈旧/重复/无人用）** | 复用价值衰减 | 入库必审 + 引用链计数可见 + 零引用提醒淘汰；supersedes 链保留演化史；V2 标签本体治理防标签失控 |
| 新手被"图/本体"吓退 | 采用率低 | 默认落 Dashboard/功能页；Graph 只读默认；本体 MVP 只读；引导浮层 |
