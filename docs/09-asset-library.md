# 09 · 资产库与知识沉淀（累计资产设计）

> v0.3 新增：跨项目的组织级累计资产——产品库、测试库、文档库等；资产管理（沉淀、版本、治理）与检索统一划归本体（08）驱动。

## 1. 定位：从"项目记忆"到"组织记忆"

项目内容仓里的工件随项目结束而沉寂，下一个项目从零开始——PRD 模板重写、回归用例重造、踩过的坑重新踩。资产库补上这一环：**把值得复用的工件沉淀为跨项目的资产，让人与 Agent 在任何项目中都能检索、引用、再演进**。

**工件（Artifact）与资产（Asset）的边界**：

| | 工件 Artifact | 资产 Asset |
| --- | --- | --- |
| 归属 | 某项目内容仓（过程产物） | 组织级资产仓（跨项目复用） |
| 生命周期 | 随项目/功能 | 独立演化（draft→published→deprecated） |
| 产生方式 | 阶段执行产出 | 从工件**沉淀**或直接创建，需入库评审 |
| 主要消费者 | 本项目的 Agent 与人 | 所有项目的 Agent 与人 |
| 例子 | 某项目的 prd.md、test-report-v3.md | PRD 模板、登录模块回归套件、"第三方支付对账"ADR |

**内置三库**（由本体注册，可自定义扩展）：

| 库 | 收纳内容（assetKind 示例） | 典型复用场景 |
| --- | --- | --- |
| 📦 产品库 | prd-template（PRD 模板）、requirement-pattern（需求模式）、competitor-note（竞品笔记）、feature-checklist | 新项目起草 PRD 时套模板；同类需求引用历史模式 |
| 🧪 测试库 | test-suite（测试套件/回归集）、bug-pattern（缺陷模式）、acceptance-checklist（验收清单） | QA 阶段自动挂载相关回归套件；评审时对照已知缺陷模式 |
| 📚 文档库 | adr（架构决策记录）、guide（指南/规范）、retro（复盘/经验教训）、prompt-template（提示词模板） | 新对话选提示词模板；设计阶段检索相关 ADR |

## 2. 核心概念模型

```
Library（资产库，本体注册）1 ─ n Asset
Asset（资产）
 ├─ 元数据：kind（本体 assetKind）/ title / tags / owner / 库归属
 ├─ 正文：资产仓中一个目录（Markdown + 附件），Git 版本化
 ├─ 生命周期：draft → in_review → published → deprecated | archived
 ├─ provenance（来源链）：从哪个项目/工件/commit 沉淀而来
 ├─ usages（引用链）：被哪些项目/工件/对话引用（反向索引）
 └─ superseded_by / supersedes（版本继承，如 ADR 被新决策取代）
```

两条链是资产模块的灵魂：

- **来源链（provenance）**：每个资产记录出生证明（项目、工件路径、commit、当时的对话/轨迹链接）——回答"这个模板是从哪次实战里长出来的"，可信度可溯；
- **引用链（usage）**：每次 Agent 或人引用资产都落事件（`asset.consumed`），资产页显示"被 12 个项目引用，最近一次上周"——回答"它还有没有生命力"，为淘汰提供依据。

## 3. 沉淀机制（项目 → 库）

三条路径，按自动化程度递进：

| 路径 | 触发 | 流程 | 版本 |
| --- | --- | --- | --- |
| A 手动沉淀 | 人在工件详情/审批通过页点「沉淀为资产」 | 选择目标库与 assetKind → 表单补元数据（本体 schema 校验）→ **入库评审 Gate** → 发布入仓 | MVP |
| B 阶段自动建议 | 阶段 Gate 通过时（如测试报告验收后），系统在审批中心附加建议卡"检测到可沉淀：回归套件 ×1" | 人一键接受 → 走路径 A 的表单 | V1.2 |
| C 复盘挖掘 | 里程碑复盘对话中，Agent 分析本项目工件与轨迹，产出《沉淀建议清单》（含理由与来源链接），人勾选批量沉淀 | 走路径 A | V1.2 |

**入库评审（asset_review Gate）**：与阶段门同一审批机制（05 §2.2），评审内容为资产预览 + 元数据 + 目标库归属；**同名/同型资产冲突时提示合并或新建版本**而非静默覆盖。

## 4. 消费机制（库 → 项目）

1. **建项引用**：新建项目/功能时，从库中勾选参考资产（如 PRD 模板），系统将其作为工件副本导入内容仓，并记录 usage；
2. **Agent 工具**（角色 YAML 白名单可配）：`search_assets(query, library?, tags?)`、`read_asset(id)`、`link_asset(id)`——PM-Agent 起草 PRD 前先 `search_assets` 检索同类模板与需求模式；QA-Agent 依据项目特征挂载回归套件；Architect-Agent 检索相关 ADR 避免重蹈覆辙（对应 dsh `session_query` 的"agent 检索历史"思想，但沉淀物是治理过的资产而非原始会话）；
3. **模板资产**：`prompt-template` 类资产直接出现在对话模板选择器（03 §2 提示词 L3 预填来源之一）；
4. **反馈回流**：项目内改进后的工件可再次沉淀为资产**新版本**（supersedes 链），形成"沉淀→复用→改进→再沉淀"的飞轮（V2 提供 fork-diff 比较 UI）。

## 5. 检索设计

| 阶段 | 能力 | 实现 |
| --- | --- | --- |
| MVP | 关键词全文 + 元数据过滤（库/kind/标签/来源项目）+ 排序（引用数/最近更新） | SQLite FTS5 索引资产正文与元数据；资产页与 ⌘K 均可搜 |
| V1.3 | 语义检索 | 向量索引（本地 embedding），查询词与资产双向；Agent 工具同一接口 |
| V2 | 标签体系由本体治理 | 标签受控词表（本体 libraries.tags 定义），避免标签腐化 |

检索接口与 NL 打通：⌘K 自然语言"找登录相关的回归套件" → UI-Agent 解析（资产词典来自本体，08 §5）→ 资产页过滤视图。

## 6. 治理与审计

- **入库必审**（asset_review Gate，可按库配置豁免低风险 kind，如 guide）；
- **淘汰**：published → deprecated（被 supersede 或长期零引用），deprecated 资产仍可检索但标注"已淘汰，替代：xxx"；archived 不可检索；
- **所有权**：每个资产有 owner（默认沉淀者），库可有维护者（V1.1 多人后生效）；
- **全程审计**：`asset.drafted / in_review / published / deprecated / archived / superseded / linked / consumed` 全部入事件流，审计页可过滤"资产域"查全程。

## 7. 存储与数据（详见 04 联动）

- **资产仓（Git，全局一个）**：真源。`libraries/<lib>/<asset-id>/asset.md（frontmatter 元数据 + 正文）` + 附件；版本 = Git 提交历史；
- **DB 投影**：`assets` 表（元数据+生命周期）、`asset_links` 表（provenance/usage/supersede 三类边）、FTS5 索引；可由事件流 + 资产仓重建；
- 元数据 frontmatter schema 由本体 assetKind 定义（JSON Schema 校验），加载时执行。

```
<assets-repo>/
  libraries/
    product/prd-template-basic/asset.md
    product/requirement-pattern-auth/asset.md
    test/regression-login-suite/asset.md      # 正文含用例清单，可含附件
    doc/adr-0007-payment-reconciliation/asset.md
```

## 8. WebUI（详见 06 §3.9）

- 左侧任务栏新增 📚 资产库入口；页面 = 库 Tab（产品/测试/文档/全部）+ 检索框 + 过滤器（kind/标签/状态）+ 资产卡片网格（标题/类型徽标/版本/引用数/最近更新）；
- 资产详情抽屉：正文预览、版本历史（Git）、**来源链**（跳原项目工件/轨迹）、**引用链**（哪些项目在用）、操作（引用到当前项目 / 编辑草稿 / 提请淘汰）；
- 工件详情抽屉与审批通过页新增「沉淀为资产」按钮（入口即路径 A）。

## 9. 与 MVP / 路线图的关系

- **MVP**：三库 + 本体 assetKinds/libraries 注册 + 手动沉淀（含入库 Gate）+ 资产页（列表/过滤/FTS 检索）+ Agent 工具 search_assets/read_asset/link_asset + 来源/引用链记录；
- **V1.2**：沉淀建议（路径 B/C）、prompt-template 资产接入对话模板选择器、库维护者；
- **V1.3**：语义检索；
- **V2**：资产 fork-diff 比较、supersede 链可视化、标签本体治理；
- **V3**：资产市场（跨组织共享模板包，与本体模板市场合并）。

**验收锚点**：在 A 项目完成登录功能后，将回归套件沉淀入测试库；新建 B 项目（同类需求）时，QA-Agent 通过 `search_assets("登录 回归")` 命中并挂载该套件，资产页可见 B 项目的引用记录与 A 项目的来源链——闭环成立。
