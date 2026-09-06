"""Smoke 26 (M20-I64): the M20 experience trio end-to-end — personal timelog
calendar feed (/my/timelog), timeline drag-to-reschedule (dual-date PATCH with
auto-schedule propagation + audit), and comment markdown roundtrip (raw plain
text preserved in storage while mentions still notify). Closes with a rebuild
consistency pass over all three surfaces."""
import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_26_m20_experience(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟体验三件套", "ontology": "software-dev", "requirement": "s26"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # 先建用户再发 @ 评论（I57 教训：先评论后建人则 mentions 为空）
    assert client.post("/api/users", json={"id": "u_qa", "name": "QA 王"}).status_code == 200

    def switch(uid):
        assert client.post("/api/session/identity", json={"user_id": uid}).status_code == 200

    saved = client.get("/api/users").json()["current"]

    # --- 1) personal timelog calendar feed: per-identity day grouping -------
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "体验甲", "start_date": "2026-09-01", "due_date": "2026-09-05"})
    assert a.status_code == 200, a.text
    item_a = a.json()
    e1 = client.post(f"/api/items/{item_a['id']}/time_entries",
                     json={"minutes": 90, "spent_on": "2026-09-04", "note": "开发"}).json()
    switch("u_qa")
    e2 = client.post(f"/api/items/{item_a['id']}/time_entries",
                     json={"minutes": 45, "spent_on": "2026-09-05", "note": "评审"}).json()
    switch(saved)
    assert e1["user_id"] == "u_admin" and e2["user_id"] == "u_qa"

    feed = client.get("/api/my/timelog").json()
    by_day = {d["date"]: d["total_minutes"] for d in feed["days"]}
    assert by_day["2026-09-04"] == 90 and feed["total_minutes"] == 90
    switch("u_qa")
    feed_qa = client.get("/api/my/timelog").json()
    assert feed_qa["total_minutes"] == 45
    switch(saved)

    # --- 2) timeline drag semantics: dual-date PATCH propagates + audits ----
    # auto_scheduled persists via the PATCH switch (M14 semantics), set it after create
    b = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "体验乙", "start_date": "2026-09-03", "due_date": "2026-09-07"})
    assert b.status_code == 200, b.text
    item_b = b.json()
    assert client.post(f"/api/items/{item_b['id']}/relations",
                       json={"to_item": item_a["id"], "relation_type": "depends_on"}).status_code == 200
    assert client.patch(f"/api/items/{item_b['id']}", json={"auto_scheduled": True}).status_code == 200

    # drag = one PATCH carrying both shifted dates (+3 days), like the timeline sends
    assert client.patch(f"/api/items/{item_a['id']}",
                        json={"start_date": "2026-09-04", "due_date": "2026-09-08"}).status_code == 200
    b2 = client.get(f"/api/items/{item_b['id']}").json()
    # M34-I104: the raw landing 09-06 is a Sunday — skipped forward to Monday
    assert b2["start_date"] == "2026-09-07" and b2["due_date"] == "2026-09-10"
    rescheds = client.get("/api/events", params={"event_type": "item.rescheduled"}).json()["events"]
    assert len(rescheds) == 1 and rescheds[0]["agg_id"] == item_b["id"]
    assert rescheds[0]["payload"]["delta_days"] == 3

    # --- 3) comment markdown roundtrip: raw text preserved, mention fires ---
    body_md = "结论如下：\n- [x] 接口跑通\n- [ ] 补用例\n\n| 场景 | 结果 |\n| --- | --- |\n| 拖拽 | +3 天 |"
    c = client.post(f"/api/items/{item_a['id']}/comments",
                    json={"body": body_md + " 请 @QA 王 复核"})
    assert c.status_code == 200, c.text
    assert c.json()["body"] == body_md + " 请 @QA 王 复核"  # storage is plain text, byte-identical
    import json as _json
    assert _json.loads(c.json()["mentions"]) == ["u_qa"]
    switch("u_qa")
    notifs = client.get("/api/notifications").json()["notifications"]
    assert any(n["kind"] == "mention" for n in notifs)
    switch(saved)

    # --- 4) rebuild: all three surfaces replay to identical state -----------
    projections.rebuild()
    feed_r = client.get("/api/my/timelog").json()
    assert feed_r["total_minutes"] == 90
    assert {d["date"]: d["total_minutes"] for d in feed_r["days"]} == by_day
    assert client.get(f"/api/items/{item_b['id']}").json()["due_date"] == "2026-09-10"
    comments = client.get(f"/api/items/{item_a['id']}/comments").json()["comments"]
    assert comments[0]["body"] == body_md + " 请 @QA 王 复核"
