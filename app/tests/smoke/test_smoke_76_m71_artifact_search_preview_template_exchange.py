"""Smoke 76 (M71): findable & visible — ① an artifact write is searchable as
the fourth global-search type; ② the artifact preview endpoint serves the
content the preview drawers render; ③ templates export from one project and
import into another with same-title dedup."""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_76_m71_artifact_search_preview_template_exchange(
        client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟可寻可看", "ontology": "software-dev"}).json()["id"]

    # --- ① 工件写 → 第四类全文搜索命中 ------------------------------------------
    r = client.put(f"/api/projects/{pid}/artifacts/artifacts%2Fprd%2Flogin.md",
                   json={"content": "# 登录 PRD\n\n只允许手机号验证码一种方式。\n",
                         "message": "seed"})
    assert r.status_code == 200, r.text
    r = client.get("/api/search",
                   params={"q": "验证码", "types": "items,comments,conversations,artifacts"})
    hits = r.json()["artifacts"]
    assert len(hits) == 1 and hits[0]["path"] == "artifacts/prd/login.md"

    # --- ② 预览端点：内容+版本史+相对上一版 diff（预览抽屉的数据源）--------------
    client.put(f"/api/projects/{pid}/artifacts/artifacts%2Fprd%2Flogin.md",
               json={"content": "# 登录 PRD v2\n\n追加失败率指标。\n", "message": "v2"})
    d = client.get(f"/api/projects/{pid}/artifacts/artifacts%2Fprd%2Flogin.md").json()
    assert "失败率" in d["content"] and len(d["history"]) == 2
    assert d["diff_vs_previous"]  # the drawer's diff block

    # --- ③ 模板导出 → 他项目导入（重名跳过） ------------------------------------
    client.post(f"/api/projects/{pid}/prompt-templates",
                json={"title": "生成 PRD", "body": "请生成 PRD，覆盖边界。", "agent_role": "pm-agent"})
    exported = client.get(f"/api/projects/{pid}/prompt-templates/export").json()
    assert len(exported["templates"]) == 1

    pid2 = client.post("/api/projects",
                       json={"name": "冒烟导入目标", "ontology": "software-dev"}).json()["id"]
    r = client.post(f"/api/projects/{pid2}/prompt-templates/import", json=exported)
    assert r.json() == {"imported": 1, "skipped": 0}
    r = client.post(f"/api/projects/{pid2}/prompt-templates/import", json=exported)
    assert r.json() == {"imported": 0, "skipped": 1}  # re-import never clobbers
