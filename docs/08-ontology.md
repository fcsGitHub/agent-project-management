# 08 · 项目本体模块（Ontology）——简化设计

> v0.2 新增，回应评审意见 5："对于不同的项目需要增加本体模块，参考并吸收 semantica-agi/semantica 的优点，进行简化设计"。

## 1. 为什么需要本体

v0.1 的模型隐含"软件研发"一种世界观：工作项类型是 task/bug、阶段是 PRD→开发→测试、工件是 Markdown 文档。一旦项目是"市场活动策划""科研课题""硬件试产"，这些硬编码就全部失效。

**本体模块 = 项目的类型系统**。创建项目时选择（或定义）一个本体，由它驱动：工作项的概念类型与字段、看板列与状态机、阶段图模板、工件种类、可绑定的 Agent 角色、以及自然语言操作时的实体词典。**系统核心只认本体内核（Kernel），软件研发只是内置本体之一**——这与 OpenProject "统一 Work Package + 可配置类型"同思路，但把配置升格为一等模块并允许跨项目复用。

## 2. 简化原则（对照 semantica 的取舍）

semantica 是 LLM 之下的重型语义层（RDF/OWL/推理机/双时态事实/PROV-O 溯源）。本模块**只保留四个思想**，其余全部砍掉：

| semantica 思想 | 本模块的简化落地 | 砍掉的部分 |
| --- | --- | --- |
| Competency Questions 驱动设计 | 每个本体必须声明"这个项目模板要回答哪些管理问题"，作为验收锚点 | — |
| 关系类型受控枚举 | 内核固定 4 种结构关系 + 每本体最多自定义 6 种，防关系爆炸 | 任意谓词 |
| 本体即数据 + 版本化 diff | 本体 = 内容仓里的 `ontology.yaml`，Git 版本化，`ontology.changed` 事件驱动重载 | 专用 VersionManager/迁移器（用 Git diff 即可） |
| Ontology Hub 浏览编辑 | "本体页"：概念卡片 + 关系列表 + 校验结果，V2 提供表单编辑器 | 图谱可视化（Sigma.js）、SHACL Studio |

**明确不做**：RDF/Turtle/SPARQL、推理机一致性检查、双时态、PROV-O、多存储后端、LLM 自动生成本体（项目域概念少，手写模板更可控；V3 可选提供"从既有工作项数据归纳概念"的辅助工具，对应 semantica 从数据推断类型）。

## 3. 概念模型

```
Ontology（本体，项目级实例）
 ├─ meta：name / version / extends（继承链，如 software-lite extends software）
 ├─ competencyQuestions[]：该项目管理要回答的问题（验收锚点）
 ├─ concepts[]：领域概念（类型系统）
 │    ├─ id / name / icon / 描述
 │    ├─ fields[]：typed 字段（string/enum/number/date/ref）
 │    ├─ lifecycle：状态组（映射五桶）+ 组内状态 + 允许迁移
 │    ├─ artifactKinds[]：可挂工件种类（如 prd/report/bom/海报），
 │    │      每种可声明沉淀目标 assetKind（工件→资产映射，见 09 §3）
 │    ├─ agentRoles[]：可绑定的 Agent 角色（引用角色 YAML）
 │    └─ parent：概念继承（Campaign ⊂ Feature）
 ├─ assetKinds[]：资产类型（v0.3，资产管理划归本体）
 │    ├─ id / name / 默认库（library）/ 元数据 schema（JSON Schema）
 │    ├─ lifecycle：draft → in_review → published → deprecated/archived
 │    └─ tags：建议标签集（V2 起作为受控词表强制）
 ├─ libraries[]：资产库注册（v0.3）
 │    └─ id / name / accepts[]（收纳的 assetKind）/ 维护者
 ├─ relations[]：受控关系定义（内核 4 种 + 自定义 ≤6）
 │    内核：contains / depends_on / produces / consumes
 ├─ phases[]：阶段图模板（Phase + Gate 序列，可含 asset_review Gate）
 └─ boardDefaults：默认看板列/泳道/分组维度
```

约束（JSON Schema 校验，加载时执行）：

1. 概念数量 ≤ 12、字段 ≤ 10/概念——**小本体主义**，倒逼建模者聚焦；
2. 每个状态的 `group` 必须落在五桶（backlog/todo/in_progress/done/cancelled）之一，保证统计与看板渲染归一；
3. 关系自定义数量 ≤ 6，且不得与内核 4 种语义重叠（校验提示）；
4. phases 必须是 DAG（建项目时实例化为 Phase Graph）；
5. assetKinds ≤ 10/本体、libraries ≤ 6/本体（小本体主义同样适用于资产域）；每个 assetKind 必须挂在某个 library 的 accepts 列表中（孤立的资产类型校验报错）。

## 4. 文件格式与示例

存内容仓 `/ontology/ontology.yaml`（版本化、可 diff、可回滚）：

```yaml
# 本体示例：marketing-campaign（市场活动），extends generic
name: marketing-campaign
version: 2
extends: generic
competencyQuestions:
  - 每场活动的资产是否都过审了？
  - 哪些渠道素材存在依赖阻塞？
concepts:
  - id: campaign          # 活动（≈功能容器）
    icon: 📣
    lifecycle: {groups: five-buckets, states: [planning, creating, reviewing, live, closed]}
    artifactKinds: [{id: brief, deposits-to: brief-template}, asset-brief, report]  # brief 工件可沉淀为 brief-template 资产
    agentRoles: [pm-agent, designer-agent]
  - id: material          # 素材（避免与 Asset 资产实体撞名）
    parent: campaign
    fields: [{id: channel, type: enum, values: [公众号, 视频, 海报]}]
    lifecycle: {groups: five-buckets, states: [drafting, in_review, approved, published]}
    artifactKinds: [copy-draft, image, video]
    agentRoles: [designer-agent, qa-agent]
relations:
  - {id: requires-material, name: 需要素材, domain: campaign, range: material}
phases:
  - {phase: intake,   gate: null}
  - {phase: briefing, gate: brief-review}     # PM-Agent 产 brief，人审
  - {phase: produce,  gate: asset-review}     # designer-agent 产素材，人审
  - {phase: publish,  gate: release}          # 恒审
boardDefaults: {group-by: lifecycle, swimlane: channel}
assetKinds:                                    # v0.3：资产管理划归本体
  - {id: brief-template, name: 简报模板, library: product, schema: schemas/brief-template.schema.json}
  - {id: brand-guide, name: 品牌规范, library: doc, lifecycle: [draft, published, superseded]}
libraries:
  - {id: product, name: 产品库, accepts: [brief-template]}
  - {id: doc,     name: 文档库, accepts: [brand-guide]}
```

内置两套：`software-dev`（默认，即 v0.1 的七阶段模型，内置三库 assetKinds：prd-template/test-suite/adr 等）与 `generic`（需求→执行→交付三阶段 + 通用概念）。**MVP 的自定义方式 = 编辑 YAML 文件后重载**（开发者路径）；表单化本体编辑器在 V2。

## 5. 本体如何驱动系统（编译点）

| 驱动点 | 机制 |
| --- | --- |
| 工作项类型 | 建项/建卡时的类型下拉 = 本体 concepts；类型决定字段表单与生命周期 |
| 看板 | 列 = 概念 lifecycle 状态（按五桶分组渲染）；泳道/分组默认值来自 boardDefaults |
| 阶段图 | phases 实例化为项目的 Phase Graph（含 Gate，含可选 asset_review 入库门）；轻/完整模板即两个内置本体的差异 |
| Agent 角色 | 概念的 agentRoles 圈定可指派角色；角色 YAML 声明适配的概念域 |
| 工件 | artifactKinds 决定工件目录结构与审批时渲染器选择；`deposits-to` 声明可沉淀的资产类型（09 §3） |
| **资产库（v0.3）** | assetKinds 决定资产元数据表单/入库校验/生命周期；libraries 决定库页 Tab、过滤项与"沉淀为资产"的目标库候选 |
| **NL 理解** | UI-Agent 的实体词典来自本体（"素材""活动""渠道""回归套件"皆可解析）——自然语言操作与资产检索共用一套词典 |
| 上下文 | 项目宪章（提示词 L1）自动注入本体概念表摘要，Agent 知道"这个项目里 Campaign 是什么、有哪些状态" |

变更传播：`ontology.changed` 事件 → 投影器重建类型注册表；已有数据若引用被删概念，校验器报**阻塞错误**并给出影响清单（哪些工作项/对话），确认后才允许落库（受控破坏性变更）。

## 6. 继承与复用

- `extends` 单继承链（generic ← software-dev ← 某定制），子本体只写差异（覆盖字段/追加概念）；
- 本体可导出为模板包（YAML + 角色包 + 提示词模板）放入内容仓 `templates/`，跨项目复制即用；
- V3 引入"本体市场"：社区共享模板包（借鉴 semantica 的生态位，但以文件而非服务形式）。

## 7. 与 MVP / 路线图的关系

- **MVP**：内核校验器 + 两套内置本体 + 本体页（只读浏览 + 校验状态）+ YAML 手工定制路径 + **三库 assetKinds/libraries 注册（09）**；
- **V1.2**：表单化本体编辑器（概念/关系/阶段/资产类型的增删改，带破坏性变更检查）、marketing 等第三套内置本体；
- **V2**：本体驱动 NL 词典的完整覆盖、资产标签受控词表、从工作项数据归纳概念的辅助工具（semantica "从数据推断类型"的轻量版）；
- **V3**：本体与资产模板市场、跨本体语义映射（若多项目组织需要）。

**验收锚点**（来自 Competency Questions 思想）：① 用 marketing-campaign 本体建一个项目，走通"brief 起草→素材生产→过审→发布"全流程，且 NL 命令"把视频类素材都指派给 designer-agent"能正确解析；② **将 brief 工件按 `deposits-to` 沉淀为产品库资产，并在新项目中让 PM-Agent 检索命中**（09 §9 闭环）——两项均过即视为本体模块（含资产域）达标。
