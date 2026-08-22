"""I1 event kernel tests: append-only, chain integrity, replay consistency."""
import asyncio
import json
import random
import sqlite3

import pytest

from apm.core import db, events, projections


def _emit_n(n: int, prefix: str = "test.kernel"):
    out = []
    for i in range(n):
        out.append(
            events.emit(
                event_type="test.thing",
                agg_type="test",
                agg_id=f"{prefix}-{i}",
                payload={"i": i},
            )
        )
    return out


def test_events_are_append_only(tmp_data):
    e = _emit_n(3)[0]
    conn = db.get_conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE events SET payload = '{}' WHERE id = ?", (e.id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM events WHERE id = ?", (e.id,))
    assert conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] == 3


def test_prev_event_chain(tmp_data):
    evts = _emit_n(5)
    assert evts[0].prev_event_id == 0
    for prev, cur in zip(evts, evts[1:]):
        assert cur.prev_event_id == prev.id


def test_events_api_filters_and_pagination(client, tmp_data):
    _emit_n(7)
    r = client.get("/api/events?limit=3")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 7
    assert len(body["events"]) == 3
    assert body["events"][0]["id"] > body["events"][1]["id"]  # newest first
    r = client.get("/api/events", params={"event_type": "nope"})
    assert r.json()["total"] == 0


def test_replay_consistency_with_random_event_stream(tmp_data):
    """Live projections must equal a full rebuild after a random event stream."""
    conn = db.get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS scratch (agg_id TEXT PRIMARY KEY, n INTEGER, last TEXT)")
    conn.commit()

    @projections.on("test.thing")
    def _scratch(c, event):
        # Handlers registered in one test persist process-wide for the module;
        # keep the scratch table self-healing across per-test databases.
        c.execute("CREATE TABLE IF NOT EXISTS scratch (agg_id TEXT PRIMARY KEY, n INTEGER, last TEXT)")
        c.execute(
            "INSERT INTO scratch (agg_id, n, last) VALUES (?,?,?)"
            " ON CONFLICT(agg_id) DO UPDATE SET n = n + 1, last = excluded.last",
            (event.agg_id, 1, json.dumps(event.payload)),
        )

    # Earlier tests in this module already emitted test.thing events before the
    # handler existed; rebuild once so live state includes that history, then
    # compare live fold vs full replay for a fresh random segment.
    conn.execute("DELETE FROM scratch")
    conn.commit()
    projections.rebuild()

    rng = random.Random(42)
    n_events = 60
    for i in range(n_events):
        events.emit(
            event_type="test.thing",
            agg_type="test",
            agg_id=f"agg-{rng.randrange(8)}",
            payload={"i": i, "pad": "x" * rng.randrange(5)},
        )

    before = conn.execute("SELECT * FROM scratch ORDER BY agg_id").fetchall()
    assert sum(r["n"] for r in before) >= n_events

    from apm.core import schema

    schema.drop_projections(conn)
    conn.execute("DELETE FROM scratch")
    conn.commit()
    replayed = projections.rebuild()
    assert replayed == n_events
    after = conn.execute("SELECT * FROM scratch ORDER BY agg_id").fetchall()
    assert [dict(r) for r in before] == [dict(r) for r in after]


def test_rebuild_endpoint(client, tmp_data):
    _emit_n(4)
    r = client.post("/api/system/rebuild-projections")
    assert r.status_code == 200
    assert r.json()["events_replayed"] == 4


def test_sse_stream_receives_events(tmp_data):
    """SSE endpoint broadcasts events appended after subscription (ASGI level)."""
    asyncio.run(_drive_sse_probe())


async def _drive_sse_probe() -> None:
    from apm.main import app

    received: list[str] = []
    subscribed = asyncio.Event()
    done = asyncio.Event()

    async def receive():
        # Real ASGI servers block until the client sends/disconnects; a receive
        # that returns instantly busy-loops sse-starlette's disconnect listener.
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] != "http.response.body":
            return
        body = msg["body"].decode()
        received.append(body)
        if "event: ready" in body and not subscribed.is_set():
            subscribed.set()
            events.emit(event_type="test.thing", agg_type="test", agg_id="sse-1", payload={"hi": 1})
        if "test.thing" in body:
            done.set()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/stream",
        "headers": [],
        "query_string": b"",
    }
    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(subscribed.wait(), 5)
    await asyncio.wait_for(done.wait(), 5)
    task.cancel()
    assert any("sse-1" in chunk for chunk in received)
