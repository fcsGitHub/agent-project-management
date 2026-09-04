"""M21-I66: personal iCal calendar subscription — feed-key auth (rotate → old
key 401), own-data scoping (only my assigned items), visible-project
milestones, deterministic UIDs, RFC 5545 escaping and CRLF framing."""
import pytest

from apm.domains.feed import get_feed_key


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "日历演示", "ontology": "software-dev", "requirement": "I66"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_item(client, pid, title, **kw):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _ics(client, key):
    r = client.get("/api/my/calendar.ics", params={"key": key})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/calendar")
    return r.text


def test_ical_feed_auth_content_and_scoping(client, pid):
    # key auth: no/invalid key → 401
    assert client.get("/api/my/calendar.ics", params={"key": "nope"}).status_code == 401

    key = get_feed_key()["feed_key"]

    # my assigned item with both dates + an unassigned item (must NOT appear)
    mine = _mk_item(client, pid, "我的截止项", start_date="2026-09-08", due_date="2026-09-12")
    assert client.patch(f"/api/items/{mine['id']}",
                        json={"assignee_type": "human", "assignee_id": "u_admin"}).status_code == 200
    _mk_item(client, pid, "别人的项", due_date="2026-09-10")
    # done items drop out (active-only)
    done = _mk_item(client, pid, "已完成项", due_date="2026-09-09")
    client.patch(f"/api/items/{done['id']}", json={"status": "done"})

    # a milestone in the visible project appears
    assert client.post(f"/api/projects/{pid}/milestones",
                       json={"title": "MVP 截止", "due_date": "2026-09-15"}).status_code == 200

    body = _ics(client, key)
    assert body.startswith("BEGIN:VCALENDAR") and body.endswith("END:VCALENDAR\r\n")
    assert "\r\n" in body  # CRLF framing
    assert "UID:" + mine["id"] + "@agentpm" in body  # deterministic UID
    assert body.count("BEGIN:VEVENT") == 2  # my item + milestone only
    assert "我的截止项" in body and "别人的项" not in body and "已完成项" not in body
    assert "◆ MVP 截止" in body
    assert "DTSTART;VALUE=DATE:20260908" in body
    assert "DTEND;VALUE=DATE:20260913" in body  # exclusive end = due + 1

    # RFC 5545 TEXT escaping: a comma in a title must not break the line
    esc_item = _mk_item(client, pid, "带,逗号;与分号", due_date="2026-09-20")
    assert client.patch(f"/api/items/{esc_item['id']}",
                        json={"assignee_type": "human", "assignee_id": "u_admin"}).status_code == 200
    body = _ics(client, key)
    assert "带\\,逗号\\;与分号" in body
    assert body.count("BEGIN:VEVENT") == 3

    # rotate → old key dead, new key serves
    new_key = client.post("/api/me/feed-key/rotate").json()["feed_key"]
    assert client.get("/api/my/calendar.ics", params={"key": key}).status_code == 401
    assert client.get("/api/my/calendar.ics", params={"key": new_key}).status_code == 200
