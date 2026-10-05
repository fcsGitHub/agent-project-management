"""验收考官首轮回归（docs/13 Round 1，M108 trace 域交付前审查）：

发现的集成缺陷——require_node 的契约写明「端点必须存在 AND 属于本项目」，
但归属校验只对 item 生效；conversation/feature 同为 project_id 列的项目级表，
却只查存在性。后果：①跨项目节点可挂进本项目追溯图（图完整性破坏——impact/
coverage 把别家证据当自家的算）；②resolve_node 按全局 id 回标题/状态，项目 A
的 trace 读面可泄露项目 B 的对话/功能标题。回归锁：

- 跨项目 conversation/feature 建链拒绝（404 未知 / 422 属别家，与 item 语义对齐）；
- 同项目 feature/conversation 节点 roundtrip 正常（修复不误伤合法用途）；
- asset 保持 org 级（资产库本就跨项目共享，docs/10 M80-I240 分门语义）——不测。
"""
import pytest


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "追溯考官A", "ontology": "software-dev",
                                           "requirement": "考官R1"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _other_project_conv_and_feature(client):
    r = client.post("/api/projects", json={"name": "别家B", "ontology": "software-dev",
                                           "requirement": "x"})
    assert r.status_code == 200, r.text
    pid2 = r.json()["id"]
    convs = client.get("/api/conversations", params={"project_id": pid2}).json()["conversations"]
    assert convs, "建项目即产生 bootstrap 会话（M66-I198）"
    feat = client.post(f"/api/projects/{pid2}/features",
                       json={"title": "别家功能"}).json()
    return pid2, convs[0]["id"], feat["id"]


def test_trace_rejects_cross_project_conversation_and_feature(client, pid):
    """问题复现→回归锁：跨项目 conversation/feature 不得挂进本项目追溯图。
    （注意 source/target 必须异侧：两端同为外项目节点会先被自环守卫 422，
    归属缺陷根本不会被触达——首轮复现即踩此假阳性，已修正。）"""
    req = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "requirement", "title": "登录鉴权"}).json()
    _, conv_id, feat_id = _other_project_conv_and_feature(client)

    r = client.post(f"/api/projects/{pid}/trace/links",
                    json={"source_type": "conversation", "source_ref": conv_id,
                          "relation": "documents", "target_type": "item",
                          "target_ref": req["id"]})
    assert r.status_code == 422, f"跨项目对话被接受：{r.status_code} {r.text}"
    r = client.post(f"/api/projects/{pid}/trace/links",
                    json={"source_type": "feature", "source_ref": feat_id,
                          "relation": "implements", "target_type": "item",
                          "target_ref": req["id"]})
    assert r.status_code == 422, f"跨项目功能被接受：{r.status_code} {r.text}"

    # 图零污染：本项目链接列表为空，他项目标题不出现在任何解析结果里
    links = client.get(f"/api/projects/{pid}/trace/links").json()["links"]
    assert links == []

    # 未知 id 仍 404（与 item 语义一致：404=不存在，422=存在但属别家）
    r = client.post(f"/api/projects/{pid}/trace/links",
                    json={"source_type": "conversation", "source_ref": "conv_ghost",
                          "relation": "documents", "target_type": "item",
                          "target_ref": "i_also_ghost"})
    assert r.status_code == 404


def test_trace_same_project_conversation_feature_roundtrip(client, pid):
    """正向控制：同项目的对话/功能节点照常建链，impact 解析出标题。"""
    req = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "requirement", "title": "登录鉴权"}).json()
    convs = client.get("/api/conversations", params={"project_id": pid}).json()["conversations"]
    conv_id = convs[0]["id"]
    feat = client.post(f"/api/projects/{pid}/features",
                       json={"title": "认证功能"}).json()

    assert client.post(f"/api/projects/{pid}/trace/links",
                       json={"source_type": "conversation", "source_ref": conv_id,
                             "relation": "documents", "target_type": "item",
                             "target_ref": req["id"]}).status_code == 200
    assert client.post(f"/api/projects/{pid}/trace/links",
                       json={"source_type": "feature", "source_ref": feat["id"],
                             "relation": "implements", "target_type": "item",
                             "target_ref": req["id"]}).status_code == 200

    impact = client.get(f"/api/projects/{pid}/trace/impact",
                        params={"node_ref": req["id"]}).json()
    assert impact["groups"]["documents"][0]["title"] == convs[0].get("title") or \
        impact["groups"]["documents"][0]["ref"] == conv_id
    assert impact["groups"]["implementation"][0]["title"] == "认证功能"
    assert impact["summary"]["needs_review"] == 0

    cov = client.get(f"/api/projects/{pid}/trace/coverage").json()
    assert cov["summary"]["closed"] == 0  # 有实现无测试——闭环判定不受对话边干扰
    assert cov["gaps"]["stale_links"] == []


def test_trace_impact_root_cross_project_refused(client, pid):
    """R2-F1（docs/13 Round 2·A 类·读面）：impact 根节点此前只查存在性不查归属
    ——项目 A 成员拿项目 B 的 conversation/feature/item id 当 impact 根，
    resolve_node 按全局 id 回 B 的 title/status（写侧 R1-F1 已堵，读侧漏网）。
    回归锁：跨项目根 422（404=不存在/422=属别家，与写路径语义一致）+ 未知根 404
    + 同项目根正向控制 + asset 保持 org 级（docs/10 M80-I240 分门语义·不测）。"""
    req_a = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "requirement", "title": "A 的需求"}).json()
    pid2, conv_b, feat_b = _other_project_conv_and_feature(client)
    item_b = client.post(f"/api/projects/{pid2}/items",
                         json={"concept_id": "task", "title": "B 的任务"}).json()

    # 修复前：三连 200，且 node 字段携带别家 title/status（读侧信息泄露）
    for ntype, nref in (("conversation", conv_b), ("feature", feat_b), ("item", item_b["id"])):
        r = client.get(f"/api/projects/{pid}/trace/impact",
                       params={"node_type": ntype, "node_ref": nref})
        assert r.status_code == 422, f"跨项目 {ntype} 根被接受：{r.status_code} {r.text}"

    # 未知根仍 404（404=不存在 / 422=存在但属别家）
    r = client.get(f"/api/projects/{pid}/trace/impact",
                   params={"node_type": "item", "node_ref": "i_ghost"})
    assert r.status_code == 404

    # 正向控制：同项目根照常解析（不误伤合法读面）
    ok = client.get(f"/api/projects/{pid}/trace/impact",
                    params={"node_type": "item", "node_ref": req_a["id"]})
    assert ok.status_code == 200
    assert ok.json()["node"]["requirement_like"] is True
    assert ok.json()["node"]["title"] == "A 的需求"
