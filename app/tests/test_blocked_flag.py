"""M42-I128 board blocked flag (docs/01 §AO.1, Businessmap blocked-flag
semantics): an item carries `blocked: true` when an unfinished blocks-blocker
or an unfinished depends_on prerequisite exists — the same caliber as the I78
closure guard, derived on every list/board payload so the flag is visible
without opening a drawer. Finishing the upstream clears the flag."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "阻塞徽标", "ontology": "software-dev", "requirement": "I128"})
    assert r.status_code == 200
    return r.json()["id"]


def _mk(client, pid, title):
    return client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": title}).json()["id"]


def test_blocks_flag_and_clear(client, tmp_data, isolated_ontologies, pid):
    blocker = _mk(client, pid, "阻塞者")
    blocked = _mk(client, pid, "被阻塞者")
    assert client.post(f"/api/items/{blocker}/relations",
                       json={"to_item": blocked, "relation_type": "blocks"}).status_code == 200

    def flag(iid):
        return client.get(f"/api/projects/{pid}/items").json()["items"] and \
            next(i["blocked"] for i in client.get(f"/api/projects/{pid}/items").json()["items"]
                 if i["id"] == iid)

    assert flag(blocked) is True
    assert flag(blocker) is False                       # the blocker isn't blocked
    # finishing the blocker clears the flag (same caliber as the I78 guard)
    assert client.patch(f"/api/items/{blocker}", json={"status": "done"}).status_code == 200
    assert flag(blocked) is False


def test_depends_on_flag_and_rebuild(client, tmp_data, isolated_ontologies, pid):
    pre = _mk(client, pid, "前置")
    dep = _mk(client, pid, "后继")
    # direction: from_item is the dependent, to_item the prerequisite
    assert client.post(f"/api/items/{dep}/relations",
                       json={"to_item": pre, "relation_type": "depends_on"}).status_code == 200

    assert flag_of(client, pid, dep) is True
    assert client.patch(f"/api/items/{pre}", json={"status": "done"}).status_code == 200
    assert flag_of(client, pid, dep) is False

    projections.rebuild()
    assert flag_of(client, pid, dep) is False           # derivation is replay-stable


def flag_of(client, pid, iid):
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    return next(i["blocked"] for i in items if i["id"] == iid)
