"""Artifact API: read/write project artifacts in the content repo (write = commit)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm import config
from apm.content import gitrepo
from apm.core import events

router = APIRouter(tags=["artifacts"])


def _artifact_gate(project_id: str, write: bool = False) -> None:
    """M72-I216 (docs/01 §BQ.1): repo-level permission inheritance — artifacts
    are files in the project repo, so they inherit project membership exactly
    like GitHub/GitLab (both ship no per-file ACL; that's the accepted
    semantics). local mode stays wide open; network mode: read = any member,
    write = owner/contributor (viewer is read-only). Fills the M45 audit blind
    spot: these endpoints live in content/, never went through the domains
    gating pass."""
    from apm.domains.members import WRITE_ROLES, member_role

    if config.settings.auth_mode == "local":
        return
    role = member_role(project_id, events.effective_actor())
    if role is None:
        raise HTTPException(status_code=403, detail="not a project member")
    if write and role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="viewer is read-only")


def list_artifacts(project_id: str) -> list[dict]:
    from apm.domains.ontology import load_ontology
    from apm.domains.projects import get_project

    project = get_project(project_id)
    if not project:
        return []
    onto = load_ontology(project["ontology"])
    deposits: dict[str, str] = {}
    for concept in onto.concepts.values():
        for ak in concept.artifact_kinds:
            if ak.get("deposits_to"):
                deposits[ak["id"]] = ak["deposits_to"]
    out = []
    for rel in gitrepo.list_files(project_id, "artifacts"):
        try:
            sha = gitrepo.latest_commit(project_id, rel)
            history = gitrepo.file_history(project_id, rel)
        except gitrepo.GitError:
            continue
        kind = rel.split("/")[-1].rsplit(".", 1)[0]
        out.append(
            {
                "path": rel,
                "kind": kind,
                "commit": sha,
                "updated_at": history[0]["date"] if history else None,
                "versions": len(history),
                "deposits_to": deposits.get(kind),
            }
        )
    out.sort(key=lambda a: a["path"])
    return out


def write_artifact(
    project_id: str,
    rel_path: str,
    content: str,
    *,
    actor_type: str,
    actor_id: str,
    message: str | None = None,
    run_id: str | None = None,
) -> dict:
    if not rel_path.startswith("artifacts/"):
        rel_path = f"artifacts/{rel_path}"
    message = message or f"update {rel_path}"
    sha = gitrepo.write_file(
        project_id, rel_path, content, message=message, actor_type=actor_type, actor_id=actor_id
    )
    event_type = "artifact.committed" if actor_type == "agent" else "artifact.human_edited"
    events.emit(
        event_type=event_type,
        agg_type="artifact",
        agg_id=rel_path,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        payload={"path": rel_path, "commit": sha, "message": message, "run_id": run_id},
    )
    return {"path": rel_path, "commit": sha}


class ArtifactWrite(BaseModel):
    content: str
    message: str | None = None


@router.get("/projects/{project_id}/artifacts")
def get_artifacts(project_id: str) -> dict:
    _artifact_gate(project_id)
    return {"artifacts": list_artifacts(project_id)}


# NOTE: registered BEFORE the {rel_path:path} GET route — FastAPI matches in
# registration order and the path converter would otherwise swallow "export".
@router.get("/projects/{project_id}/artifacts/export")
def export_artifacts(project_id: str):
    """M72-I218 (docs/01 §BQ.3): deliverable handoff — `git archive` of the
    artifacts/ subtree at HEAD: clean snapshot (no .git), pinned to the
    commit → reproducible. Streaming zip response; the audit fact records the
    delivery (export is an action worth remembering)."""
    from fastapi.responses import Response

    _artifact_gate(project_id)  # read-level: any member
    if not list_artifacts(project_id):
        raise HTTPException(status_code=404, detail="no artifacts to export")
    root = gitrepo.repo_path(project_id)
    head = gitrepo._run(["rev-parse", "--short=7", "HEAD"], cwd=root).strip()
    prefix = f"artifacts-{project_id[:8]}-{head}"
    data = gitrepo.archive_subtree_zip(project_id, "artifacts", prefix)
    events.emit(
        event_type="artifact.exported",
        agg_type="artifact",
        agg_id=f"export:{head}",
        project_id=project_id,
        actor_type="human",
        actor_id=events.effective_actor(),
        payload={"commit": head, "count": len(list_artifacts(project_id))},
    )
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{prefix}.zip"'},
    )


@router.get("/projects/{project_id}/artifacts/{rel_path:path}")
def get_artifact(project_id: str, rel_path: str, commit: str | None = None) -> dict:
    _artifact_gate(project_id)
    try:
        content = gitrepo.read_file(project_id, rel_path, commit)
        history = gitrepo.file_history(project_id, rel_path)
    except (FileNotFoundError, gitrepo.GitError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    prev = gitrepo.latest_commit_for_parent(project_id, rel_path)
    diff_text = ""
    if prev and len(history) > 1:
        try:
            diff_text = gitrepo.diff(project_id, rel_path, prev, history[0]["commit"])
        except gitrepo.GitError:
            diff_text = ""
    return {
        "path": rel_path,
        "commit": history[0]["commit"] if history else None,
        "content": content,
        "history": history,
        "diff_vs_previous": diff_text,
    }


@router.put("/projects/{project_id}/artifacts/{rel_path:path}")
def put_artifact(project_id: str, rel_path: str, body: ArtifactWrite) -> dict:
    from apm.domains.projects import require_project

    require_project(project_id)
    _artifact_gate(project_id, write=True)

    require_project(project_id)
    return write_artifact(
        project_id,
        rel_path,
        body.content,
        actor_type="human",
        actor_id=events.effective_actor(),
        message=body.message,
    )


@router.delete("/projects/{project_id}/artifacts/{rel_path:path}")
def delete_artifact(project_id: str, rel_path: str) -> dict:
    """M72-I217 (docs/01 §BQ.2): delete = git rm + artifact.deleted fact — git
    history IS the soft delete (blob recoverable, audit trail complete). The
    search projector clears the FTS row on this event (content no longer
    readable → _reindex_artifact's read-failure path already handles it)."""
    _artifact_gate(project_id, write=True)
    try:
        sha = gitrepo.delete_file(
            project_id, rel_path,
            message=f"delete {rel_path}",
            actor_type="human", actor_id=events.effective_actor())
    except (FileNotFoundError, gitrepo.GitError) as e:
        raise HTTPException(status_code=404, detail=f"artifact not found: {e}")
    events.emit(
        event_type="artifact.deleted",
        agg_type="artifact",
        agg_id=rel_path,
        project_id=project_id,
        actor_type="human",
        actor_id=events.effective_actor(),
        payload={"path": rel_path, "commit": sha},
    )
    return {"ok": True, "path": rel_path, "commit": sha}
