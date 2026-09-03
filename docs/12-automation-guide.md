# 12 · 自动化规则使用指南（M9）

> 看板自动化规则 = **触发 → 条件 → 动作** 三段式（docs/01 §H：Kanboard Automatic Actions 的项目级「事件×动作」绑定 × n8n/Node-RED 三段式抽象）。
> 规则本身事件溯源（`automation.rule_*`），执行挂在事件内核 post-emit hook 上——**事件内核即事件源**，无轮询、无外置 dispatcher。

## 1. 在哪里配置

项目 → 侧栏「本体」（项目设置页）→ **自动化规则** 面板：

- **列表**：每条规则一行——触发徽章、条件摘要、动作摘要，以及 测试运行 / 历史 / 启停 / 删除 操作；
- **新建规则**：三段式表单
  - 「当〈触发事件〉」：创建工作项 / 更新字段 / 状态变更 / 指派变更；
  - 「满足〈概念〉+〈可选字段谓词〉」：概念可选（如 缺陷 bug）；条件字段可为内置字段（priority / status / assignee_id）或本体声明字段（如 severity、regression）；
  - 「则〈动作〉」：指派给（用户下拉）/ 置优先级（高·中·低）/ 设自定义字段（enum、boolean 按本体声明出值选项；multiselect 用逗号分隔多个值）/ 改状态（状态池按所选概念收窄）。

## 2. 执行语义（重要）

| 语义 | 说明 |
| --- | --- |
| 时机 | 触发事件**落库后**执行；条件对事件发生后的工作项状态求值 |
| 归账 | 动作事件与 `automation.rule_fired` 均以 `actor_type=automation`、`actor_id=<规则id>` 归账——审计页「发起者 → ⚡ 自动化」可单独过滤 |
| 防循环 | 双保险：automation 归账的事件不再进引擎 + dispatch 期间的一切嵌套 emit 不进引擎（**单层执行**：规则动作永远不会触发其他规则，包括它自己） |
| 幂等教训 | Plane webhook「一次变更触发 3 次」的教训（docs/01 §H.3）：规则绑定在事件流上而非轮询状态，每条事件至多命中一次 |
| fail-closed | 创建时即校验：未知触发/动作/用户/字段、enum 越界、未声明状态、停用字段一律 422；运行时动作被拒（如指派人被删）记录为「被拒绝」，不影响触发方 |

## 3. 测试运行与历史

- **测试运行**：对项目内最近一条同类型触发事件做 dry-run——显示「命中哪个工作项、将执行什么动作」，**不执行任何写操作**；
- **历史**：每条规则的触发留痕（事件号 / 时间 / 已执行·被拒绝 / 动作明细），来自 `automation.rule_fired` 事件流——rebuild 后依然完整。

## 4. 权限与部署

- 规则 CRUD 属项目写操作：network 模式下 owner / contributor 可管理（viewer 与非成员 403 并落 `access.denied` 审计），local 模式单用户直通；
- 规则随项目数据存于事件溯源库，rebuild / 迁移天然存活；部署形态与 M8 相同（docs/11）。

## 5. 边界与后续（backlog）

- 每条规则绑定**单个动作**——需要组合动作时建多条规则（同触发事件按创建顺序执行）；
- 出站 webhook（事件 → 外部 URL）登记 backlog：先内嵌后外联；
- 条件谓词当前为标量相等 / multiselect 包含；区间与组合条件（AND/OR）留待有真实需求再加。

## 6. Webhooks 出站（M10-I32/I33）

项目 → 本体页 → **Webhooks 出站** 面板：配置接收端 URL + 订阅事件（白名单：item.* / approval.* / feature.created / automation.rule_fired），创建后 **secret 仅展示一次**（可随时「换发 secret」，旧签名立即失效）。

### 6.1 投递语义（对齐 Gitea/GitLab，docs/01 §I.1）

| 项 | 值 |
| --- | --- |
| 方法 / 体 | `POST` JSON，体 = 事件完整字典（原始字节） |
| `X-APM-Event` | 事件类型（如 `item.created`） |
| `X-APM-Delivery` | 投递 ID（`dl_` 前缀），接收方按它做幂等去重 |
| `X-APM-Webhook` | 本条 webhook 的 id |
| `X-APM-Signature` | `HMAC-SHA256(secret, 原始请求体字节)` 的十六进制摘要 |
| 超时 / 重试 | 单次 5s 超时；失败按 1s/4s/16s 指数退避重试 3 次，共至多 4 次尝试 |

每次投递终局都落事件流（`webhook.delivered` / `webhook.delivery_failed`：attempts、status_code、duration_ms、error），「投递历史」抽屉可查；失败投递可**一键重发**（新 delivery ID、单次尝试）；「Ping」发送合成测试载荷。投递在后台线程执行，**绝不阻塞写路径**。

### 6.2 接收方验签（Python 示例）

```python
import hmac, hashlib

def verify(secret: str, raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)   # 常量时间比较

raw = request.get_data()            # 原始字节！不要 json.loads 后重序列化
if not verify(WEBHOOK_SECRET, raw, request.headers["X-APM-Signature"]):
    abort(401)
event = json.loads(raw)
if event["id"] <= last_seen_id:     # X-APM-Delivery 去重，幂等处理
    return "dup"
```

要点（来自 GitLab 明文 token 的历史教训）：**只认 HMAC 签名不认明文 token**；对**原始字节**计算摘要（重序列化会破坏签名）；比较用常量时间函数。

## 7. 站内通知中心（M10-I34）

顶栏铃铛 = 当前登录身份的通知流（15s 轮询 + 操作后刷新）：

| 通知来源 | kind | 接收人 |
| --- | --- | --- |
| 工作项被指派给人类成员（`item.assigned`） | assigned | 被指派人 |
| 阶段门/工件审批请求（`approval.requested`） | approval | 项目 Owner |
| 自动化规则 `notify` 动作 | rule_notify | 动作指定的用户 |

- **已读状态事件溯源**（`notification.read`，记录 ids 或 all），rebuild 后未读数精确还原；
- 通知 id 确定性生成（`n_{源事件id}_{接收人}`），保证重放后与已读事件引用一致——这是事件溯源投影的通用要求（**投影生成的新实体 id 禁止随机**）；
- 自动化规则里选「通知」动作即给指定用户发站内提醒（走 M9 防循环与 automation 归账，不产生邮件依赖）。
