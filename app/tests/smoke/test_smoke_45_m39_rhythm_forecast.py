"""Smoke 45 (M39): the rhythm-and-forecast trio end-to-end — a finished cycle's
unfinished items carry into the next cycle via cycle.carried_over, a bounce
from MAILER-DAEMON flips the failed recipient's email channel off through the
plain poll pipeline, the forecast extrapolates a median weekly velocity into a
finish date, and a rebuild replays everything."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import db, projections
from apm.domains import cycles, imap_in


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_45_m39_rhythm_forecast(client, tmp_data, isolated_ontologies, monkeypatch):
    pid = client.post("/api/projects",
                      json={"name": "冒烟节奏预测", "ontology": "software-dev",
                            "requirement": "s45"}).json()["id"]
    today = datetime.now(timezone.utc).date()

    # --- ① cycle carryover: finished cycle hands unfinished work forward ------
    c1 = client.post(f"/api/projects/{pid}/cycles",
                     json={"name": "Sprint 1", "start_date": (today - timedelta(days=14)).isoformat(),
                           "end_date": (today - timedelta(days=1)).isoformat()}).json()
    c2 = client.post(f"/api/projects/{pid}/cycles",
                     json={"name": "Sprint 2", "start_date": today.isoformat(),
                           "end_date": (today + timedelta(days=13)).isoformat()}).json()
    open_i = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": "未完成项"}).json()
    done_i = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": "完成项"}).json()
    for it in (open_i, done_i):
        assert client.patch(f"/api/items/{it['id']}",
                            json={"cycle_id": c1["id"]}).status_code == 200
    assert client.patch(f"/api/items/{done_i['id']}", json={"status": "done"}).status_code == 200
    assert cycles.carryover_finished_cycles(db.get_conn(), today.isoformat()) == 1
    assert db.get_conn().execute(
        "SELECT cycle_id FROM items WHERE id = ?", (open_i["id"],)).fetchone()["cycle_id"] == c2["id"]
    assert db.get_conn().execute(
        "SELECT cycle_id FROM items WHERE id = ?", (done_i["id"],)).fetchone()["cycle_id"] == c1["id"]

    # --- ② bounce suppression through the real poll pipeline -------------------
    monkeypatch.setattr(config.settings, "imap_host", "imap.example.com")
    monkeypatch.setattr(config.settings, "imap_user", "inbox@example.com")
    monkeypatch.setattr(config.settings, "imap_pass", "secret")
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.com"})
    monkeypatch.setattr(imap_in, "_fetch_messages", lambda: [{
        "message_id": "<s45-bounce@x.com>",
        "from": "MAILER-DAEMON@example.com (Mail Delivery System)",
        "subject": "Undelivered Mail Returned to Sender",
        "body": "qa@x.com failed permanently",
        "in_reply_to": "", "references": "",
        "x_failed_recipients": "qa@x.com",
    }])
    assert imap_in.poll_inbox()["processed"] == 1
    assert db.get_conn().execute(
        "SELECT email_notify FROM users WHERE id = 'qa-wang'"
    ).fetchone()["email_notify"] == 0
    assert db.get_conn().execute(
        "SELECT routed FROM imap_seen WHERE message_id = '<s45-bounce@x.com>'"
    ).fetchone()["routed"] == "suppress"

    # --- ③ forecast: median velocity over complete weeks → finish date ---------
    # age the project so two complete weeks fall inside its history, then
    # complete 3 items in the last week and 1 the week before (median = 2)
    def backdate(when: date, iid: str):
        row = db.get_conn().execute(
            "SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
        db.get_conn().execute(
            "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
            " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (datetime(when.year, when.month, when.day, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
             "human", "u_admin", pid, "item", iid, "item.status_changed",
             '{"status": "done", "status_group": "done"}', row))
        db.get_conn().commit()  # release the write lock — TestClient runs on other threads

    backdate(today - timedelta(days=17), "i_age")  # history depth, no completion
    this_monday = today - timedelta(days=today.weekday())
    done_items = []
    for i in range(4):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": f"节奏完成{i}"}).json()
        done_items.append(it["id"])
        when = (this_monday - timedelta(days=7)) if i < 3 else (this_monday - timedelta(days=13))
        backdate(when, it["id"])
        assert client.patch(f"/api/items/{it['id']}", json={"status": "done"}).status_code == 200
    late = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "来不及",
                             "due_date": (today - timedelta(days=2)).isoformat()}).json()["id"]

    fc = client.get(f"/api/projects/{pid}/forecast").json()
    assert fc["rate_per_week"] == 2.0
    assert [w["done"] for w in fc["weeks"]] == [3, 1]
    assert fc["remaining"] == 2            # 未完成项 + 来不及
    assert fc["forecast"] is not None
    assert any(r["id"] == late for r in fc["at_risk"])

    # --- rebuild: carryover facts, suppression audit, forecast all replay ------
    projections.rebuild()
    conn = db.get_conn()
    assert conn.execute(
        "SELECT cycle_id FROM items WHERE id = ?", (open_i["id"],)).fetchone()["cycle_id"] == c2["id"]
    assert json.loads(conn.execute(
        "SELECT payload FROM events WHERE event_type = 'cycle.carried_over'"
        " AND agg_id = ?", (c1["id"],)).fetchone()["payload"])["count"] == 1
    assert conn.execute(
        "SELECT routed FROM imap_seen WHERE message_id = '<s45-bounce@x.com>'"
    ).fetchone()["routed"] == "suppress"
    # suppression itself is runtime state (M11 family) — rebuild resets the
    # flag while the suppress audit fact survives in imap_seen
    assert conn.execute(
        "SELECT email_notify FROM users WHERE id = 'qa-wang'"
    ).fetchone()["email_notify"] == 1
    assert client.get(f"/api/projects/{pid}/forecast").json()["rate_per_week"] == 2.0
