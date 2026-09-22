"""M48-I145 周期回顾包：`GET /cycles/{id}/retrospective` 把 M39-M42 的散点
报表拧成一页仪式数据——承诺完成率（I129 口径：committed 集中窗口内首达完
成）、拖入清单（commitment 日后才挂入 scope 的晚到者显性化）、周期内新增
超期、run 参与、top 阻塞依赖、与上一完成周期的速率对比。纯投影，空周期诚
实标注。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm import config
from apm.core import db, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "回顾项目", "ontology": "software-dev"}).json()["id"]


def _d(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def test_retrospective_aggregates_and_calibers(client, tmp_data, isolated_ontologies, project):
    # end_date = today (NOT -1): done events carry UTC dates while _d() uses
    # the local date — an "yesterday" end zeroes `completed` across the UTC
    # boundary (smoke_45/smoke_53 date-anchor family, third member)
    c1 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "S1", "start_date": _d(-14), "end_date": _d(0)}).json()
    # 承诺 3 项：2 done 1 仍开 → 完成率 2/3。create 不收 cycle_id——挂载走
    # PATCH；为区分「承诺日 vs 中途拖入」（口径粒度=日），承诺项的挂载用
    # backdate 历史事件（昨日），中途项用真实 now。
    import json as _json

    def _backdate_mount(iid: str, day: str):
        row = db.get_conn().execute(
            "SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
        db.get_conn().execute(
            "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
            " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"{day}T12:00:00+00:00", "human", "u_admin", project, "item", iid,
             "item.updated", _json.dumps({"cycle_id": c1["id"]}), row))
        db.get_conn().commit()

    done_ids, open_id = [], None
    items = []
    for i in range(3):
        it = client.post(f"/api/projects/{project}/items",
                         json={"concept_id": "task", "title": f"承诺{i}"}).json()
        items.append(it)
        _backdate_mount(it["id"], _d(-10))
    assert client.post("/api/system/rebuild-projections").status_code == 200
    for i, it in enumerate(items):
        if i < 2:
            done_ids.append(it["id"])
            assert client.patch(f"/api/items/{it['id']}",
                                json={"status": "done"}).status_code == 200
        else:
            open_id = it["id"]
    # 周期中途才拖入的第 4 项（晚到者，真实 now 挂载）
    late = client.post(f"/api/projects/{project}/items",
                       json={"concept_id": "task", "title": "中途插入"}).json()
    client.patch(f"/api/items/{late['id']}", json={"cycle_id": c1["id"]})
    # 周期内新增且已超期未结
    client.post(f"/api/projects/{project}/items",
                json={"concept_id": "task", "title": "新增超期",
                      "due_date": _d(-2)})
    # 阻塞（I78 语义：from 阻塞 to）——「阻塞源」阻塞周期内的承诺项0
    blocker = client.post(f"/api/projects/{project}/items",
                          json={"concept_id": "task", "title": "阻塞源"}).json()
    client.post(f"/api/items/{blocker['id']}/relations",
                json={"to_item": done_ids[0], "relation_type": "blocks"})

    rv = client.get(f"/api/cycles/{c1['id']}/retrospective").json()
    assert rv["committed"] == 3 and rv["completed"] == 2
    assert rv["completion_rate"] == round(2 / 3, 4)
    assert [x["title"] for x in rv["carried_in"]] == ["中途插入"]
    assert any(x["title"] == "新增超期" for x in rv["overdue_new"])
    assert rv["top_blockers"] and rv["top_blockers"][0]["title"] == "阻塞源"
    assert rv["top_blockers"][0]["blocks"] == 1
    assert rv["prev_completed"] is None  # 无上一完成周期
    assert rv["runs"] is not None and rv["runs"]["count"] >= 0

    # rebuild 后逐字段一致（纯投影口径）
    projections.rebuild()
    rv2 = client.get(f"/api/cycles/{c1['id']}/retrospective").json()
    for k in ("committed", "completed", "completion_rate"):
        assert rv2[k] == rv[k]
    assert [x["title"] for x in rv2["carried_in"]] == ["中途插入"]


def test_retrospective_empty_scope_is_honest(client, tmp_data, isolated_ontologies, project):
    c = client.post(f"/api/projects/{project}/cycles",
                    json={"name": "空周期", "start_date": _d(-7), "end_date": _d(-1)}).json()
    rv = client.get(f"/api/cycles/{c['id']}/retrospective").json()
    assert rv["reason"] == "empty scope" and rv["committed"] == 0
    assert rv["completion_rate"] is None


def test_retrospective_prev_cycle_velocity_delta(client, tmp_data, isolated_ontologies, project):
    """两个已完结周期各完成一项 → S2 回顾的 prev_completed=S1 完成数。
    周期窗口在过去，挂载/完成事件 backdate 进各自窗口（I129 口径：完成须
    落在窗口内）。"""
    import json as _json

    def _backdate(iid: str, day: str, payload: dict, etype: str = "item.updated"):
        row = db.get_conn().execute(
            "SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
        db.get_conn().execute(
            "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
            " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"{day}T12:00:00+00:00", "human", "u_admin", project, "item", iid,
             etype, _json.dumps(payload), row))
        db.get_conn().commit()

    c1 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "S1", "start_date": _d(-28), "end_date": _d(-15)}).json()
    c2 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "S2", "start_date": _d(-14), "end_date": _d(-1)}).json()
    it1 = client.post(f"/api/projects/{project}/items",
                      json={"concept_id": "task", "title": "S1任务"}).json()
    it2 = client.post(f"/api/projects/{project}/items",
                      json={"concept_id": "task", "title": "S2任务"}).json()
    _backdate(it1["id"], _d(-27), {"cycle_id": c1["id"]})
    _backdate(it1["id"], _d(-20), {"status": "done", "status_group": "done"},
              etype="item.status_changed")
    _backdate(it2["id"], _d(-13), {"cycle_id": c2["id"]})
    _backdate(it2["id"], _d(-6), {"status": "done", "status_group": "done"},
              etype="item.status_changed")
    assert client.post("/api/system/rebuild-projections").status_code == 200
    rv = client.get(f"/api/cycles/{c2['id']}/retrospective").json()
    assert rv["completed"] == 1 and rv["prev_completed"] == 1
