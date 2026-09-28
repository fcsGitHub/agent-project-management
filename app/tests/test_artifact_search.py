"""M71-I213: artifact content joins global search as the fourth type —
PRD/WBS/报告 are the factory's knowledge assets; until now they were
unfindable once written to git. Index = bigram(path + current content),
re-indexed on every artifact write (projector reads git's current state, so
rebuild replay converges to the same final row)."""
import pytest

from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "工件搜索", "ontology": "software-dev"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _put(client, pid: str, path: str, content: str) -> None:
    r = client.put(f"/api/projects/{pid}/artifacts/{path}",
                   json={"content": content, "message": "seed"})
    assert r.status_code == 200, r.text


def test_artifact_index_update_and_rebuild(client, pid):
    _put(client, pid, "artifacts/prd/feature-auth.md",
         "# 认证 PRD\n\n登录只保留一种方式：手机号验证码。\n")

    # content hit — the knowledge asset is findable
    r = client.get("/api/search", params={"q": "验证码", "types": "artifacts"})
    assert r.status_code == 200, r.text
    hits = r.json()["artifacts"]
    assert len(hits) == 1
    assert hits[0]["path"] == "artifacts/prd/feature-auth.md"
    assert hits[0]["title"] == "feature-auth.md"
    assert hits[0]["project_name"] == "工件搜索"

    # path token also matches
    r = client.get("/api/search", params={"q": "feature-auth", "types": "artifacts"})
    assert len(r.json()["artifacts"]) == 1

    # content rewrite: old words drop out, new words hit
    _put(client, pid, "artifacts/prd/feature-auth.md",
         "# 认证 PRD v2\n\n登录改为密码加_totp。\n")
    r = client.get("/api/search", params={"q": "验证码", "types": "artifacts"})
    assert r.json()["artifacts"] == []
    r = client.get("/api/search", params={"q": "totp", "types": "artifacts"})
    assert len(r.json()["artifacts"]) == 1

    # second artifact, first still hits
    _put(client, pid, "artifacts/wbs/plan.md", "# WBS\n\n任务拆解与里程碑。\n")
    r = client.get("/api/search", params={"q": "totp", "types": "artifacts"})
    assert len(r.json()["artifacts"]) == 1

    # rebuild replays the index to the same final state
    projections.rebuild()
    r = client.get("/api/search", params={"q": "totp", "types": "artifacts"})
    assert len(r.json()["artifacts"]) == 1
    r = client.get("/api/search", params={"q": "里程碑", "types": "artifacts"})
    assert len(r.json()["artifacts"]) == 1


def test_artifact_type_scoping_and_defaults(client, pid):
    _put(client, pid, "artifacts/prd/note.md", "# 备注\n\n只允许一种部署方式。\n")

    # artifacts type participates in the all-types query (frontend default)
    all_types = "items,comments,conversations,artifacts"
    r = client.get("/api/search", params={"q": "部署方式", "types": all_types})
    assert len(r.json().get("artifacts", [])) == 1

    # items query does not leak artifact rows and vice versa
    r = client.get("/api/search", params={"q": "部署方式", "types": "items"})
    assert r.json()["artifacts"] == []
