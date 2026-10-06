"""Smoke 46 (M40): the value-and-visibility trio end-to-end — the cost report
derives labor cost from logged minutes × hourly rates against an hours budget,
attachments round-trip bytes through the disk store with projected metadata,
the dependency graph data contract (nodes + edges + critical chain) is
complete, and a rebuild replays everything."""
from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_46_m40_value_visibility(client, tmp_data, isolated_ontologies, monkeypatch):
    pid = client.post("/api/projects",
                      json={"name": "冒烟价值可见", "ontology": "software-dev",
                            "requirement": "s46"}).json()["id"]
    client.post("/api/users", json={"id": "u_w1", "name": "王工"})
    today = datetime.now(timezone.utc).date()

    # --- ① cost & budget: 90min × rate 80 = 1.5h × 80 = 120 --------------------
    assert client.post("/api/session/identity", json={"user_id": "u_w1"}).status_code == 200
    assert client.post("/api/me/hourly-rate", json={"rate": 80}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert client.patch(f"/api/projects/{pid}", json={"budget_hours": 2}).status_code == 200

    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "记时的任务"}).json()
    client.patch(f"/api/items/{it['id']}",
                 json={"assignee_type": "human", "assignee_id": "u_w1"})
    client.post("/api/session/identity", json={"user_id": "u_w1"})
    assert client.post(f"/api/items/{it['id']}/time_entries",
                       json={"minutes": 90, "spent_on": today.isoformat()}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    cr = client.get(f"/api/projects/{pid}/cost-report").json()
    assert cr["spent_hours"] == 1.5 and cr["total_cost"] == 120.0
    assert cr["budget_hours"] == 2 and cr["burn_ratio"] == 0.75
    assert cr["over_budget"] is False

    # --- ② attachments: upload → list → download → rebuild → soft delete -------
    content = "冒烟附件 ✓".encode("utf-8")
    up = client.post(f"/api/items/{it['id']}/attachments",
                     files={"file": ("smoke46.txt", content, "text/plain")})
    assert up.status_code == 200, up.text
    aid = up.json()["id"]
    rows = client.get(f"/api/items/{it['id']}/attachments").json()["attachments"]
    assert [a["id"] for a in rows] == [aid]
    dl = client.get(f"/api/items/{it['id']}/attachments/{aid}")
    assert dl.content == content

    # --- ③ dependency graph data contract: edges + chain via existing APIs -----
    # CPM only counts items with both start and due dates (I101 caliber)
    client.patch(f"/api/items/{it['id']}",
                 json={"start_date": today.isoformat(),
                       "due_date": (today + timedelta(days=1)).isoformat()})
    # 真实方向语义（M119-I366）：POST /items/{x}/relations to=p 读作「x 依赖 p」
    # ——a 依赖 it、b 依赖 a：it 最早动工，b 是收尾交付物，全链零浮动。
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "中游",
                          "start_date": (today + timedelta(days=2)).isoformat(),
                          "due_date": (today + timedelta(days=3)).isoformat()}).json()
    b = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "下游",
                          "start_date": (today + timedelta(days=4)).isoformat(),
                          "due_date": (today + timedelta(days=7)).isoformat()}).json()
    assert client.post(f"/api/items/{a['id']}/relations",
                       json={"to_item": it["id"], "relation_type": "depends_on"}).status_code == 200
    assert client.post(f"/api/items/{b['id']}/relations",
                       json={"to_item": a["id"], "relation_type": "depends_on"}).status_code == 200
    cp = client.get(f"/api/projects/{pid}/critical-path").json()
    assert cp["cycle"] is False and set(cp["chain"]) >= {it["id"], a["id"], b["id"]}
    det = client.get(f"/api/items/{b['id']}").json()
    assert any(r["to_item"] == a["id"] and r["relation_type"] == "depends_on"
               for r in det["relations"])

    # --- rebuild: cost hours, attachment metadata, edges all replay ------------
    # (hourly_rate is runtime state — M11 family — so cost resets to 0 while
    # the logged minutes survive as events; rates can be re-entered)
    projections.rebuild()
    cr2 = client.get(f"/api/projects/{pid}/cost-report").json()
    assert cr2["spent_hours"] == cr["spent_hours"] and cr2["total_cost"] == 0.0
    assert cr2["budget_hours"] == cr["budget_hours"]
    assert [x["id"] for x in client.get(f"/api/items/{it['id']}/attachments")
            .json()["attachments"]] == [aid]
    det2 = client.get(f"/api/items/{b['id']}").json()
    assert any(r["to_item"] == a["id"] for r in det2["relations"])
