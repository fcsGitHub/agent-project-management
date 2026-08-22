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
