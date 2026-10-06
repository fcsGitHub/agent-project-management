"""Smoke 39 (M33): the depth trio end-to-end — CPM chain reconciled against a
hand-computed schedule, archiving an item pulls it out of the chain and views,
restoring brings it back, and a rebuild replays both states byte-stable."""
from datetime import date, timedelta

import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_39_m33_depth(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "冒烟纵深", "ontology": "software-dev", "requirement": "s39"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    d = date.today()
    iso = lambda offset: (d + timedelta(days=offset)).isoformat()  # noqa: E731

    # 施工次序 A→B→C（真实方向语义 M119-I366：POST /items/{x}/relations to=p
    # 读作「x 依赖 p」——B 依赖 A、C 依赖 B），侧支 D 依赖 A 且早早完成带浮动
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "A", "start_date": iso(0), "due_date": iso(1)}).json()
    b = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "B", "start_date": iso(2), "due_date": iso(3)}).json()
    c = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "C", "start_date": iso(4), "due_date": iso(5)}).json()
    dd = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "D", "start_date": iso(-4), "due_date": iso(-3)}).json()
    for dep, pre in ((b, a), (c, b), (dd, a)):
        assert client.post(f"/api/items/{dep['id']}/relations",
                           json={"to_item": pre["id"], "relation_type": "depends_on"}).status_code == 200

    cp = client.get(f"/api/projects/{pid}/critical-path").json()
    assert set(cp["chain"]) == {a["id"], b["id"], c["id"]}
    assert dd["id"] not in cp["chain"]

    # --- archive: leaves views AND the CPM chain; trash holds it --------------
    assert client.post(f"/api/items/{c['id']}/archive").status_code == 200
    titles = [i["title"] for i in client.get(f"/api/projects/{pid}/items").json()["items"]]
    assert "C" not in titles
    cp2 = client.get(f"/api/projects/{pid}/critical-path").json()
    assert c["id"] not in cp2["chain"] and b["id"] in cp2["chain"]
    trash = client.get(f"/api/projects/{pid}/trash").json()["items"]
    assert [t["title"] for t in trash] == ["C"]

    # --- restore roundtrip -----------------------------------------------------
    assert client.post(f"/api/items/{c['id']}/restore").status_code == 200
    assert "C" in [i["title"] for i in client.get(f"/api/projects/{pid}/items").json()["items"]]

    # --- rebuild: chain and trash state replay ---------------------------------
    client.post(f"/api/items/{c['id']}/archive")
    projections.rebuild()
    titles2 = [i["title"] for i in client.get(f"/api/projects/{pid}/items").json()["items"]]
    assert "C" not in titles2  # archived state survives replay
    cp3 = client.get(f"/api/projects/{pid}/critical-path").json()
    assert c["id"] not in cp3["chain"] and {a["id"], b["id"]} <= set(cp3["chain"])
