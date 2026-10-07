# Changelog

本文件记录 AgentPM 的**发布级**显著变更（人写精选，非 git log 倾倒——[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式）。迭代级细节真源=[docs/10-development-plan.md §7 状态看板](docs/10-development-plan.md)。

版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)；版本单源=`app/apm/version.py`（/api/health、web/package.json、README 版本行与 git tag 由冒烟 86 锁定一致）。

## [Unreleased]

未发布变更（攒批中——迭代细节真源=[docs/10 §7 看板](docs/10-development-plan.md)）。攒批指向 v0.23.0。

## [0.22.0] — 2026-10-07

M116~M120 五轮成版（M120 收口）：Paperclip 吸纳轮（多 Agent 团队编排与治理）+ Triage 分诊队列轮 + 质量轮（归档语义对齐与性能收口）+ 质量轮（流程图显示与 CPM 关键路径方向修复）+ 发布工程第十二轮。攒批节奏第十六版：五轮一版。基线：pytest 512→544 / 冒烟 98 / vitest 50→66 / 机械防腐七件 ✓ / 写门 146=76+70。

### Added
- **交互式流程图工件三枚**（M119-I368，archify 技能首次引入）：[系统架构](docs/diagrams/agentpm-architecture.html)（事件账本居中辐辏+单体与密钥边界）、[入流·分诊·执行工作流](docs/diagrams/intake-triage-workflow.html)（分诊主链+拒绝/暂缓旁路+阶段门授权回环）、[工作项生命周期](docs/diagrams/item-lifecycle.html)（task 主链+暂缓复浮+终态回收）——standalone HTML（内嵌 SVG，亮暗双主题/pan-zoom/引导视图/PNG-SVG 导出），事实全部取自仓库实现，showcase 档校验（构图 9 检查零错误）+四视口容纳性+亮暗人工目检；规范 JSON 同目录在案可再生产。
- **项目级批量关系读面**（M119-I366）：`GET /api/projects/{id}/relations` 一次返回项目内全部工作项关系（项目成员门；隐藏概念项的关系边整体隐去不泄露存在性；回收站项不还魂；跨项目对端只出 id 由前端 getItem 404→🔒 兜住）。
- **分诊队列报告人与深链**（M118-I363）：items 补 `reporter_id` 列（报告人=item.created 事件的 actor——建表+存量库轻量迁移·rebuild 稳定），分诊队列行显示报告人真源（intake 入流显「外部」、IMAP 已知发件人与手工创建显用户名）；队列标题可点——深链看板抽屉（`?item=` 惯例），决定前先检查描述/附件/评论。
- **Triage 分诊队列**（M117-I356/I357/I358，候选池①转正·Linear intake 语义）：软件研发本体 task/bug 概念声明 `triage` 分诊中间态（bug 补白名单流转 triage→open/wont_fix 与 open→triage；task 无白名单语义不变）——外部入流（intake token/IMAP 邮件）落分诊等人决定，手工创建仍落概念初始态（行为零变化·未声明 triage 的本体如 generic 零影响）；`POST /api/items/{id}/triage` 三决定：accept（→initial_status+可选指派走 item.assigned 既有链）/decline（→概念 cancelled 组状态按本体解析）/snooze（1-30 天·items.snoozed_until 列+事件投影）；**sweep 第八员到期复浮**（暂缓不是丢弃——automation.swept 计数新增 resurfaced）；队列页 `/p/:pid/triage`「分诊」（行式队列+接受并指派/拒绝/暂缓+「显示已暂缓」开关——读面全走既有 list_items(status=) 零新读端点）；分诊中直接派 Agent 自动出队进 in_progress（引擎可信路径·「派活即接受」如实入档）。
- **Agent 团队总览面**（M116-I353，Paperclip 吸纳）：`GET /api/agents`（org 级登录门）+ 新页面 `/team`「团队」（rail 常驻导航）——roles YAML 声明（display_name/档位/概念/工具）× agents 治理覆盖层（暂停态/预算）× runs 聚合统计（运行数/成功率/累计 tokens 与成本/最近运行）三源一屏合并；事件溯源红利：统计零新表零埋点，纯读侧 GROUP BY。
- **Agent 治理：暂停/恢复 + Agent 级月度预算**（M116-I354）：`agent.paused/resumed/updated` 事件链 + `agents` 投影覆盖层（建表+投影器+drop_projections 三件套）；`POST /api/agents/{role}/pause|resume` 与 `PATCH /api/agents/{role}`（预算，0=关闭）admin 门 + check_write_gates 台账登记（写路由 142→145=75+70）；start_run 前置校验区增查——暂停 409、预算月窗 ≥100% 402 硬顶/≥80% 软阈（M66-I200 项目预算同构）；自动化 run_agent 派发路径经既有 HTTPException 兜底自然降级 ok:false；TeamPage 卡片暂停/恢复+预算行内编辑（非管理员只读）。
- **工作项原子检出执行锁**（M116-I352）：`start_run(item_id)` 前置校验——同工作项存在活跃 run（pending/running/interrupted，挂 Gate 等人亦持锁）即 409 带持锁 run_id，终态（succeeded/failed）释放；`runs` 补 `idx_runs_item` 索引（Paperclip atomic task checkout 的翻译——batch_start 会话复用守卫之外的第三层防线，automations 派活同受管辖）。

### Fixed
- **关键路径（CPM）方向反转——M33 起关键链与浮动整体标错**（M119-I366）：depends_on 的库内语义是 from=依赖方、to=前置（自动排程/blocked 旗标/重排程传导三个消费方均如此定向），而 critical-path 独自把边建成「依赖方→前置」——截止期从最上游前置向最下游交付物反向传导，零浮动关键链标记错误集合（依赖图琥珀环同错）；**既有测试按同一误读编写（绿而错），本轮一并重写到真实语义**。
- **依赖图层级倒挂与被阻塞旗标标错对象**（M119-I367）：依赖图页把所有关系的 from 一律当上游——depends_on（from=依赖方）家族拓扑层级倒挂（前置被排到依赖方下方）、「被阻塞」红标落在**前置**头上（前置未完反而绿着）；布局与阻塞判定抽为 `lib/depgraph` 纯函数并以方向契约测试锁定（先移植旧逻辑跑红再修正）。
- **依赖图页每项一次详情请求的 N+1**（M119-I366/I367）：页面为拼关系面对每个工作项各打一次 `GET /items/{id}`（百项项目每次打开 ≈100 查、任一项变更即全量重打）；现走项目级批量端点一查代之。
- **阶段图暗色背景与依赖图空态硬编码色**（M119-I367，M114-I341 同族残留）：阶段图背景点阵 `#e7e7ea`、依赖图空态文字 `#64748b` 在暗色主题下是贴在暗底上的亮色拼图——改走 `--color-*` 语义 token 亮暗翻转。
- **阶段图节点与抽屉显示指派 raw id**（M119-I366/I367）：`/projects/{id}/graph` 任务节点此前不带显示名，图上与详情抽屉显示 `🤖 u_admin` 式 raw id；现随图携带 users.name（一次 IN 批量），图标按 assignee_type 判定不再按 id 前缀嗅探。
- **归档（回收站）语义对齐族·九处活视图与派生量仍把死项当活项**（M118-I361）：M33 引入软删除后旧查询面未回头核对（M65-I197 预言的清账轮）——项目与组合报表漏斗/逾期清单、健康分三因子、健康趋势事件重放（重放事件流此前根本不含 item.archived/restored，归档前的分被永久拉进后续全部采样点）、阶段图（回收站项永久显示为节点）、CSV 导出（死项照常导出，导回即幽灵复制）、项目克隆（连回收站一起复制）、个人日程（死项还挂日历且可拖拽改期）、标签用量计数——全部与看板/列表/回收站同语义排除。
- **阶段图隐藏概念项信息泄露**（M118-I361）：`/projects/{id}/graph` 把概念级可见性声明为仅 Owner 可见的工作项标题/指派/状态原样发给无权查看者（list/board/CSV/trash/detail/search 均已过滤，唯独图漏了——M67 读面家族收口）；同修跨项目依赖占位节点借已归档外部项「还魂」。
- **分诊动作绕过概念可见性**（M118-I361）：`POST /items/{id}/triage` 裸查工作项，项目贡献者可对仅 Owner 可见概念的项做接受/拒绝/暂缓；现与兄弟写面（PATCH/归档/清单/关系）一致返回 404（存在性不泄露）。
- **分诊队列「报告人」错标**（M118-I363）：队列行把负责人（assignee）当报告人显示——IMAP 已知发件人的入队项恒显「外部」；现显示 items.reporter_id 真源（见 Added）。
- **工作项列表 `?status=` 过滤参数半传静默忽略**（M117-I357，浏览器 E2E 走查抓获）：`GET /projects/{id}/items` 的 `status` 显式查询参数从未接入端点签名——只有保存视图路径（view definition）能带 status，显式传参被 FastAPI 静默丢弃（分诊队列读面依赖该参数才被照亮；M110 R1 留观②「过滤参数半传」同族）。现补接线并入回归锁。
- **跨项目 run 绑定 422 留幽灵 run**（M116-I352，调研发现即修）：M114-I339 的跨项目校验位于 `run.requested`/`run.started`/`conversation.status_changed` 三事件发射**之后**——422 时幽灵 run 已落库且永远停在 running、会话永远 running（且引入执行锁后会永久锁死该工作项）；校验前移到任何事件发射之前（`test_f1_cross_project_422_leaves_no_ghost_run` 回归锁）。

### Changed
- **依赖一车（发布轮起点跟随·当轮实测）**（M120-I370）：后端 openai 3.24.0→3.26.0（minor）与 langgraph 1.2.13→1.2.14（patch），requirements 下限=装机、双镜像重建后镜像内 pip 对账 13/13 逐版一致；前端 dev 三件 vite 8.3.2→8.3.3 / @vitejs/plugin-react 6.1.1→6.1.2 / jsdom 30.1.1→30.1.2（manifest range 与 lockfile 同车，web 镜像 frozen-lockfile 构建通过）。
- **Runs 列表与通知铃铛热路径批量化**（M118-I362）：`/runs` 列表逐行回查会话标题与工作项标题（RunsPage 3 秒轮询 × 默认 100 行 ≈ 每 3 秒 200 次查询）改为两条 IN 批量查询；`/notifications` 引用事件逐行回查（铃铛 10 秒轮询最多 30 查/次）改为单条 IN 批量——响应形状逐键不变，行为零变化（M114-I340 批量富化同款先例）。

## [0.21.0] — 2026-10-06

M110~M115 五轮成版（M112 收口）：验收考官 Round 2 + 真实 LLM 回归轮（DeepSeek flash 全链复演）+ 功能瘦身轮 + 质量轮（性能与漏洞/显示修复）+ Linear 吸纳轮（差距调研与四件吸纳）。攒批节奏第十五版：五轮一版。基线：pytest 492→512 / 冒烟 98 / vitest 47→50 / 机械防腐七件 ✓ / axe 基线 25 路。

### Added
- **工作项描述域**（M115-I343）：items 补 `description` 列（建表+存量库轻量迁移），create/PATCH/事件流/读面全链路，空串=清空；描述纳入 FTS 全文索引（标题关键词照旧优先）——对齐 Linear issue 正文的最高频缺口。
- **工作项活动流**（M115-I344）：`item.updated` payload 补 `_old` 旧值溯源（投影白名单键不受影响，rebuild 原样重放）、`item.assigned` 补 from 侧；新组件 ItemActivity 把 `agg_type=item` 审计事件流渲染为 Linear 风格变更时间线（状态 from→to/优先级/改期/指派/关系/清单），挂快捷编辑弹窗——事件溯源红利：数据全在库，本轮只做读面。
- **项目级标签域**（M115-I345）：`labels` 表+CRUD 端点（重名 409/改名去重/删除 404，颜色+usage 计数），items 挂 `labels` JSON 多值（同项目外键 422、[] 清空、label.deleted 投影侧从所有 items 摘除——重放确定）；看板 `group_by=labels` 多标签一物多列扇出（未标签末列）、卡片/列头色点 chip、快捷编辑内勾选+行内建签。写入全走 `/projects/{pid}/labels` 由网络写中间件管辖。
- **创建防重提示**（M115-I346）：`GET /projects/{id}/items/similar`（FTS5 `_match_expr`）+ 新建弹窗标题去抖 400ms 提示相似项、点击直达已有项——Linear similar-issues 防重语义；归档项与隐匿概念不出提示（M67 存在性不泄露）。

### Changed
- **langgraph 1.2.13 / axe-core 4.14.0 / marked 18.1.0 依赖一车**（M112-I348）：发布轮起点当轮实测——后端 13 项运行时依赖 fastapi/openai/httpx2 等顶格零漂移、仅 langgraph patch 漂移一项（1.2.12→1.2.13，requirements 下限=装机同车）；前端 axe-core（dev）与 marked minor 两项（manifest range+lockfile 同车）——runtime 测试+vitest+tsc 三关绿。
- **docs/11 解冻至 v0.21.0**（M112-I350）：全部部署面时效戳随版；§2.4 写路由计数随解冻修正为 **142=75+67**（M113 webhook 双注册去重 -6 与 M115 labels 三写路由 +3 的净差，check_write_gates 实测为准）；一键发布演练计数十一→十二次；部署链已验证声明追加 M115 轮后双镜像重建对账。
- **真实 LLM 默认示例切换到 DeepSeek 官方**（M111-I333）：`.env.example`/README 以 `https://api.deepseek.com` + `deepseek-flash` 为默认示例（智谱 coding-plan 降为备选）；角色 YAML 七件 `model.name: glm-5.3` 硬编码改为 `tier: standard` 三档路由（M48-I144）——厂商模型名不再进仓库，由 `APM_MODEL_*` 环境键解析，未配置时按回落链落到 `APM_LLM_MODEL`（回落链收拢 `roles.tier_model_name` 单一真源，档位解析永不出空模型名）。
- **角色提示词执行环境契约**（M111-I334）：六份角色提示词移除「工具使用规范」——旧文案承诺了固定图引擎不存在的模型侧工具回路，真实模型会把工具调用语法原样写进工件（DeepSeek flash 实测抓获）；改为「执行环境契约」：单轮、无工具、输出即工件、严禁工具调用标记与开场白。
- **廉价模型旋钮统一**（M113-I337）：L2 命令解析的模型选择改为 `APM_MODEL_CHEAP` 首选、`APM_UI_AGENT_MODEL` 降为兼容回落（两旋钮一语义，既有 .env 零破坏）；L2 溯源文案改用实际调用的模型名。
- **读面门禁对齐与跨项目写收口**（M114-I339）：M76 读面审计的续篇——全局 id 单资源读（runs 四面/milestones/cycles/features/time_entries 单条/attachments 下载/conversations detail·messages·context）补齐与同域写侧对等的成员门；`/events`·`/runs`·`/conversations`·`/approvals` 聚合列表接 `_visible` 家族可见性过滤（org 级行对登录者保持可见）；`GET /users` 补 org 登录门；NDJSON 事件导出补 admin 门（对齐 audit.csv）。行为影响：network 模式非成员/匿名者读这些面从 200 变 403/404/401，成员与本地模式零变化。
- **热读路径性能收口**（M114-I340）：`item_relations` 补三索引（此前零索引挂在 board/items 最热读路径，EXPLAIN 全表扫→索引命中）；board/items 的 assignee 名富化与概念可见性判定批量化（逐项 SQL→每请求一次）；WIP 计数单条 GROUP BY 取代二次全量 `list_items`；`/portfolio/health-trend` 每项目单遍重放（原为健康序列+flow 指标两次全事件扫描，Dashboard 60s 轮询放大）；`/my/work`·`/my/attention`·`/portfolio/activity` 逐行权限判定 hoist 为每请求一次；会话页空闲轮询 2s→5s（运行中仍 800ms 增量失效主导）。

### Fixed
- **全局搜索连字符查询崩溃**（M115-I343 同族即修）：`/search` 的 items/comments/messages 三面把 bigram 串裸传 FTS5 MATCH——连字符词（如 `feature-auth`）被解析为 NOT 语法报 "no such column"（M71-I213 只修了 artifacts 一处）；现三面统一走 `_match_expr` 逐 token 加引号。
- **追溯影响分析读侧归属校验**（M110-I330·验收考官 Round 2 R2-F1）：`/trace/impact` 根节点此前只查存在性不查归属——其他项目的节点 id 可作为读根返回其标题/状态（Round 1 已堵写路径，读侧为残留面）。现读写同门：404=不存在 / 422=属别家；回归锁 `test_trace_impact_root_cross_project_refused` + 写门矩阵 trace 行（pytest 490→492）。
- **批量审批跨项目越权**（M114-I339）：`POST /approvals/bulk-decision` 的路径段 "bulk-decision" 不匹配中间件的 approval id 查表→门被跳过，任意登录用户可对任意项目的审批批准/驳回并恢复引擎；`POST /ui_commands/{id}/confirm` 的批量批准同病。现逐审批过与单条决策同款的成员门（org 级资产审批保持登录即可）。
- **run 绑定与外键的跨项目引用**（M114-I339）：`POST /runs` 的 item_id 可指向别家项目（状态迁移事件以本方 project_id 落账、投影改到别家 items 行）→422；费用行/风险关联/会话 feature·item 引用跨项目→422（对齐 `_validate_milestone` 既有惯例）。
- **暗色主题显示破损一批**（M114-I341）：danger 按钮白字压浅红底、工时批准按钮、风险热力矩阵 3/4/6/9 分格硬编码亮色块、图内状态 chip 白底、追溯页琥珀警示字与四处浅色 chip、依赖图整张 SVG 硬编码亮色+图例 token 失配——全部改语义 token 双主题翻转；受影响 7 路由亮暗双主题 axe 复扫 serious/critical 全零。
- **追溯页三态与溢出**（M114-I341）：覆盖概览卡加载/失败静默空白→补三态；影响分析请求失败伪装成「没有任何关联证据」→区分错误态；`text-fg` 死类改 `text-ink`；长工件路径 chip 补 break-all；路线图里程碑长标签 375px 撑出横向滚动→行内截断（title 兜底全名）；徽章近白边框（indigo/violet-100）改 token 透明度。

### Removed
- **工具注册表三个非功能性 stub**（M113-I336）：`search_web`（返回空结果的伪搜索）、`publish_external`（无实现的伪发布）、`run_command`（恒拒绝的占位）——权限面对外只暴露真实能力，deny-by-default 名副其实（M45 收窄同向）；pm/dev/architect 角色声明同步清除，危险档语义由 `create_git_tag` 真实审批流承载，V2 沙箱承诺保留在 roadmap。
- **review.html 生成物出仓**（M113-I337）：根目录 206KB 的 MVP 评审打包页（2026-08-22 生成、可再生、零引用）不再进版本库——`tools/build_review_html.py` 工具保留，输出物 gitignore。

## [0.20.0] — 2026-10-05

M108~M109（需求到证据追溯助手 + 验收考官 Round 1 + 发布工程第十轮·lucide-react minor 一车与 v0.20.0 攒批发布）。攒批节奏第十四版：两轮一版。功能主体=追溯助手；lucide-react 1.51.0→1.52.0 minor 一车（M97 openai/M103 lucide 先例——发布轮内小车）；后端运行时 13 项零漂移（连续第六轮）。基线：pytest 490 / 冒烟 98 / vitest 47 / 机械防腐七件 ✓。

### Added
- **需求到证据追溯助手**（M108-I326）：需求/设计决定/实现/测试/交付物的关联图谱——独立 trace_links 投影表（六关系词表 implements/verifies/decides/delivers/documents/relates_to × 五类节点 item/artifact/asset/conversation/feature，事件溯源可 rebuild 复现）+ 追溯页三卡（覆盖概览/影响分析/链接登记）。改一条需求即见受波及的模块/文档/测试（impact 无向 BFS 两跳——任务上的测试也算需求的证据）；每轮缺口报告六类（缺测试/缺实现/零证据的需求+孤儿工作项+失效链接+变更未复核，支持里程碑切片；闭环=有实现且有测试，实现链上的测试传递计入）。
- **验收考官机制与首轮审查**（docs/13 Round 1）：新增长期质量轮——把设计要求变成反例与检查清单，专抓「单功能能用、连起来出问题」的接缝缺陷。首轮在追溯域抓获三例并当场修复：F1 归属缝隙（conversation/feature 跨项目可挂链·require_node 补归属门）、F2 登记链接后 trace-impact 缓存未失效（影响面板停留旧图）、F3 影响分析下拉在存在需求时只剩需求（任务侧反查 UI 不可达）——回归用例进套件（test_trace_integration + TracePage.test）。

### Changed
- **lucide-react 1.52.0 跟随**（M109-I328）：图标库 minor 一车——pnpm update 在 range 内抬 ^1.51.0→^1.52.0+lockfile 同车；vitest 47+build 全绿随收口复验。
- **docs/11 解冻至 v0.20.0**（M109-I328）：全部部署面时效戳随版；部署链已验证声明追加 M109-I327 lucide minor 车后双镜像重建对账；一键发布演练计数十→十一次。

## [0.19.0] — 2026-10-04

M106~M107（基线保鲜第四轮·v0.18.0 随版记录清偿 + 发布工程第九轮·零漂移 v0.19.0 攒批发布）。攒批节奏第十三版：两轮一版。本版零依赖变更（发布轮当轮实测双生态全零漂移——后端连续第五轮·前端 M105 pwa 车后归零·FastAPI 0.142.2 与 react/vite/lucide registry 多重外部互证）。基线：pytest 484 / 冒烟 96 / vitest 45 / 机械防腐七件 ✓。

### Changed
- **docs/06 §7 基线章随版对账 + docs/12 覆盖声明随版，均至 v0.18.0**（M106-I320）：v0.18.0 四项数字全持平（主 bundle 374.36KB / gzip 114.52KB / 36 chunks 五巡稳定 / precache 42 entries）——vite-plugin-pwa 2.0.0 构建插件零运行时影响实测坐实；docs/12 核验清单追加 M105 自动化面零新增。
- **真源指针体检四巡零漂移**（M106-I321）：NOTIFY_KINDS 9 员 / ACTION_TYPES 七种 / WATCHABLE_EVENTS 15 员 / run_daily_sweep 在案；随行写门与 env 速查对账一致——M98 首巡/M102 二巡/M104 三巡后的机制回归第四巡。
- **docs/11 解冻至 v0.19.0**（M107-I324）：全部部署面时效戳随版；部署链已验证声明追加 M107-I323 零漂移重建对账。

### Changed
- **docs/06 §7 基线章随版对账 + docs/12 覆盖声明随版，均至 v0.18.0**（M106-I320）：v0.18.0 四项数字全持平（主 bundle 374.36KB / gzip 114.52KB / 36 chunks 五巡稳定 / precache 42 entries）——vite-plugin-pwa 2.0.0 构建插件零运行时影响实测坐实；docs/12 核验清单追加 M105 自动化面零新增。
- **真源指针体检四巡零漂移**（M106-I321）：NOTIFY_KINDS 9 员 / ACTION_TYPES 七种 / WATCHABLE_EVENTS 15 员 / run_daily_sweep 在案；随行写门与 env 速查对账一致——M98 首巡/M102 二巡/M104 三巡后的机制回归第四巡。

## [0.18.0] — 2026-10-04

M104~M105（基线保鲜第三轮·v0.17.0 随版记录清偿 + 发布工程第八轮·vite-plugin-pwa 2.0.0 一车与 v0.18.0 攒批发布）。攒批节奏第十二版：两轮一版。本版前端构建插件 major 一车——唯一 breaking=assets-generator peer 扩展（本仓未装零影响；后端连续第四轮零漂移）。基线：pytest 484 / 冒烟 96 / vitest 45 / 机械防腐七件 ✓。

### Changed
- **docs/06 §7 基线章随版对账 + docs/12 覆盖声明随版，均至 v0.17.0**（M104-I314）：主 bundle 383.34→374.36KB[-9.0KB]·gzip 118.31→114.52KB·36 chunks 四巡稳定——lucide 1.51.0 一车后缩小，changelog（GitHub releases 直抓）无 tree-shaking 声明·归因未定如实记录；docs/12 核验清单追加 M103 自动化面零新增。
- **真源指针体检三巡零漂移**（M104-I315）：NOTIFY_KINDS 9 员 / ACTION_TYPES 七种 / WATCHABLE_EVENTS 15 员 / run_daily_sweep 在案；随行对账写路由 143（77 中间件+66 台账）与 env 速查 in sync——M98 首巡/M102 二巡后的机制回归第三巡。
- **vite-plugin-pwa 2.0.0 跟随**（M105-I317）：构建插件 major 一车——唯一 breaking=assets-generator peer 范围扩展（本仓未装零影响）·vite peer 含 ^8·workbox 7.4.1 无顺抬；PWA 产物核对 generateSW 保持+precache 42 entries 完全一致；pnpm update 不动 major 超 range·显式 add 改 range（minor 一车操作差异入档）。
- **docs/11 解冻至 v0.18.0**（M105-I319）：全部部署面时效戳随版；部署链已验证声明追加 M105-I318 pwa 车后双镜像重建对账。

### Changed
- **docs/06 §7 基线章随版对账 + docs/12 覆盖声明随版，均至 v0.17.0**（M104-I314）：主 bundle 383.34→374.36KB[-9.0KB]·gzip 118.31→114.52KB·36 chunks 四巡稳定——lucide 1.51.0 一车后缩小，changelog（GitHub releases 直抓）无 tree-shaking 声明·归因未定如实记录；docs/12 核验清单追加 M103 自动化面零新增。
- **真源指针体检三巡零漂移**（M104-I315）：NOTIFY_KINDS 9 员 / ACTION_TYPES 七种 / WATCHABLE_EVENTS 15 员 / run_daily_sweep 在案；随行对账写路由 143（77 中间件+66 台账）与 env 速查 in sync——M98 首巡/M102 二巡后的机制回归第三巡。

## [0.17.0] — 2026-10-03

M102~M103（基线保鲜第二轮·文档随版与留观澄清 + 发布工程第七轮·lucide-react 跟随与 v0.17.0 攒批发布）。攒批节奏第十一版：两轮一版。本版仅前端图标库 minor 一车（后端连续第三轮零漂移）。基线：pytest 484 / 冒烟 96 / vitest 45 / 机械防腐七件 ✓。

### Changed
- **docs/12 覆盖声明随版至 v0.16.0**（M102-I308）：M99~M101 三轮自动化面零新增核验入档；真源指针体检二巡零漂移（NOTIFY_KINDS 9 员/WATCHABLE_EVENTS/ACTION_TYPES 七种/run_daily_sweep 对账一致）。
- **docs/06 §7 基线章随版至 v0.16.0 + §3.4 拖拽补记**（M102-I309）：M100-I303 Board×双主题复扫 0 违规补归档+bundle 基线随版（36 chunks/主 bundle 383.34KB 持平）；§3.4 Board 章补卡片拖拽换列交互描述。
- **lucide-react 1.51.0 跟随**（M103-I311）：图标库 minor 一车（M93/M97 发布轮一车惯例·manifest/lockfile 同车·树摇消费面三关验证）。
- **docs/11 解冻至 v0.17.0**（M103-I313）：全部部署面时效戳随版；部署链已验证声明追加 M103-I312 lucide 小车后重建对账。

## [0.16.0] — 2026-10-03

M100~M101（看板拖拽补课轮·Board 拖拽换列——pointer 统一鼠标与触屏 + 发布工程第六轮·零漂移 v0.16.0 攒批发布）。攒批节奏第十版：两轮一版。本版零依赖变更（连续第二轮双生态全零漂移）。基线：pytest 484 / 冒烟 96 / vitest 45 / 机械防腐七件 ✓。

### Added
- **看板拖拽换列**（M100-I302）：Board 卡片可拖拽至生命周期桶——pointer events 单代码路径（鼠标+触屏一致·6px 阈值防误触），落列语义=目标状态组内同概念的首个状态；PATCH 失败（含状态流转白名单 422）乐观回滚；仅生命周期五桶与状态语义视图启用。QuickEdit 状态字段仍为非拖拽替代（WCAG 2.5.7 拖拽移动）。

### Changed
- **docs/11 解冻至 v0.16.0**（M101-I306）：全部部署面时效戳随版；部署链已验证声明追加 M101-I305 零漂移重建对账（连续第二轮·镜像内 13/13 一致）。

## [0.15.0] — 2026-10-03

M98~M99（基线保鲜轮·文档声明与可访问性基线随版 + 发布工程第五轮·零漂移 v0.15.0 攒批发布）。攒批节奏第九版：两轮一版。本版零依赖变更（发布轮当轮实测双生态全零漂移——13 项运行时依赖全顶格，FastAPI 官方 2026-09-30 发版与 LangGraph releases 1.2.12 双外部互证）。基线：pytest 484 / 冒烟 96 / vitest 41 / 机械防腐七件 ✓。

### Fixed
- **弹窗标题栏 landmark 伪影根治**（M98-I297）：Modal/Drawer 标题栏 `<header>`→`<div>`（语义无损）——弹窗在应用横幅内打开时不再产生重复 banner landmark（axe moderate×3）；语义由容器 `role=dialog`+`aria-labelledby` 承担。
- **docs/11 写路由计数对账 141→143**（M99-I300）：M96-I290 改密双端点入台账（64→66）时部署指南冻结窗 §2.4 计数未随——发布轮解冻随车修正（check_write_gates 实测 143=middleware 77+reviewed 66）。

### Changed
- **docs/12 覆盖声明随版至 v0.14.0**（M98-I296）：真源指针首次年度体检——修正「动作六种」漏记（实为七种，`create_recurring` 日历节拍自 M13 即在）；NOTIFY_KINDS/WATCHABLE_EVENTS/sweep 员清单对账一致。docs/06 §7 a11y 基线随版（受影响路由复扫 8 项全 clean+bundle 基线刷新）。
- **docs/11 解冻至 v0.15.0**（M99-I300）：全部部署面时效戳随版；部署链已验证声明追加 M99-I299 零漂移重建对账（双镜像 build EXIT=0+镜像内 pip 对账 13/13 一致）。

## [0.14.0] — 2026-10-03

M96~M97（账号安全补课轮·密码自助修改与会话失效 + 发布工程第四轮·openai 跟随）。攒批节奏第八版：两轮一版。基线：pytest 484 / 冒烟 96 / vitest 41 / 机械防腐七件 ✓。

### Added
- **密码自助修改与会话失效**（M96-I290/291）：右上身份区「改密」入口（旧密码再认证，OWASP 敏感操作语义）；管理员重置端点（admin 门）；会话令牌升级携凭据版本（四段 `user_id.epoch.expiry.signature`，兼容旧三段令牌）——**改密成功该账号全部会话立即失效**（含本机，需重登）；SSO 无本地密码账号 409；审计事件不含密码。`/api/health` 增 `auth_mode` 只读字段（M95-I287，匿名首访主动登录引导）。

### Changed
- **openai 3.24.0 跟随**（M97-I293）：requirements 下限=实测装机（M83「声明=装机=实测」纪律第四次）；双镜像构建+镜像内对账逐一致。

## [0.13.0] — 2026-10-02

M94~M95（全旅程自用复演轮 + 旅程 UX 反馈轮·登录语义与信息流富化）。攒批节奏第七版：两轮一版。基线：pytest 480 / 冒烟 96 / vitest 41 / 机械防腐七件 ✓。

### Added
- **端到端 PM 旅程复演**（M94-I284~286）：建项目→规划→自动化→运行→Gate 审批→工作流自动推进→通知→机器接入全链旅程级实证；看板工具栏补「＋新建」按钮（快捷新建此前仅键盘可达）。

### Fixed
- **网络模式匿名首访主动登录引导**（M95-I287）：`/api/health` 增 `auth_mode` 只读字段，SPA 守卫首屏即引导登录（此前全功能界面+本地身份切换器误导访客，只在写失败后才重定向）；登录成功回原页面（returnTo，仅相对路径防 open-redirect）；新建项目表单草稿跨登录/刷新保留。
- **仪表盘活动流显示名**（M95-I288）：`/api/events` 增 `actor_name` 批量富化（删户兜底原始 id）——与项目动态页同语义，消除「u_admin」式原始 id 直显。
- 快捷编辑优先级下拉改中文标签（与看板过滤一致，M94-I285）。

## [0.12.0] — 2026-10-02

M92~M93（后台线程韧性轮·webhooks 停机竞态修复 + 发布工程第三轮·依赖小版本跟随与攒批发布）。攒批节奏第六版：两轮一版。基线：pytest 479 / 冒烟 96 / vitest 41 / 机械防腐七件 ✓。

### Fixed
- **出站 webhook worker 停机竞态修复**（M92-I278/279）：teardown/换代间隙的缺表错误不再杀死后台投递线程（此前 db 短暂不可用一次即令出站 webhook 永久静默——daemon 线程死了无人拉起、应用表面健康）；队列条目代际标记——换代前入队的残留事件被直接丢弃，不再跨代处理（杜绝测试间串扰与恢复场景旧事件复活，`no such table` 噪声从源头归零）。

### Changed
- **依赖小版本一车跟随**（M93-I281/I282）：后端 cryptography 50.0.2 / jsonschema 4.26.0 / langgraph 1.2.12 / openai 3.23.0 / PyYAML 6.0.3（requirements 下限=实测装机，M83「声明=装机=实测」纪律第三次执行）；前端 14 项 lockfile 跟随（react 19.3.0 / react-router-dom 7.18.4 / tailwindcss 4.3.3 等，全 patch/minor 零 major）。双镜像构建+镜像内 pip 对账逐一致验证；顺带将 webhook 投递事件断言改轮询（M67-I202 坑的最后一处冷查询）。

## [0.11.0] — 2026-10-02

M90~M91（a11y 三期·低频管理面长尾收口 + 交付文档轮·自动化指南重写解冻）。攒批节奏第五版：两轮一版。基线：pytest 477 / 冒烟 96 / vitest 41 / 机械防腐七件 ✓。

### Fixed
- **低频管理面可访问名长尾清零**（M90-I272/273，axe 浏览器扫描点名 23 处）：风险登记册评分矩阵去透明度淡出、概率/影响选择器补名；本体页休假代理三个日期输入与成员/角色选择器补名；项目动态页**空文本链接根因修复**（系统事件无项目名时渲染出无名链接→兜底「（未命名项目）」）；审计页/我的工作选择器补名。**24 路由×亮暗双主题 axe 扫描全 clean**（扫描方法学入 docs/06 §7）。

### Changed
- **docs/12《自动化与集成指南》全文重写**（M91-I275/276）：858 行 40 节里程碑堆叠（覆盖止于 M43）→ 按用户任务五域拓扑（规则引擎/通知与 watch/定时 sweep/机器接入/指令模板）+时效戳+「文档描述语义·代码持有清单」活文档契约；**断言核验**抓获并修正凭印象错误（ntfy topic 为用户 profile 字段非全局 env 等），API roundtrip 走查自动化主路径四步全通。

## [0.10.0] — 2026-10-02

M88~M89（发布工程第二轮 + a11y 二期）。攒批节奏第四版：两轮一版。基线：pytest 477 / 冒烟 96 / vitest 41 / 机械防腐七件 ✓。

### Added
- **一键发布演练**（M88-I267）：`tools/release_drill.py` 一条命令跑完整恢复演练（隔离目录造数→备份→毁库[闸在备份成功后]→恢复→重建投影→项目数/事件数/FTS/工件内容四项对账→RTO 计时）；M86 三条演练纪律内嵌，发布轮收口必跑（docs/11 §2.5/§5.2.1）。

### Changed
- **发布轮收口 DoD 修订**（M88）：发布轮收口迭代 DoD 增「全链演练 + docs/11 时效戳核对」两项机制位——替代挂在 tag 动作前的记忆位（v0.9.0 曾因此漏跑演练，M88-I266 补课）。
- **a11y 对比 token 基线**（M89-I270）：五个前景色升 600/700 档（acc/ag/ok/warn/dan——500 档在白/浅底 3.07~4.46:1 不达 WCAG AA）；新增 `--color-acc-hover`；primary 系文字 `text-white`→`text-accbg`。修复后**亮暗双主题×六路由 axe 扫描全 clean**（color-contrast 72→0）。
- **表单可访问名清零**（M89-I269）：Board/Reports/Settings axe 点名 19 处补齐（select 不豁免、卡片/列表 checkbox 按工作项命名、链接下划线常显替代仅色差）。
- docs/11 部署指南解冻至 v0.10.0（web 构建链换代须知 node:24/vite 8 Rolldown；部署链已验证声明补 v0.9.0 双镜像重建对账）。

## [0.9.0] — 2026-10-02

M86~M87（运维验证轮 + 前端工具链 major 升级轮）。攒批节奏第三版：两轮一版。基线：pytest 477 / 冒烟 96 / vitest 41 / 机械防腐七件 ✓。

### Changed
- **前端工具链六 major 一车升级**（M87-I263，M83 依赖健康轮的前端续篇）：TypeScript 5.9→7.0（Go 原生编译器 tsgo，`tsc -b` 类型检查直通）、Vite 7→8（Rolldown 内核）、Vitest 3→5、@vitejs/plugin-react 5→6、jsdom 27→30、lucide-react 0.x→1.0；主 bundle 376KB→351.5KB。四懒加载路由浏览器实测零 fallback，web 镜像 frozen-lockfile 构建验证通过。
- **备份源存在性 loud fail**（M86-I261）：`tools/backup.py` 对缺失的源库不再静默连空库产出「空成功」备份（会让毁库闸失效），改为明确报错并提示检查 `APM_DATA_DIR`。
- docs/11 部署指南解冻至 v0.8.0（部署后自检速查+部署故障速查表+恢复演练纪律）；v0.8.0 镜像 compose build 双镜像验证通过（healthcheck 绿+核心路径冒烟）。

### Fixed
- **部署链两处阻断缺陷**（M86-I260 compose build 首次验证抓出）：compose 布尔透传空串被 pydantic-settings 拒绝（api 启动即崩→默认值修正）；`cryptography` 从未在 requirements 声明（OIDC 隐式依赖被共享环境掩蔽，干净容器 ModuleNotFoundError→显式声明）。

## [0.8.0] — 2026-10-02

M84~M85（测试日期稳健性 + 对话框键盘可用性）。攒批节奏第二版：两轮一版。基线：pytest 477 / 冒烟 96 / vitest 41 / 机械防腐七件 ✓。

### Added
- **对话框焦点管理**：Modal/Drawer 两原语接入 ARIA 对话框语义（`role="dialog"`/`aria-modal`/`aria-labelledby`）与零依赖焦点管理——打开即聚焦第一个可聚焦元素、Tab 循环陷阱（焦点不再逃逸进被遮挡背景）、关闭还原触发元素焦点；Drawer Escape 契约与 Modal 统一（修嵌套弹窗一次 Esc 双关）。
- **测试日期稳健性对账**：全库测试硬编码日期×真实时钟窗口端点对账（三分类判据——存量零真炸弹）；新增 `tools/check_test_dates.py` 机械防腐（窗口端点名册+REVIEWED 台账，冒烟 89 锁定含故意红自证）。

### Changed
- **可访问名长尾清零**：全库唯一无名符号按钮与高频模态表单（新建项目/评论/周期）placeholder-only 输入框补 `aria-label`。
- **a11y 机械锁**：axe-core（dequelabs 官方引擎）入 devDependencies，Modal/Drawer 代表性内容零 serious/critical 违规锁定（含故意红自证）；M82 路由懒加载全量复验（29 路由零 fallback）。

## [0.7.0] — 2026-10-02

M82~M83（前端韧性与认证安全 + 依赖健康）。攒批节奏首次兑现：两轮一版。基线：pytest 477 / 冒烟 93 / vitest 35 / check_env_doc ✓ / check_write_gates ✓。

### Added
- **前端错误边界**：零依赖 React 错误边界两级——App 级整树兜底（渲染崩溃不再白屏，错误卡+错误摘要+重载）、路由级单页隔离（单页崩溃不拖垮导航，就地重试、切页自动复位）；动态 chunk 加载失败（重部署后旧 hash 404）识别为「新版本已发布」刷新引导。
- **路由级代码分割**：27 个页面 `React.lazy` 按路由拆 chunk（vite 自动分包），主 bundle 1.1MB→376KB，首屏只加载当前页所需代码。

### Changed
- **后端依赖一车升级（I22 升级验证纪律第五次执行）**：fastapi 0.142.2 / pydantic 2.13.5 / pydantic-settings 2.15.0 / uvicorn 0.54.0 / sse-starlette 3.5.0 / openai 3.22.1（major，唯一 breaking=HTTP 客户端换装 HTTPX2，本项目零代码改动）/ **httpx→httpx2 2.13.1**（httpx 停维护后的 Pydantic 接棒正统后继，供应链核验见下）/ pytest-asyncio 1.4.0；`requirements.txt` 重写为实测版本下限（声明=装机=实测，消灭新环境拉到未验证版本组合的漂移）；全量测试日志弃用警告归零。

### Security
- **登录防爆破（OWASP API2:2023）**：`/auth/login` 失败滑窗——同一用户 10 分钟内失败 5 次即临时锁定（429+Retry-After，正确密码同样拒绝），窗口滑出自动解除、成功登录清零；锁定生效的转折点发 `session.login_locked` 审计事件（后续 429 不逐次发，防审计流灌水）；未知用户名跑同价哈希校验（计时不可用于枚举用户名）。
- **依赖供应链核验纪律**：新依赖装前 `pip download --no-deps` 解 wheel METADATA 核对 Author/Maintainer/Project-URL 三元组——弃用警告文本与第三方文章只是线索不是依据（httpx2「投毒诱饵」传言被元数据证伪案例入档 docs/01 §CB.1）。

## [0.6.0] — 2026-10-01

M78~M81（交互完备性与发布工程）。基线：pytest 561 / 冒烟 88 / vitest 30 / check_env_doc ✓ / check_write_gates ✓。

### Added
- **依赖关系解除面**：`DELETE /items/{id}/relations`（复合键定位、关系对任一侧可解、from 侧项目写门禁）+ `item.relation_removed` 事件——误建依赖从此可移除（日期不动：移除约束≠重排）；快捷编辑模态新增关系区（方向标签、解除确认含后果说明、类型/目标表单建立=非拖拽替代路径）。
- **跨项目依赖面收口**：/deps 依赖图渲染「外部依赖」占位节点（可读显真名+来源项目名、不可读 🔒——与 graph 端点语义归一）；blocked 判定计入跨项目可读上游；建链二级选择器（项目 select+目标 lazy 加载，零后端改动）。
- **触屏补课**：时间线依赖连线触点 <768px 恒可见；休假日历触屏两段点选（支持反向区间）。
- **发布工程**：版本单源 `app/apm/version.py`（/api/health 透出）；CHANGELOG.md（本文件）；git tag v0.5.0（回溯 M77 收口）/v0.6.0；docs/11 部署指南解冻至当前全部部署面。

### Security
- **写门对齐（OWASP API1 BOLA 第二轮）**：cycles/milestones/features/risks 九处 id-path 写端点补项目成员门（原不在中间件白名单且域内零门禁——非成员可改期/取消/关闭任意项目资源）；assets 六写端点分门（org 管理动作=实例成员门、deposit=from 侧项目门）；POST /runs 与 /conversations 入口补成员门；同类即修（NL 命令/orchestrator 批量发起/本体 reload+learn+apply=admin、模板包 from-asset=实例门、sweep=force 才 admin）。新增 `tools/check_write_gates.py` 路由×门禁对账（141 条写路由全覆盖，冒烟 85 锁定含故意红自证）。

## [0.5.0] — 2026-09-30

M46~M77（约 30 个里程碑）的发布级浓缩；全部迭代细节见 [docs/10 看板](docs/10-development-plan.md)。

### Added（精选）
- **真实 LLM 接入**（Anthropic/OpenAI 协议双适配+token 落账+NL 命令 L2 白名单漏斗）；**流式输出**（瞬态广播零落库）。
- **通知与分发面**：watch 自定义关注（条件化+导入导出+静默时段）、铃铛降噪折叠、周报三件套（自动生成+digest 邮件 HTML+Markdown 附件+订阅制）、ntfy 推送通道（SSRF 门复用）、Atom 动态流。
- **项目管理深化**：Cycles 周期+结转+燃尽 burnup、基线对比/S 曲线、关键路径 CPM、风险登记册（PMBOK）、项目收尾清单、完成自动重建 respawn、跨项目依赖图+路线图、成员负载+跨周热力。
- **工件与资产面**：工件清单页/删除/包导出/预览/全文搜索/运行历史、资产退役与归档、资产使用洞察、版本历史与 diff、模板包实例溯源。
- **观测与治理**：Prometheus 出站、端点性能观测+EXPLAIN 审计、事件表体积观测、备份/恢复演练工具、审计 CSV 导出、项目设置中心（混合 IA）、概念级可见性、项目级角色指令层。
- **AI 协作面**：运行分叉+血缘、run 重试对比、成本预算护栏（硬顶 402）、运行产物自动沉淀（评审门不绕过）、产物回流工作项、指令模板库+导入导出、PAT 机器接入、对话树导航。

### Security
- 读面门禁对齐 OWASP API1 BOLA：assets/template_packs 挂实例登录门、expenses/automations 挂项目成员门（M76）；交付面防腐 check_env_doc.py（M77）。

### Fixed
- propagate_reschedule 跨项目归因缺陷（M47）；gitrepo per-project 写锁修并行 run 竞争（M48）；快照语义：归档项不入新基线（M65）。
