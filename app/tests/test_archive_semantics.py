"""M118-I361 归档语义对齐族（docs/01 §DI）：M33-I103 引入软删除后，M65-I197
预言的「旧的全量查询都要回头核对」清账轮——回收站里的项必须从一切活视图
与派生量消失。board/list/trash 早已对齐；本轮清的是报表 funnel/concepts/
overdue、组合报表、健康分三因子、健康趋势重放、阶段图、CSV 导出、克隆、
个人日程、标签用量九处残留。死项带齐全部脏标记（过期 due+指派+标签）
进回收站，逐面断言它不再出现。"""
from __future__ import annotations

import pytest


@pytest.fixture()
def env(client, tmp_data, isolated_ontologies) -> dict:
    pid = client.post("/api/projects",
                      json={"name": "归档语义项目", "ontology": "software-dev"}).json()["id"]
    me = "u_admin"
    live = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "活项"}).json()
    dead = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "死项历史包袱",
                             "due_date": "2026-01-01"}).json()
    label = client.post(f"/api/projects/{pid}/labels",
                        json={"name": "急"}).json()
    for it in (live, dead):  # 指派+标签：让个人日程/标签用量/健康分都有赃可染
        assert client.patch(f"/api/items/{it['id']}", json={
            "assignee_type": "human", "assignee_id": me}).status_code == 200
        assert client.patch(f"/api/items/{it['id']}",
                            json={"labels": [label["id"]]}).status_code == 200
    assert client.post(f"/api/items/{dead['id']}/archive").status_code == 200
    return {"pid": pid, "live": live["id"], "dead": dead["id"], "label": label["id"]}


def test_project_report_excludes_archived(client, env):
    r = client.get(f"/api/projects/{env['pid']}/report").json()
    assert r["funnel"]["backlog"] == 1  # 只剩活项
    assert r["concepts"] == {"task": 1}
    assert all(x["id"] != env["dead"] for x in r["overdue"])


def test_portfolio_report_excludes_archived(client, env):
    r = client.get("/api/portfolio/report").json()
    row = next(p for p in r["projects"] if p["project_id"] == env["pid"])
    assert row["funnel"]["backlog"] == 1
    assert row["items_active"] == 1 and row["overdue"] == 0
    assert r["totals"]["items_active"] == 1


def test_health_factors_and_trend_exclude_archived(client, env):
    r = client.get("/api/portfolio/health").json()
    factors = next(p for p in r["projects"]
                   if p["project_id"] == env["pid"])["factors"]
    assert factors["active"] == 1 and factors["overdue"] == 0

    hist = client.get(f"/api/projects/{env['pid']}/health/history",
                      params={"days": 7}).json()
    # 重放学得会 item.archived：最后一个采样点只数活项
    assert hist["series"][-1]["active"] == 1


def test_graph_excludes_archived(client, env):
    nodes = client.get(f"/api/projects/{env['pid']}/graph").json()["nodes"]
    assert all(n["id"] != env["dead"] for n in nodes)
    assert any(n["id"] == env["live"] for n in nodes)


def test_csv_export_excludes_archived(client, env):
    text = client.get(f"/api/projects/{env['pid']}/items.csv").text
    assert "死项历史包袱" not in text
    assert "活项" in text


def test_clone_skips_archived(client, env):
    r = client.post(f"/api/projects/{env['pid']}/clone",
                    json={"name": "克隆体", "structure": False, "items": True,
                          "milestones": False}).json()
    assert r["counts"]["items"] == 1


def test_my_schedule_excludes_archived(client, env):
    items = client.get("/api/my/schedule").json()["items"]
    assert all(x["id"] != env["dead"] for x in items)


def test_label_usage_excludes_archived(client, env):
    labels = client.get(f"/api/projects/{env['pid']}/labels").json()["labels"]
    assert next(l for l in labels if l["id"] == env["label"])["usage"] == 1  # 只剩活项挂着
