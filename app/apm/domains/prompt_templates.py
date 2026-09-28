"""Reusable instruction templates (M69-I208, docs/01 §BN.2): saved prompts
for conversation/run kickoff — the Copilot `.prompt.md` pattern (instructions
versioned in the project repo, invoked near the workflow). Three adjacent
layers are deliberately NOT this: M35 canned replies live on the comment
face, M4 template packs instantiate whole projects, the template center ships
ontology packs. A template is a *draft*, not a shortcut: the client inserts
it into the composer for editing before sending — human review preserved.
Content is git-versioned via the prompts/ pipeline (I204 convention); the
projection keeps metadata and the event payload keeps the body for rebuild."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.projections import on

router = APIRouter(tags=["prompt-templates"])

_TITLE_MAX = 100
_BODY_MAX = 4000


def _require_member(project_id: str) -> str:
    from apm.domains.members import member_role
    from apm.domains.projects import require_project

    require_project(project_id)
    me = events.effective_actor()
    if not member_role(project_id, me):
        raise HTTPException(status_code=403, detail="project membership required")
    return me


def _check_role(agent_role: str | None) -> None:
    if not agent_role:
        return
    from apm.runtime import roles

    try:
        roles.get_role(agent_role)
    except KeyError:
        raise HTTPException(
            status_code=422,
            detail=f"agent_role must be a registered role, got '{agent_role}'")


# ------------------------------------------------------------- projection
@on("template.created")
@on("template.updated")
def _upsert(conn, e) -> None:
    p = e.payload
    conn.execute(
        "INSERT OR REPLACE INTO prompt_templates"
        " (id, project_id, title, agent_role, git_path, version, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (e.agg_id, e.project_id, p.get("title", ""),
         p.get("agent_role"), p.get("git_path", ""),
         p.get("version", 1), e.ts),
    )


@on("template.deleted")
def _delete(conn, e) -> None:
    conn.execute("DELETE FROM prompt_templates WHERE id = ?", (e.agg_id,))


def read_template_body(project_id: str, git_path: str) -> str:
    from apm.content import prompts as prompt_files

    try:
        return prompt_files.read_prompt(project_id, git_path) or ""
    except Exception:
        return ""  # repo missing / file gone — list stays usable, body empty


# ----------------------------------------------------------------- models
class TemplateIn(BaseModel):
    title: str
    body: str
    agent_role: str | None = None


class TemplatePatchIn(BaseModel):
    title: str | None = None
    body: str | None = None
    agent_role: str | None = None


# ---------------------------------------------------------------- endpoints
@router.get("/projects/{project_id}/prompt-templates")
def list_templates(project_id: str) -> dict:
    _require_member(project_id)
    rows = db.get_conn().execute(
        "SELECT id, title, agent_role, git_path, version, updated_at"
        " FROM prompt_templates WHERE project_id = ? ORDER BY updated_at DESC, id",
        (project_id,),
    ).fetchall()
    return {"templates": [
        {"id": r["id"], "title": r["title"], "agent_role": r["agent_role"],
         "body": read_template_body(project_id, r["git_path"]),
         "version": r["version"], "updated_at": r["updated_at"]}
        for r in rows
    ]}


def _validate(title: str, body: str, agent_role: str | None) -> tuple[str, str]:
    t = title.strip()
    b = body.strip()
    if not t or len(t) > _TITLE_MAX:
        raise HTTPException(status_code=422, detail=f"title must be a 1-{_TITLE_MAX} char string")
    if not b or len(b) > _BODY_MAX:
        raise HTTPException(status_code=422, detail=f"body must be a 1-{_BODY_MAX} char string")
    _check_role(agent_role)
    return t, b


@router.post("/projects/{project_id}/prompt-templates")
def create_template(project_id: str, body_in: TemplateIn) -> dict:
    me = _require_member(project_id)
    title, body = _validate(body_in.title, body_in.body, body_in.agent_role)
    return _create_row(project_id, me, title, body, body_in.agent_role)


def _create_row(project_id: str, me: str, title: str, body: str,
                agent_role: str | None) -> dict:
    """Shared emit+git path for the API create and the import (I215) — one
    code path so imported templates are indistinguishable from manual ones."""
    from apm import config as apm_config
    from apm.core.ids import new_id
    from apm.content import prompts as prompt_files

    tid = new_id("pt")
    git_path = f"prompts/templates/{tid}.md"
    events.emit(
        event_type="template.created",
        agg_type="prompt_template",
        agg_id=tid,
        project_id=project_id,
        actor_type="human",
        actor_id=me,
        payload={"title": title, "agent_role": agent_role,
                 "git_path": git_path, "content": body, "version": 1},
    )
    prompt_files.write_prompt(project_id, git_path, body,
                              actor_type="human", actor_id=me or apm_config.settings.user_id)
    return get_template_row(project_id, tid)


# ------------------------------------------- M71-I215: JSON export/import
# (watch-rules mirror, M56-I168): one project's template set re-applies to
# any project the importer is a member of; same-title rows are skipped, never
# clobbered — the count report keeps the outcome honest.

@router.get("/projects/{project_id}/prompt-templates/export")
def export_templates(project_id: str) -> dict:
    _require_member(project_id)
    rows = db.get_conn().execute(
        "SELECT title, agent_role, git_path FROM prompt_templates"
        " WHERE project_id = ? ORDER BY updated_at DESC, id",
        (project_id,),
    ).fetchall()
    return {"version": 1, "templates": [
        {"title": r["title"], "agent_role": r["agent_role"],
         "body": read_template_body(project_id, r["git_path"])}
        for r in rows
    ]}


class TemplateImportIn(BaseModel):
    templates: list[TemplateIn]


@router.post("/projects/{project_id}/prompt-templates/import")
def import_templates(project_id: str, body: TemplateImportIn) -> dict:
    me = _require_member(project_id)
    if len(body.templates) > 50:
        raise HTTPException(status_code=422, detail="template supports at most 50 templates")
    imported = skipped = 0
    for i, t in enumerate(body.templates):
        try:
            title, tpl_body = _validate(t.title, t.body, t.agent_role)
        except HTTPException as e:
            raise HTTPException(status_code=422, detail=f"templates[{i}]: {e.detail}")
        if db.get_conn().execute(
                "SELECT 1 FROM prompt_templates WHERE project_id = ? AND title = ?",
                (project_id, title)).fetchone():
            skipped += 1  # same title already there — import never clobbers
            continue
        _create_row(project_id, me, title, tpl_body, t.agent_role)
        imported += 1
    return {"imported": imported, "skipped": skipped}


@router.patch("/prompt-templates/{tid}")
def update_template(tid: str, body_in: TemplatePatchIn) -> dict:
    row = db.get_conn().execute(
        "SELECT * FROM prompt_templates WHERE id = ?", (tid,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="template not found")
    me = _require_member(row["project_id"])
    title, body = _validate(
        body_in.title if body_in.title is not None else row["title"],
        body_in.body if body_in.body is not None else read_template_body(row["project_id"], row["git_path"]),
        body_in.agent_role if body_in.agent_role is not None else row["agent_role"],
    )
    from apm.content import prompts as prompt_files

    events.emit(
        event_type="template.updated",
        agg_type="prompt_template",
        agg_id=tid,
        project_id=row["project_id"],
        actor_type="human",
        actor_id=me,
        payload={"title": title, "agent_role": body_in.agent_role if body_in.agent_role is not None else row["agent_role"],
                 "git_path": row["git_path"], "content": body,
                 "version": row["version"] + 1},
    )
    prompt_files.write_prompt(row["project_id"], row["git_path"], body,
                              actor_type="human", actor_id=me)
    return get_template_row(row["project_id"], tid)


@router.delete("/prompt-templates/{tid}")
def delete_template(tid: str) -> dict:
    row = db.get_conn().execute(
        "SELECT * FROM prompt_templates WHERE id = ?", (tid,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="template not found")
    me = _require_member(row["project_id"])
    events.emit(
        event_type="template.deleted",
        agg_type="prompt_template",
        agg_id=tid,
        project_id=row["project_id"],
        actor_type="human",
        actor_id=me,
        payload={"title": row["title"], "git_path": row["git_path"]},
    )
    # git 历史保留（prompts/templates/{tid}.md 不删）——投影行消失即"删除"
    return {"ok": True, "id": tid}


def get_template_row(project_id: str, tid: str) -> dict:
    r = db.get_conn().execute(
        "SELECT id, title, agent_role, git_path, version, updated_at"
        " FROM prompt_templates WHERE id = ?", (tid,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="template not found")
    return {"id": r["id"], "title": r["title"], "agent_role": r["agent_role"],
            "body": read_template_body(project_id, r["git_path"]),
            "version": r["version"], "updated_at": r["updated_at"]}
