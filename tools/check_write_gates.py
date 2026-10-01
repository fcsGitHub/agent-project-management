"""Route×gate 对账（M80-I240，docs/01 §BY.2）——check_env_doc 同哲学的第三次
机械防腐：每条非 GET 路由必须被下列之一**有意识地**覆盖——

①中间件（main.py auth_gate：/api/projects/* 前缀，或 id-path 白名单
  items|conversations|runs|approvals|artifacts/{id} 前缀——与
  project_id_for_path 的正则逐字镜像，含多段 id 路径）；
②域内门（REVIEWED 台账登记：M80-I240 补门的 cycles/milestones/features/
  risks/assets/nl/ontology/orchestrator/template-packs/sweep 等——门禁逻辑
  本身由矩阵测试另行证明，本脚本只锁「复审完备性」）；
③公开/自面（auth 登录、intake 令牌面、me/* 与 notifications 自面等）。

新增写路由不命中三者即非零退出并列出路径——教训：白名单是
allow-if-matched，新资源域不回补=裸奔（M80 审计四域+assets 六写实证）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from apm.main import app  # noqa: E402

# 与 main.py project_id_for_path 逐字镜像（无 $ 锚——多段 id 路径靠前缀匹配）
_ID_WHITELIST = re.compile(r"^/api/(items|conversations|runs|approvals|artifacts)/([^/]+)")

# 域内门/公开面台账：路径 → 依赖的门（M80-I240 全量登记）
REVIEWED: dict[str, str] = {
    # —— M80-I240 域内补门（require_project_write：项目成员制）——
    "/api/cycles/{cycle_id}": "require_project_write（M80-I240）",
    "/api/cycles/{cycle_id}/action-items": "require_project_write（M80-I240）",
    "/api/milestones/{milestone_id}": "require_project_write（M80-I240）",
    "/api/features/{feature_id}": "require_project_write（M80-I240）",
    "/api/features/{feature_id}/archive": "require_project_write（M80-I240）",
    "/api/risks/{risk_id}": "require_project_write（M80-I240）",
    "/api/risks/{risk_id}/close": "require_project_write（M80-I240）",
    "/api/conversations": "require_project_write（M80-I240——require_project 仅 404 存在性）",
    "/api/runs": "require_project_write（M80-I240——POST /runs 无 id 段不匹配白名单）",
    "/api/ui_commands": "require_project_write（有 project_id 时·M80-I240）",
    "/api/orchestrator/batch-start": "require_project_write（逐项目·M80-I240）",
    # —— M80-I240 assets 分门（org 库写面·M76 只补了读面）——
    "/api/assets": "require_project_write（from 侧 deposit·M80-I240）",
    "/api/assets/{asset_id}/deprecate": "require_instance_user（M80-I240）",
    "/api/assets/{asset_id}/archive": "require_instance_user（M80-I240）",
    "/api/assets/{asset_id}/restore": "require_instance_user（M80-I240）",
    "/api/assets/{asset_id}/submit_review": "require_instance_user（M80-I240）",
    "/api/assets/{asset_id}/link": "require_instance_user（M80-I240）",
    "/api/template-packs/from-asset": "require_instance_user（M80-I240）",
    # —— M80-I240 admin 门（org 治理动作）——
    "/api/ontologies/{name}/learn": "is_instance_admin（M80-I240·M4 C 级部分清账）",
    "/api/ontologies/{name}/learn-llm": "is_instance_admin（M80-I240）",
    "/api/ontologies/{name}/apply": "is_instance_admin（M80-I240·分层仍 V2）",
    "/api/system/reload-ontologies": "is_instance_admin（M80-I240）",
    "/api/automations/sweep": "登录即可（幂等节拍提前）·force=True admin（M80-I240）",
    # —— 既有域内门（M26~M79 期间已审）——
    "/api/comments/{comment_id}": "_gate 项目成员（M17）",
    "/api/comments/{comment_id}/extract-task": "_gate 项目成员（M21）",
    "/api/time_entries/{entry_id}": "member_role+冻结门（M26/M33）",
    "/api/prompt-templates/{tid}": "member_role（M71）",
    "/api/timesheets/{ts_id}/approve": "owner/admin（M33）",
    "/api/timesheets/{ts_id}/reject": "owner/admin（M33）",
    "/api/views/{view_id}": "member_role/owner 内联门（M12/M65）",
    "/api/views/{view_id}/make-default": "member_role/owner 内联门",
    "/api/calendar/holidays": "is_instance_admin（M34）",
    "/api/calendar/holidays/{day}": "is_instance_admin（M34）",
    "/api/imap/poll": "is_instance_admin（M37）",
    "/api/system/rebuild-projections": "is_instance_admin（M45）",
    "/api/system/llm/ping": "is_instance_admin（M44——花真 token）",
    "/api/ontologies/import": "is_instance_admin（M7·ontology_pack）",
    # —— 公开/自面（设计如此）——
    "/api/auth/login": "公开（登录）",
    "/api/auth/logout": "公开",
    "/api/auth/tokens": "自面（本人 PAT·display-once）",
    "/api/auth/tokens/{token_id}": "自面（本人 PAT）",
    "/api/intake/{token}": "公开（令牌面——token 即凭证·M32）",
    "/api/users": "local 引导/admin（M8）",
    "/api/session/identity": "local-mode only（network 422）",
    "/api/me/feed-key/rotate": "自面（本人 key）",
    "/api/me/hourly-rate": "自面",
    "/api/me/notification-prefs": "自面",
    "/api/me/push": "自面",
    "/api/me/quiet-hours": "自面",
    "/api/me/saved-replies": "自面",
    "/api/me/saved-replies/{reply_id}": "自面",
    "/api/me/time-off": "自面",
    "/api/me/time-off/{off_id}": "自面",
    "/api/me/timesheets/submit": "自面（本人工时单）",
    "/api/notifications/prefs": "自面（effective_actor）",
    "/api/notifications/read": "自面（user_id 限定）",
    "/api/ui_commands/{cmd_id}/confirm": "只读动作面（navigate/set_filter 白名单·I136）",
    "/api/template-packs/{name}/instantiate": "建项目面（creator=owner·与 POST /projects 同语义）",
}


def collect_routes() -> list[tuple[str, str]]:
    """(effective path, methods) for every non-GET route across the app."""
    rows: list[tuple[str, str]] = []
    for r in app.routes:
        if type(r).__name__ != "_IncludedRouter":
            continue
        prefix = r.include_context.prefix or ""
        for rt in getattr(r.original_router, "routes", []):
            methods = getattr(rt, "methods", None) or set()
            if not methods or methods <= {"GET", "HEAD", "OPTIONS"}:
                continue
            shown = "+".join(sorted(m for m in methods if m not in ("HEAD", "OPTIONS")))
            rows.append((prefix + rt.path, shown))
    return rows


def unreviewed_routes(rows: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    out = []
    for path, shown in rows:
        if path.startswith("/api/projects") or _ID_WHITELIST.match(path):
            continue  # ①中间件
        reason = REVIEWED.get(path)
        if reason:
            continue  # ②域内门/③公开自面（台账登记）
        out.append((path, shown, reason or "未登记"))
    return out


def main() -> int:
    rows = collect_routes()
    unreviewed = unreviewed_routes(rows)
    mw = sum(1 for p, _ in rows if p.startswith("/api/projects") or _ID_WHITELIST.match(p))
    print(f"write routes: {len(rows)} · middleware-covered {mw} · reviewed-ledger {len(rows) - mw - len(unreviewed)}")
    if unreviewed:
        print("UNREVIEWED write routes — 先补门（域内 require_project_write/instance/admin）"
              "再在 tools/check_write_gates.py REVIEWED 台账登记，勿裸奔：")
        for path, shown, _ in unreviewed:
            print(f"  {shown:12s} {path}")
        return 1
    print("write gates reconciled ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
