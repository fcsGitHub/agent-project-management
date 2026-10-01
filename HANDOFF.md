# HANDOFF —— 写给下一个新会话（2026-10-01 更新 · M80 调研已定案，下一步 I240 写门对齐）

> 你是完全没有任何上下文的新会话。先读完本文件，再按「下一步」开工。**不要重新调研已调研过的东西，不要重做已完成的事。**

## 1. 我们在做什么

**AgentPM**（`D:\project\agent-project-management`）：一套「人指挥、Agent 执行」的项目管理 Web 系统。项目生命周期建模为图（阶段+Gate+任务），角色化 Agent（YAML 声明）执行，人在审批门批准/拒绝/改后恢复；事件溯源记录一切；工件 Markdown 入 Git；本体（ontology YAML）是项目类型系统；资产库沉淀可复用工件。

**长期目标（用户设定，2026-09-05 更新，持续有效）**：
1. 持续调研同类开源项目优势，融合进项目，持续补齐短板与缺陷，直至满足工程管理落地标准；
2. **每一轮修剪 HANDOFF.md** 防止文档过大（详情真源=docs/10 §7 看板与附录 A/B）；
3. **每一轮只做改动相关的验证**（对应 test_*.py + build），**每 5 轮（≈每个里程碑正式审阅）做一次全局验证**；
4. 上下文超限自动压缩（本文件即压缩产物），每轮结束更新本文件。

**进度真源**：[docs/10-development-plan.md](docs/10-development-plan.md) §7 状态看板——发现任何文档与代码不一致，以看板为准并即时修正。

## 2. 已经完成什么（一行一里程碑，详情看 docs/10 看板行与附录 A）

- **MVP（I0-I13，2026-08-22 终验）**：FastAPI + 事件溯源内核（append-only events + @on 投影注册表 + rebuild）+ LangGraph Runtime（replay provider）+ 对话域 + 资产域 + NL 命令 + React 全套页面 + docker-compose。
- **M4~M7（I14-I25）**：本体构建闭环（learn 四规则 + 版本化 diff + CQ 检查）、LLM 辅助归纳 + 模板包、custom_fields 类型系统、模板中心。
- **M8~M11（I26-I37）**：network 双模认证 + 三角色写门禁、看板自动化规则（防循环双保险）、webhook + 站内通知中心、SMTP/Atom feed + 通知偏好。
- **M12~M16（I38-I52）**：纯投影报表、里程碑 + 时间线 Gantt-lite、依赖自动排期 + NDJSON 导入导出、PWA 响应式基座、自定义视图。
- **M17~M24（I53-I76，审阅全过）**：OIDC SSO（零依赖 RS256+PKCE+JIT）、评论域 + 订阅通知、工时跟踪报表、个人工时日历、时间线拖拽改期、评论 Markdown 渲染、依赖连线图内编辑、iCal 订阅、清单转子任务、全局搜索 FTS5、归档克隆、批量编辑、甘特基线、组合总览、MD 工具栏、子任务层级、CSV 导入导出、泳道避让 + 多基线。
- **M25~M33（I77-I103，审阅全过）**：基线偏差表、blocks 闭锁 + 关系可视化、列表分页、WIP 限制、评论修订史、状态流转白名单、lag 排期联动、跨项目路线图、里程碑燃尽、工时锁定审批、成员负载、打印视图、个人排期月历、卡片快捷编辑、运行报表、健康评分/趋势、评论引用、键盘快捷键、通知偏好细分、响应力指标、定时自动化 sweep、外部 intake 收件、列表分组、关键路径、子任务进度、工作项归档回收站。
- **M34~M37（I104-I115，审阅全过）**：工作日历跳休、到期提醒、基线 S 曲线（事件溯源红利第六例）、IMAP 邮件转任务、常用回复、引用快捷键、主题 `[项目名]` 路由、回复转评论、Atom 动态流。
- **M38~M43（I116-I133，审阅全过，详情=docs/10 §M38-§M43 与看板行）**：多级加权 rollup（vitest+5）、休假代理转派、超载标记、Cycles 周期 + 结转、退信静默 + 邮件过滤、完成日预测（红利第八例）、时薪成本预算、附件域、跨项目依赖图、周期燃尽 burnup、审批超时提醒 + 升级链、审计 CSV 导出、看板阻塞徽标、速率对比卡、风险登记册、项目收尾清单、完成自动重建 respawn。**基线演进：pytest 277→328，冒烟 43→49。**
- **M44 真实 LLM 接入（I134-I136，2026-09-15 完成，docs/10 §M44）**：AnthropicCompat/OpenAI Provider 真实化 + `GET /api/system/llm`/ping 观测面 + run.tokens_recorded 落账 + NL 命令层 L2（`_normalize_llm_actions` 白名单 + parser 溯源 + 冒烟 50）+ 浏览器真实复演（glm-5.3）。
- **M45 安全加固与性能/显示优化（I137，2026-09-19 完成，用户指令轮；详情=docs/10 §M45 与附录 A）**：双代理全库审计收口——后端高危×6（匿名不继承管理员/feed_key/导入穿越/git 前缀绕过/rebuild 门禁/SSRF）+ 中低危一批；前端裸 fetch 收口/补 catch/href 转义/备忘化/渲染缓存/失效收敛/三态。
- **M46~M48（I138-I146，审阅全过，docs/01 §AQ-§AS + docs/10 §M46-§M48）**：LLM 流式输出（`run.token_delta` 瞬态广播零落库+逐字渲染）、多币种轻量版（`APM_FX_RATES` 手工汇率表+折算披露）、深色模式（Tailwind v4 `@theme` 变量双通道+ThemeToggle 三态）、上下文压缩（读路径字符预算+fold_constraints+summarize 角色）、单元成本行项（expense 域+cost-report 双轨）、跨项目依赖（403 门禁+**修 propagate_reschedule 跨项目归因缺陷**+🔒 占位节点）、模型三档+cascade 降级（显式 name 不参与）、周期回顾包（retrospective 端点+抽屉）、并发治理（per-conversation 锁+_active_runs 终态 pop+**gitrepo per-project 写锁修并行 run 竞争**+看板列渐进渲染）。基线演进：pytest 360→387，冒烟 51→53。
- **M49 闭环与表达三件套（I147-I149，2026-09-21 完成，docs/01 §AT + docs/10 §M49）**：I147 回顾行动项落地（`POST /cycles/{id}/action-items` 走 create_item 全校验链+`retro_of` 审计链+同名幂等+上届带出）+ I148 状态报告自动生成（汇编 Markdown 工件入 git+可选 AI 摘要降级）+ I149 关系类型扩展（duplicates/includes 标注型+图表色 token 化）。基线 pytest 394 / 冒烟 54。
- **M50 周期性自动状态报告（I150-I152，2026-09-21 完成，docs/01 §AU + docs/10 §M50）**：sweep 第七员 `_report_status_weekly`（ISO 周一 `weekly_report_day` 可关；payload source/week 心跳幂等零新表；`reported` 计数）+ 汇编核三层重构（手动端点不变）+ owner 通知 `report_weekly`[白名单第八员] + `GET /projects/{id}/reports` 列表 + ReportsPage 最近报告卡抽屉预览 + 环比分区[首期诚实标注]。基线 pytest 405 / 冒烟 55。
- **M51 周报深化与分发三件套（I153-I155，2026-09-21 完成，docs/01 §AV + docs/10 §M51）**：I153 评论语料段+AI 叙事开关（`_activity_lines` 确定语料层[近 7 天评论按项分组+独立 COUNT 溢出行] + `weekly_report_ai` 默认关[失败降级]）+ I154 digest 邮件（notification.sent payload 加 `digest` 字段+mailer body 分支——正文自含结论；**调研修正候选池假设：M11 分发通道早已通，增量只在正文**）+ I155 冒烟 56。基线 pytest 410 / 冒烟 56。
- **M52 周报分发完备三件套（I156-I158，2026-09-21 完成，docs/01 §AW + docs/10 §M52）**：I156 周报 Markdown 附件（payload 加 path/week + `_send` 工作线程 gitrepo 读工件 add_attachment[bytes 乱码→str+charset utf-8；multipart 后测试 stub 改 get_body；读失败降级]；服务端 PDF 裁决不引入）+ I157 周报订阅制（事件对+report_subscribers 投影+三端点成员门+sweep 收件人 owner∪订阅者去重+前端开关）。基线 pytest 416 / 冒烟 57。
- **M53 分发呈现与资源面三件套（I159-I161，2026-09-21 完成，docs/01 §AX + docs/10 §M53）**：I159 digest 邮件 HTML part（`_digest_html()` 纯函数[table+内联样式+三色徽标+单 CTA 链 `web_base_url`] + `add_alternative`[alternative 必须先于 attachment；双重降级纯文本]）+ I160 跨周资源热力（workload `weeks` 两桶 ISO 锚定+estimate 求和+桶级 on_leave 整周标灰——OpenProject 17.7 轻量裁决：只做读视图不做分配层）+ I161 冒烟 58 + 修 smoke_53 日期敏感。基线 pytest 420 / 冒烟 58。
- **M54 自定义关注三件套（I162-I164，2026-09-21 完成，docs/01 §AY + docs/10 §M54）**：I162 watch 规则域（新域 watch.py：`人×项目×事件类型` 用户自建通知规则[白名单 13 类排除通知机制自身防递归 + 事件对+投影 rebuild 复现 + 三端点 own-data+成员门 + post-emit hook→notification.sent kind=watch：自事件抑制/多规则单份]）+ I163 偏好门+前端（NOTIFY_KINDS 第九员 `watch` + 铃铛偏好浮层管理区）+ I164 冒烟 59 + 修 test_retrospective 日期敏感（同族第三例）。基线 pytest 426 / 冒烟 59。
- **M55~M57（I165-I173，2026-09-21/27 完成，docs/01 §AZ-§BB + docs/10 §M55-§M57）**：watch 条件化（condition_json 全等匹配·红利第九例）+ 铃铛降噪折叠 + watch 导入导出 + 静默时段（跨午夜+mailer 第四道门）+ watch 规则编辑暂停（修 M55 的 409 删了重加坑）+ 资产使用洞察（红利第十例）。基线 pytest 437 / 冒烟 62。
- **M58~M62（I174-I188，2026-09-27 完成，docs/01 §BC-§BG + docs/10 §M58-§M62）**：run 生命周期入 watch 白名单 + 通知直达 + 「等待我」行动聚合 + 模板包实例溯源 + 备份/恢复演练工具（sqlite3 backup API——「备份会自己跑，演练是为了证明恢复仍然有效」）+ 组合健康趋势与流指标（红利第十二例）+ 事件表体积观测（先测后治）+ 会话搜索与导出（**红利第十三例**）+ 移动端 375px 审计 + 端点性能观测（**索引审计补 idx_watch_rules_hit**）+ watch 渠道偏好（永不越过 DND）+ Agent 用量聚合（**红利第十四例**）。基线 pytest 466 / 冒烟 67。
- **M63~M65（I189-I197，2026-09-27/28 完成，docs/01 §BH-§BJ + docs/10 §M63-§M65）**：自动化 run_agent（第七动作·**防环三闸**）+ 项目级通知降级 + 工作项检查清单 + run 重试对比（**红利第十五例**）+ ⌘K palette 深化 + 清单转子任务 + 运行分叉（forked_from 血缘）+ lineage 树感知 + 看板泳道 + 基线对比（**修快照语义：归档项不入新基线**）。
- **M66~M79（I198-I239，2026-09-28/10-01 完成，docs/01 §BK-§BX + docs/10 §M66-§M79）**：对话树导航（**parent_conversation_id 自 MVP 有存储无写入方——补 Branch in new chat 写入面**）+ PAT 机器接入（display-once+Bearer 旁路）+ run 成本预算护栏（硬顶 402/软阈 80%）+ 概念级可见性（两级声明+读写通知三门）+ ntfy 推送通道（mailer 镜像+SSRF 门复用+通道矩阵第三列）+ Prometheus 出站（**红利十六：events 账本出站只是读侧**）+ 项目级角色指令层（prompt_layers L1.5——**AGENTS.md 嵌套语义深层优先**）+ 运行产物自动沉淀（**git blob sha 去重·评审门不绕过止步 draft**）+ 报告模板定制（段落开关+自定义标题·手动与周报同源）+ 看板运行实时徽章（**SSE 直驱 overlay·run.requested 是 run→item 绑定唯一机会**）+ 指令模板库（**`.prompt.md` 语义·草稿非快捷键人审不绕过**）+ run 产物回流工作项（**write-back to issue 正统·同步 hook 第六员·同 run 幂等**）+ 资产版本历史与 diff（**append-only 恢复·半截链第二例**）+ 项目设置中心（**混合 IA hub·原页零改动**）+ run 发起工件绑定面（**一次性语义·半截链第三例**）+ 工件内容全文搜索（**第四类 FTS·连字符 token 双引号坑**）+ 工件预览通用入口（**Cloudscape inline preview 三触点·半截链第四例**）+ 指令模板导入导出（**watch 对称面 JSON·重名永不 clobber**）+ 工件读写权限门（**repo 级继承成员制·M45 盲区补课[content/ 端点]**）+ 工件清单页+删除（**半截链第五例收口·git rm·git 历史即软删**）+ 工件包导出（**git archive 锚定 commit·审计事件**）+ run 发起指令回显（**半截链第六例**）+ 工件项运行历史（**半截链第七例·GitHub issue 盲区补位**）+ 角色选择器（**opt-in 与 I212/I219 并排一次性三件套**）+ 费用记账面（**反向半截链第八例：I142 报表读 expense_entries 在·记账端零 UI——CostCard 表单+🗑·后端零改动**）+ 里程碑管理面（**TimelinePage 浮层就近 CRUD·三个零消费函数接线·后端零改动**）+ list 视图运行徽章（**I207 收尾·board+list 两视图可见性一致**）+ 资产退役与归档（**半截链第九例：deprecated/archived 投影就绪零发射方——POST deprecate/archive+抽屉处置卡·payload 必带 status/tags·重复动作 409**）+ 视图改名+周期取消（**patchView/cancelCycle 接线·取消即退场·后端零改动**）+ 审计与复演轮（**读面门禁对齐 API1 BOLA：require_instance_user org 登录门[assets/template_packs]+项目 _gate[expense/automations]·EXPLAIN 对账四热查询全命中不加索引·perf 实测热读毫秒级·E2E 复演发现 asset_review 门 UI 不可达→就近批准修复**）+ 交付面与新面可达轮（**README v0.5 锚点化：数字全移除进度真源指向看板·check_env_doc.py 对账脚本先红后绿自证·env 补 4 键+compose 透传·375px 走查修 SettingsPage 两处挤压·冒烟 82 防腐锁**）+ 交互完备性深审轮（**依赖关系解除面：DELETE /items/{id}/relations 复合键+任一侧可解+from 侧写门禁+item.relation_removed 事件——半截链第十一例变体「创建面在·解除面从未设计」收口·QuickEditModal 关系区[方向标签+✕ 后果说明确认+表单建立=WCAG 2.5.7 非拖拽替代]·日期不动：移除约束≠重排；触屏补课：时间线 link 触点 <768px 恒可见[touch-action 祖先链相交·缺的只是可见性]+SchedulePage 两段点选[preventDefault 抑制合成 mouse]；分叉合并采纳面正式关闭[四轮降级零翻案]；附录 C 清账[M38 已消化补记/M41 条件未触发]**）+ 跨项目依赖面收口轮（**/deps 依赖图跨项目收口：外部依赖占位节点[可读显真名+来源项目名·不可读 🔒——与 graph 端点 M47 语义归一·终结两图分叉]+blocked 口径修正[跨项目可读上游计入对齐看板 I128]**；**建链二级选择器：项目 select+目标 lazy+跨项目 toast+外部项标题解析——零后端改动**；冒烟 84 跨项目链 roundtrip+源码锁；附录 C 登记 graph 端点入边不对称）。基线 pytest 555 / 冒烟 86[84 文件] / vitest 30。

## 3. 现在卡在哪

**没有硬阻塞。** 真实 LLM 路径已可用：复制 `.env.example` 为 `.env` 填 `APM_LLM_API_KEY` 即 `APM_PROVIDER_MODE=openai` 跑真实模型（本机 ZCode 配置含 BigModel coding-plan key，运行时注入、不进仓库）。遗留 B/C 级意见见 docs/10 附录 B/C。

## 4. 下一步是什么（按序）

1. ~~M24~M65 全闭环~~ ✅（审阅提交号索引=docs/10 附录 B；单迭代详情真源=docs/10 §7 看板行与附录 A/B）。
2. **M80 全局质量轮·写门对齐（下一步，调研已定案 7cbc35b）**：docs/01 §BY + docs/10 §M80（I240-I242）。**定案依据（grep 实证四件）**：assets 写端点六写全裸（post/submit_review/deprecate/archive/restore/link——中间件白名单不含 /api/assets/*·M76 只补读面）；cycles/milestones/features/risks 四域 id-path 写端点零门禁（views 内联门作对照）；POST /runs、POST /conversations 无 /{id} 段不匹配白名单；白名单 allow-if-matched 新域从未回补。**执行序**：I240 写门对齐（四域 PATCH/DELETE 域内挂项目成员门[items require_visible_item 同款] + assets 六写分门[deprecate/archive/restore/submit_review/link=require_instance_user·post_asset=from 侧项目成员门] + runs/conversations 入口核验 + tools/check_write_gates.py[遍历 app.routes 非 GET·显式已审清单外即非零退出] + 矩阵测试[非成员 403/成员 200/local 可信]）→ I241 校验抽查+E2E 复演（隔离环境 CUA 走 M77~M79 新面全旅程·发现即修）→ I242 冒烟 85（对账脚本入冒烟含故意红自证）+ 附录 C + 全量回归 + M80 审阅。测试参照：test_read_gates（M76 矩阵惯例）、test_relation_removal（M78 写门测试惯例）。
3. 每轮纪律不变：演示/审阅隔离 data+ontologies 且 netstat 确认单监听（**preview 必须显式从 web/ 起**；**8000 常被本机其他项目占用——vite 代理 target 临时改走查端口，走查完 `git checkout` 还原，绝不带补丁提交**）；**复演造数脚本失败后必须清理半成品数据再重跑**；**复演假阴性先核对输入（ID/造数/SW 旧缓存）再怀疑系统**；中文文档/源码/测试一律 Edit/Write 工具（**heredoc 彻底禁止**——M56 再证：python 脚本改 db.py 整文件 CRLF→LF 造 353 行假 diff）；**commit message 反引号用单引号包裹**；python 写文本 newline="\n"；**每段式提交前 `git status` 核对源码文件齐全**；**HANDOFF 每轮收口时修剪**；**复演造数含中文 JSON 用 python urllib 不用 curl**；**切身份后必须恢复 settings.user_id**（M58 冒烟再证：run.failed 规则误在 u_admin 身份下添加→通知落 admin·关注者轮询空列表超时）；**docs/10 追加表格行的 Edit：old_string 用行首片段锚定、new_string 必须以原文行开头再接新行**；**本地模式 _visible 第三分支使配置用户天然全可见——可见性测试须显式切 network 模式**（M60 再证）；**追加看板行后 grep 行标题计数核对**（M78 发现 M77 收口造出过全同重复行）。

## 5. 有哪些坑不要再踩

- **投影器 INSERT 的列序与参数元组必须逐列目视核对**（I20）。**单用例可能过、套跑才炸，别信单绿**。
- **起服务做演示/审阅必须同时隔离 data 与 ontologies**：env `APM_DATA_DIR` + `APM_ONTOLOGY_DIR_OVERRIDE`（还要 `cp -r ontologies/. <override目录>/`）；**只设 APM_DATA_DIR 不够**（M4 审阅污染源文件事故）。
- **replay_templates.py 模板函数必须定义在 `_TEMPLATES` 字典之前**（import 时求值）。
- **测试/冒烟绝不写真实 `ontologies/` 源目录**：用 conftest `isolated_ontologies`；改本体相关代码要 `reload_all()`。
- **diff 的 from/to 语义不对称**（I15）：from 快照优先、to=当前永远读活文件。
- **前端是 HashRouter**：直接导航要用 `/#/p/{pid}/board`；同 hash URL 不重载 SPA → location.reload() 强刷。
- **run 由后台线程执行，"interrupted"=挂在 Gate**；注入=对话内发消息；恢复=▸ 继续。参考 `app/tests/test_runtime.py`。
- **演示环境 console 会有 404/连接拒绝噪声**：长命标签页跨隔离库轮询——逐条核对来源再下结论。
- **items 投影对 custom_fields 是整列覆盖**：任何「改一个字段」的路径必须合并现值后再发 item.updated。
- **投影器新生成实体的 id 禁止随机**（I34）：必须由事件流确定性导出；单测 rebuild 断言直接对比。
- **/api/session/identity 直接改全局 settings.user_id**（local 模式）：切换后不恢复，下个测试的 `ensure_default_user` 会把该用户**提升为管理员**（is_admin=1 UPDATE 按 settings.user_id）——切身份测试一律带 `_restore_identity` fixture（M44 再证）。
- **改源码一律用 Edit 工具，禁 heredoc/python 脚本**；**python 写文本必须 `newline="\n"`**（Windows CRLF 噪声）；中文段落一律 Edit 工具。
- **commit 纪律**：迭代号前缀；冒烟基线只增不减；docs/10 的 Edit 锚点务必唯一定位。小本体主义硬约束（概念 ≤12、字段 ≤10、关系 ≤6）；别引入 RDF/SPARQL/推理机。
- **Windows 允许多进程同时 LISTEN 同一端口**：起演示先 `netstat -ano | grep :8000` 确认单监听。
- **本机 5173 被用户另一项目占用**：`pnpm dev` 自动落到 5174——复演前从 dev server 日志确认实际端口，别假设 5173。
- **TestClient 默认 follow_redirects=True**：302 断言须 `follow_redirects=False`。
- **改前端后生产构建页面须 SW update+reload 才见新 UI**（autoUpdate precache 旧 bundle）。
- **浏览器 IAB 合成键盘/locator 点击对自定义组件可能 actionability 超时**：先用 CUA 坐标点击（从最新截图取整像素），打字前先点输入框确保焦点；M44 复演两种情况都遇到。
- **auto_scheduled 只认 PATCH 开关**（M14 语义）：create 载荷传 True 静默不持久化。
- **pnpm 命令注意 cwd**：后台起 preview 前确认在 web/ 目录。
- **task 状态集无 todo**（software-dev task）：open/ready/in_progress/awaiting_review/done/cancelled，测试用 ready。
- **功能提升使旧测试前提失效属正常演进**（I78）：换仍未注册的触发器保持断言强度，不是放宽断言。
- **推理模型走真实 provider 必须给宽松 max_tokens**（M44）：GLM-5.x thinking 先吃预算，4096 会让长工件空返回；错误信息已自带「提高 APM_LLM_MAX_TOKENS」指路。
- **演示密钥注入**：`export APM_LLM_API_KEY="$(python -c ...)"` 运行时读本机 ZCode 配置，永不 echo、不进仓库（.gitignore 第 24 行 `.env`）。
- **日期敏感测试教训（M45/smoke_45）**：凡用 `today - N` 造历史数据的测试，先问「N 在任意星期几下语义是否一致」——forecast 只认「完全落入历史的完整周」，`today-17` 只在周一~周四成立；锚点一律按周对齐（`this_monday - N`）。**基线全绿的证明力受验证日期约束，周五跑一次全量是便宜的保险**。
- **webhook 测试必须显式开 `APM_WEBHOOK_ALLOW_PRIVATE`（M45）**：SSRF 防护默认拒环回/私网，接收器跑 127.0.0.1 的套件要 monkeypatch `config.settings.webhook_allow_private=True`（test_webhooks autouse 已带）。
- **前端「稳定函数引用」用 useCallback 而非 useMemo（M45）**：useMemo 工厂被当 predicate 传入时缓存的是布尔返回值，`filter(matches)` 直接类型爆炸——tsc 会当场揭穿，但要第一遍就写对。
- **流式的 Event-Sourcing 纪律（M46-I138）**：token 增量走 `event_bus.publish`（瞬态），**绝不 events.emit**——逐 token 入库会造数千事件/run；完整文本仍是 message.created 唯一真相。engine 的 provider stub 测试若签名不带 `on_delta`，mode 设为 replay 或加 `**kwargs`（streaming 分支只在 mode∈(openai,record) 时传回调）。
- **Tailwind v4 主题换肤（M46-I140）**：`@theme` 变量就是普通 CSS 自定义属性，`html.theme-dark`/media 下重写 `--color-*` 即全局换肤，无需 dark: 前缀；两组暗变量（media 块与 .theme-dark 类）必须同步维护；手动切换的 localStorage 键 `apm-theme` 与 index.html 引导脚本类名 `theme-dark`/`theme-light` 三处（css/html/AppShell）必须一致。
- **httpx 流式测试**：MockTransport 配 `client.stream()` 官方高层 API 可用；手写 `client.send(request, stream=True)` 的 Response 上下文管理器在 mock 下会炸（'Response' object does not support the context manager protocol）。
- **排期测试日期必须锚周一网格（M47 再证）**：`_day(offset)` 锚下一个周一——任意日期会撞周末被 advance_to_workday 吞掉；且 I44 传播语义是「**移动**才传播」——上游首次设 due（old=None）不触发，必须先设旧值再改。
- **跨项目链上事件归属（M47-I143）**：关系/传播沿链触达别的项目时，emit 的 project_id 用**被操作项自己的项目**（原 propagate_reschedule 记调用者项目，同项目场景二者相同故潜伏 M14 以来）。
- **pytest 全量已超 10 分钟**（360+ 项）：后台命令 timeout 上限 600s 会把进程杀掉（退出码 1 + 日志截断的假失败）——用 `--ignore=tests/smoke` 分片跑 pytest + 冒烟 runner 对账。
- **裸调 `projections.rebuild()` 会连 users 投影一起清掉**（M61-I183）：admin 身份随投影消失→后续 admin 门 403——测试里重建走 `POST /api/system/rebuild-projections`（端点内部 ensure_default_user 恢复引导管理员）。
- **network 模式测试身份必须走 `POST /auth/login`**（M61-I184 再证）：`/api/session/identity` 是 local-mode only（422），network 下 effective_actor 无会话即 "anonymous"（403/404 会「意外通过」其实身份根本没建立）——造用户带 password + admin_password 先设再 ensure_default_user。
- **后台命令 cwd 会漂移**（M61-I185）：run_in_background 的 shell 工作目录不保证在 repo 根，`cd app` 相对路径静默失败致回归空跑（exit 0 假绿）——后台命令一律绝对路径 `cd /d/project/agent-project-management/app`，完成后核对日志里的 passed 数。
- **pytest -q 的进度点会被测试自身输出污染**（M62-I188）：`grep` 点数统计会虚高（399 项数出 408 点）——计数以 `--collect-only` 与 EXIT 码为准，点数只看有没有 F/E 混入。
- **合成 run 事件必须带 conversation_id**（M62-I188）：runs 投影该列 NOT NULL——`run.requested` payload 缺键会 IntegrityError；token 账走 `run.tokens_recorded`（payload 可带 estimated_cost_usd，replay 诚实零）。
- **upsert 加列时 VALUES 占位符逐列重数**（M62-I187）：watch.updated 整行 upsert 加 channels 列后少写一个 `?` 报 "6 values for 7 columns"——列数与占位符必须目视逐一对账（I20 纪律的变体）。
- **日期敏感测试的锚点必须与被测窗口同一时钟源**（M63-I191 再证，§4 纪律升级）：workload 桶锚 `reports._now()`=UTC，测试造数用 `date.today()`=本地——本地已跨日（9-28 周一 00:31 本地=9-27 周日 UTC）时 local monday+8 落出 UTC 的 14 天窗→两桶皆 0 假红。修法=造数也从服务端时钟取锚（`from apm.domains.reports import _now`）。
- **GET /notifications 列表含历史已读行**（M63-I190）：断言通知增量须过滤 `read` 或先 `POST /notifications/read {"all":true}` 清基线，否则基线行混入假阳。
- **角色 id 是 `-agent` 后缀**（M63-I189）：写自动化/规则测试前先查 `agents/roles/*.yaml`（planner-agent/dev-agent/qa-agent…）——凭印象写 "planner" 会 422 假红。
- **pydantic 输入模型丢未知键**（M64-I194）：ChecklistItemIn 无 extracted 字段时客户端回显的标记被静默剥掉（整列覆盖语义下=标记丢失）——全量提交的载荷模型必须含全部往返字段。
- **造数 span 事件是 `run.span_opened`/`run.span_closed`**（M64-I192）：不存在 span.started/ended——合成轨迹前先 grep 投影器的事件名。
- **满载回归中的单点瞬态假红**（M64）：test_pm_agent_run_to_gate_approval 曾报 running≠awaiting_review——emit 在全局 db 锁下事件序一致，单测与复跑全绿即负载时序抖动；复跑确认为准，非回归不追改生产码。
- **合成 run+fork 时 run_id 由调用方先铸**（M65-I195）：fork 端点必须先发 run.forked 血缘再 start_run(run_id=...)——start_run 新增 run_id 可选参数；次序反了树回溯会漏支线。
- **sqlite Row 的 keys 就是 SELECT 列**（M65-I195）：SELECT 漏列后 row["event_type"] 报 IndexError——遍历 rows 前核对 SELECT 清单。
- **快照/导出类查询要跟删除语义对齐**（M65-I197）：M24 基线快照曾把归档项照入快照（先于 M33 归档语义）——新增软删除类状态后，所有旧的全量查询都要回头核对是否需要排除。
- **树/计类断言要算上项目 bootstrap 自带会话**（M66-I198）：建项目即产生一个 drafting 会话——`/conversations/tree` 的 roots/total 断言要 +1，否则 5≠4 假红。
- **rebuild 清 users 投影后只恢复引导管理员**（M66-I199 再证）：凭据不进事件流，POST /users 造的用户随 rebuild 消失——网络模式测试的会话操作（建 token/吊销/读卡）必须排在 rebuild 之前，rebuild 用 u_admin+admin_password 登录执行。
- **session cookie 会掩护 Bearer 断言**（M66-I199）：auth_gate 里 session 优先、无会话才看 Bearer——登出前用 Bearer 头发请求会因 cookie 命中而 200，401 断言前必须先 POST /auth/logout。
- **PATCH 的 changes 过滤 None**（M66-I200）：`{k: v for k, v in body... if v is not None}` 无法把数值档位清成 NULL——「0=关闭」是既定语义，新档位字段照此办。
- **第三方产品名常与 id 后缀不符、端点序常有 DESC**（M66 汇总重申）：写测试前 grep 注册表/投影器与既有断言方向，勿凭记忆。
- **`item.assigned` 只在 PATCH 指派时发射**（M67-I202）：create 载荷带 assignee 不发事件——造「指派」链路必须 create 后 PATCH；同理 watch 路由测试要换 actor（**M54 自事件抑制**会吞掉规则主人自己触发的变更）。
- **后台投递线程的事件落库晚于 HTTP 返回**（M67-I202）：mailer/pusher 的 `_send` 成功后才 emit 投递事实——接收器收到请求≠事件已入流，断言事件行要轮询（`_wait_for` 同款）。
- **物理出站通道一律复用 `webhooks._validate_url`**（M67-I202）：push_url 等用户可控的服务端出站目标与 webhook 同受 SSRF 门管（`APM_WEBHOOK_ALLOW_PRIVATE=1` 收内网自托管 ntfy）；新出站面勿自行放宽。
- **整文件重写会把 CRLF 源码拍平成 LF 造全文件假 diff**（M67-I201 再证）：python `open(newline="\n")` 重写源码文件=每一行都进 diff——追加/小改一律 Edit 工具；已发生时按原行尾恢复后 `git commit --amend` 收敛历史。
- **project.updated 投影器加新键要动两处**（M68-I206）：`_proj_project_updated` 的 keys 元组（漏加=事件带了键但投影静默不落列）与 isinstance-dict→json.dumps 特例清单——PATCH 200 ≠ 落库，加键后必须 GET 回读验证。
- **ontology `deposits_to` 指资产 kind 而非 library**（M68-I205）：解析链是 artifact kind → deposits_to 资产 kind → accepts 它的 library，直接把 deposits_to 当 library 会 422。
- **assetsrepo.read_asset_body 会 strip 正文**（M68-I205）：内容指纹比较两侧都要 `.strip()` 归一化，否则同一内容哈希不同、去重失效。
- **build_context 的合并全文键是 `merged_preview`**（M68-I204）：断言 L1.5 段落时别用 `merged`。
- **投影器签名是 `handler(conn, e)` 双参且 Event 是对象非 dict**（M69-I208 两连修）：新域写投影器照 watch.py 惯例（`e.payload`/`e.agg_id`/`e.project_id`/`e.ts` 属性访问），凭 dict 下标写会在首次事件时 TypeError。
- **runs 列表端点是 `/runs?project_id=` 不是 `/projects/{pid}/runs`**（M69-I209 再证）：端点序/路径勿凭印象，写测试前 grep `@router.get`。
- **post-emit hook 与 rebuild 的边界**（M69-I209）：hook 只在运行时 emit 触发，rebuild 走 projections.apply 不重触发——运行时产生的衍生事件（回流评论）已在流中，重放原样恢复不会重复；hook 内的查重是防运行时双发的第二道保险。
- **资产在独立 assets repo，gitrepo.diff/file_history 是项目 repo 侧不能直接用**（M70-I210）：资产历史/_diff 走 assetsrepo 自己的 asset_log/asset_diff（镜像惯例但 cwd=assets repo）。
- **restore 类端点返回详情形状**（M70-I210）：get_asset 不含 content 键（只有 get_asset_detail 加）——端点返回什么形状测试才能断言什么键。
- **设置中心类 hub 页零回归的做法**（M70-I211）：原页面板一行不动，hub 内联实现简单项（开关/数字 PATCH）+复杂项深链原页锚点——混合 IA 的「场景控制留原地」本就是共识语义。
- **FTS5 MATCH 的 latin token 必须双引号包裹**（M71-I213）：_bigrams 保留连字符词[feature-auth]，裸传 MATCH 时 `-` 被解析为 NOT 语法报「no such column: auth」——查询侧用 _match_expr 逐 token 加引号；既有三类分支未动（防回归），新面一律走 _match_expr。
- **JS 没有 rsplit**（M71-I214）：`path.rsplit("/",1)` 是 Python——前端取尾段用 `path.split("/").pop()`；tsc 不会提示不存在的 Python 方法会直接编译错，但要在第一遍就写对。
- **导入类端点永不 clobber + 计数报告**（M71-I215 重申 M56 语义）：同 title/同键已存在=skipped 跳过，坏行 422 带索引（templates[i]），导入走与手工创建同一条代码路径（提取 _create_row）保证不可区分。
- **FastAPI 注册序：字面量路由必须在 {param:path} 之前**（M72-I218）：GET /artifacts/{rel_path:path} 会吞掉 /artifacts/export（detail:"export" 404）——字面量端点写在前或用注释钉住顺序约束。
- **gitrepo._run 是 text=True**（M72-I218）：二进制输出（git archive zip）必须独立 subprocess binary capture，否则编码替换毁包。
- **content/ 下的端点也要过门禁**（M72-I216 再证 M45 盲区）：权限面检查要专门 grep content/ 目录——M45 双代理审计只扫了 domains/，工件四端点裸奔到 M72 才补门；新增端点无论住哪个目录一律挂门。
- **api.ts→前端镜像扫描要剔除类型行误报**（M74 调研）：`grep -oP '^\s{2}\K\w+(?=: \()'` 会把响应类型字面量的键（entries/overdue/items/approvals）一并抓出当函数——先读定义行分辨；「零消费函数」还要查同语义替代消费面（closeRisk 与 PATCH transition 重复=RisksPage 已有关闭按钮）再判缺口，勿直接开工。
- **历轮「正向半截链」的反向镜像同样成立**（M74 调研）：读侧齐全写侧 UI 缺失（I142 报表读 expense_entries 在·记账面零 UI）与展示有管理无（TimelinePage 里程碑行在·CRUD 零入口）都是真缺口；但「工作项发起运行」这类看似的缺口先查 orchestrator/scheduler.py 的既有指派驱动路径（batch_start 早已实现）——防重查第六/七例。
- **`pytest | tail -N` 管道既截断日志又掩盖真实退出码**（M74-I224）：管道退出码=tail 的（exit 0 伪绿），且 tail -N 只留最后 N 行（当时 passed 行都没进来）——全量验证一律 `> 文件 2>&1; echo EXIT=$?` 完整落文件再读。
- **.pytest_cache 的 lastfailed 保留「永不收集」的化石条目**（M74-I224 再证）：已删除/改名的测试条目永不被清除，缓存既不能证明也不能证伪某次运行——判定全量结果只认 pytest 自身退出码+passed 行。
- **资产退役端点发射 asset.deprecated 时 payload 必带 status 键**（M75-I225）：upsert 投影 `p.get("status", "draft")` 默认 draft——漏带则退了役还落 draft（superseded 投影能直接改列是因为它走专用 UPDATE 语句，通用 upsert 只认 payload）。
- **「产出物无建项目入口」先查 instantiate 类共链路**（M75 调研第八例）：模板包导入产物看着只能靠硬编码的 ProjectPicker 建项目，实际 TemplatesPage 的 instantiate 与 POST /projects 完全共链路（宪章/首特性/起草对话/内容仓 bootstrap）——评「入口缺失」前把同类面的替代消费路径全走一遍。
- **读侧语义断言前把 grep 到的过滤行读进完整函数体**（M75-I225 再证 M73 笔误教训）：assets.py 39 行的 `status in ("archived",)` 过滤属于 `_reindex`（FTS 维护）而非 get_asset——凭行号+关键词断言「详情 404」直接写出错误测试；「archived 过滤」真实住 _reindex 与 search 两处。
- **upsert 投影的 payload 漏键=静默清列**（M75-I225）：status 漏带落 draft、tags 漏带清空——通用 upsert 从 payload 取值而非保留旧值（superseded 走专用 UPDATE 才能免带）——给既有事件补发射方时 payload 键集必须对照投影消费清单。
- **assetsrepo.write_asset 的 commit 无 nothing-to-commit 容忍且失败 stderr 为空**（M75-I225）：git commit 的「nothing to commit」走 stdout——GitError 文本只有命令无原因；同内容二连写即炸。调试用内容哈希探针（临时 pytest 插件 print 每次写入的 sha1）定位重复写入。
- **api 级扫描之后还有事件级扫描，结论是「无死事件」**（M76 调研第九例变体）：131 发射 vs 119 @on 的 25 个差集全部有活消费（幂等 SELECT FROM events/血缘遍历/写 guard 白名单/审计显示）——投影缺失≠消费缺失，事件流本身即读侧；「扫描出差集」不等于「发现缺口」，差集要逐个找消费方。
- **读面开放是 M8 起的惯性而非决定**（M76 审计种子）：auth_gate「GET 保持开放」把读门下放域内——items/comments/artifacts(M72) 有 _gate 而 assets/expense/automations/template_packs 没有；补门时 org 域（资产/模板包）用登录门（实例成员可读）而非项目成员制，且 **feed_key 等既有匿名裁决面不要误伤**。
- **org 级审批门挂 project_id="" 就进不了项目审批面**（M76-I230 E2E 发现）：asset_review 门在 ApprovalsPage（按 pid 过滤）与「待我审批」跳转后都不可见——资产永久卡 in_review。修法=处置动作长在资产上（AssetActionsCard 拉 pending 审批按 payload_snapshot.asset_id 匹配就近渲染批准/拒绝）——**org 级门的 UI 出口必须在 org 级面**。
- **E2E 复演改前端后必须 SW update+清 caches+reload**（M76-I230 再证 §5 既有坑）：preview 服务的 precache SW 会喂旧 bundle——修复验证时浏览器先 `serviceWorker.getRegistrations→update + caches.keys→delete` 再看新 UI。
- **全量回归的管道纪律已固化**（M74-I224→M76 持续有效）：`pytest | tail` 掩盖退出码且截断日志——一律 `> 文件 2>&1; echo EXIT=$?`；判定只认 pytest 退出码+collect-only 计数（.pytest_cache lastfailed 有化石条目无证明力）。
- **README 的数字是漂移源**（M77 调研）：「冒烟 7 条」「I15 I16 进行中」冻结在 M4——写进 README 的任何会变化的数字都会腐烂；对策=README 只写不变事实（定位/架构/命令），动态数字一律指向 docs/10 §7 看板真源；「入口活正文死」（一行链到活文档但主叙述过时）是文档半截链的新形态。
- **env 面对账要全源码 grep 而非只查 config.py**（M77 调研）：config.py 字面只引 3 个 env，全源码 9 个——SMTP/OIDC/METRICS 在各自域文件里 `os.environ`/`settings` 引用；对账脚本必须扫 `app/apm` 全树。
- **交付面防腐已机械化**（M77-I233）：tools/check_env_doc.py 入冒烟 82（故意红自证路径在）——env 新增不进 .env.example/compose 会被锁住；README 数字断言防腐（「冒烟 7 条」类语句不得再现）——**新指标写 README 前先问「它会变吗」，会变就只写看板**。
- **tests/smoke 下测试文件相对 repo 根是 parents[3]**（M77-I233）：app/tests/smoke/x.py → parents[0]=smoke[1]=tests[2]=app[3]=repo 根；写文件路径断言前 print 一层确认。
- **成员角色枚举是 owner/contributor/viewer**（M78-I234 再证 M63 家族教训）：凭印象写 "editor" 422 假红——写成员相关测试前 grep members.py 的枚举。
- **network 模式身份必须真实登录且 cookie 会互相覆盖**（M78-I234 再证 M61 纪律）：TestClient 的 cookie jar 全局共享——中途切身份须重新 POST /auth/login（后登的会话顶掉先前的），不是改 settings.user_id。
- **touch-action 的有效值沿祖先链相交**（M78-I235）：父级 touch-none 已让子触点（resize/link 拖点）在触屏可用——hover-only 类触屏死路的真实缺口往往只是**可见性**（opacity-0 group-hover），修 visibility 不必重写事件层；W3C Pointer Events 明文「hover 显隐与无 hover 设备不兼容」。
- **触屏分支要 preventDefault 抑制合成 mouse 序列**（M78-I235）：pointerdown(pointerType=touch) 处理后，浏览器还会补发 mousedown/mouseup——不抑制会与既有鼠标 handler 双触发；配 touch-manipulation 防双击缩放干扰两段点选。
- **vite dev/preview 代理 target 硬编码 localhost:8000**（M78 走查）：8000 常被本机其他项目长驻占用（CareThread 实证）——走查时临时 patch target 到隔离端口、`git checkout vite.config.ts` 还原；netstat 核对来源时 `curl /docs` 看 title 别误杀别人的进程。
- **TaskStop 杀不掉后台 vite 的 node 子进程**（M79 走查再证）：Windows 下后台 bash 被停后 vite node 进程残留继续 LISTEN（4173 占用 500 假象——新 preview 落到 4175 而浏览器还连 4173 旧实例[代理指向已死后端→全 500]）——走查前 netstat 核对端口归属+curl 验证代理连通，残留 node 按端口 PID taskkill（4174 是 docker.backend 勿杀）。
- **「占位节点在」≠「双向都有」**（M79-I239）：graph 端点只扫本侧 relations[from 侧]——「别人依赖我」的入边 GraphView 不显示；评两图语义分叉前把端点的 SQL 范围读进完整函数体（I225/M75 教训的端点版）。

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 555 项，应全绿（>10 分钟：后台跑会被超时杀，用 --ignore=tests/smoke 分片 + 冒烟 runner 对账；完整日志落文件+EXIT=$? 勿用管道 tail）
python tools/smoke/run_smoke.py       # 冒烟基线 86 例（84 文件·smoke 83/84 双用例），应 GREEN（repo 根目录跑）
python tools/check_env_doc.py         # env 文档对账，应 ✓（冒烟 82 已锁）
cd web && pnpm vitest run             # 前端单测 30 项；pnpm build 须绿
# 真实 LLM（先复制 .env.example 为 .env 填 key）
cd app && APM_PROVIDER_MODE=openai python -m uvicorn apm.main:app --port 8000
# 后端（演示/审阅时必须隔离：APM_DATA_DIR + APM_ONTOLOGY_DIR_OVERRIDE 且拷贝本体进去！）
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`；域 `app/apm/domains/`；LLM Provider `app/apm/runtime/provider.py`（replay/openai/anthropic/record 四实现 + `LLMError`）；NL 命令层 `app/apm/domains/nl.py`（L1 规则 + L2 `parse_llm`/`_normalize_llm_actions`）；本体 `ontology*.py`；前端 `web/src/pages/` + `web/src/components/`（AppShell 模型徽标/CommandBar L2 徽标）。
