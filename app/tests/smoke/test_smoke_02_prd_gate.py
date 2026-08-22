"""Smoke 2 (first half, I5 DoD, replay mode): PM-Agent PRD + interrupt-inject-resume."""
import pytest
from tests.conftest import wait_for


@pytest.mark.smoke
def test_smoke_02_prd_approval_with_interrupt_injection(client, tmp_data):
    p = client.post(
        "/api/projects",
        json={"name": "周报工具", "ontology": "software-dev",
              "requirement": "汇总 Git 提交与任务状态，自动生成周报"},
    ).json()
    conv_id = p["bootstrap"]["conversation_id"]

    run = client.post(
        "/api/runs", json={"conversation_id": conv_id, "agent_role": "pm-agent"}
    ).json()
    run = wait_for(lambda: (
        r := client.get(f"/api/runs/{run['id']}").json()
    )["status"] == "interrupted" and r)
    assert run["status"] == "interrupted"

    apr = client.get(
        "/api/approvals", params={"status": "pending", "project_id": p["id"]}
    ).json()["approvals"][0]
    assert apr["payload_snapshot"]["gate"] == "prd_review"
    assert apr["payload_snapshot"]["artifact"]["path"] == "artifacts/prd.md"

    # Interrupt the conversation, inject a constraint, resume.
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "必须兼容 Python 3.9，不要用 3.10+ 语法"},
    )
    client.post(f"/api/conversations/{conv_id}/resume", json={"instruction": "按补充约束重拟 PRD"})
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")

    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    final = wait_for(lambda: (
        r := client.get(f"/api/runs/{run['id']}").json()
    )["status"] in ("succeeded", "failed") and r)
    assert final["status"] == "succeeded", final

    prd = client.get(f"/api/projects/{p['id']}/artifacts/artifacts/prd.md").json()
    assert "Python 3.9" in prd["content"]  # injected constraint is in the PRD

    # Spans carry graph/conversation anchors (I5 DoD).
    spans = client.get(f"/api/runs/{run['id']}/spans").json()["spans"]
    gen = next(s for s in spans if s["span_kind"] == "generation")
    assert gen["attributes"]["apm.conversation_id"] == conv_id
    tool = next(s for s in spans if s["name"] == "tool.write_artifact")
    assert tool["attributes"]["apm.diff_ref"]
