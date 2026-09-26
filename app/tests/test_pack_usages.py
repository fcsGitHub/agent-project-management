"""M59-I178 模板包实例溯源（docs/01 §BD.2，marketplace update 语义的组织内
翻译）：project.created 记录出生版本（增量键，旧库事件自然缺键）；usages
从事件流聚合实例清单——出生版本 vs 当前版本对比（behind）、「早期实例」
诚实显示、落后徽标数据面；只做可见性不做自动迁移。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def test_pack_usages_provenance(client, tmp_data, isolated_ontologies):
    # 两个实例走真实建项目共链路（builtin software-dev）
    p1 = client.post("/api/template-packs/software-dev/instantiate",
                     json={"project_name": "实例一", "requirement": "r"}).json()
    p2 = client.post("/api/template-packs/software-dev/instantiate",
                     json={"project_name": "实例二"}).json()
    packs = client.get("/api/template-packs").json()["packs"]
    current = next(p["version"] for p in packs if p["name"] == "software-dev")

    # 早期实例（旧库事件无版本键——合成历史事实）与落后实例（出生旧版）
    events.emit(event_type="project.created", agg_type="project", agg_id="p_legacy",
                project_id="p_legacy", actor_id="u_admin",
                payload={"name": "早期项目", "ontology": "software-dev",
                         "template": "software-dev"})
    events.emit(event_type="project.created", agg_type="project", agg_id="p_old",
                project_id="p_old", actor_id="u_admin",
                payload={"name": "落后项目", "ontology": "software-dev",
                         "ontology_version": current - 1})

    u = client.get("/api/template-packs/software-dev/usages").json()
    assert u["pack"] == "software-dev" and u["current_version"] == current
    by_name = {x["name"]: x for x in u["usages"]}
    assert by_name["实例一"]["project_id"] == p1["id"]
    assert by_name["实例一"]["behind"] == 0
    assert by_name["实例二"]["born_version"] == current
    assert by_name["早期项目"]["born_version"] is None
    assert by_name["早期项目"]["behind"] is None
    assert by_name["落后项目"]["behind"] == 1
    # 排序按创建时间：两个真实实例在前，合成事实按落账顺序
    names = [x["name"] for x in u["usages"]]
    assert names.index("实例一") < names.index("实例二") < names.index("早期项目")

    assert client.get("/api/template-packs/ghost/usages").status_code == 404
