"""Prompt file persistence: prompt layer bodies live in the content repo prompts/."""
from __future__ import annotations

from apm import config
from apm.content import gitrepo


def write_prompt(
    project_id: str, git_path: str, content: str, *, actor_type: str, actor_id: str
) -> str:
    if not git_path.startswith("prompts/"):
        git_path = f"prompts/{git_path}"
    return gitrepo.write_file(
        project_id,
        git_path,
        content,
        message=f"prompts: update {git_path}",
        actor_type=actor_type,
        actor_id=actor_id,
    )


def read_prompt(project_id: str, git_path: str, commit: str | None = None) -> str | None:
    try:
        return gitrepo.read_file(project_id, git_path, commit)
    except (FileNotFoundError, gitrepo.GitError):
        return None


def seed_role_prompts(project_id: str) -> None:
    """Copy agent role prompt bodies (L4) into the project repo once."""
    roles_dir = config.settings.agents_dir / "prompts" / "roles"
    if not roles_dir.exists():
        return
    for f in sorted(roles_dir.glob("*.md")):
        rel = f"prompts/roles/{f.name}"
        existing = read_prompt(project_id, rel)
        if existing is None:
            write_prompt(
                project_id,
                rel,
                f.read_text(encoding="utf-8"),
                actor_type="system",
                actor_id="apm",
            )
