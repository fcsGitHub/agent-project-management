"""I3 tests: message tree, interrupt/resume, prompt layering, persistence."""
from apm.core import db, events, projections


def _mk_project(client, **kw):
    return client.post(
        "/api/projects",
        json={"name": "P", "ontology": "software-dev", "requirement": "需求一句话", **kw},
    ).json()


def _mk_conversation(client, project_id, **kw):
    return client.post(
        "/api/conversations",
        json={"project_id": project_id, "kind": "drafting", "title": "PRD 起草", **kw},
    ).json()


def test_project_template_creates_drafting_conversation(client, tmp_data):
    p = _mk_project(client)
    bootstrap = p["bootstrap"]
    assert bootstrap.get("conversation_id")
    conv = client.get(f"/api/conversations/{bootstrap['conversation_id']}").json()
    assert conv["kind"] == "drafting"
    assert "起草 PRD" in conv["instruction"]
    assert conv["feature_id"] == bootstrap["feature_id"]


def test_message_tree_persistence(client, tmp_data):
    p = _mk_project(client)
    conv = _mk_conversation(client, p["id"], instruction="起草 PRD")
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "注意兼容 Python 3.9"})
    assert r.status_code == 200
    m1 = r.json()["message"]
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "好的，已记录", "role": "assistant"},
    )
    m2 = r.json()["message"]
    assert m2["parent_id"] == m1["id"]  # linear thread links parent chain
    msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()["messages"]
    assert [m["content"] for m in msgs] == ["注意兼容 Python 3.9", "好的，已记录"]


def test_interrupt_resume_transitions(client, tmp_data):
    p = _mk_project(client)
    conv = _mk_conversation(client, p["id"])
    # simulate a running conversation (runtime sets this in I5)
    events.emit(
        event_type="conversation.status_changed",
        agg_type="conversation",
        agg_id=conv["id"],
        project_id=p["id"],
        actor_type="system",
        payload={"status": "running"},
    )
    # sending a message while running => interrupt + inject
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "停下，改成重试三次"})
    assert r.json()["interrupted"] is True
    assert r.json()["conversation"]["status"] == "interrupted"
    msg = r.json()["message"]
    # resume with a new instruction: instruction lands as injected message
    r = client.post(f"/api/conversations/{conv['id']}/resume", json={"instruction": "继续，按新约束来"})
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()["messages"]
    assert any("继续，按新约束来" in m["content"] for m in msgs)

    # manual interrupt from active also works
    r = client.post(f"/api/conversations/{conv['id']}/interrupt")
    assert r.json()["status"] == "interrupted"
    # archive
    r = client.post(f"/api/conversations/{conv['id']}/archive")
    assert r.json()["status"] == "archived"
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "x"})
    assert r.status_code == 422


def test_context_layers_and_editing(client, tmp_data):
    p = _mk_project(client, requirement="自动生成周报")
    conv = _mk_conversation(client, p["id"], instruction="为 T7 生成导入解析")
    ctx = client.get(f"/api/conversations/{conv['id']}/context").json()
    assert "自动生成周报" in ctx["L1"]["content"]
    assert ctx["L3"]["content"] == "为 T7 生成导入解析"
    assert ctx["L1"]["version"] == 1
    assert "L1 项目宪章" in ctx["merged_preview"]

    # edit L1 (charter): new version, applies to context, history untouched
    r = client.put(
        f"/api/conversations/{conv['id']}/context/L1",
        json={"content": "# 新宪章\n必须兼容 Python 3.9"},
    )
    assert r.status_code == 200
    assert r.json()["L1"]["version"] == 2
    ctx2 = client.get(f"/api/conversations/{conv['id']}/context").json()
    assert "必须兼容 Python 3.9" in ctx2["L1"]["content"]

    # edit L3 (instruction)
    r = client.put(
        f"/api/conversations/{conv['id']}/context/L3", json={"content": "新指令：改用 pandas"}
    )
    assert r.json()["L3"]["content"] == "新指令：改用 pandas"

    # L2 not editable in MVP
    r = client.put(f"/api/conversations/{conv['id']}/context/L2", json={"content": "x"})
    assert r.status_code == 422

    # prompt.updated events recorded with level
    evs = client.get("/api/events", params={"event_type": "prompt.updated"}).json()["events"]
    levels = {e["payload"]["level"] for e in evs}
    assert levels == {"L1_charter", "L3_instruction"}


def test_restart_recovery_via_rebuild(client, tmp_data):
    """Conversation state + messages survive a full projection rebuild."""
    p = _mk_project(client)
    conv = _mk_conversation(client, p["id"], instruction="指令X")
    client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "消息1"})
    client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "消息2", "role": "assistant"})
    before = client.get(f"/api/conversations/{conv['id']}").json()

    r = client.post("/api/system/rebuild-projections")
    assert r.status_code == 200

    after = client.get(f"/api/conversations/{conv['id']}").json()
    assert after["status"] == before["status"]
    assert after["instruction"] == "指令X"
    assert [m["content"] for m in after["messages"]] == ["消息1", "消息2"]
    assert [m["id"] for m in after["messages"]] == [m["id"] for m in before["messages"]]
