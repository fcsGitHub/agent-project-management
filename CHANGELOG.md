# Changelog

本文件记录 AgentPM 的**发布级**显著变更（人写精选，非 git log 倾倒——[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式）。迭代级细节真源=[docs/10-development-plan.md §7 状态看板](docs/10-development-plan.md)。

版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)；版本单源=`app/apm/version.py`（/api/health、web/package.json、README 版本行与 git tag 由冒烟 86 锁定一致）。

## [Unreleased]

未发布变更（攒批中——迭代细节真源=[docs/10 §7 看板](docs/10-development-plan.md)）。当前攒批：空——v0.20.0 已发布（M108~M109 成版），下两轮（M110~M111）成版 v0.21.0。

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
