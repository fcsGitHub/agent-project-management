"""Content repo: one plain Git working repo per project (git CLI via subprocess).

Artifacts, prompts and the project ontology live here (docs/04 §6): every
write is a commit, so diffs, version history and rollback come for free.
"""
from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path

from apm import config

GIT_NAME = "AgentPM"
GIT_EMAIL = "agentpm@local"

# M48-I146: per-project git write locks（index.lock 冲突防护）
_git_locks: dict[str, threading.Lock] = {}
_git_locks_guard = threading.Lock()


def _project_git_lock(project_id: str) -> threading.Lock:
    with _git_locks_guard:
        lock = _git_locks.get(project_id)
        if lock is None:
            lock = threading.Lock()
            _git_locks[project_id] = lock
        return lock


class GitError(Exception):
    pass


def _run(args: list[str], cwd: Path | None = None, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-c", f"user.name={GIT_NAME}", "-c", f"user.email={GIT_EMAIL}", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def repo_path(project_id: str) -> Path:
    return config.settings.content_root / project_id


def init_project_repo(project_id: str, charter: str, ontology_name: str) -> Path:
    """Create the repo skeleton: ontology/ + prompts/ + artifacts/."""
    import shutil

    root = repo_path(project_id)
    root.mkdir(parents=True, exist_ok=True)
    _run(["init", "-q", "-b", "main"], cwd=root)
    (root / "ontology").mkdir(exist_ok=True)
    (root / "prompts").mkdir(exist_ok=True)
    (root / "artifacts").mkdir(exist_ok=True)

    src = config.settings.ontology_dir / f"{ontology_name}.yaml"
    if src.exists():
        shutil.copyfile(src, root / "ontology" / "ontology.yaml")
    (root / "prompts" / "charter.md").write_text(charter, encoding="utf-8", newline="\n")
    commit_all(
        project_id,
        message="chore: initialize content repo (ontology + charter)",
        actor_type="system",
        actor_id="apm",
    )
    return root


def _safe_relpath(project_id: str, rel_path: str) -> Path:
    root = repo_path(project_id).resolve()
    target = (root / rel_path).resolve()
    # 逐级父目录比较，杜绝字符串前缀绕过（p1 的 ../p1-evil/x 会解析成兄弟目录，
    # startswith(".../p1") 却为 True）。
    if target != root and root not in target.parents:
        raise GitError(f"path escapes content repo: {rel_path}")
    return target


def write_file(
    project_id: str, rel_path: str, content: str, *, message: str, actor_type: str, actor_id: str
) -> str:
    """Write one file and commit; returns the new commit sha."""
    target = _safe_relpath(project_id, rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return commit_file(project_id, rel_path, message=message, actor_type=actor_type, actor_id=actor_id)


def commit_file(
    project_id: str, rel_path: str, *, message: str, actor_type: str, actor_id: str
) -> str:
    root = repo_path(project_id)
    # M48-I146: git 工作仓非并发安全（index.lock 冲突）——并行 run 写同一
    # 项目仓时按项目互斥；跨项目仓互不阻塞。
    with _project_git_lock(project_id):
        _run(["add", "--", rel_path], cwd=root)
        trailer = f"Actor: {actor_type}({actor_id})"
        # 并行 run 可能写入与上一次提交完全相同的内容（确定性模板）——
        # nothing to commit 不是错误（status 已干净）；仍有变更 = 真失败。
        _run(["commit", "-q", "-m", message, "-m", trailer], cwd=root, check=False)
        if _run(["status", "--porcelain", "--", rel_path], cwd=root).strip():
            raise GitError(f"git commit failed for {rel_path}")
        return latest_commit(project_id, rel_path)


def commit_all(project_id: str, *, message: str, actor_type: str, actor_id: str) -> str:
    root = repo_path(project_id)
    with _project_git_lock(project_id):
        _run(["add", "-A"], cwd=root)
        _run(["commit", "-q", "-m", message, "-m", f"Actor: {actor_type}({actor_id})"], cwd=root,
             check=False)
        return latest_commit(project_id, None)


def read_file(project_id: str, rel_path: str, commit: str | None = None) -> str:
    root = repo_path(project_id)
    _safe_relpath(project_id, rel_path)
    if commit is not None and not re.fullmatch(r"[0-9a-fA-F]{4,40}", commit):
        raise GitError(f"invalid commit ref: {commit}")  # 防 git 选项注入（--output 等）
    ref = f"{commit}:{rel_path}" if commit else f"HEAD:{rel_path}"
    try:
        out = _run(["show", ref], cwd=root)
    except GitError:
        raise FileNotFoundError(rel_path)
    # `git show` prints the raw blob for files; strip nothing.
    return out


def latest_commit(project_id: str, rel_path: str | None) -> str:
    root = repo_path(project_id)
    args = ["log", "-1", "--format=%H"]
    if rel_path:
        args += ["--", rel_path]
    out = _run(args, cwd=root)
    return out.strip()


def file_history(project_id: str, rel_path: str, limit: int = 50) -> list[dict]:
    root = repo_path(project_id)
    _safe_relpath(project_id, rel_path)
    out = _run(
        ["log", f"-{limit}", "--format=%H|%ad|%s", "--date=iso", "--", rel_path], cwd=root
    )
    history = []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        sha, date, subject = line.split("|", 2)
        history.append({"commit": sha, "date": date, "message": subject})
    return history


def diff(project_id: str, rel_path: str, from_commit: str | None = None, to_commit: str | None = None) -> str:
    root = repo_path(project_id)
    _safe_relpath(project_id, rel_path)
    frm = from_commit or latest_commit_for_parent(project_id, rel_path)
    to = to_commit or "HEAD"
    if not frm:
        return ""
    out = _run(["diff", frm, to, "--", rel_path], cwd=root)
    return out


def latest_commit_for_parent(project_id: str, rel_path: str) -> str | None:
    """Commit before the latest one touching rel_path (for 'previous version')."""
    root = repo_path(project_id)
    out = _run(["log", "-2", "--format=%H", "--", rel_path], cwd=root).strip().splitlines()
    return out[1] if len(out) > 1 else (out[0] if out else None)


def list_files(project_id: str, prefix: str = "") -> list[str]:
    root = repo_path(project_id)
    if not (root / ".git").exists():
        return []
    args = ["ls-files"]
    if prefix:
        args += ["--", prefix]
    out = _run(args, cwd=root)
    return [line for line in out.strip().splitlines() if line]
