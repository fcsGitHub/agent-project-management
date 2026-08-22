"""Smoke 6: deposit regression suite → asset_review Gate → publish → search/link
in a second project → bidirectional links visible on the asset page."""
import pytest
from tests.conftest import wait_for


@pytest.mark.smoke
def test_smoke_06_asset_flywheel(client, tmp_data):
    # Project A finishes the login feature and writes a regression suite report
    a = client.post(
        "/api/projects", json={"name": "项目A", "ontology": "software-dev", "requirement": "登录功能"}
    ).json()
    report = "# 登录模块回归套件 v3\n\n## 用例\n- 正确账号密码登录 ✅\n- 密码错误 5 次锁定 ✅\n- 记住我 30 天 ✅\n"
    r = client.put(
        f"/api/projects/{a['id']}/artifacts/test/login-regression.md",
        json={"content": report, "message": "qa: login regression suite"},
    )
    assert r.status_code == 200
    path, commit = r.json()["path"], r.json()["commit"]

    # Deposit to the test library, then submit for the asset_review gate
    asset = client.post("/api/assets", json={
        "source_project_id": a["id"], "artifact_path": path, "commit": commit,
        "library": "test", "kind": "test-suite", "title": "登录回归套件",
        "tags": ["登录", "回归"],
    }).json()
    assert asset["status"] == "draft"
    detail = client.get(f"/api/assets/{asset['id']}").json()
    assert detail["provenance"][0]["target"]["project_id"] == a["id"]

    rev = client.post(f"/api/assets/{asset['id']}/submit_review").json()
    assert client.get(f"/api/assets/{asset['id']}").json()["status"] == "in_review"
    apr = next(
        x for x in client.get("/api/approvals", params={"status": "pending"}).json()["approvals"]
        if x["payload_snapshot"].get("gate") == "asset_review"
    )
    assert "登录回归套件" in apr["payload_snapshot"]["summary"]

    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved", "comment": "值得复用"})
    published = wait_for(lambda: (
        x := client.get(f"/api/assets/{asset['id']}").json()
    )["status"] == "published" and x)
    assert published["commit_sha"]

    # Second project: QA-Agent searches and links the suite (agent tools path)
    b = client.post("/api/projects", json={"name": "项目B", "ontology": "software-dev", "requirement": "登录改造"}).json()
    from apm.domains.assets import install_agent_tools
    from apm.runtime import tools

    install_agent_tools()
    ctx = tools.ToolContext(project_id=b["id"], run_id="r_smoke6", conversation_id=None, role="qa-agent")
    found = tools.execute("search_assets", {"query": "登录 回归"}, ctx)
    assert any(x["id"] == asset["id"] for x in found["results"]), found
    read = tools.execute("read_asset", {"id": asset["id"]}, ctx)
    assert "密码错误 5 次锁定" in read["content"]
    linked = tools.execute("link_asset", {"id": asset["id"]}, ctx)
    assert linked["citations"] >= 1

    # Asset page shows both directions of the chain
    detail = client.get(f"/api/assets/{asset['id']}").json()
    assert detail["provenance"][0]["target"]["project_id"] == a["id"]
    assert any(u["target"]["project_id"] == b["id"] for u in detail["usages"])
    assert detail["citation_count"] >= 1

    # Library listing finds it via FTS + filters
    listing = client.get("/api/assets", params={"library": "test", "q": "登录 回归"}).json()["assets"]
    assert any(x["id"] == asset["id"] for x in listing)

    # The whole flywheel is auditable
    evs = client.get("/api/events", params={"agg_type": "asset"}).json()["events"]
    types = {e["event_type"] for e in evs}
    assert {"asset.drafted", "asset.in_review", "asset.published", "asset.linked", "asset.consumed"} <= types
