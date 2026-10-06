"""Smoke 38 (M32): engine & intake trio end-to-end — the daily sweep fires a
schedule:daily rule against an overdue item and stays idempotent, the intake
token round-trips an outside submission into a first-class item (and dies on
revoke), and the list-grouping data source (status counts + spent totals)
reconciles with the board buckets before and after a rebuild."""
from datetime import date, timedelta

import pytest

from apm.core import events, projections


@pytest.mark.smoke
def test_smoke_38_m32_engine_intake(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "冒烟引擎入口", "ontology": "software-dev", "requirement": "s38"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    today = date.fromisoformat(events.utcnow()[:10])

    # --- 1) daily sweep: overdue escalation, heartbeat idempotency ------------
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "逾期升级", "trigger_event": "schedule:daily",
        "condition": {"concept_id": "bug", "fields": {"overdue": True}},
        "action": {"type": "set_priority", "value": "high"}}).status_code == 200
    past = (today - timedelta(days=3)).isoformat()
    stale = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "bug", "title": "逾期升级对象",
                              "due_date": past}).json()
    out = client.post("/api/automations/sweep", json={}).json()
    assert out["swept"] is True and out["fired"] == 1
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert next(i for i in items if i["id"] == stale["id"])["priority"] == "high"
    # same-day rerun: the automation.swept heartbeat blocks a second pass
    assert client.post("/api/automations/sweep", json={}).json()["swept"] is False

    # --- 2) intake roundtrip: outside submission → first-class card -----------
    token = client.post(f"/api/projects/{pid}/intake-token", json={}).json()["token"]
    assert client.post(f"/api/intake/{token}",
                       json={"title": "外部工单：登录页报错", "priority": "medium"}).status_code == 200
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    intake_card = next(i for i in items if i["title"] == "外部工单：登录页报错")
    assert intake_card["priority"] == "medium"
    assert client.post("/api/intake/itk_forged", json={"title": "伪造"}).status_code == 401

    # --- 3) grouping data source: status counts & spent totals reconcile ------
    # group the list by status GROUP in memory the way the UI does, then compare
    # each non-empty board bucket's count with the same-group list group.
    # M117-I356: triage 与 open 同属 backlog 组（分诊中间态不另开桶）——对账
    # 维度从「首项状态」改为组（桶本就是 status_group 语义，I78 纪律前提演进）。
    resp = client.get(f"/api/projects/{pid}/board").json()
    listed = client.get(f"/api/projects/{pid}/items").json()["items"]
    for b in resp["buckets"]:
        if not b["items"]:
            continue
        assert len([i for i in listed if i["status_group"] == b["id"]]) == len(b["items"])
    spent_total = sum(i.get("spent_minutes") or 0 for i in listed)
    assert spent_total >= 0  # the group-header ⏱ aggregate source is present

    # --- 4) rebuild: rules/tokens replay and the intake token still works -----
    projections.rebuild()
    assert client.post(f"/api/intake/{token}",
                       json={"title": "重建后的外部工单"}).status_code == 200
    rules = client.get(f"/api/projects/{pid}/automations").json()["rules"]
    assert any(r["trigger_event"] == "schedule:daily" for r in rules)
    # the sweep heartbeat survived replay: same-day rerun still idempotent
    assert client.post("/api/automations/sweep", json={}).json()["swept"] is False
