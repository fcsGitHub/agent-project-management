"""Smoke 20 (M14-I46): scheduling automation + portability roundtrip — a moved
predecessor due date cascades through an auto-scheduled depends_on chain via
explicit item.rescheduled events, and the project's event export restores
into a brand-new database (import + rebuild) with identical projections."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import db, projections


@pytest.mark.smoke
def test_smoke_20_scheduling_and_portability(client, tmp_data, isolated_ontologies,
                                             monkeypatch, tmp_path):
    r = client.post("/api/projects",
                    json={"name": "冒烟可携", "ontology": "software-dev", "requirement": "s20"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    def day(n):
        # M34-I104: auto-scheduled landings skip non-working days — anchor to
        # a Monday grid; the +4 chain shift lands C on day(21) (a workday),
        # whereas the old naive day(19) was a Saturday and now gets skipped.
        base = (datetime.now(timezone.utc) + timedelta(days=7)).date()
        while base.weekday() != 0:
            base -= timedelta(days=1)
        return (base + timedelta(days=n)).isoformat()

    # A ← B(auto) ← C(auto): moving A shifts the whole chain
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "A", "start_date": day(0),
                          "due_date": day(5)}).json()
    b = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "B", "start_date": day(5),
                          "due_date": day(10)}).json()
    c = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "bug", "title": "C", "start_date": day(10),
                          "due_date": day(15)}).json()
    for dep, on in ((b, a), (c, b)):
        assert client.post(f"/api/items/{dep['id']}/relations",
                           json={"to_item": on["id"], "relation_type": "depends_on"}).status_code == 200
        assert client.patch(f"/api/items/{dep['id']}",
                            json={"auto_scheduled": True}).status_code == 200

    assert client.patch(f"/api/items/{a['id']}", json={"due_date": day(9)}).status_code == 200  # +4
    assert client.get(f"/api/items/{b['id']}").json()["due_date"] == day(14)
    assert client.get(f"/api/items/{c['id']}").json()["due_date"] == day(21)
    evs = client.get("/api/events", params={"event_type": "item.rescheduled"}).json()["events"]
    assert [(e["id"], e["payload"]["follow_of"]) for e in sorted(evs, key=lambda e: e["id"])] == \
           sorted([(e["id"], e["payload"]["follow_of"]) for e in evs])
    assert {e["payload"]["follow_of"] for e in evs} == {a["id"], b["id"]}
    report_before = client.get(f"/api/projects/{pid}/report").json()

    # portability: export → restore into a brand-new database → identical items/report
    exp = client.get(f"/api/projects/{pid}/events/export")
    assert exp.status_code == 200
    data2 = tmp_path / "restore-db"
    monkeypatch.setattr(config.settings, "data_dir", data2)
    db.reset_for_tests(data2)
    from apm.main import create_app
    from fastapi.testclient import TestClient
    with TestClient(create_app()) as c2:
        imp = c2.post(f"/api/projects/{pid}/events/import", json={"data": exp.text})
        assert imp.status_code == 200, imp.text
        assert imp.json()["imported"] > 0

        items2 = c2.get(f"/api/projects/{pid}/items").json()["items"]
        got = {i["title"]: (i["start_date"], i["due_date"]) for i in items2}
        assert got["A"][1] == day(9) and got["B"][1] == day(14) and got["C"][1] == day(21)
        rep2 = c2.get(f"/api/projects/{pid}/report").json()
        assert rep2["funnel"] == report_before["funnel"]

        # rebuild in the restored database keeps projections identical
        projections.rebuild()
        rep3 = c2.get(f"/api/projects/{pid}/report").json()
        assert rep3["funnel"] == report_before["funnel"]
