"""Smoke 79 (M74): ledger & management faces — ① expense recorded via the
recordExpense endpoint lands in the ledger listing and the cost report's
expense track (the I222 UI wires exactly these), then deletes cleanly;
② a milestone created via createMilestone shows in the timeline listing,
patch (due date + status) sticks, and delete removes it (the I223 panel
wires exactly these). The list-view run badge (I224) is frontend-only —
its SSE/projection data plane is already covered by smoke 74/78."""
from __future__ import annotations

import pytest


@pytest.mark.smoke
def test_smoke_79_m74_ledger_management(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟台账管理", "ontology": "software-dev"}).json()["id"]

    # --- ① 费用记账面：record → 台账可见 → 报表双轨计入 → delete → 双面消失 ----------
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "冒烟挂项"}).json()
    r = client.post(f"/api/projects/{pid}/expenses", json={
        "description": "云 GPU 租用", "qty": 2, "unit_price": 60,
        "currency": "CNY", "spent_on": "2026-09-30", "vendor": "云厂商",
        "item_id": item["id"],
    })
    assert r.status_code == 200, r.text
    exp_id = r.json()["id"]

    ledger = client.get(f"/api/projects/{pid}/expenses").json()["expenses"]
    assert [e["id"] for e in ledger] == [exp_id]
    assert ledger[0]["description"] == "云 GPU 租用" and ledger[0]["vendor"] == "云厂商"

    cr = client.get(f"/api/projects/{pid}/cost-report").json()
    assert cr["expense_cost"] == 120.0 and cr["total_cost"] >= 120.0
    assert [e["id"] for e in cr["expenses"]] == [exp_id]

    assert client.delete(f"/api/projects/{pid}/expenses/{exp_id}").status_code == 200
    assert client.get(f"/api/projects/{pid}/expenses").json()["expenses"] == []
    cr2 = client.get(f"/api/projects/{pid}/cost-report").json()
    assert cr2["expense_cost"] == 0.0

    # --- ② 里程碑管理面：create → 列表与时间线数据面 → patch → delete ---------------
    r = client.post(f"/api/projects/{pid}/milestones",
                    json={"title": "M1 架构定型", "due_date": "2026-10-15",
                          "description": "冒烟里程碑"})
    assert r.status_code == 200, r.text
    ms = r.json()
    assert ms["status"] == "planned" and ms["due_date"] == "2026-10-15"

    listed = client.get(f"/api/projects/{pid}/milestones").json()["milestones"]
    assert [m["id"] for m in listed if m["id"] == ms["id"]]

    r = client.patch(f"/api/milestones/{ms['id']}",
                     json={"due_date": "2026-10-20", "status": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["due_date"] == "2026-10-20" and r.json()["status"] == "in_progress"

    assert client.delete(f"/api/milestones/{ms['id']}").status_code == 200
    assert client.get(f"/api/projects/{pid}/milestones").json()["milestones"] == []
