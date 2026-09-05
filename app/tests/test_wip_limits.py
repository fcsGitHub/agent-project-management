"""M26-I80 (docs/01 §Y.1): kanban WIP limits — board_defaults.wip_limits from
the ontology, project-wide counts (Kanboard's "count all open tasks, not the
filtered ones" fix), soft semantics (the board never blocks transitions), and
backward compatibility for ontologies without the declaration."""
import pytest

from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "WIP 演示", "ontology": "software-dev", "requirement": "I80"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_in_progress(client, pid, title):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert client.patch(f"/api/items/{iid}", json={"status": "in_progress"}).status_code == 200
    return iid


def test_wip_limits_surface_on_board(client, pid):
    onto = client.get(f"/api/projects/{pid}/ontology").json()
    assert onto["board_defaults"]["wip_limits"] == {"in_progress": 5}

    # 6 items in progress vs a limit of 5, plus one left open
    for i in range(6):
        _mk_in_progress(client, pid, f"进行中{i}")
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": "待办项"})

    board = client.get(f"/api/projects/{pid}/board").json()
    assert board["wip_limits"] == {"in_progress": 5}
    assert board["wip"] == {"in_progress": 6}
    assert board["wip"]["in_progress"] > board["wip_limits"]["in_progress"]


def test_wip_count_ignores_board_filters(client, pid):
    _mk_in_progress(client, pid, "A")
    _mk_in_progress(client, pid, "B")

    # a feature-scoped board still counts the whole column (project-wide)
    feat = client.post(f"/api/projects/{pid}/features", json={"title": "特例"}).json()
    board = client.get(f"/api/projects/{pid}/board", params={"feature_id": feat["id"]}).json()
    assert len(board["buckets"][2]["items"]) == 0  # filtered view shows nothing
    assert board["wip"] == {"in_progress": 2}      # ...but the WIP count sees both


def test_ontology_without_wip_limits_stays_compat(client, tmp_data, isolated_ontologies):
    (isolated_ontologies / "nowip.yaml").write_text(
        "name: nowip\nconcepts:\n  - id: task\n    name: 任务\n"
        "    states:\n      - {id: open, name: 待办, group: backlog}\n"
        "      - {id: done, name: 完成, group: done}\n",
        encoding="utf-8")
    r = client.post("/api/projects", json={"name": "无限制项目", "ontology": "nowip", "requirement": "x"})
    assert r.status_code == 200, r.text
    board = client.get(f"/api/projects/{r.json()['id']}/board").json()
    assert "wip" not in board and "wip_limits" not in board


def test_wip_survives_rebuild(client, pid):
    for i in range(6):
        _mk_in_progress(client, pid, f"重建{i}")
    projections.rebuild()
    board = client.get(f"/api/projects/{pid}/board").json()
    assert board["wip"] == {"in_progress": 6}
