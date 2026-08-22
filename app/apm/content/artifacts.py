"""Artifact API: read/write project artifacts in the content repo (write = commit)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm import config
from apm.content import gitrepo
from apm.core import events

router = APIRouter(tags=["artifacts"])


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
    return {"artifacts": list_artifacts(project_id)}


@router.get("/projects/{project_id}/artifacts/{rel_path:path}")
def get_artifact(project_id: str, rel_path: str, commit: str | None = None) -> dict:
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
    return write_artifact(
        project_id,
        rel_path,
        body.content,
        actor_type="human",
        actor_id=config.settings.user_id,
        message=body.message,
    )
