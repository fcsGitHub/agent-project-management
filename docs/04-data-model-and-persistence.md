# 04 · 数据模型与持久化

## 1. 存储总览

| 存储 | 内容 | 技术 |
| --- | --- | --- |
| **事件日志**（唯一事实源） | 一切人与 Agent 的写操作，append-only | SQLite → PostgreSQL |
| **投影/索引**（可重建） | 工作项当前状态、看板列、轨迹树索引、统计、资产检索（FTS5） | 同上（单独表，由投影器维护） |
| **内容仓** | 工件：PRD/设计/WBS/测试报告/发布说明/代码 | 每项目一个 Git 仓库 |
| **资产仓**（v0.3） | 跨项目累计资产：产品库/测试库/文档库的资产正文与版本 | 全局一个 Git 仓库（09 §7） |
| **检查点** | Agent Run 的挂起/恢复快照 | LangGraph checkpointer 表（SQLite/PG） |

设计不变式：**事件表之外的一切结构化数据都是缓存，可由事件流重建**（重建命令 `agentpm rebuild-projections`）。这保证审计与轨迹永远与历史一致，也让后续加视图零迁移成本。

## 2. 实体模型（投影层 ER）

```
Workspace 1─n Project 1─n Milestone
Project 1─1 Ontology（ontology.yaml，类型系统，见 08）
Project 1─n Feature（功能，v0.2）
Feature 1─n Item（自引用 parent_id 成树；concept_id 引用本体概念）
Feature 1─n Conversation（对话；feature_id 可空=项目级临时对话）
Conversation 1─n Message（id/parentId 消息树）
Conversation 1─n Run；Run 1─n Span（轨迹树，parent_id 自引用）
Item 1─n ItemRelation（受控枚举：contains/depends_on/produces/consumes + 本体自定义）
Item/Feature 1─n ArtifactRef（git 路径 + commit）
Run 1─n Approval；Approval n─1 User（reviewer）
PromptLayer（L1 项目宪章 / L2 功能简报 / L4 角色，正文存 Git prompts/）
Workspace 1─n Library（资产库，本体注册，v0.3）
Library 1─n Asset（kind=本体 assetKind；正文存资产仓 Git）
Asset 1─n AssetLink（type: provenance|usage|supersedes → 工件/项目/资产）
Project 1─1 ContentRepo（Git）；Workspace 1─1 AssetsRepo（Git）
Project 1─n AgentRoleBinding
```

### 核心表 DDL 示意（SQLite 方言，MVP）

```sql
-- 事件日志（唯一事实源；不可 UPDATE/DELETE，触发器强制）
CREATE TABLE events (
  id            INTEGER PRIMARY KEY,          -- 全局单调 = 全序
  ts            TEXT NOT NULL,                -- ISO8601 UTC
  actor_type    TEXT NOT NULL,                -- 'human' | 'agent' | 'system' | 'ui_agent'
  actor_id      TEXT NOT NULL,                -- user_id / agent角色:run_id / ui_agent(on_behalf_of 在 payload)
  project_id    TEXT NOT NULL,
  agg_type      TEXT NOT NULL,                -- 'item'|'run'|'approval'|'project'|'feature'|'conversation'
  agg_id        TEXT NOT NULL,
  event_type    TEXT NOT NULL,                -- 见 §3 事件词典
  payload       TEXT NOT NULL,                -- JSON
  prev_event_id INTEGER NOT NULL              -- 链式指向前一条（防篡改，轻量哈希链可选）
);

-- 投影：功能（项目下的推进单元，v0.2 新增）
CREATE TABLE features (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
  title TEXT NOT NULL, brief TEXT,            -- 功能简报（提示词 L2，最新版；历史在 Git）
  status TEXT NOT NULL,                       -- active | paused | done | archived
  sort_order INTEGER, created_at TEXT, updated_at TEXT
);

-- 投影：对话（人机交互原子单元，v0.2 新增；事件流才是真源）
CREATE TABLE conversations (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, feature_id TEXT,
  kind TEXT NOT NULL,                         -- drafting|executing|reviewing|adhoc|ui_command
  title TEXT, status TEXT NOT NULL,           -- active|running|interrupted|awaiting_review|archived
  item_id TEXT, run_id TEXT,                  -- 可选绑定
  parent_conversation_id TEXT, seed_length INTEGER,  -- 分叉血统（dsh 模式）
  instruction TEXT,                           -- L3 会话指令（最新版）
  created_at TEXT, updated_at TEXT
);

-- 投影：消息树（pi 模式：id/parentId 支持单流内分支）
CREATE TABLE messages (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
  parent_id TEXT,                             -- 树状分支
  role TEXT NOT NULL,                         -- user | assistant | system | tool
  actor_type TEXT, actor_id TEXT,
  content TEXT, span_id TEXT,                 -- Agent 步骤关联轨迹 span
  created_at TEXT
);

-- 投影：提示词层（v0.2 新增；正文存内容仓 prompts/，此处为索引）
CREATE TABLE prompt_layers (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
  level TEXT NOT NULL,                        -- 'L1_charter' | 'L2_brief'(feature_id) | 'L4_role'(agent_role)
  feature_id TEXT, agent_role TEXT,
  git_path TEXT NOT NULL, version INTEGER NOT NULL,
  updated_by TEXT, updated_at TEXT
);

-- 投影：工作项当前状态（可重建）
CREATE TABLE items (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, feature_id TEXT, parent_id TEXT,
  concept_id TEXT,                            -- 本体概念类型（08），v0.2 起替代硬编码 type
  title TEXT NOT NULL, status TEXT NOT NULL, status_group TEXT NOT NULL,
  priority TEXT, assignee_type TEXT,          -- 'human' | 'agent'
  assignee_id TEXT,                           -- user_id 或 agent 角色名
  estimate_hours REAL, milestone_id TEXT,
  created_at TEXT, updated_at TEXT, version INTEGER   -- 乐观锁
);

-- Run 与 Span（轨迹，字段对齐 OTel GenAI semconv，便于 V2 导出）
CREATE TABLE runs (
  id TEXT PRIMARY KEY, project_id TEXT, feature_id TEXT, item_id TEXT,
  conversation_id TEXT NOT NULL,              -- v0.2：Run 必属于某对话
  agent_role TEXT, graph_node_id TEXT,
  status TEXT NOT NULL,                       -- pending|running|interrupted|succeeded|failed|cancelled
  thread_id TEXT NOT NULL,                    -- = LangGraph thread = run_id
  input TEXT, output TEXT,                    -- JSON
  started_at TEXT, ended_at TEXT,
  total_input_tokens INTEGER, total_output_tokens INTEGER,
  estimated_cost_usd REAL, error TEXT
);

CREATE TABLE spans (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, parent_id TEXT,
  span_kind TEXT NOT NULL,                    -- 'agent'|'tool'|'generation'|'chain'|'gate'|'human_action'|'ui_command'
  name TEXT NOT NULL,                         -- 如 'pm_agent.draft_prd' / 'tool.write_file'
  ts_start TEXT, ts_end TEXT,
  status TEXT,                                -- ok|error|interrupted
  attributes TEXT,                            -- JSON：gen_ai.request.model、gen_ai.tool.name、
                                             --      gen_ai.usage.input_tokens/output_tokens 等
  io TEXT                                     -- JSON：input/output（脱敏后），思考文本，diff 引用
);

-- 资产（v0.3：跨项目累计资产；正文真源在资产仓 Git，此处为投影索引）
CREATE TABLE assets (
  id TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,                   -- 本体 libraries 注册的库
  kind TEXT NOT NULL,                         -- 本体 assetKind（决定元数据 schema）
  title TEXT NOT NULL, status TEXT NOT NULL,  -- draft|in_review|published|deprecated|archived
  tags TEXT,                                  -- JSON 数组
  owner_id TEXT, version INTEGER NOT NULL,
  git_path TEXT NOT NULL, commit_sha TEXT NOT NULL,
  citation_count INTEGER DEFAULT 0,           -- 引用链计数（投影）
  created_at TEXT, updated_at TEXT
);

-- 资产边：来源链 / 引用链 / 版本继承
CREATE TABLE asset_links (
  id TEXT PRIMARY KEY, asset_id TEXT NOT NULL,
  type TEXT NOT NULL,                         -- 'provenance'|'usage'|'supersedes'
  target_type TEXT NOT NULL,                  -- 'artifact'|'project'|'conversation'|'asset'
  target_ref TEXT NOT NULL,                   -- JSON（项目/工件路径/commit 或资产 id）
  created_at TEXT
);

-- 审批（不可变，只追加终态事件）
CREATE TABLE approvals (
  id TEXT PRIMARY KEY, project_id TEXT, run_id TEXT, item_id TEXT, conversation_id TEXT,
  kind TEXT NOT NULL,                         -- 'gate'(阶段门) | 'tool'(危险工具) | 'item_status'
  payload_snapshot TEXT NOT NULL,             -- 提议内容快照（含 diff/文件路径）
  status TEXT NOT NULL,                       -- pending | approved | rejected | auto_approved
  requested_at TEXT, decided_at TEXT,
  reviewer_id TEXT,                           -- auto_approved 时为 'policy:<rule>'
  comment TEXT
);
```

## 3. 事件词典（MVP 必需集）

事件类型即系统的"动词表"，也是轨迹与审计的统一语言（借鉴 OpenHands Action/Observation 三元组）：

| 聚合 | 事件类型 | 发起者 |
| --- | --- | --- |
| project | `project.created` / `project.template_applied` / `ontology.changed` | human / system |
| feature | `feature.created` / `feature.updated` / `feature.archived` | human / agent |
| conversation | `conversation.created` / `conversation.interrupted` / `conversation.resumed` / `conversation.forked` / `conversation.archived` / `message.created` / `prompt.updated`(含 level) | human / agent / system |
| item | `item.created` / `item.updated` / `item.status_changed` / `item.assigned` / `item.related` | human / agent |
| artifact | `artifact.committed`（路径+commit）/ `artifact.human_edited` | agent / human |
| run | `run.requested` / `run.started` / `run.span_opened` / `run.span_closed` / `run.interrupted` / `run.resumed` / `run.succeeded` / `run.failed` / `run.retried_from_checkpoint` | system / human |
| approval | `approval.requested` / `approval.granted` / `approval.rejected` / `approval.auto_granted`（payload 含规则 id）/ `approval.resumed_with_edit` | system / human |
| ui | `ui_command.executed`（含原文/解析/API 调用，on_behalf_of） | ui_agent |
| asset | `asset.drafted` / `asset.in_review` / `asset.published` / `asset.deprecated` / `asset.archived` / `asset.superseded` / `asset.linked`（引用登记）/ `asset.consumed`（Agent/人实际使用） | human / agent / system |
| audit | `audit.exported` / `policy.changed` | human |

事件示例（Agent 完成草稿请求审批）：

```json
{
  "id": 1042, "ts": "2026-08-22T09:12:33Z",
  "actor_type": "agent", "actor_id": "pm-agent:run_8f3",
  "project_id": "p_demo", "agg_type": "approval", "agg_id": "apr_55",
  "event_type": "approval.requested",
  "payload": {
    "kind": "gate", "gate": "prd_review",
    "artifact": {"path": "artifacts/prd.md", "commit": "a1b2c3"},
    "summary": "PRD 草稿完成，共 6 个用户故事"
  }
}
```

## 4. 轨迹 Schema：对齐 OTel GenAI semconv

span 的 `span_kind` 与 `attributes` 采用 OTel GenAI 约定（`gen_ai.operation.name` 取 `invoke_agent`/`execute_tool`/`chat`；属性 `gen_ai.request.model`、`gen_ai.usage.input_tokens/output_tokens`、`gen_ai.tool.name`、`gen_ai.agent.name`、`gen_ai.input.messages`）。**本项目特有扩展**（semconv 允许自定义命名空间）：

- `apm.actor_type`：human / agent / ui_agent —— 支撑"人机交织时间线"视图；
- `apm.item_id` / `apm.graph_node_id`：把 span 锚定到工作项与图节点（Graph×Trajectory 联动视图的数据基础，见 05 §3.5）；
- `apm.conversation_id`：span 所属对话（对话视图内嵌 Agent 步骤行）；
- `apm.diff_ref`：指向内容仓 diff，避免在 span 里存大文本；
- `span_kind: 'gate'` / `'human_action'` / `'ui_command'`：审批等待、人工操作与自然语言命令也是轨迹的一部分（**人的轨迹**由此建模：`item.status_changed`、`approval.granted`、`artifact.human_edited`、`ui_command.executed` 均产生对应 span）。

脱敏规则：io 落库前过一遍 redact 管道（环境变量、密钥模式），原文仅存于内容仓或对象存储（V2）。

## 5. 检查点与恢复

- Run 的 `thread_id = run_id`，LangGraph checkpointer 在**每次节点转移**与**每次 interrupt** 时落快照（SQLite 表 `checkpoints`）；
- 服务重启：Orchestrator 扫描 `status='running'|'interrupted'` 的 Run → 从最近 checkpoint 恢复（interrupted 的等待审批，running 的续跑）；
- **从历史点重放**（time travel）：轨迹页任选历史 checkpoint → `run.retried_from_checkpoint` 事件 → 新建分支 Run（原 Run 保留只读，审计不断链）；
- **对话分叉**（v0.2）：消息树任意时点「从此分叉」→ 新对话记录 `parent_conversation_id + seed_length` 血统（dsh 模式），原对话只读保留；
- 人在审批时"修改后恢复"：编辑 Agent 状态（如修正 PRD 某节）→ `Command(update=...)` 语义写入 checkpoint → resume。

## 6. 工件（Artifact）持久化

```
<content-repo>/
  ontology/ontology.yaml     # 本体（08）：概念/关系/阶段图，Git 版本化
  prompts/                   # 提示词层正文：charter.md / features/<id>/brief.md / roles/*.md
  artifacts/
    requirement.md           # 阶段1
    prd.md                   # 阶段2
    design.md                # 阶段3
    wbs.md                   # 阶段4
    test/report-v3.md        # 阶段6（版本化的测试报告）
    release/v0.1-notes.md    # 阶段7
  code/                      # 或以 submodule/独立分支关联真正代码仓
```

规则：

1. **Agent 与人写文件都走内容仓**：Agent 提交带 `actor: agent(run_id)` 的 commit trailer，人编辑走 WebUI 编辑器（同样产生 commit）→ "谁改的"在 Git 与事件表双重可查；
2. 工件评审 = 审批 payload 内嵌该文件的 **diff 链接 + 渲染预览**，点开即看；
3. 打回 = 重开 Run 以旧 commit 为输入；历史版本永不丢失。

## 7. 迁移与扩展策略

- SQLite → PostgreSQL：ORM（SQLAlchemy）+ Alembic 迁移脚本，事件表不变；
- **新增视图/报表 = 新投影器**，不动事件 schema；
- **新增 Agent 角色 = 新 YAML + 新 span 命名**，轨迹表 schema 不变；
- 多租户（V3）：`events`/`items` 加 `tenant_id` 列 + 索引，投影按租户分区；
- 归档：完结项目的事件流导出为 JSONL + 内容仓 bundle，系统内只留索引（冷数据下沉）。
