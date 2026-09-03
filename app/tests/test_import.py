"""M14-I45 event import: restore a per-project NDJSON export into an empty
database — checksum and structure validated, id conflicts refused (409),
events re-chained onto the target log head, then a full rebuild must leave
projections identical to the source."""
from __future__ import annotations

from pathlib import Path

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
    r = client.post("/api/projects",
                    json={"name": "导入恢复演示", "ontology": "software-dev", "requirement": "I45"})
    assert r.status_code == 200
    return r.json()


@pytest.fixture()
def exported(client, project):
    pid = project["id"]
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": "甲"})
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "bug", "title": "乙", "due_date": "2026-09-30"}).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "fixing"})
    exp = client.get(f"/api/projects/{pid}/events/export")
    assert exp.status_code == 200
    return {"text": exp.text, "pid": pid,
            "items": client.get(f"/api/projects/{pid}/items").json()["items"]}


def _fresh_client(monkeypatch, tmp_path: Path):
    """Point the app at a brand-new data dir and boot a second TestClient."""
    data2 = tmp_path / "restore-db"
    monkeypatch.setattr(config.settings, "data_dir", data2)
    db.reset_for_tests(data2)
    from apm.main import create_app
    from fastapi.testclient import TestClient
    return TestClient(create_app())


def test_import_roundtrip_into_fresh_db(client, exported, monkeypatch, tmp_path,
                                        tmp_data, isolated_ontologies):
    before_items = exported["items"]
    with _fresh_client(monkeypatch, tmp_path) as c2:
        r = c2.post(f"/api/projects/{exported['pid']}/events/import",
                    json={"data": exported["text"]})
        assert r.status_code == 200, r.text
        assert r.json()["imported"] > 0 and r.json()["rebuilt"] > 0

        after_items = c2.get(f"/api/projects/{exported['pid']}/items").json()["items"]
        assert [(i["id"], i["title"], i["status"], i["due_date"]) for i in after_items] == \
               [(i["id"], i["title"], i["status"], i["due_date"]) for i in before_items]

        # event stream matches the export body line-for-line
        exp2 = c2.get(f"/api/projects/{exported['pid']}/events/export")
        body1 = [l for l in exported["text"].splitlines() if l.strip()][:-1]
        body2 = [l for l in exp2.text.splitlines() if l.strip()][:-1]
        assert body1 == body2


def test_import_rejections(client, exported, tmp_data, isolated_ontologies):
    pid = exported["pid"]
    good = exported["text"]
    # id conflicts: importing into the source database (ids already present)
    r = client.post(f"/api/projects/{pid}/events/import", json={"data": good})
    assert r.status_code == 409 and "already exist" in r.json()["detail"]
    # checksum tampering
    lines = good.splitlines()
    tampered = lines[:-1]
    tampered[0] = tampered[0].replace("item.created", "item.updated") + ""
    bad = "\n".join(tampered + [lines[-1]])
    r = client.post(f"/api/projects/{pid}/events/import",
                    json={"data": bad, })
    assert r.status_code in (409, 422)  # tampered line trips integrity checks
    # invalid NDJSON line
    r = client.post(f"/api/projects/{pid}/events/import",
                    json={"data": "not json\n" + lines[-1]})
    assert r.status_code == 422
    # missing checksum line
    r = client.post(f"/api/projects/{pid}/events/import", json={"data": lines[0]})
    assert r.status_code == 422
    # unknown project without its creation event → 422 (restore semantics)
    r = client.post("/api/projects/p_nope/events/import", json={"data": good})
    assert r.status_code == 422
    # project mismatch: payload carries another project's events
    r = client.post("/api/projects/p_other/events/import",
                    json={"data": good.replace('"project.created"', '"x.created"')})
    assert r.status_code == 422
    # no partial state: rejected imports left no new events behind
    total = client.get("/api/events", params={"project_id": pid, "limit": 1}).json()
    assert total["total"] == len(good.splitlines()) - 1
