"""I101 critical path (docs/01 §AF.1, CPM): backward pass over the scheduled
dependency DAG; zero-float items form the critical chain, side branches carry
float, lag participates in the latest-finish arithmetic, and a dependency
cycle yields an honest cycle flag instead of a partial chain.

M119-I366 方向修正：depends_on 的本库语义是 from=依赖方（后继）、to=前置——
与自动排程（add_relation 的 lag realign）、blocked 旗标（list_items I128）、
重排程传导（propagate_reschedule）三个消费方同向；CPM 此前独自反向（截止期
从 前置 向 依赖方 传导，关键链与浮动全部标错），本文件旧口径同样写反
（_link(a,b) 被读成「b 在 a 后」）。现按真实语义重写：_link(x, p) 恒读作
「x 依赖 p」，p 是 x 的前置。"""
from __future__ import annotations

import pytest

from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    from apm import config

    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "关键路径演示", "ontology": "software-dev", "requirement": "I101"})
    assert r.status_code == 200
    return r.json()


def _mk(client, pid: str, title: str, start: str, due: str) -> str:
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": title,
                           "start_date": start, "due_date": due}).json()
    return it["id"]


def _link(client, pid: str, dependent: str, prerequisite: str, lag: int | None = None) -> None:
    """真实语义：dependent 依赖 prerequisite（POST /items/{dependent}/relations）。"""
    body: dict = {"to_item": prerequisite, "relation_type": "depends_on"}
    if lag is not None:
        body["lag_days"] = lag
    assert client.post(f"/api/items/{dependent}/relations",
                       json=body).status_code == 200


def _cp(client, pid: str) -> dict:
    return client.get(f"/api/projects/{pid}/critical-path").json()


def test_chain_float_and_side_branch(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    f = _mk(client, pid, "地基", "2026-09-01", "2026-09-02")
    m = _mk(client, pid, "主体", "2026-09-03", "2026-09-04")
    t = _mk(client, pid, "装修", "2026-09-05", "2026-09-06")
    _link(client, pid, m, f)  # 主体 依赖 地基
    _link(client, pid, t, m)  # 装修 依赖 主体
    # 侧支：写文档只需在装修（项目末环）开始前完成，早于其最晚完成 → 带浮动
    d = _mk(client, pid, "写文档", "2026-09-01", "2026-09-02")
    _link(client, pid, t, d)  # 装修 依赖 写文档

    out = _cp(client, pid)
    assert out["cycle"] is False
    assert set(out["chain"]) == {f, m, t}
    assert d not in out["chain"]
    assert out["float"][d] == 2  # 最晚 09-04（=装修最晚开始前一天）vs 截止 09-02


def test_lag_participates_in_latest_finish(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # B 是前置；A 依赖 B 且声明 2 天 lag（A 的开工 = B 截止 +1+2）
    b = _mk(client, pid, "前置B", "2026-09-05", "2026-09-08")
    a = _mk(client, pid, "依赖A", "2026-09-11", "2026-09-12")
    _link(client, pid, a, b, lag=2)

    out = _cp(client, pid)
    # B 最晚完成 = A 最晚完成(09-12) - A 工期(2) - lag(2) = 09-08，
    # float = 09-08 - 截止 09-08 = 0 → B→A 全链关键。
    assert set(out["chain"]) == {a, b}
    assert out["float"][b] == 0


def test_negative_float_is_critical(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # 前置 B 排得远晚于依赖方所需：B 最晚完成 = 09-06 - A 工期(2) - lag(2)
    # = 09-02，早于其自身截止 09-10 → 负浮动，也是关键（进度已爆）。
    b = _mk(client, pid, "误期前置", "2026-09-08", "2026-09-10")
    a = _mk(client, pid, "依赖A", "2026-09-05", "2026-09-06")
    _link(client, pid, a, b, lag=2)
    out = _cp(client, pid)
    assert b in out["chain"]
    assert out["float"][b] == -4
    assert a not in out["chain"]  # A 自身截止即项目最晚前的宽松侧 → 带正浮动


def test_lag_zero_float_chain(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    b = _mk(client, pid, "前置B", "2026-09-04", "2026-09-05")
    a = _mk(client, pid, "依赖A", "2026-09-08", "2026-09-09")
    _link(client, pid, a, b, lag=2)
    out = _cp(client, pid)
    # A 截止 09-09 即项目最晚；B 最晚 = 09-09 - A 工期(2) - lag(2) = 09-05，
    # 恰等于其自身截止 → 零浮动全链关键。
    assert set(out["chain"]) == {a, b}
    assert out["float"][b] == 0 and out["float"][a] == 0


def test_cycle_reports_honestly(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    a = _mk(client, pid, "A", "2026-09-01", "2026-09-02")
    b = _mk(client, pid, "B", "2026-09-03", "2026-09-04")
    _link(client, pid, a, b)
    # force a cycle past the API guard (raw insert)
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO item_relations (id, project_id, from_item, to_item, relation_type,"
        " lag_days, created_at) VALUES ('rel_cycle', ?, ?, ?, 'depends_on', NULL,"
        " '2026-09-06T00:00:00')", (pid, b, a))
    conn.commit()

    out = _cp(client, pid)
    assert out["cycle"] is True and out["chain"] == []


def test_no_scheduled_items_empty_chain(client, tmp_data, isolated_ontologies, project):
    out = _cp(client, project["id"])
    assert out["cycle"] is False and out["chain"] == []
