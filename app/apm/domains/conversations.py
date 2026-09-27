"""Conversation domain: persistent, interruptible human-agent interaction units.

Conversation = append-only message event stream (message tree with parent_id),
with L1-L4 layered prompt assembly (docs/03 §2-§3). Sending a message while a
run is executing interrupts it and injects the message as new instruction
context.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["conversations"])

CONVERSATION_KINDS = ("drafting", "executing", "reviewing", "adhoc", "ui_command")
ACTIVE_STATUSES = ("active", "running", "interrupted", "awaiting_review")

L0_SYSTEM = (
    "你是 AgentPM 中的角色化 Agent。安全规范：文件写入仅限项目内容仓；"
    "危险操作必须请求人工审批；输出使用 Markdown。"
)


# ------------------------------------------------------------ projections
@on("conversation.created")
def _proj_conv_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO conversations (id, project_id, feature_id, kind, title, status, item_id,"
        " run_id, parent_conversation_id, seed_length, instruction, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            e.agg_id,
            e.project_id,
            p.get("feature_id"),
            p.get("kind", "adhoc"),
            p.get("title"),
            p.get("status", "active"),
            p.get("item_id"),
            p.get("run_id"),
            p.get("parent_conversation_id"),
            p.get("seed_length"),
            p.get("instruction"),
            e.ts,
            e.ts,
        ),
    )


@on("conversation.interrupted")
def _proj_conv_interrupted(conn, e):
    conn.execute(
        "UPDATE conversations SET status = 'interrupted', updated_at = ? WHERE id = ?", (e.ts, e.agg_id)
    )


@on("conversation.resumed")
def _proj_conv_resumed(conn, e):
    conn.execute(
        "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
        (e.payload.get("status", "active"), e.ts, e.agg_id),
    )


@on("conversation.archived")
def _proj_conv_archived(conn, e):
    conn.execute(
        "UPDATE conversations SET status = 'archived', updated_at = ? WHERE id = ?", (e.ts, e.agg_id)
    )


@on("conversation.status_changed")
def _proj_conv_status(conn, e):
    conn.execute(
        "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
        (e.payload.get("status", "active"), e.ts, e.agg_id),
    )


@on("conversation.instruction_updated")
def _proj_conv_instruction(conn, e):
    conn.execute(
        "UPDATE conversations SET instruction = ?, updated_at = ? WHERE id = ?",
        (e.payload.get("instruction"), e.ts, e.agg_id),
    )


@on("message.created")
def _proj_message(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO messages (id, conversation_id, parent_id, role, actor_type, actor_id,"
        " content, span_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            e.agg_id,
            e.payload["conversation_id"],
            p.get("parent_id"),
            p.get("role", "user"),
            e.actor_type,
            e.actor_id,
            p.get("content", ""),
            p.get("span_id"),
            e.ts,
        ),
    )


@on("project.created")
def _proj_prompt_seed(conn, e):
    """Project creation seeds the L1 charter prompt layer at version 1."""
    conn.execute(
        "INSERT OR IGNORE INTO prompt_layers (id, project_id, level, feature_id, agent_role,"
        " git_path, version, updated_by, updated_at) VALUES (?,?,?,?,?,?,1,'system',?)",
        (f"{e.agg_id}:L1_charter::", e.agg_id, "L1_charter", None, None, "prompts/charter.md", e.ts),
    )


@on("prompt.updated")
def _proj_prompt(conn, e):
    p = e.payload
    level = p["level"]
    if level == "L1_charter":
        layer_id = f"{e.project_id}:L1_charter::"  # one layer per project
    elif level == "L3_instruction":
        layer_id = f"{e.project_id}:L3_instruction::{p.get('conversation_id') or ''}"
    else:  # L2/L4 land in later versions; keyed by feature/role scope
        layer_id = f"{e.project_id}:{level}:{p.get('feature_id') or ''}:{p.get('agent_role') or ''}"
    git_path = p.get(
        "git_path",
        "prompts/charter.md" if p["level"] == "L1_charter" else "prompts/roles/unknown.md",
    )
    existing = conn.execute(
        "SELECT version FROM prompt_layers WHERE id = ?", (layer_id,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE prompt_layers SET version = version + 1, updated_by = ?, updated_at = ?,"
            " git_path = ? WHERE id = ?",
            (e.actor_id, e.ts, git_path, layer_id),
        )
    else:
        conn.execute(
            "INSERT INTO prompt_layers (id, project_id, level, feature_id, agent_role, git_path,"
            " version, updated_by, updated_at) VALUES (?,?,?,?,?,?,1,?,?)",
            (layer_id, e.project_id, p["level"], p.get("feature_id"), p.get("agent_role"), git_path, e.actor_id, e.ts),
        )


# ---------------------------------------------------------------- helpers
def get_conversation(conversation_id: str) -> dict | None:
    row = db.get_conn().execute(
        "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    return dict(row) if row else None


def require_conversation(conversation_id: str) -> dict:
    c = get_conversation(conversation_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"conversation {conversation_id} not found")
    return c


def create_conversation(
    *,
    project_id: str,
    feature_id: str | None = None,
    kind: str = "adhoc",
    title: str | None = None,
    instruction: str | None = None,
    item_id: str | None = None,
    actor_type: str = "human",
    actor_id: str | None = None,
) -> dict:
    if kind not in CONVERSATION_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {CONVERSATION_KINDS}")
    cid = new_id("c")
    events.emit(
        event_type="conversation.created",
        agg_type="conversation",
        agg_id=cid,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        payload={
            "feature_id": feature_id,
            "kind": kind,
            "title": title,
            "status": "active",
            "item_id": item_id,
            "instruction": instruction,
        },
    )
    return get_conversation(cid)  # type: ignore[return-value]


def list_conversations(
    *, project_id: str | None = None, feature_id: str | None = None, include_archived: bool = False
) -> list[dict]:
    where, params = ["1=1"], []
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if feature_id:
        where.append("feature_id = ?")
        params.append(feature_id)
    if not include_archived:
        where.append("status != 'archived'")
    rows = db.get_conn().execute(
        f"SELECT * FROM conversations WHERE {' AND '.join(where)} ORDER BY updated_at DESC", params
    ).fetchall()
    return [dict(r) for r in rows]


def get_messages(conversation_id: str) -> list[dict]:
    rows = db.get_conn().execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at, id",
        (conversation_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_message(
    conversation: dict,
    *,
    content: str,
    role: str = "user",
    actor_type: str = "human",
    actor_id: str | None = None,
    span_id: str | None = None,
    injected: bool = False,
    parent_id: str | None = None,
) -> dict:
    """Append one message; interrupts a running conversation first (docs/03 §3.2)."""
    interrupted = False
    if role == "user" and conversation["status"] == "running":
        events.emit(
            event_type="conversation.interrupted",
            agg_type="conversation",
            agg_id=conversation["id"],
            project_id=conversation["project_id"],
            payload={"reason": "user_message_injection"},
        )
        interrupted = True
    if parent_id is None:
        last = db.get_conn().execute(
            "SELECT id FROM messages WHERE conversation_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (conversation["id"],),
        ).fetchone()
        parent_id = last["id"] if last else None
    mid = new_id("m")
    events.emit(
        event_type="message.created",
        agg_type="message",
        agg_id=mid,
        project_id=conversation["project_id"],
        actor_type=actor_type,
        actor_id=actor_id,
        payload={
            "conversation_id": conversation["id"],
            "parent_id": parent_id,
            "role": role,
            "content": content,
            "span_id": span_id,
            "injected": injected,
        },
    )
    if interrupted:
        from apm.runtime import runkeeper

        runkeeper.mark_interrupted_for_conversation(conversation["id"])
    message = db.get_conn().execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone()
    return {"message": dict(message), "interrupted": interrupted}


# --------------------------------------------------------- prompt layers
def _prompt_version(project_id: str, level: str, conversation_id: str | None) -> int:
    row = db.get_conn().execute(
        "SELECT version FROM prompt_layers WHERE id = ?",
        (f"{project_id}:{level}::{conversation_id or ''}",),
    ).fetchone()
    return row["version"] if row else 1


def build_context(conversation: dict) -> dict:
    """Assemble L0-L4 layered context + merged effective prompt (docs/03 §2)."""
    from apm.domains.features import get_feature
    from apm.domains.projects import get_project

    project = get_project(conversation["project_id"]) or {}
    charter = project.get("charter") or ""
    brief = None
    if conversation.get("feature_id"):
        feature = get_feature(conversation["feature_id"])
        brief = feature.get("brief") if feature else None
    instruction = conversation.get("instruction")
    l1_over = len(charter) > 2000
    l2_over = bool(brief and len(brief) > 3200)
    merged = (
        f"[L0 全局系统提示]\n{L0_SYSTEM}\n\n"
        f"[L1 项目宪章 · {project.get('name', '')}]\n{charter}\n\n"
        f"[L2 功能简报]\n{brief or '（无）'}\n\n"
        f"[L3 会话指令]\n{instruction or '（无）'}\n\n"
        "[L4 角色提示词]\n（由 Run 的角色 YAML 提供，见 agents/roles/*.md）"
    )
    return {
        "conversation_id": conversation["id"],
        "L0": {"content": L0_SYSTEM, "editable": False},
        "L1": {
            "content": charter,
            "version": _prompt_version(conversation["project_id"], "L1_charter", None),
            "git_path": "prompts/charter.md",
            "editable": True,
            "budget_chars": 2000,
            "budget_exceeded": l1_over,
        },
        "L2": {
            "content": brief,
            "git_path": f"prompts/features/{conversation.get('feature_id')}/brief.md",
            "editable": False,  # L2 editing lands in V1.1 (docs/03 §2)
        },
        "L3": {
            "content": instruction,
            "version": _prompt_version(conversation["project_id"], "L3_instruction", conversation["id"]),
            "git_path": f"prompts/conversations/{conversation['id']}/instruction.md",
            "editable": True,
            "budget_exceeded": False,
        },
        "L4": {
            "content": None,
            "git_path": "agents/prompts/roles/*.md",
            "editable": False,
        },
        "merged_preview": merged,
    }


def update_prompt_layer(conversation: dict, level: str, content: str) -> dict:
    from apm import config as apm_config
    from apm.content import prompts as prompt_files

    if level == "L1":
        events.emit(
            event_type="prompt.updated",
            agg_type="project",
            agg_id=conversation["project_id"],
            project_id=conversation["project_id"],
            payload={
                "level": "L1_charter",
                "content": content,
                "git_path": "prompts/charter.md",
                "conversation_id": conversation["id"],
            },
        )
        events.emit(
            event_type="project.updated",
            agg_type="project",
            agg_id=conversation["project_id"],
            project_id=conversation["project_id"],
            payload={"charter": content},
        )
        prompt_files.write_prompt(
            conversation["project_id"],
            "prompts/charter.md",
            content,
            actor_type="human",
            actor_id=apm_config.settings.user_id,
        )
    elif level == "L3":
        git_path = f"prompts/conversations/{conversation['id']}/instruction.md"
        events.emit(
            event_type="prompt.updated",
            agg_type="conversation",
            agg_id=conversation["id"],
            project_id=conversation["project_id"],
            payload={
                "level": "L3_instruction",
                "content": content,
                "git_path": git_path,
                "conversation_id": conversation["id"],
            },
        )
        events.emit(
            event_type="conversation.instruction_updated",
            agg_type="conversation",
            agg_id=conversation["id"],
            project_id=conversation["project_id"],
            payload={"instruction": content},
        )
        prompt_files.write_prompt(
            conversation["project_id"],
            git_path,
            content,
            actor_type="human",
            actor_id=apm_config.settings.user_id,
        )
    else:
        raise HTTPException(status_code=422, detail=f"level '{level}' is not editable in MVP (L1/L3 only)")
    return build_context(get_conversation(conversation["id"]))  # type: ignore[arg-type]


# ------------------------------------------------------------------ models
class ConversationIn(BaseModel):
    project_id: str
    feature_id: str | None = None
    kind: str = "adhoc"
    title: str | None = None
    instruction: str | None = None
    item_id: str | None = None


class MessageIn(BaseModel):
    content: str
    role: str = "user"


class ResumeIn(BaseModel):
    instruction: str | None = None


class PromptLayerIn(BaseModel):
    content: str


@router.post("/conversations")
def post_conversation(body: ConversationIn) -> dict:
    from apm.domains.projects import require_project

    require_project(body.project_id)
    conv = create_conversation(
        project_id=body.project_id,
        feature_id=body.feature_id,
        kind=body.kind,
        title=body.title,
        instruction=body.instruction,
        item_id=body.item_id,
    )
    conv["context"] = build_context(conv)
    return conv


@router.get("/conversations")
def get_conversations(
    project_id: str | None = None,
    feature_id: str | None = None,
    include_archived: bool = False,
) -> dict:
    return {
        "conversations": list_conversations(
            project_id=project_id, feature_id=feature_id, include_archived=include_archived
        )
    }


@router.get("/conversations/{conversation_id}")
def get_conversation_detail(conversation_id: str) -> dict:
    conv = require_conversation(conversation_id)
    conv["messages"] = get_messages(conversation_id)
    return conv


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str) -> dict:
    require_conversation(conversation_id)
    return {"messages": get_messages(conversation_id)}


@router.get("/conversations/{conversation_id}/export")
def export_conversation(conversation_id: str) -> dict:
    """M61-I184 (docs/01 §BF.3): human-readable Markdown transcript — the
    archive/export answer to the forgotten-conversation problem. The NDJSON
    event export stays the machine channel (§K.3: DB 留存 + 外送语义).
    Visibility matches /search `_visible` scoping."""
    from apm.domains.feed import _visible

    conv = require_conversation(conversation_id)
    me = events.effective_actor()
    user = db.get_conn().execute("SELECT * FROM users WHERE id = ?", (me,)).fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail=f"unknown user '{me}'")
    if not _visible(conv["project_id"], user):
        raise HTTPException(status_code=404, detail=f"conversation {conversation_id} not found")

    msgs = get_messages(conversation_id)
    proj = db.get_conn().execute(
        "SELECT name FROM projects WHERE id = ?", (conv["project_id"],)).fetchone()
    lines = [
        f"# {conv['title'] or '会话'}",
        "",
        f"- 项目：{proj['name'] if proj else conv['project_id']}",
        f"- 类型：{conv['kind']} · 状态：{conv['status']}",
        f"- 起止：{conv['created_at']} → {conv['updated_at']}",
        f"- 消息数：{len(msgs)}",
        "",
        "---",
        "",
    ]
    for m in msgs:
        actor = m["actor_id"] or m["actor_type"] or "?"
        lines.append(f"### {m['created_at']} · {m['role']} · {actor}")
        if m["parent_id"]:
            lines.append(f"> ↳ 回复 {m['parent_id']}")
        lines.extend(["", m["content"], ""])
    return {
        "filename": f"conversation-{conversation_id}.md",
        "markdown": "\n".join(lines),
    }


@router.post("/conversations/{conversation_id}/messages")
def post_message(conversation_id: str, body: MessageIn) -> dict:
    conv = require_conversation(conversation_id)
    if conv["status"] == "archived":
        raise HTTPException(status_code=422, detail="conversation is archived")
    result = add_message(conv, content=body.content, role=body.role)
    result["conversation"] = get_conversation(conversation_id)
    return result


@router.post("/conversations/{conversation_id}/interrupt")
def post_interrupt(conversation_id: str) -> dict:
    conv = require_conversation(conversation_id)
    if conv["status"] not in ("running", "active"):
        raise HTTPException(status_code=422, detail=f"cannot interrupt from status '{conv['status']}'")
    events.emit(
        event_type="conversation.interrupted",
        agg_type="conversation",
        agg_id=conversation_id,
        project_id=conv["project_id"],
        payload={"reason": "manual"},
    )
    from apm.runtime import runkeeper

    runkeeper.mark_interrupted_for_conversation(conversation_id)
    return get_conversation(conversation_id)  # type: ignore[return-value]


@router.post("/conversations/{conversation_id}/resume")
def post_resume(conversation_id: str, body: ResumeIn | None = None) -> dict:
    conv = require_conversation(conversation_id)
    if conv["status"] not in ("interrupted", "awaiting_review", "active"):
        raise HTTPException(status_code=422, detail=f"cannot resume from status '{conv['status']}'")
    instruction = body.instruction if body and body.instruction else None
    payload: dict = {"status": "active"}
    if instruction:
        payload["instruction"] = instruction
        payload["resumed_with_instruction"] = True
    events.emit(
        event_type="conversation.resumed",
        agg_type="conversation",
        agg_id=conversation_id,
        project_id=conv["project_id"],
        payload=payload,
    )
    if instruction:
        add_message(
            get_conversation(conversation_id),  # type: ignore[arg-type]
            content=instruction,
            role="user",
            injected=True,
        )
    from apm.runtime import runkeeper

    runkeeper.request_resume(conversation_id, instruction)
    return get_conversation(conversation_id)  # type: ignore[return-value]


@router.post("/conversations/{conversation_id}/archive")
def post_archive(conversation_id: str) -> dict:
    conv = require_conversation(conversation_id)
    events.emit(
        event_type="conversation.archived",
        agg_type="conversation",
        agg_id=conversation_id,
        project_id=conv["project_id"],
    )
    return get_conversation(conversation_id)  # type: ignore[return-value]


@router.get("/conversations/{conversation_id}/context")
def get_context(conversation_id: str) -> dict:
    conv = require_conversation(conversation_id)
    return build_context(conv)


@router.put("/conversations/{conversation_id}/context/{level}")
def put_context(conversation_id: str, level: str, body: PromptLayerIn) -> dict:
    conv = require_conversation(conversation_id)
    if level not in ("L1", "L3"):
        raise HTTPException(status_code=422, detail="only L1/L3 are editable in MVP")
    return update_prompt_layer(conv, level, body.content)
