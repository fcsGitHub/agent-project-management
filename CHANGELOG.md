# Changelog

本文件记录 AgentPM 的**发布级**显著变更（人写精选，非 git log 倾倒——[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式）。迭代级细节真源=[docs/10-development-plan.md §7 状态看板](docs/10-development-plan.md)。

版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)；版本单源=`app/apm/version.py`（/api/health、web/package.json、README 版本行与 git tag 由冒烟 86 锁定一致）。

## [Unreleased]

M82（前端韧性与认证安全——攒批中：发布节奏已从每轮转攒批，随 v0.7.0 统一 bump+tag）。

### Added
- **前端错误边界**：零依赖 React 错误边界两级——App 级整树兜底（渲染崩溃不再白屏，错误卡+错误摘要+重载）、路由级单页隔离（单页崩溃不拖垮导航，就地重试、切页自动复位）；动态 chunk 加载失败（重部署后旧 hash 404）识别为「新版本已发布」刷新引导。
- **路由级代码分割**：27 个页面 `React.lazy` 按路由拆 chunk（vite 自动分包），主 bundle 1.1MB→376KB，首屏只加载当前页所需代码。

### Security
- **登录防爆破（OWASP API2:2023）**：`/auth/login` 失败滑窗——同一用户 10 分钟内失败 5 次即临时锁定（429+Retry-After，正确密码同样拒绝），窗口滑出自动解除、成功登录清零；锁定生效的转折点发 `session.login_locked` 审计事件（后续 429 不逐次发，防审计流灌水）；未知用户名跑同价哈希校验（计时不可用于枚举用户名）。

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
