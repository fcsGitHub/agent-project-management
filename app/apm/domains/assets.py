"""Asset domain: deposit → review gate → publish → search/consume (docs/09)."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm import config
from apm.content import assetsrepo
from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["assets"])


# ------------------------------------------------------------ FTS helpers
def _bigrams(text: str) -> str:
    """Chinese char bigrams + latin words (SQLite FTS5 has no CJK tokenizer)."""
    tokens: list[str] = []
    for latin in re.findall(r"[A-Za-z0-9_-]+", text):
        tokens.append(latin.lower())
    cjk = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in cjk:
        if len(run) == 1:
            tokens.append(run)
        for i in range(len(run) - 1):
            tokens.append(run[i : i + 2])
    return " ".join(tokens)


def _reindex(conn, asset_id: str) -> None:
    row = conn.execute(
        "SELECT a.id, a.title, a.kind, a.tags, a.status FROM assets a WHERE a.id = ?", (asset_id,)
    ).fetchone()
    conn.execute("DELETE FROM assets_fts WHERE asset_id = ?", (asset_id,))
    if not row or row["status"] in ("archived",):
        return
    try:
        body = assetsrepo.read_asset_body(
            conn.execute("SELECT library_id FROM assets WHERE id = ?", (asset_id,)).fetchone()["library_id"],
            asset_id,
        )
    except Exception:
        body = ""
    text = _bigrams(f"{row['title']} {row['kind']} {row['tags'] or ''} {body}")
    conn.execute("INSERT INTO assets_fts (asset_id, text) VALUES (?, ?)", (asset_id, text))


def _fts_query(q: str) -> list[str]:
    return [r["asset_id"] for r in db.get_conn().execute(
        "SELECT asset_id FROM assets_fts WHERE assets_fts MATCH ? ORDER BY rank", (_bigrams(q) or "*",)
    ).fetchall()]


# ------------------------------------------------------------ projections
@on("asset.drafted", "asset.in_review", "asset.published", "asset.deprecated", "asset.archived")
def _proj_asset_upsert(conn, e):
    p = e.payload
    existing = conn.execute("SELECT version FROM assets WHERE id = ?", (e.agg_id,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE assets SET status = ?, updated_at = ?, title = ?, tags = ?, version = version + 1"
            " WHERE id = ?",
            (p.get("status", "draft"), e.ts, p.get("title"), json.dumps(p.get("tags") or [], ensure_ascii=False), e.agg_id),
        )
    else:
        conn.execute(
            "INSERT INTO assets (id, library_id, kind, title, status, tags, owner_id, version,"
            " git_path, commit_sha, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                e.agg_id, p["library"], p["kind"], p.get("title", ""), p.get("status", "draft"),
                json.dumps(p.get("tags") or [], ensure_ascii=False), e.actor_id, 1,
                assetsrepo.asset_path(p["library"], e.agg_id), p.get("commit", ""),
                e.ts, e.ts,
            ),
        )
    _reindex(conn, e.agg_id)


@on("asset.linked")
def _proj_asset_linked(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO asset_links (id, asset_id, type, target_type, target_ref, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (new_id("al"), e.agg_id, p["type"], p["target_type"], json.dumps(p["target"], ensure_ascii=False), e.ts),
    )
    if p["type"] == "usage":
        conn.execute(
            "UPDATE assets SET citation_count = citation_count + 1, updated_at = ? WHERE id = ?",
            (e.ts, e.agg_id),
        )


@on("asset.consumed")
def _proj_asset_consumed(conn, e):
    conn.execute("UPDATE assets SET updated_at = ? WHERE id = ?", (e.ts, e.agg_id))


@on("asset.superseded")
def _proj_asset_superseded(conn, e):
    conn.execute(
        "UPDATE assets SET status = 'deprecated', updated_at = ? WHERE id = ?", (e.ts, e.agg_id)
    )


# ---------------------------------------------------------------- helpers
def get_asset(asset_id: str) -> dict | None:
    row = db.get_conn().execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return dict(row) if row else None


def require_asset(asset_id: str) -> dict:
    a = get_asset(asset_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"asset {asset_id} not found")
    return a


def _links(asset_id: str, type_: str) -> list[dict]:
    rows = db.get_conn().execute(
        "SELECT * FROM asset_links WHERE asset_id = ? AND type = ? ORDER BY created_at",
        (asset_id, type_),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["target"] = json.loads(d["target_ref"])
        out.append(d)
    return out


def deposit(
    *,
    source_project_id: str,
    artifact_path: str,
    commit: str | None,
    library: str,
    kind: str,
    title: str,
    tags: list[str] | None = None,
    body: str | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
    actor_type: str = "human",
    actor_id: str | None = None,
) -> dict:
    """Path A manual deposit: artifact → draft asset with provenance link."""
    from apm.domains.ontology import load_ontology
    from apm.domains.projects import require_project

    project = require_project(source_project_id)
    onto = load_ontology(project["ontology"])
    lib = next((l for l in onto.libraries if l["id"] == library), None)
    if not lib:
        raise HTTPException(status_code=422, detail=f"unknown library '{library}'")
    kinds = {k["id"] for k in onto.asset_kinds}
    if kind not in kinds or kind not in set(lib["accepts"]):
        raise HTTPException(status_code=422, detail=f"kind '{kind}' not accepted by library '{library}'")

    if body is None:
        from apm.content import gitrepo

        try:
            body = gitrepo.read_file(source_project_id, artifact_path, commit)
        except (FileNotFoundError, gitrepo.GitError) as e:
            raise HTTPException(status_code=404, detail=f"artifact not found: {e}")

    aid = new_id("a")
    sha = assetsrepo.write_asset(
        library, aid,
        {"title": title, "kind": kind, "library": library, "tags": tags or [],
         "status": "draft", "owner": actor_id or config.settings.user_id},
        body,
    )
    provenance: dict = {"project_id": source_project_id, "path": artifact_path,
                        "commit": commit, "conversation_id": conversation_id}
    if run_id:
        provenance["run_id"] = run_id  # M68-I205: auto deposits trace to their run
    events.emit(
        event_type="asset.drafted",
        agg_type="asset",
        agg_id=aid,
        project_id=source_project_id,
        actor_type=actor_type,
        actor_id=actor_id or config.settings.user_id,
        payload={"library": library, "kind": kind, "title": title, "tags": tags or [],
                 "commit": sha, "status": "draft"},
    )
    events.emit(
        event_type="asset.linked",
        agg_type="asset",
        agg_id=aid,
        project_id=source_project_id,
        actor_type=actor_type,
        actor_id=actor_id or config.settings.user_id,
        payload={"type": "provenance", "target_type": "artifact",
                 "target": provenance},
    )
    return get_asset(aid)  # type: ignore[return-value]


# ------------------------------------------- M68-I205: auto deposit (docs/01 §BM.2)
# run.succeeded × projects.auto_deposit → the run's artifact becomes a draft
# asset automatically. CAS discipline: git already content-addresses the
# bodies, so dedup is a plain sha256 compare — exact match only (SimHash
# fuzzy matching is deliberately out). The review gate is NOT bypassed:
# auto deposits stop at draft. Queue + worker thread: deposit does git I/O
# and must never block the write path (mailer/pusher mirror).
import logging
import queue
import threading

logger = logging.getLogger(__name__)

_ad_queue: "queue.Queue[dict]" = queue.Queue(maxsize=200)
_ad_worker: threading.Thread | None = None


def install_auto_deposit() -> None:
    """Idempotent: wire the run.succeeded hook + start the worker."""
    global _ad_worker
    events.add_post_emit_hook(_auto_deposit_enqueue)
    if _ad_worker is None or not _ad_worker.is_alive():
        _ad_worker = threading.Thread(target=_ad_worker_loop, name="apm-autodeposit", daemon=True)
        _ad_worker.start()


def _auto_deposit_enqueue(event: events.Event) -> None:
    """Post-emit hook: cheap checks inline (project setting + payload shape),
    git work deferred to the worker. Never raises into the request path."""
    if event.event_type != "run.succeeded" or not event.project_id:
        return
    output = event.payload.get("output") if isinstance(event.payload, dict) else None
    path = output.get("artifact_path") if isinstance(output, dict) else None
    if not path:
        return
    row = db.get_conn().execute(
        "SELECT auto_deposit FROM projects WHERE id = ?", (event.project_id,)).fetchone()
    if not row or not row["auto_deposit"]:
        return
    try:
        _ad_queue.put_nowait({"project_id": event.project_id,
                              "run_id": event.agg_id, "path": path})
    except queue.Full:
        logger.warning("auto-deposit queue full; dropping %s", path)


def _ad_worker_loop() -> None:
    while True:
        item = _ad_queue.get()
        try:
            _auto_deposit(item)
        except Exception:  # the worker must survive anything
            logger.exception("auto deposit crashed on %s", item)
        finally:
            _ad_queue.task_done()


def _auto_deposit(item: dict) -> None:
    from apm.content import gitrepo
    from apm.domains.ontology import load_ontology

    try:
        body = gitrepo.read_file(item["project_id"], item["path"])
    except (FileNotFoundError, gitrepo.GitError):
        return  # artifact unreadable — nothing to deposit
    import hashlib

    # normalize like read_asset_body (strips) so both sides hash identically
    sha = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
    # dedup: exact body match among assets already provenance-linked to this project
    conn = db.get_conn()
    linked = conn.execute(
        "SELECT asset_id, target_ref FROM asset_links WHERE type = 'provenance'").fetchall()
    for link in linked:
        try:
            target = json.loads(link["target_ref"] or "{}")
        except ValueError:
            continue
        if target.get("project_id") != item["project_id"]:
            continue
        row = conn.execute("SELECT library_id FROM assets WHERE id = ?",
                           (link["asset_id"],)).fetchone()
        if not row:
            continue
        try:
            existing = assetsrepo.read_asset_body(row["library_id"], link["asset_id"])
        except FileNotFoundError:
            continue
        if hashlib.sha256(existing.strip().encode("utf-8")).hexdigest() == sha:
            logger.info("auto deposit: deduped %s (same content as asset %s)",
                        item["path"], link["asset_id"])
            return

    project = conn.execute("SELECT ontology FROM projects WHERE id = ?",
                           (item["project_id"],)).fetchone()
    if not project:
        return
    onto = load_ontology(project["ontology"])
    parts = item["path"].split("/")
    kind_id = parts[1] if len(parts) > 2 and parts[0] == "artifacts" else ""
    # artifact kind → deposits_to ASSET kind → the library that accepts it
    asset_kind = None
    for c in onto.concepts.values():
        for ak in c.artifact_kinds:
            if ak.get("id") == kind_id and ak.get("deposits_to"):
                asset_kind = ak["deposits_to"]
    if not asset_kind:
        logger.info("auto deposit: kind '%s' has no deposits_to — skipping", kind_id)
        return
    library = next((l["id"] for l in onto.libraries
                    if asset_kind in l.get("accepts", [])), None)
    if not library:
        logger.info("auto deposit: no library accepts asset kind '%s'", asset_kind)
        return
    deposit(
        source_project_id=item["project_id"],
        artifact_path=item["path"],
        commit=None,
        library=library,
        kind=asset_kind,
        title=f"自动沉淀 · {parts[-1]}",
        tags=["auto"],
        run_id=item["run_id"],
        actor_type="system",
        actor_id=f"runtime:{item['run_id']}",
    )


def submit_review(asset_id: str) -> dict:
    asset = require_asset(asset_id)
    if asset["status"] != "draft":
        raise HTTPException(status_code=422, detail=f"asset is {asset['status']}, expected draft")
    from apm.domains.approvals import _request

    body = assetsrepo.read_asset_body(asset["library_id"], asset_id)
    approval = _request(
        kind="gate",
        snapshot={
            "gate": "asset_review",
            "asset_id": asset_id,
            "title": asset["title"],
            "library": asset["library_id"],
            "kind": asset["kind"],
            "summary": f"资产入库评审：{asset['title']} → {asset['library_id']}",
            "preview": body[:600],
        },
        project_id="",
    )
    events.emit(
        event_type="asset.in_review",
        agg_type="asset",
        agg_id=asset_id,
        actor_type="human",
        actor_id=config.settings.user_id,
        payload={"status": "in_review", "title": asset["title"], "library": asset["library_id"],
                 "kind": asset["kind"], "approval_id": approval["id"]},
    )
    return {"asset": get_asset(asset_id), "approval_id": approval["id"]}


def publish_from_approval(approval: dict) -> dict | None:
    """Called when an asset_review gate approval is granted."""
    snap = approval.get("payload_snapshot") or {}
    if snap.get("gate") != "asset_review":
        return None
    asset_id = snap.get("asset_id")
    asset = get_asset(asset_id) if asset_id else None
    if not asset:
        return None
    sha = assetsrepo.write_asset(
        asset["library_id"], asset_id,
        {"title": asset["title"], "kind": asset["kind"], "library": asset["library_id"],
         "status": "published"},
        assetsrepo.read_asset_body(asset["library_id"], asset_id),
    )
    events.emit(
        event_type="asset.published",
        agg_type="asset",
        agg_id=asset_id,
        actor_type="human",
        actor_id=config.settings.user_id,
        payload={"status": "published", "commit": sha, "title": asset["title"],
                 "library": asset["library_id"], "kind": asset["kind"]},
    )
    return get_asset(asset_id)


def link_usage(
    asset_id: str, *, project_id: str, artifact_path: str | None = None,
    conversation_id: str | None = None, actor_type: str = "agent", actor_id: str = "",
) -> dict:
    asset = require_asset(asset_id)
    events.emit(
        event_type="asset.linked",
        agg_type="asset",
        agg_id=asset_id,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id or "agent",
        payload={"type": "usage", "target_type": "project",
                 "target": {"project_id": project_id, "path": artifact_path,
                            "conversation_id": conversation_id}},
    )
    events.emit(
        event_type="asset.consumed",
        agg_type="asset",
        agg_id=asset_id,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id or "agent",
        payload={"by": actor_id or "agent", "project_id": project_id},
    )
    return get_asset(asset_id)  # type: ignore[return-value]


def search(query: str | None, library: str | None, kind: str | None, tag: str | None) -> list[dict]:
    where, params = ["status != 'archived'"], []
    if library:
        where.append("library_id = ?")
        params.append(library)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if tag:
        where.append("tags LIKE ?")
        params.append(f'%"{tag}"%')
    if query and query.strip():
        ids = _fts_query(query.strip())
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        where.append(f"id IN ({marks})")
        params.extend(ids)
    rows = db.get_conn().execute(
        f"SELECT * FROM assets WHERE {' AND '.join(where)} ORDER BY citation_count DESC, updated_at DESC",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------ agent tools
def install_agent_tools() -> None:
    from apm.runtime import tools

    def _search(args: dict, ctx: "tools.ToolContext") -> dict:
        results = search(args.get("query", ""), args.get("library"), args.get("kind"), args.get("tag"))
        return {"results": [
            {"id": a["id"], "title": a["title"], "kind": a["kind"], "library": a["library_id"],
             "citations": a["citation_count"], "status": a["status"]} for a in results[:10]
        ]}

    def _read(args: dict, ctx: "tools.ToolContext") -> dict:
        asset = get_asset(args.get("id", ""))
        if not asset:
            return {"found": False}
        body = assetsrepo.read_asset_body(asset["library_id"], asset["id"])
        return {"found": True, "title": asset["title"], "kind": asset["kind"], "content": body}

    def _link(args: dict, ctx: "tools.ToolContext") -> dict:
        asset = link_usage(
            args.get("id", ""),
            project_id=ctx.project_id,
            artifact_path=args.get("artifact_path"),
            conversation_id=ctx.conversation_id,
            actor_type="agent",
            actor_id=ctx.agent_actor,
        )
        return {"linked": asset["id"], "citations": asset["citation_count"]}

    tools.register_asset_tools(_search, _read, _link)


# -------------------------------------------------------------------- API
class DepositIn(BaseModel):
    source_project_id: str
    artifact_path: str
    commit: str | None = None
    library: str
    kind: str
    title: str
    tags: list[str] | None = None
    conversation_id: str | None = None


class LinkIn(BaseModel):
    project_id: str
    artifact_path: str | None = None
    conversation_id: str | None = None


@router.get("/assets")
def list_assets(
    library: str | None = None, kind: str | None = None, q: str | None = None, tag: str | None = None
) -> dict:
    return {"assets": search(q, library, kind, tag)}


# NOTE: registered before "/assets/{asset_id}" so "insights" is not eaten as
# an asset id by FastAPI's first-match routing.
@router.get("/assets/insights")
def get_asset_insights() -> dict:
    """Registry trust signals (M57-I172, docs/01 §BB.2): usage telemetry over
    the asset.consumed / asset.linked facts that have been on the stream since
    M6 — a pure read-side projection, zero instrumentation (npm-style usage
    counts and staleness, translated for an org-internal library)."""
    return asset_insights()


def asset_insights(now: str | None = None) -> dict:
    """Aggregate per-asset usage. Sort: most consumed first; linked count and
    deposit order break ties. Stale = published, never consumed, and older
    than 90 days (the deprecation candidate list); `now` is injectable so the
    rule stays testable without sleeping."""
    conn = db.get_conn()
    now_ts = now or events.utcnow()
    consumed: dict[str, int] = {}
    last_consumed: dict[str, str] = {}
    linked: dict[str, int] = {}
    for r in conn.execute(
            "SELECT event_type, agg_id, ts, payload FROM events"
            " WHERE event_type IN ('asset.consumed','asset.linked') ORDER BY id"):
        if r["event_type"] == "asset.consumed":
            consumed[r["agg_id"]] = consumed.get(r["agg_id"], 0) + 1
            last_consumed[r["agg_id"]] = r["ts"]
        else:
            # only usage-type links count — deposit-time provenance links are
            # not reuses (same semantics as the citation_count projection)
            p = json.loads(r["payload"] or "{}")
            if p.get("type") == "usage":
                linked[r["agg_id"]] = linked.get(r["agg_id"], 0) + 1
    from datetime import datetime as _dt
    now_d = _dt.fromisoformat(now_ts)
    out = []
    for a in conn.execute("SELECT * FROM assets ORDER BY created_at, id").fetchall():
        c = consumed.get(a["id"], 0)
        age_days = max(0, (now_d - _dt.fromisoformat(a["created_at"])).days)
        item = dict(a)
        item["consumed_count"] = c
        item["last_consumed"] = last_consumed.get(a["id"])
        item["linked_count"] = linked.get(a["id"], 0)
        item["age_days"] = age_days
        item["stale"] = bool(a["status"] == "published" and c == 0 and age_days > 90)
        out.append(item)
    out.sort(key=lambda x: (-x["consumed_count"], -x["linked_count"], x["created_at"]))
    return {"assets": out}


@router.post("/assets")
def post_asset(body: DepositIn) -> dict:
    return deposit(
        source_project_id=body.source_project_id,
        artifact_path=body.artifact_path,
        commit=body.commit,
        library=body.library,
        kind=body.kind,
        title=body.title,
        tags=body.tags,
        conversation_id=body.conversation_id,
    )


@router.post("/assets/{asset_id}/submit_review")
def post_submit_review(asset_id: str) -> dict:
    return submit_review(asset_id)


@router.get("/assets/{asset_id}")
def get_asset_detail(asset_id: str) -> dict:
    asset = require_asset(asset_id)
    asset["tags"] = json.loads(asset["tags"] or "[]")
    asset["provenance"] = _links(asset_id, "provenance")
    asset["usages"] = _links(asset_id, "usage")
    try:
        asset["content"] = assetsrepo.read_asset_body(asset["library_id"], asset_id)
    except FileNotFoundError:
        asset["content"] = None
    return asset


@router.post("/assets/{asset_id}/link")
def post_link(asset_id: str, body: LinkIn) -> dict:
    return link_usage(
        asset_id, project_id=body.project_id, artifact_path=body.artifact_path,
        conversation_id=body.conversation_id, actor_type="human",
        actor_id=config.settings.user_id,
    )
