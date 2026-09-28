"""M70-I210 资产版本历史与 diff（docs/01 §BO.1）：write_asset 每次 git
commit+assets.version 自增——账本早已存在，读侧三端点把它翻开（history/
diff/restore）。恢复是 append-only：旧 body 重写为新版本（version+1），
历史永不回卷——与事件流同一纪律。"""
from __future__ import annotations

import pytest

from apm import config
from apm.content import assetsrepo


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def asset_id(client, tmp_data, isolated_ontologies):
    """One asset written twice directly through the repo layer (content drift)."""
    aid = "a_hist1"
    assetsrepo.write_asset("doc-lib", aid,
                           {"title": "测试资产", "kind": "doc", "library": "doc-lib",
                            "tags": [], "status": "draft"},
                           "# 第一版\n\n原始内容。\n")
    assetsrepo.write_asset("doc-lib", aid,
                           {"title": "测试资产", "kind": "doc", "library": "doc-lib",
                            "tags": [], "status": "draft"},
                           "# 第二版\n\n内容已演进。\n")
    # register in the projection so require_asset resolves it
    from apm.core import events
    events.emit(event_type="asset.drafted", agg_type="asset", agg_id=aid,
                payload={"library": "doc-lib", "kind": "doc", "title": "测试资产",
                         "tags": [], "commit": assetsrepo.asset_log("doc-lib", aid)[0]["commit"],
                         "status": "draft"})
    return aid


def test_history_and_diff(client, asset_id):
    r = client.get(f"/api/assets/{asset_id}/history")
    assert r.status_code == 200, r.text
    hist = r.json()["history"]
    assert len(hist) == 2  # two writes = two commits
    assert hist[0]["commit"] != hist[1]["commit"]

    r = client.get(f"/api/assets/{asset_id}/diff",
                   params={"from_commit": hist[1]["commit"], "to_commit": hist[0]["commit"]})
    assert r.status_code == 200, r.text
    patch = r.json()["patch"]
    assert "-原始内容" in patch.replace(" ", "") or "-# 第一版" in patch
    assert "+内容已演进" in patch.replace(" ", "") or "+# 第二版" in patch

    # missing params → 422
    assert client.get(f"/api/assets/{asset_id}/diff",
                      params={"from_commit": hist[1]["commit"]}).status_code == 422


def test_restore_is_append_only(client, asset_id):
    hist = client.get(f"/api/assets/{asset_id}/history").json()["history"]
    oldest = hist[-1]["commit"]

    r = client.post(f"/api/assets/{asset_id}/restore", json={"commit": oldest})
    assert r.status_code == 200, r.text
    assert "第一版" in r.json()["content"]  # body restored
    assert r.json()["version"] == 2  # version bumped, not rewound

    hist2 = client.get(f"/api/assets/{asset_id}/history").json()["history"]
    assert len(hist2) == 3  # restore appends a third commit
    assert "第一版" in client.get(f"/api/assets/{asset_id}").json()["content"]

    # unknown commit → 422
    assert client.post(f"/api/assets/{asset_id}/restore",
                       json={"commit": "deadbeef"}).status_code == 422
