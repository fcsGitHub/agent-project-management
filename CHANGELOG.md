# Changelog

本文件记录 AgentPM 的**发布级**显著变更（人写精选，非 git log 倾倒——[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式）。迭代级细节真源=[docs/10-development-plan.md §7 状态看板](docs/10-development-plan.md)。

版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)；版本单源=`app/apm/version.py`（/api/health、web/package.json、README 版本行与 git tag 由冒烟 86 锁定一致）。

## [Unreleased]

未发布变更（攒批中——迭代细节真源=[docs/10 §7 看板](docs/10-development-plan.md)）。

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
