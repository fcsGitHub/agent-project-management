"""M68-I204 项目级角色指令层（docs/01 §BM.1，AGENTS.md 嵌套模型的翻译）：
prompt_layers 已有 project_id+agent_role 列——L1.5 层按 project×role 一条，
git 版本化；build_context 在 L1 与 L2 之间插段；engine._messages 把该指令
追加进 system（深层作用域细化全局角色提示词）。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "角色指令项目", "ontology": "software-dev"}).json()["id"]


def test_write_read_and_context_assembly(client, pid):
    r = client.put(f"/api/projects/{pid}/role-instructions",
                   json={"agent_role": "dev-agent",
                         "content": "本项目的 dev-agent 一律使用 pytest，禁止引入 unittest。"})
    assert r.status_code == 200, r.text

    listing = client.get(f"/api/projects/{pid}/role-instructions").json()["instructions"]
    assert len(listing) == 1
    assert listing[0]["agent_role"] == "dev-agent"
    assert "pytest" in listing[0]["content"] and listing[0]["version"] == 1

    # build_context carries the L1.5 section between L1 and L2
    conv = client.post("/api/conversations",
                       json={"project_id": pid, "kind": "executing"}).json()
    ctx = client.get(f"/api/conversations/{conv['id']}/context").json()
    merged = ctx.get("merged_preview") or ""
    assert "[L1.5 项目角色指令]" in merged
    assert merged.index("[L1 项目宪章") < merged.index("[L1.5 项目角色指令]") < merged.index("[L2 功能简报]")
    assert "pytest" in merged

    # version bumps on rewrite, not a second row
    client.put(f"/api/projects/{pid}/role-instructions",
               json={"agent_role": "dev-agent", "content": "改用 pytest-mock。"})
    listing = client.get(f"/api/projects/{pid}/role-instructions").json()["instructions"]
    assert len(listing) == 1 and listing[0]["version"] == 2
    assert "pytest-mock" in listing[0]["content"]


def test_validation_and_engine_injection(client, pid, tmp_data, isolated_ontologies):
    # unregistered role → 422; empty content → 422
    assert client.put(f"/api/projects/{pid}/role-instructions",
                      json={"agent_role": "no-such-role", "content": "x"}).status_code == 422
    assert client.put(f"/api/projects/{pid}/role-instructions",
                      json={"agent_role": "dev-agent", "content": "  "}).status_code == 422

    client.put(f"/api/projects/{pid}/role-instructions",
               json={"agent_role": "dev-agent", "content": "禁止 unittest，统一 pytest。"})
    conv = client.post("/api/conversations",
                       json={"project_id": pid, "kind": "executing",
                             "instruction": "写一个工具函数"}).json()
    # real run through the standard chain — a software-dev run parks at the
    # phase gate (terminal 'interrupted'); what matters is that the L1.5
    # injection path executes without breaking the run
    r = client.post("/api/runs", json={"conversation_id": conv["id"],
                                       "agent_role": "dev-agent", "wait": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] in ("succeeded", "interrupted")


def test_layer_survives_rebuild(client, pid):
    client.put(f"/api/projects/{pid}/role-instructions",
               json={"agent_role": "qa-agent", "content": "回归范围以 smoke 清单为准。"})
    assert client.post("/api/system/rebuild-projections").status_code == 200
    listing = client.get(f"/api/projects/{pid}/role-instructions").json()["instructions"]
    assert len(listing) == 1
    assert listing[0]["agent_role"] == "qa-agent"
    assert "smoke" in listing[0]["content"]
    # layer row rides the prompt.updated event — git file holds the content
    row = db.get_conn().execute(
        "SELECT git_path, agent_role FROM prompt_layers"
        " WHERE project_id = ? AND level = 'L1.5_role_project'", (pid,)).fetchone()
    assert row["agent_role"] == "qa-agent" and "roles/" in row["git_path"]
