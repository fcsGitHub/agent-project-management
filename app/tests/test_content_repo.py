"""I4 tests: content repo commits, artifact versions/diff, prompt files."""
from apm.content import gitrepo


def _mk_project(client, **kw):
    return client.post(
        "/api/projects", json={"name": "P", "ontology": "software-dev", "requirement": "r", **kw}
    ).json()


def test_project_initializes_content_repo(client, tmp_data):
    p = _mk_project(client)
    files = gitrepo.list_files(p["id"])
    assert "ontology/ontology.yaml" in files
    assert "prompts/charter.md" in files
    onto_yaml = gitrepo.read_file(p["id"], "ontology/ontology.yaml")
    assert "software-dev" in onto_yaml


def test_artifact_write_commit_and_diff(client, tmp_data):
    p = _mk_project(client)
    # first write
    r = client.put(
        f"/api/projects/{p['id']}/artifacts/prd.md",
        json={"content": "# PRD v1\n目标：自动周报", "message": "draft prd"},
    )
    assert r.status_code == 200
    sha1 = r.json()["commit"]

    # second write on the same artifact
    r = client.put(
        f"/api/projects/{p['id']}/artifacts/prd.md",
        json={"content": "# PRD v2\n目标：自动周报\n约束：兼容 Python 3.9", "message": "add constraint"},
    )
    sha2 = r.json()["commit"]
    assert sha1 != sha2

    detail = client.get(f"/api/projects/{p['id']}/artifacts/artifacts/prd.md").json()
    assert "兼容 Python 3.9" in detail["content"]
    assert len(detail["history"]) == 2
    assert detail["history"][0]["commit"] == sha2
    assert "Python 3.9" in detail["diff_vs_previous"]

    # listing exposes versions + deposits_to from ontology
    arts = client.get(f"/api/projects/{p['id']}/artifacts").json()["artifacts"]
    prd = next(a for a in arts if a["path"].endswith("prd.md"))
    assert prd["versions"] == 2
    assert prd["deposits_to"] == "prd-template"

    # artifact.human_edited events landed
    evs = client.get(
        "/api/events", params={"event_type": "artifact.human_edited"}
    ).json()["events"]
    assert len(evs) == 2


def test_agent_write_emits_artifact_committed(client, tmp_data):
    from apm.content.artifacts import write_artifact

    p = _mk_project(client)
    write_artifact(
        p["id"], "artifacts/wbs.md", "# WBS", actor_type="agent", actor_id="planner-agent:run_x"
    )
    evs = client.get("/api/events", params={"event_type": "artifact.committed"}).json()["events"]
    assert len(evs) == 1
    assert evs[0]["actor_type"] == "agent"
    assert evs[0]["payload"]["path"] == "artifacts/wbs.md"


def test_prompt_edit_persists_to_git(client, tmp_data):
    p = _mk_project(client)
    conv = client.get("/api/conversations/{0}".format(p["bootstrap"]["conversation_id"])).json()
    r = client.put(
        f"/api/conversations/{conv['id']}/context/L1",
        json={"content": "# 宪章 v2\n必须兼容 Python 3.9"},
    )
    assert r.status_code == 200
    body = gitrepo.read_file(p["id"], "prompts/charter.md")
    assert "必须兼容 Python 3.9" in body
    history = gitrepo.file_history(p["id"], "prompts/charter.md")
    assert len(history) >= 2  # init commit + edit commit

    # L3 edit writes conversation instruction file
    r = client.put(
        f"/api/conversations/{conv['id']}/context/L3", json={"content": "新指令内容"}
    )
    assert r.status_code == 200
    body = gitrepo.read_file(p["id"], f"prompts/conversations/{conv['id']}/instruction.md")
    assert body == "新指令内容"


def test_path_traversal_rejected(client, tmp_data):
    p = _mk_project(client)
    r = client.put(
        f"/api/projects/{p['id']}/artifacts/../ontologies/evil.md",
        json={"content": "x"},
    )
    assert r.status_code in (400, 404, 422)
