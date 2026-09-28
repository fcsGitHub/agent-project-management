"""M69-I208 指令模板库（docs/01 §BN.2，Copilot .prompt.md 语义）：对话/运行
发起指令的复用层——与 M35 评论常用回复、M4 项目模板包三层互斥。模板是草稿
不是快捷键：填入输入框可改后发送。内容走 prompts/ git 管道（I204 惯例），
投影存元数据，事件载荷带 body 供 rebuild。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "指令模板项目", "ontology": "software-dev"}).json()["id"]


def test_crud_and_git_roundtrip(client, pid):
    r = client.post(f"/api/projects/{pid}/prompt-templates",
                    json={"title": "生成 PRD", "body": "请为登录功能生成一份 PRD，覆盖认证方式与边界。",
                          "agent_role": "pm-agent"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["version"] == 1 and t["agent_role"] == "pm-agent"
    assert "PRD" in t["body"]

    listing = client.get(f"/api/projects/{pid}/prompt-templates").json()["templates"]
    assert len(listing) == 1 and listing[0]["id"] == t["id"]

    # update bumps version, body round-trips through the git pipeline
    r = client.patch(f"/api/prompt-templates/{t['id']}",
                     json={"body": "请为登录功能生成 PRD，补充失败率指标。"})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2 and "失败率" in r.json()["body"]

    # delete removes the projection row (git history retained by design)
    assert client.delete(f"/api/prompt-templates/{t['id']}").status_code == 200
    assert client.get(f"/api/projects/{pid}/prompt-templates").json()["templates"] == []
    assert client.patch(f"/api/prompt-templates/{t['id']}",
                        json={"title": "x"}).status_code == 404


def test_validation_and_membership(client, pid):
    # unregistered role → 422; empty/oversized title & body → 422
    assert client.post(f"/api/projects/{pid}/prompt-templates",
                       json={"title": "t", "body": "b", "agent_role": "no-such"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/prompt-templates",
                       json={"title": "  ", "body": "b"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/prompt-templates",
                       json={"title": "t", "body": "x" * 4001}).status_code == 422

    # anonymous (no membership) → 403
    saved = config.settings.user_id
    try:
        config.settings.user_id = "u_stranger"
        assert client.get(f"/api/projects/{pid}/prompt-templates").status_code == 403
    finally:
        config.settings.user_id = saved


def test_templates_survive_rebuild(client, pid):
    client.post(f"/api/projects/{pid}/prompt-templates",
                json={"title": "冒烟清单", "body": "回归以 smoke 清单为准，逐条核对。",
                      "agent_role": "qa-agent"})
    assert client.post("/api/system/rebuild-projections").status_code == 200
    listing = client.get(f"/api/projects/{pid}/prompt-templates").json()["templates"]
    assert len(listing) == 1
    assert listing[0]["title"] == "冒烟清单" and listing[0]["agent_role"] == "qa-agent"
    assert "smoke" in listing[0]["body"]  # body restored from the git pipeline


def test_export_import_roundtrip_with_dedup(client, pid):
    """M71-I215: the watch-rules mirror — export as project-agnostic JSON,
    import into another project, same-title rows skipped never clobbered."""
    client.post(f"/api/projects/{pid}/prompt-templates",
                json={"title": "生成 PRD", "body": "请生成 PRD（含边界）。",
                      "agent_role": "pm-agent"})
    client.post(f"/api/projects/{pid}/prompt-templates",
                json={"title": "回归清单", "body": "以 smoke 清单逐条核对。", "agent_role": None})

    exported = client.get(f"/api/projects/{pid}/prompt-templates/export").json()
    assert exported["version"] == 1 and len(exported["templates"]) == 2
    titles = {t["title"] for t in exported["templates"]}
    assert titles == {"生成 PRD", "回归清单"}

    # import into a second project
    pid2 = client.post("/api/projects",
                       json={"name": "导入目标项目", "ontology": "software-dev"}).json()["id"]
    r = client.post(f"/api/projects/{pid2}/prompt-templates/import", json=exported)
    assert r.status_code == 200, r.text
    assert r.json() == {"imported": 2, "skipped": 0}
    assert len(client.get(f"/api/projects/{pid2}/prompt-templates").json()["templates"]) == 2

    # re-import: same-title rows skipped (never clobbered), bodies untouched
    client.patch(f"/api/prompt-templates/{client.get(f'/api/projects/{pid2}/prompt-templates').json()['templates'][0]['id']}",
                 json={"body": "本地改过的版本。"})
    r = client.post(f"/api/projects/{pid2}/prompt-templates/import", json=exported)
    assert r.json() == {"imported": 0, "skipped": 2}
    listing2 = client.get(f"/api/projects/{pid2}/prompt-templates").json()["templates"]
    assert any("本地改过" in t["body"] for t in listing2)

    # invalid rows are rejected with their index
    bad = {"version": 1, "templates": [{"title": "  ", "body": "b"}]}
    r = client.post(f"/api/projects/{pid2}/prompt-templates/import", json=bad)
    assert r.status_code == 422 and "templates[0]" in r.json()["detail"]
