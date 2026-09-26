"""M60-I181 组合健康趋势与流指标（docs/01 §BE.2/BE.3，Flow Framework 三件）：
健康史采样对齐 + 组合中位线 + 首尾方向；流指标=事件对投影（中位完成周期/
近 4 周吞吐/WIP——事件溯源红利第十二例，零埋点）；不可见项目不泄漏；
rebuild 一致。健康分是结论，流指标是归因入口。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def test_portfolio_health_trend_and_flow_metrics(client, tmp_data, isolated_ontologies,
                                                 monkeypatch):
    p = client.post("/api/projects",
                    json={"name": "流指标项目", "ontology": "software-dev",
                          "requirement": "flow"}).json()
    # 三个周期样本：创建→完成（同日，周期 0 天）+ 一个 in_progress（WIP）
    for i in range(3):
        it = client.post(f"/api/projects/{p['id']}/items",
                         json={"concept_id": "task", "title": f"周期项{i}"}).json()
        client.patch(f"/api/items/{it['id']}", json={"status": "in_progress"})
        client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    wip = client.post(f"/api/projects/{p['id']}/items",
                      json={"concept_id": "task", "title": "进行中项"}).json()
    client.patch(f"/api/items/{wip['id']}", json={"status": "in_progress"})

    u = client.get("/api/portfolio/health-trend").json()
    assert u["days"] == 30
    proj = next(x for x in u["projects"] if x["project_id"] == p["id"])
    # 年轻项目只有末位采样点有分数 → direction 诚实为 None；有 ≥2 个分数时必为三值之一
    assert proj["direction"] is None or proj["direction"] in ("up", "down", "flat")
    assert proj["last"] is not None and len(proj["series"]) >= 2  # 采样点对齐
    assert proj["median_cycle_days"] == 0       # 同日完成
    assert proj["throughput_4w"] == 0.75        # 3 done / 4 周
    assert proj["wip"] == 1
    assert u["portfolio_median"] is not None

    # 不可见项目不泄漏：network 模式下非成员（非管理员）看不到
    # （本地模式 qa-wang 是隐式单用户，_visible 第三分支天然全可见）
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    u2 = client.get("/api/portfolio/health-trend").json()
    monkeypatch.setattr(config.settings, "auth_mode", "local")
    assert all(x["project_id"] != p["id"] for x in u2["projects"])
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # rebuild 一致（纯投影）
    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    u3 = client.get("/api/portfolio/health-trend").json()
    proj3 = next(x for x in u3["projects"] if x["project_id"] == p["id"])
    assert proj3["median_cycle_days"] == proj["median_cycle_days"]
    assert proj3["throughput_4w"] == proj["throughput_4w"]
    assert proj3["wip"] == proj["wip"]
