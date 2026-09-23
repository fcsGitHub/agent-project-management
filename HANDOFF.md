# HANDOFF —— 写给下一个新会话（2026-09-21 更新 · M55 调研定义完成，下一步迭代 I165）

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
- **M54 自定义关注三件套（I162-I164，2026-09-21 完成，docs/01 §AY + docs/10 §M54）**：**I162 watch 规则域**——新域 watch.py：`人×项目×事件类型` 用户自建通知规则（WATCHABLE_EVENTS 白名单 13 类[排除 notification.sent/email.*/watch.* 防递归] + `watch.added/removed` 事件+投影表 rebuild 复现 + 三端点 own-data+成员门 + `install_watcher` post-emit hook[命中→notification.sent kind=watch；自事件抑制；多规则单份]——规则=数据不是代码）。**I163 偏好门+前端**——NOTIFY_KINDS 第九员 `watch`（「发给谁」由 watch、「怎么发」由 I96 偏好）+ 铃铛偏好浮层关注规则管理区。**I164 冒烟 59**（watch→双通道→偏好关断→删规则 roundtrip）+ **修 test_retrospective 日期敏感**[smoke_45/53 同族第三例：本地 end_date vs UTC 事件 ts 跨翻转点——修复模式 end=_d(0)]。**当前验证基线：pytest 426 全绿（非 smoke 367 EXIT=0 + smoke runner 59 GREEN 对账）；冒烟 59 条 GREEN；vitest 14/build 绿。**

## 3. 现在卡在哪

**没有硬阻塞。** 真实 LLM 路径已可用：复制 `.env.example` 为 `.env` 填 `APM_LLM_API_KEY` 即 `APM_PROVIDER_MODE=openai` 跑真实模型（本机 ZCode 配置含 BigModel coding-plan key，运行时注入、不进仓库）。遗留 B/C 级意见见 docs/10 附录 B/C。

## 4. 下一步是什么（按序）

1. ~~M24~M54 全闭环~~ ✅（审阅提交号索引=docs/10 附录 B；单迭代详情真源=docs/10 §7 看板行与附录 A/B）。
2. **M55 关注精修与降噪三件套（进行中，调研定义已提交）**：docs/01 §AZ + docs/10 §M55 已落（三路调研：Jira/GitHub 原生无 payload 条件——AgentPM 结构化事件原生支持[红利第九例]；降噪=源头条件+展示层 bundling 两层，定时窗口 digest 与周报节律重复不做）。**迭代序**：I165 watch 条件化（`condition_json` 扁平等值 ≤5 键 + hook 全等匹配 + 前端条件输入与徽标）→ I166 铃铛降噪折叠（连续同 kind+同项目 watch 一行折叠带计数——纯函数+vitest）→ I167 **冒烟 60** + M55 审阅。
3. 每轮纪律不变：演示/审阅隔离 data+ontologies 且 netstat 确认单监听（**preview 必须显式从 web/ 起**）；**复演造数脚本失败后必须清理半成品数据再重跑**；**复演假阴性先核对输入（ID/造数/SW 旧缓存）再怀疑系统**；中文文档/源码/测试一律 Edit/Write 工具（**heredoc 彻底禁止**）；**commit message 反引号用单引号包裹**；python 写文本 newline="\n"；**每段式提交前 `git status` 核对源码文件齐全**；**HANDOFF 每轮收口时修剪**；**复演造数含中文 JSON 用 python urllib 不用 curl**；**切身份后必须恢复 settings.user_id**；**docs/10 追加表格行的 Edit：old_string 用行首片段锚定、new_string 必须以原文行开头再接新行**。

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

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 394 项，应全绿（>10 分钟：后台跑会被超时杀，用 --ignore=tests/smoke 分片 + 冒烟 runner 对账）
python tools/smoke/run_smoke.py       # 冒烟基线 54 条，应 GREEN（repo 根目录跑）
cd web && pnpm vitest run             # 前端单测 14 项；pnpm build 须绿
# 真实 LLM（先复制 .env.example 为 .env 填 key）
cd app && APM_PROVIDER_MODE=openai python -m uvicorn apm.main:app --port 8000
# 后端（演示/审阅时必须隔离：APM_DATA_DIR + APM_ONTOLOGY_DIR_OVERRIDE 且拷贝本体进去！）
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`；域 `app/apm/domains/`；LLM Provider `app/apm/runtime/provider.py`（replay/openai/anthropic/record 四实现 + `LLMError`）；NL 命令层 `app/apm/domains/nl.py`（L1 规则 + L2 `parse_llm`/`_normalize_llm_actions`）；本体 `ontology*.py`；前端 `web/src/pages/` + `web/src/components/`（AppShell 模型徽标/CommandBar L2 徽标）。
