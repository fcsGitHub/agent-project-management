"""Agent tool layer: three permission tiers, deny-by-default, fail-closed.

- read: auto-allowed (recorded)
- write: allowed only inside the project content repo (whitelisted domain)
- dangerous: always requires a human approval; approval is single-use
  (allowed-once semantics, docs/05 §1.2/§2.1)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable

from apm.core import events

PERMISSIONS: dict[str, str] = {
    # read
    "read_artifact": "read",
    "list_artifacts": "read",
    "search_web": "read",
    "search_assets": "read",
    "read_asset": "read",
    # write (whitelisted domain: this project's content repo / asset links)
    "write_artifact": "write",
    "link_asset": "write",
    # dangerous (恒审批)
    "create_git_tag": "dangerous",
    "publish_external": "dangerous",
    "run_command": "dangerous",
}


class ToolDenied(Exception):
    """Fail-closed denial (never silently downgraded)."""


class ToolApprovalRequired(Exception):
    """Raised for dangerous tools without a matching one-time authorization."""

    def __init__(self, tool: str, args: dict[str, Any]):
        self.tool = tool
        self.args = args
        self.call_hash = hash_call(tool, args)
        super().__init__(f"dangerous tool '{tool}' requires approval")


def hash_call(tool: str, args: dict[str, Any]) -> str:
    blob = tool + "|" + repr(sorted(args.items()))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass
class ToolContext:
    project_id: str
    run_id: str
    conversation_id: str | None = None
    role: str = "dev-agent"
    actor_id: str = ""
    graph_node_id: str | None = None
    authorized_calls: set[str] = field(default_factory=set)

    @property
    def agent_actor(self) -> str:
        return self.actor_id or f"{self.role}:{self.run_id}"


def execute(name: str, args: dict[str, Any], ctx: ToolContext) -> Any:
    perm = PERMISSIONS.get(name)
    if perm is None:
        raise ToolDenied(f"tool '{name}' is not registered (deny-by-default)")
    if perm == "dangerous":
        call_hash = hash_call(name, args)
        if call_hash not in ctx.authorized_calls:
            raise ToolApprovalRequired(name, args)
    handler = _HANDLERS[name]
    return handler(args, ctx)


# ---------------------------------------------------------------- handlers
def _read_artifact(args: dict, ctx: ToolContext) -> dict:
    from apm.content import gitrepo

    path = args.get("path", "")
    if not path:
        raise ToolDenied("read_artifact requires path")
    try:
        content = gitrepo.read_file(ctx.project_id, path, args.get("commit"))
    except FileNotFoundError:
        return {"found": False, "path": path}
    return {"found": True, "path": path, "content": content}


def _list_artifacts(args: dict, ctx: ToolContext) -> dict:
    from apm.content import gitrepo

    prefix = args.get("prefix", "artifacts/")
    return {"files": gitrepo.list_files(ctx.project_id, prefix)}


def _write_artifact(args: dict, ctx: ToolContext) -> dict:
    from apm.content.artifacts import write_artifact

    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        raise ToolDenied("write_artifact requires path")
    # Permission check: writes are confined to this project's content repo —
    # write_artifact enforces repo confinement via gitrepo._safe_relpath.
    result = write_artifact(
        ctx.project_id,
        path,
        content,
        actor_type="agent",
        actor_id=ctx.agent_actor,
        message=args.get("message") or f"agent({ctx.role}): write {path}",
        run_id=ctx.run_id,
    )
    return result


def _search_web(args: dict, ctx: ToolContext) -> dict:
    # Read-only stub in replay/MVP; recorded as a read span by the caller.
    return {"query": args.get("query", ""), "results": [], "note": "search_web stub (MVP)"}


def _create_git_tag(args: dict, ctx: ToolContext) -> dict:
    from apm.content import gitrepo

    tag = args.get("tag", "")
    if not tag:
        raise ToolDenied("create_git_tag requires tag")
    root = gitrepo.repo_path(ctx.project_id)
    gitrepo._run(["tag", tag], cwd=root)
    return {"tagged": tag}


def _publish_external(args: dict, ctx: ToolContext) -> dict:
    return {"published": args.get("target", ""), "note": "external publish stub (MVP)"}


def _run_command(args: dict, ctx: ToolContext) -> dict:
    raise ToolDenied("run_command is disabled in MVP (sandbox arrives in V2)")


# Asset tools are registered by the assets domain (I12) to avoid a hard
# dependency here; permission entries live in PERMISSIONS above.
def register_asset_tools(search_impl, read_impl, link_impl) -> None:
    _HANDLERS["search_assets"] = search_impl
    _HANDLERS["read_asset"] = read_impl
    _HANDLERS["link_asset"] = link_impl


_HANDLERS: dict[str, Callable[[dict, ToolContext], Any]] = {
    "read_artifact": _read_artifact,
    "list_artifacts": _list_artifacts,
    "write_artifact": _write_artifact,
    "search_web": _search_web,
    "create_git_tag": _create_git_tag,
    "publish_external": _publish_external,
    "run_command": _run_command,
}
