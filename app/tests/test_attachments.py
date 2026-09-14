"""M40-I123 item attachments (docs/01 §AM.2, Redmine files/-directory
semantics): binaries live on disk under data_dir/attachments/{project_id}/,
metadata is projected (drop_projections ⇒ rebuild reproduces rows); uploads
are multipart with a conservative MB ceiling (Jira DC default), download
streams the stored bytes back byte-identical, and delete is a soft removal
(the disk file survives, the row is flagged removed)."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def item(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "附件演示", "ontology": "software-dev",
                            "requirement": "I123"}).json()["id"]
    return client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "带附件的任务"}).json()["id"]


def test_attachment_roundtrip(client, item, tmp_data):
    content = "附件内容 A ✓".encode("utf-8")
    r = client.post(f"/api/items/{item}/attachments",
                    files={"file": ("设计说明.txt", content, "text/plain")})
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["filename"] == "设计说明.txt" and meta["size"] == len(content)

    rows = client.get(f"/api/items/{item}/attachments").json()["attachments"]
    assert [a["id"] for a in rows] == [meta["id"]]

    dl = client.get(f"/api/items/{item}/attachments/{meta['id']}")
    assert dl.status_code == 200
    assert dl.content == content                       # byte-identical
    assert "attachment" in dl.headers.get("content-disposition", "")

    # metadata survives rebuild; the disk file is outside the event stream
    projections.rebuild()
    rows = client.get(f"/api/items/{item}/attachments").json()["attachments"]
    assert [a["id"] for a in rows] == [meta["id"]]
    dl2 = client.get(f"/api/items/{item}/attachments/{meta['id']}")
    assert dl2.content == content

    # soft delete: list hides it, download 404s
    assert client.delete(f"/api/items/{item}/attachments/{meta['id']}").status_code == 200
    assert client.get(f"/api/items/{item}/attachments").json()["attachments"] == []
    assert client.get(f"/api/items/{item}/attachments/{meta['id']}").status_code == 404


def test_attachment_size_limit(client, item, tmp_data, monkeypatch):
    monkeypatch.setattr(config.settings, "attachment_max_mb", 1)
    big = b"x" * (1024 * 1024 + 1)
    r = client.post(f"/api/items/{item}/attachments",
                    files={"file": ("big.bin", big, "application/octet-stream")})
    assert r.status_code == 413
    # empty upload refused
    r2 = client.post(f"/api/items/{item}/attachments",
                     files={"file": ("empty.txt", b"", "text/plain")})
    assert r2.status_code == 422


def test_attachment_wrong_item_is_404(client, item, tmp_data, isolated_ontologies):
    content = b"hello"
    meta = client.post(f"/api/items/{item}/attachments",
                       files={"file": ("a.txt", content, "text/plain")}).json()
    other = client.post("/api/projects",
                        json={"name": "别处", "ontology": "software-dev",
                              "requirement": "I123"}).json()["id"]
    other_item = client.post(f"/api/projects/{other}/items",
                             json={"concept_id": "task", "title": "别人的任务"}).json()["id"]
    assert client.get(f"/api/items/{other_item}/attachments/{meta['id']}").status_code == 404
    assert client.delete(f"/api/items/{other_item}/attachments/{meta['id']}").status_code == 404
    assert client.get(f"/api/items/{item}/attachments/at_nope").status_code == 404
