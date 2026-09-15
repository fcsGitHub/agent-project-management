# HANDOFF —— 写给下一个新会话（2026-09-15 更新 · M44 真实 LLM 接入 完成，下一步 M45 调研定义）

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
- **M44 真实 LLM 接入（I134-I136，2026-09-15 完成，docs/10 §M44；用户指令转向轮「避免一切 mock，要看到真实调用 LLM 的效果」）**：**I134 Provider 真实化**——AnthropicCompatProvider（httpx 零新依赖、thinking 块跳过、429/5xx 退避重试、MockTransport 可测）+ openai SDK timeout/max_retries/max_tokens + `LLMError` 可读错误直通 run.failed + `resolve_protocol` auto（base 含 `/anthropic` 即 anthropic 协议）+ 角色 YAML×7 与默认模型 `glm-5.3` + `llm_max_tokens=16384`（**推理模型预算教训：GLM-5.x 思考吃预算，4096→长工件空内容 finish=length，可读错误当场指路**）+ `.env.example`。**I135 观测与控制面**——`GET /api/system/llm`（永不泄露 key）+ `POST /api/system/llm/ping`（admin；replay 诚实拒绝；真实回 usage/latency）+ engine 真实补全后 `run.tokens_recorded` 事件落账（**修 M29 遗留：runs token 列首次被写入**；replay 保持诚实零）+ 侧栏模型徽标（点击即 ping toast）+ Runs 页 tooltip 条件化。**I136 NL 命令层 L2**——rules 未命中且非 replay → `ui_agent_model`（glm-5.3-flash）严格 JSON 契约解析 + `_normalize_llm_actions` 白名单（模型提议、确定性校验裁决、强制只读）+ `parser: rules|llm` 全链路溯源（事件/投影列/API/命令栏徽标）+ **冒烟 50** + 浏览器真实复演（glm-5.3 PRD 全文→门禁批准→succeeded→编排器自动接力 planner/release 双门禁→runs 真实 tokens 1182/37695→L2 flash 解析跳转→ping toast，截图 `.demo-m44/m44-review-1~5`）。**当前验证基线：pytest 339 全绿；冒烟 50 条 GREEN；vitest 14/build 绿。**

## 3. 现在卡在哪

**没有硬阻塞。** 真实 LLM 路径已可用：复制 `.env.example` 为 `.env` 填 `APM_LLM_API_KEY` 即 `APM_PROVIDER_MODE=openai` 跑真实模型（本机 ZCode 配置含 BigModel coding-plan key，运行时注入、不进仓库）。遗留 B/C 级意见见 docs/10 附录 B/C。

## 4. 下一步是什么（按序）

1. ~~M24~M44 全闭环~~ ✅（审阅提交号索引=docs/10 附录 B；单迭代详情真源=docs/10 §7 看板行与附录 A/B）。
2. **M45 调研定义（下一步）**：先 `grep -n "候选\|AP\|AQ" docs/01-open-source-research.md` 防重查 → 三路并行 WebSearch → docs/01 §AR 新节 + docs/10 §M45 节 + 看板行 + 附录 A →「M45 调研定义」提交 → HANDOFF 收口 → 3 迭代 → M45 审阅。**候选池**：①Cycles 多周期视图/燃尽对比（I125 留位）；②单元成本行项/多币种（I122 留）；③跨项目依赖图[需跨项目关系模型，V2 级]（I124 留）；④subject 正则全量路由（I113 前缀版已够用）；⑤digest 邮件[明确不做除非用户要求]；⑥LLM 深化：流式输出（SSE 逐 token）/ 对话多轮上下文压缩 / 角色 YAML 温度与模型分档 / record 模式录制真实 fixtures 供 CI 回放；⑦M45 调研新发现。
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

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 339 项，应全绿
python tools/smoke/run_smoke.py       # 冒烟基线 50 条，应 GREEN（repo 根目录跑）
cd web && pnpm vitest run             # 前端单测 14 项；pnpm build 须绿
# 真实 LLM（先复制 .env.example 为 .env 填 key）
cd app && APM_PROVIDER_MODE=openai python -m uvicorn apm.main:app --port 8000
# 后端（演示/审阅时必须隔离：APM_DATA_DIR + APM_ONTOLOGY_DIR_OVERRIDE 且拷贝本体进去！）
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`；域 `app/apm/domains/`；LLM Provider `app/apm/runtime/provider.py`（replay/openai/anthropic/record 四实现 + `LLMError`）；NL 命令层 `app/apm/domains/nl.py`（L1 规则 + L2 `parse_llm`/`_normalize_llm_actions`）；本体 `ontology*.py`；前端 `web/src/pages/` + `web/src/components/`（AppShell 模型徽标/CommandBar L2 徽标）。
