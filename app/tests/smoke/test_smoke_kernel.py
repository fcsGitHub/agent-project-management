"""Smoke 1 baseline (I1 DoD): event log is append-only; projections == replay."""
import json
import random
import sqlite3

import pytest

from apm.core import db, events, projections


@pytest.mark.smoke
def test_smoke_event_log_append_only(tmp_data):
    e = events.emit(event_type="smoke.kernel", agg_type="smoke", agg_id="s1", payload={"a": 1})
    conn = db.get_conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE events SET payload = ? WHERE id = ?", ("{}", e.id))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM events WHERE id = ?", (e.id,))


@pytest.mark.smoke
def test_smoke_projection_equals_replay(tmp_data):
    conn = db.get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS smoke_counter (agg_id TEXT PRIMARY KEY, n INTEGER)")
    conn.commit()

    @projections.on("smoke.count")
    def _count(c, event):
        c.execute("CREATE TABLE IF NOT EXISTS smoke_counter (agg_id TEXT PRIMARY KEY, n INTEGER)")
        c.execute(
            "INSERT INTO smoke_counter (agg_id, n) VALUES (?, 1)"
            " ON CONFLICT(agg_id) DO UPDATE SET n = n + 1",
            (event.agg_id,),
        )

    rng = random.Random(7)
    for i in range(30):
        events.emit(
            event_type="smoke.count",
            agg_type="smoke",
            agg_id=f"smoke-{rng.randrange(5)}",
            payload={"i": i},
        )
    before = conn.execute("SELECT * FROM smoke_counter ORDER BY agg_id").fetchall()
    total_before = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]

    from apm.core import schema

    schema.drop_projections(conn)
    conn.execute("DELETE FROM smoke_counter")
    conn.commit()
    replayed = projections.rebuild()
    after = conn.execute("SELECT * FROM smoke_counter ORDER BY agg_id").fetchall()

    assert replayed == total_before
    assert [dict(r) for r in before] == [dict(r) for r in after]
