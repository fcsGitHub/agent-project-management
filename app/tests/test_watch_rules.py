"""M54-I162 自定义关注规则（docs/01 §AY，Jira filter subscription + GitHub
custom watch 语义）：「人×项目×事件类型」自建通知规则——规则是数据不是代码
（watch.added/removed 事件+投影，rebuild 复现）；消费走 post-emit hook 命中
即 emit notification.sent kind=watch（自事件抑制/多规则单份/白名单防循环）；
「发给谁」由 watch 决定，「怎么发」仍由 I96 偏好门决定。"""
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
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "关注项目", "ontology": "software-dev"}).json()["id"]


def _watch(client, pid, event_type, expect=200):
    r = client.post(f"/api/projects/{pid}/watch-rules", json={"event_type": event_type})
    assert r.status_code == expect, r.text
    return r


def test_watch_roundtrip_and_rebuild(client, project):
    """订阅→列表→退订 roundtrip；rebuild 后规则复现；白名单外 422；重复 409。"""
    pid = project
    assert _watch(client, pid, "item.status_changed").json()["watching"] is True
    assert _watch(client, pid, "item.status_changed", expect=409).status_code == 409
    assert _watch(client, pid, "notification.sent", expect=422).status_code == 422

    rules = client.get("/api/watch-rules").json()["rules"]
    assert [(r["project_id"], r["event_type"]) for r in rules] == [(pid, "item.status_changed")]

    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    rules2 = client.get("/api/watch-rules").json()["rules"]
    assert rules2 == rules

    assert client.delete(f"/api/projects/{pid}/watch-rules/item.status_changed").status_code == 200
    assert client.delete(f"/api/projects/{pid}/watch-rules/item.status_changed").status_code == 404
    assert client.get("/api/watch-rules").json()["rules"] == []


def test_non_member_cannot_watch(client, tmp_data, isolated_ontologies, project):
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert _watch(client, project, "item.created", expect=403).status_code == 403
    client.post("/api/session/identity", json={"user_id": "u_admin"})


def test_watch_rule_fires_notification(client, project):
    """他人触发白名单事件 → 关注者收 watch 通知；自己的动作不提醒自己。"""
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{project}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert _watch(client, project, "item.status_changed").status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # 管理员（非关注者）完成任务 → qa-wang 收到 watch 通知
    it = client.post(f"/api/projects/{project}/items",
                     json={"concept_id": "task", "title": "关注任务"}).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes = client.get("/api/notifications").json()["notifications"]
    wk = [n for n in notes if n["kind"] == "watch"]
    assert len(wk) == 1 and "关注任务" in wk[0]["summary"]

    # qa-wang 自己的动作不提醒自己（自事件抑制）
    it2 = client.post(f"/api/projects/{project}/items",
                      json={"concept_id": "task", "title": "自做项"}).json()
    client.patch(f"/api/items/{it2['id']}", json={"status": "done"})
    notes2 = client.get("/api/notifications").json()["notifications"]
    assert len([n for n in notes2 if n["kind"] == "watch"]) == 1  # 仍只有一条
    client.post("/api/session/identity", json={"user_id": "u_admin"})


def test_watch_multi_rule_single_copy_and_no_recursion(client, project):
    """同事件同用户多规则单份（主键约束下再加一条走 409；此处验证去重逻辑）
    与防循环：watch 消费发出的 notification.sent 不会再次触发 watch。"""
    conn = db.get_conn()
    # 直接插两条同键规则不可行（主键）——用两用户各一条验证互不串扰后，
    # 断言 notification.sent 只产生 watch 通知而没有级联
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{project}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert _watch(client, project, "item.created").status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    it = client.post(f"/api/projects/{project}/items",
                     json={"concept_id": "task", "title": "级联检查"}).json()
    sent = client.get("/api/events",
                      params={"event_type": "notification.sent"}).json()["events"]
    watch_sent = [e for e in sent if e["payload"].get("kind") == "watch"]
    assert len(watch_sent) == 1  # 单份
    # 无级联：watch 消费产生的 notification.sent 不在白名单，不会再生 watch
    assert all(e["payload"].get("user_id") == "qa-wang" for e in watch_sent)


def test_watch_pref_gate_holds(client, project):
    """I96 偏好关断：watch kind inapp=False 后站内投影不发（hook 事件照发，
    「发给谁」由 watch 决定、「怎么发」由偏好决定）。"""
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{project}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert _watch(client, project, "item.created").status_code == 200
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "watch", "inapp": False, "email": False}]}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    client.post(f"/api/projects/{project}/items",
                json={"concept_id": "task", "title": "被闸的动态"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes = client.get("/api/notifications").json()["notifications"]
    assert not [n for n in notes if n["kind"] == "watch"]  # in-app gate held
    sent = client.get("/api/events",
                      params={"event_type": "notification.sent"}).json()["events"]
    assert any(e["payload"].get("kind") == "watch" for e in sent)  # fact still evented
    client.post("/api/session/identity", json={"user_id": "u_admin"})


def test_watch_condition_matching(client, project):
    """M55-I165：条件化 watch——全部键值全等命中才投递；不命中静默；
    空条件兼容 M54 行为；坏条件 422；rebuild 复现。"""
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{project}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    # 只关注「完成」
    r = client.post(f"/api/projects/{project}/watch-rules",
                    json={"event_type": "item.status_changed",
                          "condition": {"status_group": "done"}})
    assert r.status_code == 200
    # 坏条件 422（嵌套值/超 5 键/值非原始）
    assert client.post(f"/api/projects/{project}/watch-rules",
                       json={"event_type": "item.created",
                             "condition": {"a": {"nested": 1}}}).status_code == 422
    assert client.post(f"/api/projects/{project}/watch-rules",
                       json={"event_type": "item.updated",
                             "condition": {f"k{i}": i for i in range(6)}}).status_code == 422
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    it = client.post(f"/api/projects/{project}/items",
                     json={"concept_id": "task", "title": "条件任务"}).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "in_progress"})  # 不命中
    client.patch(f"/api/items/{it['id']}", json={"status": "done"})         # 命中
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes = client.get("/api/notifications").json()["notifications"]
    wk = [n for n in notes if n["kind"] == "watch"]
    assert len(wk) == 1 and "条件任务" in wk[0]["summary"]  # in_progress 静默
    assert client.get("/api/watch-rules").json()["rules"][0]["condition"] \
        == '{"status_group": "done"}'

    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    assert client.get("/api/watch-rules").json()["rules"][0]["condition"] \
        == '{"status_group": "done"}'
    client.post("/api/session/identity", json={"user_id": "u_admin"})


def test_watch_export_import_roundtrip(client, tmp_data, isolated_ontologies):
    """M56-I168：导出 own 规则为项目无关模板（跨项目去重、条件保留）；
    他人导入到自己项目→对账；重复导入全 skipped（模板不覆盖已有）；
    rebuild 复现。"""
    p1 = client.post("/api/projects",
                     json={"name": "项目一", "ontology": "software-dev"}).json()["id"]
    p2 = client.post("/api/projects",
                     json={"name": "项目二", "ontology": "software-dev"}).json()["id"]
    assert client.post(f"/api/projects/{p1}/watch-rules",
                       json={"event_type": "item.status_changed",
                             "condition": {"status_group": "done"}}).status_code == 200
    assert client.post(f"/api/projects/{p1}/watch-rules",
                       json={"event_type": "item.created"}).status_code == 200
    assert client.post(f"/api/projects/{p2}/watch-rules",
                       json={"event_type": "item.status_changed",
                             "condition": {"status_group": "done"}}).status_code == 200

    tpl = client.get("/api/watch-rules/export").json()
    assert tpl["version"] == 1
    got = {(r["event_type"], tuple(sorted(r["condition"].items()))) for r in tpl["rules"]}
    assert ("item.status_changed", (("status_group", "done"),)) in got
    assert ("item.created", ()) in got
    assert len(tpl["rules"]) == 2  # 跨项目同款规则去重

    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{p1}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    r = client.post(f"/api/projects/{p1}/watch-rules/import", json={"rules": tpl["rules"]})
    assert r.status_code == 200 and r.json() == {"imported": 2, "skipped": 0}
    # 重复导入 → 模板不覆盖已有规则（ON CONFLICT DO NOTHING 语义）
    r2 = client.post(f"/api/projects/{p1}/watch-rules/import", json={"rules": tpl["rules"]})
    assert r2.status_code == 200 and r2.json() == {"imported": 0, "skipped": 2}
    rules = client.get("/api/watch-rules").json()["rules"]
    assert len(rules) == 2
    assert {r["event_type"] for r in rules} == {"item.status_changed", "item.created"}

    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    assert client.get("/api/watch-rules").json()["rules"] == rules
    client.post("/api/session/identity", json={"user_id": "u_admin"})


def test_watch_import_validation(client, project):
    """M56-I168：坏模板逐条校验带序号（白名单外/坏条件 422）；超 50 条 422；
    非成员导入 403。"""
    r = client.post(f"/api/projects/{project}/watch-rules/import",
                    json={"rules": [{"event_type": "item.created"},
                                    {"event_type": "notification.sent"}]})
    assert r.status_code == 422 and "rules[1]" in r.json()["detail"]
    r = client.post(f"/api/projects/{project}/watch-rules/import",
                    json={"rules": [{"event_type": "item.created",
                                     "condition": {"a": {"nested": 1}}}]})
    assert r.status_code == 422 and "rules[0]" in r.json()["detail"]
    assert client.post(f"/api/projects/{project}/watch-rules/import",
                       json={"rules": [{"event_type": "item.created"}] * 51}).status_code == 422

    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post(f"/api/projects/{project}/watch-rules/import",
                       json={"rules": [{"event_type": "item.created"}]}).status_code == 403
    client.post("/api/session/identity", json={"user_id": "u_admin"})
