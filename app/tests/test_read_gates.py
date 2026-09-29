"""M76-I228: read-side gate audit (docs/01 §BU.1, API1:2023 BOLA matrix) —
auth_gate has left GETs open since M8 and pushed read gates into the domains;
items/comments/artifacts(M72) had them but the assets org library, template
packs, expense ledger and automation rules did not. Matrix: org-level reads
(assets / template-packs) gate on LOGIN (401 anonymous — there is no project
to be a member of); project-level reads (expenses / automations) gate on
PROJECT MEMBERSHIP (403 for anonymous and outsiders alike). Local mode stays
trusted (every other test depends on it)."""
import pytest

from apm import config


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "读门审计", "ontology": "software-dev", "requirement": "I228"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    # seed one row on each audited surface (local mode — trusted)
    assert client.put(f"/api/projects/{pid}/artifacts/test/g.md",
                      json={"content": "# g", "message": "qa: gate"}).status_code == 200
    art = client.get(f"/api/projects/{pid}/artifacts").json()["artifacts"][0]
    client.post("/api/assets", json={
        "source_project_id": pid, "artifact_path": art["path"], "commit": art["commit"],
        "library": "test", "kind": "test-suite", "title": "门禁资产"})
    client.post(f"/api/projects/{pid}/expenses", json={
        "description": "门禁费用", "qty": 1, "unit_price": 1,
        "currency": "CNY", "spent_on": "2026-09-30"})
    client.post(f"/api/projects/{pid}/automations", json={
        "name": "读门审计规则", "trigger_event": "item.created",
        "condition": {"concept_id": "bug"},
        "action": {"type": "set_field", "field_id": "severity", "value": "P0"}})
    return pid


def _switch_network_with(client, users: list[tuple[str, str]]):
    """Create users BEFORE the switch (POST /users is admin-only in network
    mode — smoke 77 lesson), then flip auth_mode."""
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    for uid, pwd in users:
        assert client.post("/api/users", json={"id": uid, "name": uid, "password": pwd}).status_code == 200, uid
    config.settings.auth_mode = "network"


def _login(client, uid, pwd):
    assert client.post("/api/auth/login", json={"user_id": uid, "password": pwd}).status_code == 200


def test_org_reads_gate_on_login(client, pid):
    _switch_network_with(client, [("outsider", "out-pass")])
    try:
        # anonymous: org reads 401 (login required), project reads 403 (no membership)
        assert client.get("/api/assets").status_code == 401
        assert client.get("/api/assets/insights").status_code == 401
        assert client.get("/api/template-packs").status_code == 401
        assert client.get(f"/api/projects/{pid}/expenses").status_code == 403
        assert client.get(f"/api/projects/{pid}/automations").status_code == 403

        # logged-in outsider: org library readable (instance member), project ledger not
        _login(client, "outsider", "out-pass")
        assert client.get("/api/assets").status_code == 200
        assert client.get("/api/template-packs").status_code == 200
        assert client.get(f"/api/projects/{pid}/expenses").status_code == 403
        assert client.get(f"/api/projects/{pid}/automations").status_code == 403

        # logged-in owner: everything readable
        assert client.post("/api/auth/logout").status_code == 200
        _login(client, "u_admin", "admin-pass")
        assert client.get(f"/api/projects/{pid}/expenses").json()["expenses"]
        assert client.get(f"/api/projects/{pid}/automations").json()["rules"]

        # feed surfaces keep their M45 feed_key semantics (keyless → 422), untouched here
        assert client.get(f"/api/projects/{pid}/feed.atom").status_code == 422
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
        client.post("/api/auth/logout")


def test_local_mode_stays_trusted(client, pid):
    # no login at all — local mode gates return early (every other test relies on this)
    assert client.get("/api/assets").status_code == 200
    assert client.get("/api/template-packs").status_code == 200
    assert client.get(f"/api/projects/{pid}/expenses").status_code == 200
    assert client.get(f"/api/projects/{pid}/automations").status_code == 200
