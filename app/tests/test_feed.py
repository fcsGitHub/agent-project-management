"""M11-I36 Atom feeds: per-user feed keys (view/generate/rotate), key
authentication without cookies, membership-based visibility (non-member keys
are refused — the Redmine #20173 lesson), and well-formed Atom output."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest


@pytest.fixture(autouse=True)
def _restore_identity():
    from apm import config

    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "feed 演示", "ontology": "software-dev", "requirement": "I36"})
    assert r.status_code == 200
    return r.json()


def test_feed_key_lifecycle_and_rotate(client, tmp_data, isolated_ontologies, project):
    out = client.get("/api/me/feed-key").json()
    assert out["user_id"] == "u_admin" and len(out["feed_key"]) == 40 and out["created"] is True
    # Second view returns the SAME key (owner may read their own credential).
    again = client.get("/api/me/feed-key").json()
    assert again["feed_key"] == out["feed_key"] and again["created"] is False

    rot = client.post("/api/me/feed-key/rotate").json()
    assert rot["feed_key"] != out["feed_key"]
    # Old key is dead after rotation.
    out = client.get("/api/me/feed-key").json()
    assert out["feed_key"] == rot["feed_key"]


def test_feed_roundtrip_and_xml_shape(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    key = client.get("/api/me/feed-key").json()["feed_key"]
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "bug", "title": "feed 条目缺陷"})
    r = client.get(f"/api/projects/{pid}/feed.atom", params={"key": key})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/atom+xml")
    root = ET.fromstring(r.text)  # must be well-formed XML
    assert root.tag.endswith("feed")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    titles = [e.findtext("a:title", namespaces=ns) for e in root.findall("a:entry", ns)]
    assert any(t and "item.created" in t and "feed 条目缺陷" in t for t in titles)

    # Wrong key refused.
    assert client.get(f"/api/projects/{pid}/feed.atom", params={"key": "bad"}).status_code == 401
    assert client.get(f"/api/projects/{pid}/feed.atom").status_code in (401, 422)


def test_non_member_key_forbidden(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # A second user generates their own key (local-mode identity switch).
    client.post("/api/users", json={"id": "outsider", "name": "外人"})
    client.post("/api/session/identity", json={"user_id": "outsider"})
    out_key = client.get("/api/me/feed-key").json()["feed_key"]
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    r = client.get(f"/api/projects/{pid}/feed.atom", params={"key": out_key})
    assert r.status_code == 403
    denied = client.get("/api/events", params={"event_type": "access.denied"}).json()["events"]
    assert any("feed.atom" in (e["payload"].get("path") or "") for e in denied)

    # Once the owner adds them, the same key works (visibility, not the key, gates).
    client.post(f"/api/projects/{pid}/members",
                json={"user_id": "outsider", "role": "viewer"})
    r = client.get(f"/api/projects/{pid}/feed.atom", params={"key": out_key})
    assert r.status_code == 200
    ET.fromstring(r.text)
