# HANDOFF —— 写给下一个新会话（2026-09-05 更新 · M20 进行中：I62 已完成，下一步 I63 时间线拖拽改期）

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
- **当前验证基线：pytest 167 全绿；冒烟 25 GREEN；vitest 2/build 绿。**

## 3. 现在卡在哪

**没有硬阻塞。** 遗留 B/C 级意见见 docs/10 附录 B/C（本体治理权限分层 V2、本体版本事件级归档等）。

## 4. 下一步是什么（按序）

1. ~~M20 调研定义（e56b89e）~~ ✅ **M20-I62 个人工时日历已完成**（`7dc990f`+docs）：`GET /my/timelog?days=`（按日分组+日合计+窗口合计，days 钳 1-60）+「我的工时」页 `#/my/time`（周/月双视图+点日期格快捷记时，spent_on 预填，编辑仅时长/备注）+ 侧栏 CalendarClock 入口；timelog 单测 7 项绿。
2. **M20-I63 时间线拖拽改期**（docs/01 §S.2）：TimelinePage 条形 pointer 拖拽移动/右缘缩放 → PATCH start_date/due_date（M14 rescheduled 审计与冲突重算自动生效）；拖拽中半透明+悬浮日期；Esc 取消；未设日期项与里程碑菱形不参与；test_items.py 补改期审计断言。**只跑相关验证。**
3. **M20-I64 评论 Markdown 渲染 + 收尾**（§S.3）：CommentsModal GFM 只读渲染（marked+DOMPurify）+ mention chip + 编辑/预览切换，存储保持纯文本；docs/12 §17；**新增冒烟 26**（my/timelog 聚合 + 改期审计链 + 评论原文往返 + rebuild 一致）。
4. **M20 正式审阅**：审阅时点 HEAD 重跑**全量**（pytest 167+ / 冒烟 25+26 / vitest+build）+ I62/I63/I64 DoD 逐项 + 浏览器隔离复演三件套 + 附录 B +「M20 正式审阅通过」提交。之后开 M21 调研定义（先 grep docs/01 防重查）。
5. 每轮纪律不变：演示/审阅隔离 data+ontologies 且 netstat 确认单监听；中文文档用 Edit 工具；python 写文本必须 newline="\n"；**HANDOFF 每轮收口时修剪**。

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
- **task 状态集无 todo**（software-dev task）：open/ready/in_progress/awaiting_review/done/cancelled，测试用 ready。

## 6. 快速上手命令

```bash
cd app && python -m pytest            # 167 项，应全绿
python tools/smoke/run_smoke.py       # 冒烟基线 25 条，应 GREEN（repo 根目录跑）
# 前端
cd web && pnpm install && pnpm dev    # http://localhost:5173
# 后端（演示/审阅时必须隔离：APM_DATA_DIR + APM_ONTOLOGY_DIR_OVERRIDE 且拷贝本体进去！）
cd app && python -m uvicorn apm.main:app --port 8000 --reload
# 一键起（Docker）：docker compose up -d --build && python tools/seed.py
```

关键代码位置：事件内核 `app/apm/core/`（含 schema.py 迁移/drop_projections、events.py actor ContextVar + post-emit hook）；域 `app/apm/domains/`（items/comments/notifications/timelog/reports/milestones/scheduling 视 test_scheduling.py、views/webhooks/mailer/feed/members/automations/template_packs…）；本体 `ontology.py`+`ontology_learn.py`+`ontology_versions.py`+`ontology_cq.py`+`ontology_pack.py`；OIDC `core/oidc.py` + 演示 `tools/keycloak/`+`tools/oidc_stub.py`；前端 `web/src/pages/`（Board/TimelinePage/ReportsPage/MyWorkPage/TemplatesPage/OntologyPage）+ `web/src/components/`（CommentsModal/TimeLogModal/AppShell）。

M20 相关现状：I62 依赖 timelog 投影（M19）；I63 依赖 TimelinePage 只读渲染（M13）与 rescheduled 审计（M14，PATCH 端点已带冲突重算）；I64 依赖 comments 域 @解析口径（M18）。md 渲染选型 marked+DOMPurify（前端新依赖，pnpm add）。
