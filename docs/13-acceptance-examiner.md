# 13 · 验收考官（Acceptance Examiner）

> 用户目标（2026-10-04 设定，持续有效）：**持续把设计要求变成测试场景、反例和检查清单，专门找"单个功能能用，连起来就出问题"的地方。每轮交付：问题复现、影响分析、回归用例。**
>
> 定位：独立于功能/发布轮的质量轮。在交付前后对「新面×旧面」的接缝做验收审查；遵守项目"发现即修"纪律——确认的真缺陷当场修复，回归用例进套件（先红后绿自证）。审查优先级：**最新交付未提交面 > 最新发布版块 > 抽查旧接缝**。

## 1. 方法：设计要求 → 场景 / 反例 / 检查清单

每条设计要求（docs 里的承诺句、docstring 契约、看板行的能力描述）必须产出四件东西：

1. **正向场景**：设计承诺的行为，至少一条可执行断言（多数已被开发轮的测试覆盖——考官核对覆盖面，不重复造）。
2. **反例**：按三个维度各至少一条——输入越界（未知 ref/坏格式）、**身份越界（跨项目 ref/无门角色）**、时序越界（并发/先后/精度）。
3. **接缝检查**：与既有面的组合——门禁矩阵、事件/rebuild、前端缓存失效、投影消费、计数基线。**"单功能能用、连起来出问题"几乎都发生在接缝上。**
4. **契约镜像**：文档/docstring 里每个「必须 / 只能 / 不 / AND」都是一条可测断言——把句子和代码逐字对读（Round 1 的 F1 即来自 `require_node` docstring 的 "AND belong to this project" 只兑现了一半）。

## 2. 集成缺陷分类学（七类，随轮次增补）

| 类 | 名称 | 特征 | 案例 |
|---|---|---|---|
| A | 归属/门禁缝隙 | 同类资源校验强度不一致；某类节点漏归属门 | R1-F1：item 有归属校验，conversation/feature 没有 |
| B | 状态同步缝隙 | 同屏多数据源，mutation 后缓存失效不齐 | R1-F2：unlink 失效 impact，add 漏失效 |
| C | 入口可达缝隙 | 后端能力在 UI 无入口（半截链族） | R1-F3：任务侧反查不可达；先例 I142 记账面、I220 里程碑 CRUD |
| D | 计数/基线漂移 | 新增页面/测试改计数，文档或锁定件不随 | precache 42→43 型；README 数字腐烂（M77 教训） |
| E | 语义对齐缝隙 | 两个面板/端点对同一概念口径不同 | graph vs deps 入边不对称（M79） |
| F | 时序/精度缝隙 | 毫秒精度比较、后台落库晚于返回 | M67 webhook 投递竞态、事件 ts 同毫秒 |
| G | 重建/事件缝隙 | 投影漏 drop_projections、payload 漏键 | I225 status 漏带落 draft 型 |

## 3. 每轮固定检查清单（新域/新端点接线时逐条过）

- [ ] **写门禁**：每个 POST/PUT/PATCH/DELETE 被中间件或域内门覆盖？`tools/check_write_gates.py` 台账登记？
- [ ] **归属一致性**：所有带 `project_id` 的资源，写路径是否同语义校验归属（404=不存在/422=属别家）？
- [ ] **事件溯源**：新投影表进 `drop_projections`？rebuild 复现有测试？payload 键集=投影消费清单？
- [ ] **读面口径**：列表/详情/聚合等多个读点对 missing/archived/cross-project 的处理一致？
- [ ] **前端缓存**：每次 mutation 失效了**所有**受影响 queryKey？（正反两个 mutation 对照读）
- [ ] **UI 入口**：设计文档承诺的每条用户路径在 UI 有可达入口？
- [ ] **计数基线**：pytest/冒烟/vitest/precache/chunk 计数变化同步到 docs/10 看板+HANDOFF+锁定件？
- [ ] **时间戳比较**：跨表时间比较双方同一时钟源/格式/精度？
- [ ] **反例三连**：未知 ref（404）/别家 ref（422）/自环空值（422）各有断言？
- [ ] **新路由 a11y**：新页面进了 axe 扫描基线清单？

## 4. 轮次记录

### Round 1（2026-10-04）——M108 需求到证据追溯助手（I326）交付前审查

审查对象：M108 未提交工作树（trace.py + TracePage.tsx + api.ts + 测试）。核对 M108 看板行的能力承诺与 docs/01 §DA 设计要求逐条镜像。

**F1（A 类·后端）跨项目节点归属缝隙 —— 已修**
- **复现**：`tests/test_trace_integration.py::test_trace_rejects_cross_project_conversation_and_feature` 首跑 RED——项目 B 的对话 `c_…` 挂进项目 A 追溯图返回 **200**。`require_node` docstring 承诺 "exist **AND belong to this project**"，归属校验却只对 item 生效；conversations/features 同为 `project_id` 列的项目级表，只查存在性。
- **影响**：①图完整性——别家证据计入本项目 impact/coverage 口径，缺口报告失真；②信息泄露——`resolve_node` 按全局 id 回标题/状态，A 项目成员可读 B 项目对话/功能标题；③契约违背——写路径契约与实现不符。
- **回归用例**：跨项目 conversation/feature 建链 422 + 未知 id 仍 404 + 图零污染断言 + 同项目 roundtrip 正向控制（asset 保持 org 级不误伤，docs/10 M80-I240 分门语义）。
- **修复**：`trace.py require_node` 对 conversation/feature 补 `project_id` 归属校验（404=不存在 / 422=属别家，与 item 语义对齐）。

**F2（B 类·前端）登记链接后影响面板失同步 —— 已修**
- **复现**：代码对照——`unlink()` 失效 links/coverage/impact 三个 query，`add()` 只失效两个；`TracePage.test.tsx` 断言 `invalidateQueries({queryKey:["trace-impact",…]})` 被调用（修复前不调用）。
- **影响**：登记一条边后同屏自相矛盾——「已登记链接」列表增长而「影响分析」面板停留登记前旧图，违背页面核心语义「改一条需求前先看波及」。
- **修复**：`add()` 补 `await qc.invalidateQueries({ queryKey: ["trace-impact", pid] })`。

**F3（C 类·前端）任务侧反查入口不可达 —— 已修**
- **复现**：`TracePage.test.tsx` 断言「分析对象」下拉同时含需求与任务选项——修复前只要 coverage 有需求，下拉就只剩需求。
- **影响**：docs/10 §M108 承诺「从任务侧进入则反查波及的需求」，后端支持（impact 反查有测试），UI 却把任务挡在选项外——半截链 C 类，与 I142/I220 同族。
- **修复**：下拉恒列全部工作项，需求类加 `[需求]` 前缀、其余显示 `[状态]`。

**考官自纠（误报入档）**：F1 首版复现把 source/target 写成同一个跨项目节点，422 来自**自环守卫**而非归属缺陷——假阳性复现（测试绿了但没测到目标缺陷）。修正为跨项目节点→本项目需求的真实缺陷路径，并在测试注释里留痕。**教训：复现必须命中真实缺陷路径，绿 ≠ 测到了。**

**检查清单核查通过项**（有证据，无缺陷）：写门禁链闭合（`/api/projects/*` 写请求经 auth_gate 成员制 `project_id_for_path` 正则覆盖 trace 路径；DELETE 域内门+台账登记）；事件溯源（trace_links 进 drop_projections、rebuild 复现入测）；needs_review 时间戳双方同源（均事件 `e.ts` 毫秒精度 ISO，字符串比较安全）。

**登记留观（不即修）**：①`/trace` 路由未进 axe a11y 扫描基线（24 路由清单为 M89/M90 存量）——随 v0.20.0 基线保鲜轮补扫，新页面 axe 违规风险（原生色板 chip）届时暴露；②`list_trace_links` 的 `source_type`/`source_ref` 过滤参数只传其一时静默忽略——低危，待真实使用证据。

**基线变化**：pytest 488→**490**（+test_trace_integration 2 项）、vitest 45→**47**（+TracePage.test 2 项）、冒烟 98 不变。
**验证**：trace 三文件 8 项绿 + vitest 47 绿 + `pnpm build` 绿 + 机械防腐（write_gates/env_doc/test_dates）✓。

## 5. 与既有纪律的关系

- 考官轮遵守「每轮只做改动相关的验证」——不替代每 5 轮的全局回归。
- 三件套（复现/影响/回归）先行，修复随后；先红后绿自证是回归用例的准入门槛。
- 误报与自纠照实入档——考官的证明力取决于复现质量，不取决于发现数量。
