# HANDOFF —— 写给下一个新会话（2026-09-06 更新 · M36 调研定义完成[透明与容量三件套 I110-I112]，下一步 I110 跨项目动态流）

> 你是完全没有任何上下文的新会话。先读完本文件，再按「下一步」开工。**不要重新调研已调研过的东西，不要重做已完成的事。**

## 1. 我们在做什么

**AgentPM**（`D:\project\agent-project-management`）：一套「人指挥、Agent 执行」的项目管理 Web 系统。项目生命周期建模为图（阶段+Gate+任务），角色化 Agent（YAML 声明）执行，人在审批门批准/拒绝/改后恢复；事件溯源记录一切；工件 Markdown 入 Git；本体（ontology YAML）是项目类型系统；资产库沉淀可复用工件。

**长期目标（用户设定，2026-09-05 更新，持续有效）**：
1. 持续调研同类开源项目优势，融合进项目，持续补齐短板与缺陷，直至满足工程管理落地标准；
2. **每一轮修剪 HANDOFF.md** 防止文档过大（本轮已把 §2 里程碑史压缩为索引行，详情真源=docs/10 §7 看板）；
3. **每一轮只做改动相关的验证**（对应 test_*.py + build），**每 5 轮（≈每个里程碑正式审阅）做一次全局验证**；
4. 上下文超限自动压缩（本文件即压缩产物），每轮结束更新本文件。

**进度真源**：[docs/10-development-plan.md](docs/10-development-plan.md) §7 状态看板——发现任何文档与代码不一致，以看板为准并即时修正。

## 2. 已经完成什么（一行一里程碑，详情看 docs/10 看板行与附录 A）

- **MVP（I0-I13，2026-08-22 终验）**：FastAPI + 事件溯源内核（append-only events + @on 投影注册表 + rebuild）+ LangGraph Runtime（replay provider）+ 对话域 + 资产域 + NL 命令 + React 全套页面 + docker-compose。
- **M4 本体构建闭环（I14-I16）**：本体归纳 learn 四规则 L1-L4 + provenance、版本化语义 diff + 数据影响分析、CQ 可回答性检查（semantica 融合第一里程碑）。
- **M5 协作与归纳增强（I17-I19）**：LLM 辅助归纳（confidence 门+去重合并）、本体模板包 export/import、users 事件投影 + 注册/切换身份 + emit 身份透传。
- **M6 类型系统（I20-I22）**：custom_fields（boolean/multiselect + `?cf=` 过滤，fail-closed 校验）、看板字段分组（含 multiselect 扇出）、LangGraph 1.0.9→1.2.11 升级全量回归零改动。
- **M7 模板中心（I23-I25）**：template_packs 注册表（本体目录活扫描）+ 模板中心页 + 资产沉淀为模板包 + 项目级字段激活。
- **M8 多人网络协作（I26-I28）**：pbkdf2 + HMAC 会话 + `auth_mode=local/network` 双模、项目成员三角色（owner/contributor/viewer）+ 写门禁 + access.denied 审计、会话→actor ContextVar 归账 + /login 页。
- **M9 看板自动化规则（I29-I31）**：规则事件溯源 + events post-emit hook 执行器 + 防循环双保险 + 规则管理面板 + 审计 ⚡ 过滤。
- **M10 webhook 与通知中心（I32-I34）**：webhook（入队/投递分离零阻塞 + HMAC-SHA256 + 退避重试 + replay/ping）、站内通知中心（**投影实体 id 必须确定性**）。
- **M11 邮件与 Atom（I35-I37）**：SMTP env 可选通道（`plan_notifications` 单源收件人）、Atom feed per-user key + 权限裁剪、通知偏好（邮件开关/站内照常）。
- **M12 报表与工作台（I38-I40）**：纯投影报表 API（零 ETL 零新表）+ ReportsPage/MyWorkPage + CSV 导出同数。
- **M13 里程碑与时间线（I41-I43）**：milestone.* 域 + items start_date/due_date、TimelinePage（**只读** Gantt-lite：条形/菱形/依赖连线/冲突标红）、NDJSON 导出（校验和+链序）。
- **M14 排程自动化与可携（I44-I46）**：依赖传播自动排期（auto_scheduled + item.rescheduled 显式事件 + 防环）、NDJSON 导入 roundtrip（冲突 409 整批拒绝）。
- **M15 PWA 与移动端（I47-I49）**：响应式基座（汉堡抽屉/横滚/栅格 md: 前缀）、vite-plugin-pwa（**/api 永不入 SW 缓存**）、关键路径触控。
- **M16 自定义视图（I50-I52）**：saved_views 投影 + 视图管理器（保存/切换/共享/URL 直开）+ 默认视图。
- **M17 OIDC SSO（I53-I55）**：零依赖 RS256 OIDC client（code+PKCE+id_token 全校验）+ JIT 四约束 + Keycloak compose 演示环境 + mini IdP 桩。
- **M18 评论与参与通知（I56-I58，审阅通过）**：评论域（@mention 精确最长匹配→通知 + item_participants 参与投影）、评论前端（补全下拉/💬 徽标/`?item=` 直开/点击置已读）、订阅 watch + 参与者通知最小面；**审阅即修 change_status actor_id 硬编码 A 级缺陷**。
- **M19 工时跟踪与报表（I59-I61，审阅通过）**：time.* 事件 + item_time_entries 投影 + CRUD（校验 fail-closed）、记时抽屉 + spent/estimate 徽标、项目工时报表按人/按日 + 本周工时（**补位 Plane GH #8045** 项目级聚合缺口，对账单测）。
- **M20 体验补齐三件套（I62-I64，审阅通过 8005d36）**：个人工时日历（GET /my/timelog + `#/my/time` 周/月视图 + 点日快捷记时，own-data）、时间线拖拽改期（条形拖拽移动/右缘缩放 → 单 PATCH，M14 审计与冲突重算自动生效，半透明预览 + Esc 取消）、评论 Markdown 渲染（lib/md.ts：marked+DOMPurify，mentions 令牌化 chip，任务清单只读 checkbox，存储纯文本不变）；docs/12 §17；冒烟 26。审阅即修：任务清单 checkbox 被 DOMPurify FORBID input 剔除 → 钩子白名单放行。
- **M21 日程集成三件套（I65-I67，审阅通过 f27bb33）**：依赖连线图内编辑（条形端点圆圈拖拽 → POST relations depends_on，橡皮筋线，Esc 取消；落点 elementFromPoint，重叠条形命最上层→自依赖守卫静默取消）、iCal 订阅（`/my/calendar.ics?key=` 复用 feed_key，own-data+可见性裁剪，RFC 5545 手写 VEVENT 零新依赖，rebuild 清运行态 key 属既有语义）、评论清单项转子任务（extract-task 端点复用 create_item，409/422/404；存储字节不变；渲染层 🔗链接+已提取徽标+显式「转为子任务」按钮防 #4261 误触）；docs/12 §18；冒烟 27。
- **M22 治理与效率三件套（I68-I70，审阅通过）**：全局搜索（`domains/search.py` FTS5 中文 bigram + `GET /search?q=` 可见性裁剪 + ⌘K「搜索 'xx'」入口与 `#/search?q=` 结果页；索引 handler 注册在 items/comments 投影器之后——注册序即执行序）、项目归档与克隆（`add_emit_guard` pre-emit 守卫：归档项目写 409，白名单 reopened/cloned/access.denied；`/reopen` 专用事件；`/clone` 成员/指派永不复制、关系复制；列表 include_archived + 归档/恢复/克隆按钮）、批量编辑（`POST /projects/{id}/items/batch-patch` 逐项复用 patch_item——逐事件审计、逐项结果不回滚；列表 checkbox + 批量条，同概念才能改状态，选择与分组解耦）；docs/12 §19；冒烟 28。
- **M23 计划对照与总览三件套（I71-I73，审阅通过）**：甘特基线（baselines 投影 UNIQUE 单活动快照 + baseline.set/cleared 事件 + TimelinePage 幽灵虚线条形偏离 amber；改期永不触碰快照）、组合总览（`GET /portfolio/report` `_visible` 裁剪 + totals 对账 + Dashboard「🗺 组合总览」卡）、Markdown 工具栏（CommentsModal 手写选区包裹/行前缀、保焦点选区、存储纯文本）；docs/12 §20；冒烟 29。
- **M24 结构与数据管理三件套（I74-I76，审阅通过，代码补交 9200f14）**：子任务层级（`_validate_parent` 防环 + ItemPatch re-parent + `?parent=`/`?descendants=` + 列表缩进树/「＋子」/后代 chip + 卡片父徽标）、CSV 导入导出（固定表头 + parent_title 引用 + 逐行校验报告——**行级 try 需捕 ValueError/TypeError**，float() 数据错误曾逃逸致 500 + 模板 + items.csv 导出 + 导入弹窗）、泳道避让（时间线概念行内子行贪心分配，区间染色 O(n log n)——修 M21 重叠 C 级）与多基线（baselines 去 UNIQUE + **db.py 存量迁移重建表** + set 追加历史 + 列表/切换）；docs/12 §21；冒烟 30。
- **M25 计划治理深化三件套（I77-I79，审阅通过 2fca11f）**：I77 基线偏差表（`GET /baseline-variance?baseline_id=&include_same=` 当前−基线天数偏差 + 汇总 + TimelinePage 偏差抽屉正红负绿）、I78 blocks 闭锁与关系可视化（**KERNEL_RELATIONS 增 blocks/precedes/relates**[blocked_by 存储单向不入内核] + change_status 前置守卫 422 "blocked by X" 全入口继承 + item_relations.lag_days 列/ALTER 迁移/载荷透传 + 时间线连线 EDGE_STYLE 分类型[depends_on 红虚/blocks 橙实/precedes 灰虚/relates 点线]）、I79 列表分页（`?limit=&offset=` 缺省全量兼容 + total 过滤后计数 + limit 钳 1-200 + 列表渐进渲染「加载更多」——重置按 **id 签名**防 refetch 误重置，审阅即修 d68ff25）+ docs/12 §22；冒烟 31。
- **M26 流程纪律三件套（I80-I82，审阅通过 7a67013）**：I80 看板 WIP 限制（本体 `board_defaults.wip_limits`[generic=4/software-dev=5] + board resp `wip` **全项目口径**计数[Kanboard「计全部 open 非过滤后」修复语义] + 列头「n/limit」徽标超限红 ⚠ 软约束不拦截；test_wip_limits 4 项）、I81 评论编辑与修订史（`PATCH /comments/{id}` 仅作者 + comment.updated 事件 + comment_revisions 投影[id=cr_{事件id} 确定性、rowid 倒序] + edited_at 列/迁移/drop 清单 + 「✎ 已编辑」徽标行内历史/作者行内编辑 + 新提及入图零通知；test_comments 8 项）、I82 状态流转白名单（Concept.transitions 可选声明**缺省全兼容** + validate_transition fail-closed 接入 change_status 与 blocks 同层全入口一致 + software-dev bug 白名单[open 不能直跳 verified]；test_transitions 2 项；test_reports 触发器迁移走合法链）+ docs/12 §23；冒烟 32。
- **M27 排期深化三件套（I83-I85，审阅通过 993540a，审阅即修 3 前端缺陷 ab00660）**：I83 lag 排期联动（post_relation 对 depends_on **显式非零 lag** 立即重对齐 auto_scheduled 后继[start=前置 due+1+lag、负=lead 重叠、span 保持、级联传播；None/0 不动 opt-in 兼容]——两段式：绝对对齐只在建关系时、改期走 M14 相对平移天然保间隔；时间线「+N 天」注记）、I84 跨项目里程碑路线图（`GET /portfolio/roadmap` 复用 feed._visible 三层同组合总览口径 + 排除归档/无里程碑项目 + overdue=逾期未达成[achieved 永不超期] + progress 复用 milestone_progress；「📅 路线图」页 + Dashboard 组合卡入口 + 顶导航——补 GitLab epic #1105 跨项目缺口）、I85 里程碑燃尽（`GET /milestones/{id}/burndown` **纯事件重放零新表**：done 首达日累计、实际线画到 min(today,due) 过期定格、理想线线性、velocity=近 7 天完成数、cancelled 不入口径、**rebuild 后逐字节相等**；报表「🔥 燃尽」卡 SVG 双折线）+ docs/12 §24 + 冒烟 33。审阅即修：RoadmapPage 链接 #/ 前缀畸形 URL + done_ratio 拼 % 显示 0.6%、TimelinePage depends_on 已对齐边静默不画致 lag 注记永不可见（新增 depends_on_ok 灰虚线）。
- **M28 落地闭环三件套（I86-I88，审阅通过 5e8be63，审阅即修 6fd42de）**：I86 工时锁定与审批 ✅（timesheet 域：submit 按期间聚合[空 422/重复 409/重叠已批 409/驳回复用同 id 重提交 OR REPLACE]、approve/reject 仅 Owner·admin、**approved 后 timelog 三写路径 409 锁定**——计薪事实整条冻结含备注；MyTimePage 🧾 审批面板；test_timesheet 3 项）、I87 成员负载横切 ✅（`GET /portfolio/workload` _visible 项目循环内按 assignee 聚合活跃/超期/项目分布 + 7 天工时**按项目隔离聚合防不可见项目泄漏** + 「👥 负载」页/Dashboard 入口/顶导航；test_workload 2 项）、I88 打印视图 ✅（`@media print` 隐藏 no-print/nav/aside + Card 统一挂 print-card[去阴影细边框 break-inside avoid] + PrintButton 接入看板/报表/Dashboard——window.print 另存 PDF 零服务端零新依赖）+ docs/12 §25 + **冒烟 34**（审批冻结矩阵/负载对账/rebuild 一致），约 9 人日。
- **M29 效率与可观测三件套（I89-I91，审阅通过 5fd751c）**：I89 个人排期月历 ✅（`GET /my/schedule` own-data 口径全可见未归档项目有日期项；「📅 我的日程」页 /my/schedule：月网格 + 跨度逐日 chip + HTML5 DnD 拖卡片改期[span 保持 delta 平移→单 PATCH 复用 M14 审计] + 拖选空白格范围建任务[自动指派自己]；test_schedule 2 项）、I90 看板卡片快捷编辑 ✅（卡片/列表行「⚡」→ QuickEditModal 直改状态/优先级/执行者/截止日——**仅提交变化键走既有 patchItem**，白名单/闭锁/WIP/审计零成本继承，agent: 前缀保持 agent 指派）、I91 运行聚合报表 ✅（`GET /projects/{id}/runs/report` 按角色/状态聚合成功率/平均时长/Gate 挂起率/步骤数——**tokens 直接 SUM 既有列如实报零**；RunsPage「📊 运行报表」卡对账；test_runs_report 2 项）+ docs/12 §26 + **冒烟 35**（月历对账/快捷编辑守卫继承/报表对账/rebuild 一致），约 9 人日。
- **M30 治理洞察三件套（I92-I94，审阅通过 11cc1b2，审阅即修 60a043c）**：I92 项目健康评分 ✅（`_health_factors`+`_health_score` 四因子加权[超期率 40/滞留率 20/吞吐动量 30 min 封顶/Gate 挂起 10，加法式各因子健康贡献满权重，无活跃 None]；`GET /portfolio/health` _visible 同口径评分升序；Dashboard 组合卡 ♥ 评分徽标绿/黄/红；test_health_score 3 项[公式级+集成手算 60/70+rebuild]）、I93 健康趋势 ✅（`GET /projects/{id}/health/history` 事件重放 item/approval 五类事件、每 5 天周界采样[末点=今天与 I92 同真相]、stale 用 last_touch 近似；报表页「💚 健康趋势」卡 SVG 迷你线；test_health_history 2 项[尾点 70→超期 60 手算/rebuild 序列相等]——事件溯源红利第三例）、I94 评论引用回复 ✅（CommentsModal「❝」→「@作者 引用：」独立行 + 原文逐行 blockquote 预填聚焦，存储纯文本不变、渲染免费，零后端；**审阅即修 60a043c**：原「@作者 > 原文」同行内联 `>` 非引用语法不渲染 blockquote）+ docs/12 §27 + **冒烟 36**（评分手算/趋势末点对齐/引用 roundtrip/rebuild 一致），约 9 人日。
- **M31 响应力三件套（I95-I97，审阅通过 f859af5，审阅即修 7026c13）**：I95 键盘优先操作面 ✅（lib/shortcuts.ts 单一真源注册表 + ShortcutsOverlay 可搜索 `?` 浮层 + 看板 j/k 游标 + `C` 快捷新建；vitest 6）、I96 通知偏好按事件类型细分 ✅（notification_prefs 运行态表[缺行=全开] + pref_allows 单一闸门[mention 恒真]双通道收口 + GET/PUT /me/notification-prefs 五类矩阵；test_notification_prefs 6——rebuild 重放按当前偏好重算=投递收口语义）、I97 响应性指标 ✅（`GET /projects/{id}/responsiveness` 审批响应/评论首响应[事件重放排作者自评] + 报表「⏱ 响应力」卡——CHAOSS Time to First Response；test_responsiveness 4）。审阅即修 7026c13：Modal 组件接入 Esc 关闭 + 冒烟 37 补 _restore_identity 身份恢复夹具。
- **M32 引擎与入口三件套（I98-I100，审阅通过 6f247c2，审阅即修 scheduler_enabled 开关）**：I98 时间触发自动化 ✅（`e339824`+docs `54858a7`：trigger:schedule:daily[不进 TRIGGERS、dispatch 零感知] + run_daily_sweep[**派生字段 overdue** 注入走既有等值条件、条件引擎零改动] + automation.swept 心跳幂等[**零新表**、当日事件即跳过、force 强扫] + create_recurring[emit 真实 item.created 一等卡] + ticker 线程[邮件同款] + POST /automations/sweep + 规则面板触发器下拉/⟳手动扫描；test_scheduled_rules 3 + M9 回归 5 绿）、I99 外部 intake 收件 ✅（`2286a5a`+docs `689375f`：intake.py 新域[intake_tokens **投影表**进 drop 清单+单活动令牌+明文存储] + POST /intake/{token} 公开端点[compare_digest/白名单/actor=intake/复用 create_item] + `/#/intake/:token` 公开表单页 + 设置页「📮 外部收件」卡 owner-only；test_intake 3）、I100 列表分组聚合 ✅（`b864fe9`+docs `61b3077`：列表「按组聚合」下拉 + 组头行[n 项+⏱ spent 合计+折叠] + 分组作用于已显示行与 I79 兼容 + docs/12 §29 + **冒烟 38**）。审阅即修：**scheduler_enabled 测试开关**（config+conftest 置 False+main 条件安装——lifespan ticker 在长全量跑中醒来抢发 swept 心跳致测试显式 sweep 被幂等跳过）。
- **M33 纵深三件套（I101-I103，审阅通过 9fc20d1，审阅即修关键路径按钮移出基线条件块）**：I101 关键路径高亮 ✅（`9782142`+docs `c5d37c7`：`GET /projects/{id}/critical-path` CPM 逆向传递[latest_fin[n]=min(latest_fin[m]−dur[m]−lag)、float=latest−due、**float≤0 关键**] + Kahn 拓扑环安全[cycle:true 诚实态] + TimelinePage「⛔ 关键路径」开关红框条形；test_critical_path 6）、I102 子任务进度汇总 ✅（`8697b31`+docs `77f1af2`：lib/rollup.ts subtaskProgress 纯函数[直接子任务 done/total+spent 合计、孙任务不跨级] + 看板父卡/列表行「🧩 n/m」徽标[全完成转绿] + TimelinePage 父条形微型进度条；纯前端零后端；vitest 8）、I103 工作项归档与回收站 ✅（`a9d6695`+docs `bf3730e`：item.archived/restored 事件 + items.archived_at 列[ALTER 迁移] + list_items 单点收口默认排除 + critical-path 同步排除 + archive/restore 端点[重复 409] + trash 端点 + 卡片「🗄」+「🗑 回收站」抽屉恢复；test_archive 3）+ docs/12 §30 + **冒烟 39**。
- **M34 时间关怀三件套（I104-I106，审阅通过 1fd27b5，审阅即修 0 处；docs/01 §AG + docs/10 §M34 + docs/12 §31）**：I104 工作日历跳休 ✅（calendar.holiday_added/removed 事件 + non_working_days 投影表 + **advance_to_workday 单一辅助函数**收口 M14 传播与 I83 对齐两处[落点顺延、手排期零感知、工期保持日历日跨度] + GET/POST/DELETE /calendar/holidays admin only + 设置页「📅 工作日历」卡；test_calendar 3 + test_scheduling 周一网格重排——**语义演进处理范式：造数锚定周一网格而非加产品开关**）、I105 到期邻近提醒 ✅（run_daily_sweep 内建 `_notify_due_soon` + item.due_soon_notified 专用事件[事件流查当日幂等] + NOTIFY_KINDS 第六类 due_soon + 站内 @on/邮件 NOTIFY_EVENTS 双通道同闸——**事件是事实投递是收口**；due_soon_days 配置默认 3；test_due_soon 3——**教训：NOTIFY_EVENTS 与 @on 是两套名册，新 kind 两处都挂**）、I106 基线 S 曲线 ✅（`GET /projects/{id}/baseline-curve` PV 按基线 due 周界采样累计 + EV 事件重放 done 首达 + SPI=EV/PV 诚实 None——**事件溯源红利第六例**；快照 3 元组 [start,due,estimate_hours]、旧快照回退权重 1.0——**索引解构兼容、整组相等断言不兼容**；报表「📈 S 曲线」卡 + **冒烟 40**[S 曲线段独立项目防权重盘污染]）。
- **M35 通道与回复三件套（I107-I109，审阅通过 2e5f70a，审阅即修 ba5623c；docs/01 §AH + docs/10 §M35 + docs/12 §32）**：I107 IMAP 邮件转任务 ✅（新域 imap_in.py：`_fetch_messages` 唯一 imaplib 接缝[测试 stub 同 FakeSMTP 范式] + **parseaddr 收口 `_route_message`**[任何入口路径同构规范化] + From 匹配 users.email → 该用户身份路由默认项目复用 create_item 全校验链、**正文转首条评论**[零 mention 解析] + 降级双态=IMAP_FALLBACK_PROJECT_ID 配置则 intake 否则 ignore[Redmine --unknown-user=ignore] + imap_seen 投影表进 drop 清单 + POST /imap/poll admin + ticker 顺带 poll；test_imap_in 4——教训：解析收口在抓取层会被旁路，收口点必须在消费决策层）、I108 常用回复 ✅（saved_replies 用户级**运行态表不进 drop 清单**[notification_prefs 同构] + GET/POST/DELETE /me/saved-replies own-data[≤100/≤2000 超长 422、删他人 404——查询收口而非过滤收口] + CommentsModal「⌨ 常用回复」/`Ctrl+.` 面板[过滤/Enter 插入第一条/点击插入光标处/✕ 删除] + 「☆ 存为常用」选中文本入库；test_saved_replies 3）、I109 引用快捷键 ✅（SHORTCUTS `R` 条目自动收录浮层 + 看板游标选中按 `R` 直开评论预填引用最后一条评论[autoQuote 一次性 effect + 草稿空守卫——数据异步到达且用户可能已输入；Enter 不预填双键双意图]；vitest 9；**冒烟 41**[IMAP stub roundtrip/常用回复 own-data+rebuild/引用字节一致 roundtrip]——**审阅即修 ba5623c：面板 Enter 插入渲染闭包时序加固**[函数式 setDraft + 实时取 e.target 值]；**环境教训：IAB 合成键盘 press 派发不到页面，浏览器复演键盘路径用 dispatchEvent KeyboardEvent**）。
- **当前验证基线：pytest 268 全绿；冒烟 41 条 GREEN；vitest 9/build 绿。**
- **M36 透明与容量三件套（I110-I112，定义 7f7e938，docs/01 §AI + docs/10 §M36）**：调研结论——I110 跨项目动态流（OpenProject「My activity」浏览态聚合语义[区别于 Linear Inbox 通知态]：`GET /portfolio/activity` feed._visible 三层裁剪 + 事件白名单[item.created/status_changed/comment.created/milestone.*/approval.requested] + actor/project/kind/limit 过滤 + 「📰 项目动态」页——**零新表零重放直读 events，事件溯源红利第七例：活动流免费**）、I111 个人 Availability 休假（Taiga「某人 11 月只工作 13 天」容量痛点/Jira PTO 插件语义：user_time_off_started/cancelled 事件 + 投影表 + 设置页「🏖 我的休假」卡 own-data 重叠 409 + 消费两端=I87 workload「🏖 休假中」标记 + I89 我的日程休假条；自动转派留 backlog）、I112 S 曲线扩展（MS Project 多基线+EV+AC 叠图原生缺失需导 Excel：AC 第三线=重放 timelog.time_logged 累计基线项 spent + `?compare=` 双基线 PV 并列——事件溯源零导出直出）。+ docs/12 §33 + 冒烟 42（并入 I112）+ M36 审阅。
- **I110 已完成（代码 b92dbef + docs c96c41a）**：reports.py `GET /portfolio/activity`（ACTIVITY_EVENTS 八类白名单 + over-fetch 3 倍→可见性裁剪→截 limit + 批量 map 无 N+1 + _activity_summary 中文摘要）+「📰 项目动态」页 /activity + 侧栏 Newspaper 入口；test_activity 3 项（**local 隐式 self 边界：端点级裁剪不可测，函数级断言**——I87 同款）。**当前验证基线：pytest 271；冒烟 41；vitest 9/build 绿。**

## 3. 现在卡在哪

**没有硬阻塞。** 遗留 B/C 级意见见 docs/10 附录 B/C（本体治理权限分层 V2、本体版本事件级归档等）。

## 4. 下一步是什么（按序）

1. ~~M24~M35 全闭环~~ ✅（每轮：调研定义 → 3 迭代[三段式提交] → 正式审阅[全量回归+DoD 逐项+浏览器隔离复演]；审阅提交号 566967d/2fca11f/7a67013/993540a/5e8be63/5fd751c/11cc1b2/f859af5/6f247c2/9fc20d1/1fd27b5/**2e5f70a**；单迭代详情真源=docs/10 §7 看板行与附录 A/B——本节不再保留单迭代条目）。
2. **M36 三迭代（I110 ✅ b92dbef/c96c41a[端点+动态页+侧栏；test_activity 3——local 隐式 self 边界函数级断言]；下一步 I111）**：**I110 跨项目动态流**（reports.py `GET /portfolio/activity`——复用 feed._visible 三层裁剪 + 事件白名单[item.created/item.status_changed/comment.created/milestone.*/approval.requested] + ts 倒序 + `?actor=&project_id=&kind=&limit=` 过滤 + 「📰 项目动态」页 /activity 时间线式[图标+摘要+项目名+相对时间+点击跳转] + 侧栏全局入口，纯读事件零新表；单测：_visible 裁剪/白名单/过滤 limit/rebuild 后序不变）→ **I111 个人 Availability 休假**（`user.time_off_started`/`user.time_off_cancelled` 显式事件 + user_time_off 投影表[进 drop 清单] + 设置页「🏖 我的休假」卡 own-data[重叠 409] + I87 workload 成员行「🏖 休假中」标记 + I89 我的日程月历休假条；单测：roundtrip/重叠 409/取消/双端标记/rebuild）→ **I112 S 曲线扩展 + 冒烟 42 + M36 审阅**（baseline-curve 加 AC 第三线[重放 timelog.time_logged 累计基线项 spent] + `?compare=<baseline_id>` 双基线 PV 并列 + 报表三线图例/对比下拉；docs/12 §33；冒烟 42=动态流对账/休假 roundtrip+双端标记/S 曲线 AC 手算 + rebuild；审阅=全量回归+DoD 逐项+附录 B+浏览器隔离复演）。每迭代三段式提交：代码 → docs → HANDOFF 收口。设计细节真源=docs/10 §M36 三小节 + docs/01 §AI。
7. 每轮纪律不变：演示/审阅隔离 data+ontologies 且 netstat 确认单监听（**preview 必须显式从 web/ 起**）；**复演造数脚本失败后必须清理半成品数据再重跑**（M22 审阅踩；M26 审阅：events append-only 不可单删→**整库重建重 seed**；**M31 审阅重跑 seed 前清库重启后端**）；**复演假阴性先核对输入（ID/造数/SW 旧缓存）再怀疑系统**（M25 ID 笔误、M26 SW 旧缓存；**M28 审阅 console 200 错误=SW 旧 precache 第四次验证**；**M31 审阅第七次验证：构建后必须 SW 清理+reload 才见修复**）；中文文档/源码/测试一律 Edit/Write 工具（**heredoc 彻底禁止**——I79 第 4 次违例；**M28-I86 收口第 5 次违例自记**：python heredoc 改 HANDOFF 虽带引号形式无损，仍属违例——改用 Edit 工具）；**commit message 反引号用单引号包裹**（M23-I72 踩）；python 写文本 newline="\n"；**每段式提交前 `git status` 核对源码文件齐全**（M24-I76 漏 stage 被审阅揪出）；**看板行状态 Edit 失败必须重试补正**（M25 定义时发现 M24 行漏改）；**HANDOFF 每轮收口时修剪**；**复演造数含中文 JSON 用 python urllib 不用 curl**（M27 审阅踩：Git Bash curl GBK 编码致 error parsing body）；**「按人聚合」端点的造数必须含「指派给谁」**（I88 冒烟踩：未指派则 members 空 IndexError）；**blocks 关系造数方向=from 阻塞者 to 被阻塞者**（I91 冒烟踩：方向反了闭锁守卫静默不触发）；**docs/10 追加表格行的 Edit：old_string 用行首片段锚定、new_string 必须以原文行开头再接新行**（M31 三次同型失误——把原文行整行替换掉，均靠 git diff 纯新增校验兜住）；**冒烟/测试切身份后必须恢复 settings.user_id**（M31 审阅踩：smoke 首个切身份测试泄漏身份致字母序后续测试失败）；**测试切身份前先确认目标用户已注册**（I97 踩：未注册用户切换静默无效）。

## 5. 有哪些坑不要再踩

- **投影器 INSERT 的列序与参数元组必须逐列目视核对**（I20 踩坑，连续三处错）。**单用例可能过、套跑才炸，别信单绿**。
- **`sets.append(a, b)` 双参 TypeError**：item.updated 投影隐藏 bug——新键接入既有投影器时把整段逻辑读一遍。
- **起服务做演示/审阅必须同时隔离 data 与 ontologies**：env `APM_DATA_DIR` + `APM_ONTOLOGY_DIR_OVERRIDE`（还要 `cp -r ontologies/. <override目录>/`，override 目录不会自动建文件）；**只设 APM_DATA_DIR 不够**（M4 审阅污染源文件事故）。
- **replay_templates.py 模板函数必须定义在 `_TEMPLATES` 字典之前**（import 时求值）。
- **测试/冒烟绝不写真实 `ontologies/` 源目录**：用 conftest `isolated_ontologies`（同时隔离 agents/）；改本体相关代码要 `reload_all()`。夹具 teardown 先清 override 再 reload。
- **diff 的 from/to 语义不对称**（I15）：from 快照优先、to=当前永远读活文件。
- **测试造信号必须发真实事件**（带 project_id）；sqlite Row 无 `.get()`；`Ontology.concepts` 是 dict；`asset_links.target_ref`/`mentions` 是 JSON 字符串需 json.loads；事件 append-only 触发器强制。
- **前端是 HashRouter**：直接导航要用 `/#/p/{pid}/board`；同 hash URL 不重载 SPA（React Query 缓存旧值）→ location.reload() 强刷。
- **打/恢复演示的确定性时序**：run 由后台线程执行，"interrupted"=挂在 Gate；注入=对话内发消息；恢复=▸ 继续。参考 `app/tests/test_runtime.py`。
- **演示环境 console 会有 404/连接拒绝噪声**：长命标签页跨隔离库轮询+关服重连——逐条核对来源再下结论。
- **自动化断言先想清「活规则已在造数阶段触发过」**（I29 踩两次）：要验证静默就先停用所有规则再数事件。
- **items 投影对 custom_fields 是整列覆盖**（I20/I29）：任何「改一个字段」的路径必须合并现值后再发 item.updated。
- **投影器新生成实体的 id 禁止随机**（I34）：必须由事件流确定性导出（如 `n_{事件id}_{用户}`）；单测 rebuild 断言直接对比 id/未读数。
- **/api/session/identity 是后端全局状态**（local 模式）：bash curl 切过身份浏览器也变（复演前核对顶栏 chip）；依赖 effective_actor 的测试加身份还原夹具；权限探针先固定配置身份再测 403。
- **改源码一律用 Edit 工具，禁 heredoc/python 脚本**（I35 踩两次）；**python 写文本必须 `newline="\n"`**（Windows 默认 CRLF 制造全文 diff 噪声）；中文文档段落一律 Edit 工具（bash 反引号吞字、heredoc GBK 乱码）。
- **commit 纪律**：迭代号前缀；冒烟基线只增不减；范围变更先记 docs/10 附录 A；docs/10 的 Edit 锚点务必唯一定位（曾把附录 A 行插进附录 B）。小本体主义硬约束（概念 ≤12、字段 ≤10、关系 ≤6）；别引入 RDF/SPARQL/推理机。
- **全局导航入口的 to 映射别硬编码**（M8 审阅）：加导航项时逐条点一遍图标。
- **演示中后端后台进程可能被系统回收**（Windows exit 1073807364）：截图前先探 `GET /api/health`。
- **Windows 允许多进程同时 LISTEN 同一端口**（I57 复演）：双实例各持不同数据目录请求随机分流——「badge 与列表同源自相矛盾」即此症；**起演示先 `netstat -ano | grep :8000` 确认单监听**。
- **复演造数顺序：先建用户再发 @ 评论**（I57）：评论先于被提及者落库则 mentions 为空、无通知。
- **actor 归因排查先看事件行 actor_id**（M18 审阅）：签名默认参数里的硬编码身份 grep 扫不出来——新加带 actor 的函数一律 `actor_id: str | None = None` + `or events.effective_actor()`。
- **装饰器与函数名之间永远不要插新函数**（I60）：`_attach_spent` 插进 `@router.get` 与 get_items 之间，装饰器落到 helper 头上 405/KeyError。
- **注册新域两处都要**：`main.py`（import + include_router）与 `apm/domains/__init__.py`（handler 注册——rebuild 靠它，漏了 rebuild 后投影丢失）。
- **新投影表必须进 drop_projections 清单**，否则重放撞 UNIQUE。
- **改前端后生产构建页面须 SW update+reload 才见新 UI**（autoUpdate precache 旧 bundle）。
- **TestClient 默认 follow_redirects=True**：302 到外部 IdP 后 404 极易误判为路由缺失——断言须 `follow_redirects=False`。
- **后端重启窗口期前端 refetch 失败留陈旧缓存**（console 一串错误）：先 reload 再下结论。
- **浏览器残留上一会话的 SW 旧 precache**：新会话复演首访新路由可能落旧路由表被重定向（M20 审阅踩：/my/time 重定向 #/）——先 unregister+caches.delete 再 reload。
- **marked 渲染的任务清单 checkbox 会被 DOMPurify FORBID input 剔除**（M20 审阅即修）：要渲染只读复选框用钩子白名单（仅 type=checkbox 放行）。
- **auto_scheduled 只认 PATCH 开关**（M14 语义）：create 载荷传 True 静默不持久化——依赖传播测试/复演必须创建后 PATCH。
- **pnpm 命令注意 cwd**：后台起 preview 前确认在 web/ 目录（repo 根无 package.json，且残留旧 preview 实例会抢答端口）。
- **task 状态集无 todo**（software-dev task）：open/ready/in_progress/awaiting_review/done/cancelled，测试用 ready。
- **源码/测试文件追加也必须用 Edit 工具**（I63 重申；**I79 第 4 次违例自记**）：bash heredoc 即使引号形式无替换也是侥幸——不再用作任何文件写入手段，写长 Markdown 段落也不例外。
- **功能提升使旧测试前提失效属正常演进**（I78）：blocks 入内核后 5 个以「blocks 未注册被拒」为前提的 learn 测试失败——处理方式是换仍未注册的 blocked_by 作触发器（保持 learn/unlock/diff 断言强度），不是放宽断言。

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 271 项，应全绿
python tools/smoke/run_smoke.py       # 冒烟基线 41 条，应 GREEN（repo 根目录跑）
# 前端
cd web && pnpm install && pnpm dev    # http://localhost:5173
# 后端（演示/审阅时必须隔离：APM_DATA_DIR + APM_ONTOLOGY_DIR_OVERRIDE 且拷贝本体进去！）
cd app && python -m uvicorn apm.main:app --port 8000 --reload
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`（含 schema.py 迁移/drop_projections、events.py actor ContextVar + post-emit hook + emit guard）；域 `app/apm/domains/`（items/comments/notifications/timelog/reports[milestone 燃尽将入]/milestones[内含 milestone_progress]/scheduling 视 test_scheduling.py、views/webhooks/mailer/feed[内含 _visible 可见性谓词]/members/automations/template_packs…）；本体 `ontology.py`+`ontology_learn.py`+`ontology_versions.py`+`ontology_cq.py`+`ontology_pack.py`；OIDC `core/oidc.py` + 演示 `tools/keycloak/`+`tools/oidc_stub.py`；前端 `web/src/pages/`（Board/TimelinePage/ReportsPage/MyWorkPage/TemplatesPage/OntologyPage/RoadmapPage）+ `web/src/components/`（CommentsModal/TimeLogModal/AppShell）。
