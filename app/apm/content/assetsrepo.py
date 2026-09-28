"""Assets repo: one global Git repo holding all library assets (docs/09 §7)."""
from __future__ import annotations

from pathlib import Path

from apm import config
from apm.content.gitrepo import GitError, _run


def repo_root() -> Path:
    return config.settings.assets_repo_path


def ensure_repo() -> Path:
    root = repo_root()
    if not (root / ".git").exists():
        root.mkdir(parents=True, exist_ok=True)
        _run(["init", "-q", "-b", "main"], cwd=root)
    return root


def asset_path(library_id: str, asset_id: str) -> str:
    return f"libraries/{library_id}/{asset_id}/asset.md"


def write_asset(
    library_id: str, asset_id: str, frontmatter: dict[str, object], body: str
) -> str:
    ensure_repo()
    fm_lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    content = "\n".join(fm_lines) + "\n\n" + body + "\n"
    rel = asset_path(library_id, asset_id)
    target = repo_root() / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    _run(["add", "--", rel], cwd=repo_root())
    _run(["commit", "-q", "-m", f"asset: {asset_id} ({frontmatter.get('status', 'draft')})",
          "-m", f"Actor: system(asset:{asset_id})"], cwd=repo_root())
    out = _run(["log", "-1", "--format=%H"], cwd=repo_root())
    return out.strip()


def read_asset_body(library_id: str, asset_id: str) -> str:
    rel = asset_path(library_id, asset_id)
    path = repo_root() / rel
    if not path.exists():
        raise FileNotFoundError(rel)
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            return text[end + 3:].strip()
    return text


def asset_log(library_id: str, asset_id: str, limit: int = 50) -> list[dict]:
    """M70-I210: version history of one asset — every write_asset is a commit,
    so the ledger already exists; this is its read side (gitrepo.file_history
    mirror, but against the assets repo, not a project repo)."""
    rel = asset_path(library_id, asset_id)
    out = _run(
        ["log", f"-{limit}", "--format=%H|%ad|%s", "--date=iso", "--", rel], cwd=repo_root()
    )
    history = []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        sha, date, subject = line.split("|", 2)
        history.append({"commit": sha, "date": date, "message": subject})
    return history


def asset_diff(library_id: str, asset_id: str, from_commit: str, to_commit: str) -> str:
    rel = asset_path(library_id, asset_id)
    out = _run(["diff", from_commit, to_commit, "--", rel], cwd=repo_root())
    return out


def asset_body_at(library_id: str, asset_id: str, commit: str) -> str:
    """Body at a historical commit (frontmatter stripped like read_asset_body)."""
    rel = asset_path(library_id, asset_id)
    text = _run(["show", f"{commit}:{rel}"], cwd=repo_root())
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            return text[end + 3:].strip()
    return text
