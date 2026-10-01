"""Orchestrator API: batch start, phase statuses."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["orchestrator"])


class BatchStartIn(BaseModel):
    item_ids: list[str]


@router.post("/orchestrator/batch-start")
def post_batch_start(body: BatchStartIn) -> dict:
    from apm.domains.items import get_item
    from apm.domains.members import require_project_write
    from apm.orchestrator.scheduler import batch_start

    seen: set[str] = set()
    for iid in body.item_ids:
        it = get_item(iid)
        if it and it["project_id"] not in seen:
            seen.add(it["project_id"])
            require_project_write(it["project_id"])  # M80-I240
    return batch_start(body.item_ids)


@router.get("/projects/{project_id}/phases")
def get_phases(project_id: str) -> dict:
    from apm.orchestrator.state_machine import phase_statuses
    from apm.domains.projects import require_project

    require_project(project_id)
    return {"project_id": project_id, "phases": phase_statuses(project_id)}


@router.post("/projects/{project_id}/deliver")
def post_deliver(project_id: str) -> dict:
    """Generate delivery: release-agent run on a fresh release conversation."""
    from apm.core import db
    from apm.domains.conversations import create_conversation
    from apm.domains.projects import require_project
    from apm.runtime.engine import start_run

    project = require_project(project_id)
    row = db.get_conn().execute(
        "SELECT id FROM features WHERE project_id = ? AND status != 'archived'"
        " ORDER BY sort_order LIMIT 1",
        (project_id,),
    ).fetchone()
    conv = create_conversation(
        project_id=project_id,
        feature_id=row["id"] if row else None,
        kind="reviewing",
        title=f"{project['name']} 交付",
        instruction="汇总本里程碑工件与人机轨迹，生成发布说明",
        actor_type="human",
    )
    run = start_run(conversation_id=conv["id"], agent_role="release-agent")
    return {"conversation_id": conv["id"], "run_id": run["id"]}
