"""Smoke 27 (M21-I67): the schedule-integration trio end-to-end — in-chart
dependency creation (the exact payload the timeline drag sends), the personal
iCal feed (key auth, VEVENT content), and comment task-list extraction with a
byte-identical stored body. Closes with a rebuild consistency pass."""
import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_27_m21_integration(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟日程集成", "ontology": "software-dev", "requirement": "s27"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # --- 1) dependency creation (I65 drag drop-payload equivalence) ---------
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "前置任务", "due_date": "2026-09-10"})
    assert a.status_code == 200, a.text
    item_a = a.json()
    b = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "后继任务", "start_date": "2026-09-11", "due_date": "2026-09-14"})
    assert b.status_code == 200, b.text
    item_b = b.json()
    rel = client.post(f"/api/items/{item_b['id']}/relations",
                      json={"to_item": item_a["id"], "relation_type": "depends_on"})
    assert rel.status_code == 200, rel.text
    detail = client.get(f"/api/items/{item_b['id']}").json()
    assert any(x["relation_type"] == "depends_on" and x["to_item"] == item_a["id"]
               for x in detail["relations"])

    # --- 2) personal iCal feed (I66) ----------------------------------------
    assert client.post(f"/api/projects/{pid}/milestones",
                       json={"title": "MVP 截止", "due_date": "2026-09-15"}).status_code == 200
    key = client.get("/api/me/feed-key").json()["feed_key"]
    ics = client.get("/api/my/calendar.ics", params={"key": key})
    assert ics.status_code == 200
    assert ics.headers["content-type"].startswith("text/calendar")
    body = ics.text
    assert body.startswith("BEGIN:VCALENDAR") and "\r\n" in body
    # B is unassigned → absent; the visible project's milestone IS present
    assert f"UID:{item_b['id']}@agentpm" not in body
    assert "◆ MVP 截止" in body and "DTEND;VALUE=DATE:20260916" in body

    # assignment changes the feed: assign 前置任务 to admin → appears with UID
    assert client.patch(f"/api/items/{item_a['id']}",
                        json={"assignee_type": "human", "assignee_id": "u_admin"}).status_code == 200
    body = client.get("/api/my/calendar.ics", params={"key": key}).text
    assert f"UID:{item_a['id']}@agentpm" in body
    assert "DTEND;VALUE=DATE:20260911" in body  # exclusive end = due + 1

    # --- 3) comment task-list extraction (I67) -------------------------------
    c = client.post(f"/api/items/{item_a['id']}/comments",
                    json={"body": "收尾清单：\n- [ ] 写部署文档\n- [ ] 补冒烟\n已完成的部分不是清单项"})
    assert c.status_code == 200, c.text
    comment_id = c.json()["id"]
    ex = client.post(f"/api/comments/{comment_id}/extract-task", json={"text": "写部署文档"})
    assert ex.status_code == 200, ex.text
    new_item = ex.json()["item"]
    assert new_item["title"] == "写部署文档" and new_item["concept_id"] == "task"
    lst = client.get(f"/api/items/{item_a['id']}/comments").json()
    assert [x["text"] for x in lst["extracted"]] == ["写部署文档"]
    assert lst["comments"][0]["body"].endswith("已完成的部分不是清单项")  # byte-identical
    assert client.post(f"/api/comments/{comment_id}/extract-task",
                       json={"text": "写部署文档"}).status_code == 409

    # --- 4) rebuild: relations, ICS content and extraction all replay --------
    projections.rebuild()
    detail = client.get(f"/api/items/{item_b['id']}").json()
    assert any(x["to_item"] == item_a["id"] for x in detail["relations"])
    lst = client.get(f"/api/items/{item_a['id']}/comments").json()
    assert [x["text"] for x in lst["extracted"]] == ["写部署文档"]
    # feed_key is runtime state (like password_hash) — rebuild clears it; the
    # owner re-views to regenerate, and the reassigned item is still in the feed
    key2 = client.get("/api/me/feed-key").json()["feed_key"]
    assert f"UID:{item_a['id']}@agentpm" in client.get("/api/my/calendar.ics", params={"key": key2}).text
