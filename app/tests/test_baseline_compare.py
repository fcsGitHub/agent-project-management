"""M65-I197 基线对比（docs/01 §BJ.3，MS Project 多基线语义——多基线的价值
在比不在存）：M24-I76 存了任意多条快照，本轮补「A vs B」item 级横向 diff——
日期偏移天数/仅 A 有/仅 B 有/一致计数，偏移最大的排前。纯读投影零新表。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "基线对比项目", "ontology": "software-dev"}).json()["id"]


def test_baseline_compare_diffs_two_snapshots(client, project):
    # 基线 A：三项
    x = client.post(f"/api/projects/{project}/items",
                    json={"concept_id": "task", "title": "漂移项",
                          "start_date": "2026-10-05", "due_date": "2026-10-09"}).json()
    y = client.post(f"/api/projects/{project}/items",
                    json={"concept_id": "task", "title": "取消项",
                          "start_date": "2026-10-05", "due_date": "2026-10-07"}).json()
    w = client.post(f"/api/projects/{project}/items",
                    json={"concept_id": "task", "title": "归档项",
                          "start_date": "2026-10-05", "due_date": "2026-10-06"}).json()
    client.post(f"/api/projects/{project}/baseline")
    # 基线 B 前的变化：x 顺延 3 天；w 归档（archived_at 不为空 → 不入 B 快照）；z 新增
    client.patch(f"/api/items/{x['id']}",
                 json={"start_date": "2026-10-08", "due_date": "2026-10-14"})
    client.post(f"/api/items/{w['id']}/archive")
    z = client.post(f"/api/projects/{project}/items",
                    json={"concept_id": "task", "title": "新增项",
                          "start_date": "2026-10-12", "due_date": "2026-10-16"}).json()
    client.post(f"/api/projects/{project}/baseline")

    baselines = client.get(f"/api/projects/{project}/baselines").json()["baselines"]
    assert len(baselines) == 2
    a_id, b_id = baselines[0]["id"], baselines[1]["id"]

    u = client.get(f"/api/projects/{project}/baselines/compare",
                   params={"a": a_id, "b": b_id}).json()
    assert u["a"] == a_id and u["b"] == b_id
    s = u["summary"]
    assert s["total"] == 3                       # 快照 A 有 x、y、w
    assert s["shifted"] == 1                     # x 顺延
    assert s["removed"] == 1                     # w 归档后不在 B 快照
    assert s["added"] == 1                       # z 只在 B
    row = u["shifted"][0]
    assert row["item_id"] == x["id"]
    assert row["start_shift_days"] == 3 and row["due_shift_days"] == 5

    # 顺序与 404
    assert client.get(f"/api/projects/{project}/baselines/compare",
                      params={"a": a_id, "b": "nope"}).status_code == 404
    # 反向对比只是方向互换（shift 符号相反）
    r2 = client.get(f"/api/projects/{project}/baselines/compare",
                    params={"a": b_id, "b": a_id}).json()
    rev = next(e for e in r2["shifted"] if e["item_id"] == x["id"])
    assert rev["start_shift_days"] == -3
