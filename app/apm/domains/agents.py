"""M116-I353/I354 Agent 团队域（docs/01 §DG，Paperclip 吸纳轮）：「用户统筹
管理支配多 Agent 团队」的总览与治理面。三源合并只读目录——①roles YAML 静态
声明（能力面：display_name/tier/concepts/tools）②agents 投影治理覆盖层
（暂停状态+Agent 级预算，org 级 project_id=''）③runs 台账聚合（事件溯源红利
第十七例：活跃数/成功率/累计 tokens 与成本零新表零埋点）。治理动作（暂停/
恢复/预算）走事件链 rebuild 稳定，admin 门对齐 reload-ontologies 惯例；执行
侧拦截在 engine.start_run 前置校验区（409/402）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.projections import on

router = APIRouter(tags=["agents"])


# ------------------------------------------------------------ projections
# 覆盖层三事件共享一个 upsert：INSERT OR IGNORE 先落行（保住既有 budget_usd/
# status 列），再 UPDATE 本事件管的列——INSERT OR REPLACE 会把兄弟列抹成默认。
def _upsert_overlay(conn, role_id: str, ts: str, **cols: str) -> None:
    conn.execute("INSERT OR IGNORE INTO agents (role_id, status) VALUES (?, 'active')",
                 (role_id,))
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(f"UPDATE agents SET {sets}, updated_at = ? WHERE role_id = ?",
                 (*cols.values(), ts, role_id))


@on("agent.paused")
def _proj_agent_paused(conn, e):
    _upsert_overlay(conn, e.agg_id, e.ts, status="paused")


@on("agent.resumed")
def _proj_agent_resumed(conn, e):
    _upsert_overlay(conn, e.agg_id, e.ts, status="active")


@on("agent.updated")
def _proj_agent_updated(conn, e):
    # payload 只带被改的键（PATCH 语义）；预算 0=关闭护栏（对齐 M66 项目预算）
    if "budget_usd" in e.payload:
        _upsert_overlay(conn, e.agg_id, e.ts, budget_usd=e.payload.get("budget_usd"))


# ------------------------------------------------------------------- API
class AgentBudgetIn(BaseModel):
    budget_usd: float


def _require_admin() -> None:
    """org 级治理动作（影响全实例所有项目的 run 派活）——对齐 system.py
    reload-ontologies 的 admin 门惯例；local 模式信任引导管理员不变。"""
    from apm.domains.members import is_instance_admin

    if not is_instance_admin(events.effective_actor()):
        raise HTTPException(status_code=403, detail="admin role required for agent governance")


def _require_role(role_id: str) -> None:
    from apm.runtime import roles as role_registry

    if role_id not in role_registry.load_roles():
        raise HTTPException(
            status_code=404, detail=f"unknown agent role '{role_id}'")


def _role_face(role_id: str) -> dict:
    from apm.runtime import roles as role_registry

    r = role_registry.load_roles()[role_id]
    return {
        "id": r.id,
        "display_name": r.display_name,
        "tier": r.model.get("tier") or ("custom" if r.model.get("name") else None),
        "model": r.model.get("name"),
        "concepts": r.concepts,
        "tools": r.tools,
    }


@router.get("/agents")
def list_agents() -> dict:
    """团队总览（org 级登录门·对齐 M76 assets 读惯例）：YAML 声明 × 治理
    覆盖层 × runs 聚合统计一屏合并——「谁在忙/成本/成功率」的统筹面。"""
    from apm.domains.members import require_instance_user
    from apm.runtime import roles as role_registry

    require_instance_user()
    conn = db.get_conn()
    overlay = {r["role_id"]: dict(r) for r in
               conn.execute("SELECT role_id, status, budget_usd FROM agents").fetchall()}
    stats: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT agent_role, COUNT(*) AS total_runs,"
        " SUM(status = 'succeeded') AS succeeded, SUM(status = 'failed') AS failed,"
        " SUM(status IN ('pending', 'running', 'interrupted')) AS active_runs,"
        " MAX(COALESCE(started_at, '')) AS last_started_at,"
        " SUM(total_input_tokens + total_output_tokens) AS total_tokens,"
        " SUM(estimated_cost_usd) AS estimated_cost_usd,"
        " SUM(CASE WHEN strftime('%Y-%m', COALESCE(started_at, ''))"
        "      = strftime('%Y-%m', 'now') THEN estimated_cost_usd ELSE 0 END)"
        "  AS month_cost_usd"
        " FROM runs GROUP BY agent_role"
    ):
        stats[r["agent_role"]] = dict(r)
    agents = []
    for role_id in sorted(role_registry.load_roles()):
        ov = overlay.get(role_id, {})
        st = stats.get(role_id, {})
        agents.append({
            **_role_face(role_id),
            "status": ov.get("status", "active"),
            "budget_usd": ov.get("budget_usd"),
            "stats": {
                "total_runs": st.get("total_runs") or 0,
                "succeeded": st.get("succeeded") or 0,
                "failed": st.get("failed") or 0,
                "active_runs": st.get("active_runs") or 0,
                "last_started_at": st.get("last_started_at") or None,
                "total_tokens": st.get("total_tokens") or 0,
                "estimated_cost_usd": st.get("estimated_cost_usd") or 0.0,
                "month_cost_usd": st.get("month_cost_usd") or 0.0,
            },
        })
    return {"agents": agents}


@router.post("/agents/{role_id}/pause")
def pause_agent(role_id: str) -> dict:
    _require_admin()
    _require_role(role_id)
    events.emit(event_type="agent.paused", agg_type="agent", agg_id=role_id,
                project_id="", actor_type="human")
    return {"role_id": role_id, "status": "paused"}


@router.post("/agents/{role_id}/resume")
def resume_agent(role_id: str) -> dict:
    _require_admin()
    _require_role(role_id)
    events.emit(event_type="agent.resumed", agg_type="agent", agg_id=role_id,
                project_id="", actor_type="human")
    return {"role_id": role_id, "status": "active"}


@router.patch("/agents/{role_id}")
def patch_agent(role_id: str, body: AgentBudgetIn) -> dict:
    """Agent 级月度预算（Paperclip budgets-at-agent-level 的翻译）。0=关闭
    护栏（对齐项目预算语义）；402/软阈拦截在 start_run 前置校验区。"""
    _require_admin()
    _require_role(role_id)
    if body.budget_usd < 0:
        raise HTTPException(status_code=422, detail="budget_usd 不得为负")
    events.emit(event_type="agent.updated", agg_type="agent", agg_id=role_id,
                project_id="", actor_type="human",
                payload={"budget_usd": body.budget_usd})
    row = db.get_conn().execute(
        "SELECT status, budget_usd FROM agents WHERE role_id = ?", (role_id,)).fetchone()
    return {"role_id": role_id, "status": row["status"], "budget_usd": row["budget_usd"]}
