"""M72-I216 (docs/01 §BQ.1): artifact endpoints gated by project membership —
repo-level permission inheritance, the GitHub/GitLab orthodoxy (artifacts are
files in the project repo; no per-file ACL, matching both platforms). Fills
the M45 audit blind spot: these endpoints live in content/ and never went
through the domains gating pass. local mode stays wide open (existing tests
unaffected — the gate only bites in network mode)."""
import pytest

from apm import config


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "工件门项目", "ontology": "software-dev"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture()
def network(client, pid):
    """network-mode rig: bootstrap admin + one viewer + one outsider."""
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user

    ensure_default_user()
    assert client.post("/api/auth/login",
                       json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
    assert client.post("/api/users",
                       json={"id": "u_viewer", "name": "只读员", "password": "v-pass"}).status_code == 200
    # add viewer as project member
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "u_viewer", "role": "viewer"}).status_code == 200, \
        client.post(f"/api/projects/{pid}/members",
                    json={"user_id": "u_viewer", "role": "viewer"}).text
    assert client.post("/api/users",
                       json={"id": "u_outsider", "name": "外人", "password": "o-pass"}).status_code == 200
    config.settings.auth_mode = "network"
    yield
    config.settings.auth_mode = "local"
    config.settings.admin_password = ""


def _put(client, pid: str):
    return client.put(f"/api/projects/{pid}/artifacts/artifacts/prd/x.md",
                      json={"content": "# x\n", "message": "seed"})


def test_network_mode_membership_gate(client, pid, network):
    # outsider (logged in, not a member): read and write both 403
    assert client.post("/api/auth/login",
                       json={"user_id": "u_outsider", "password": "o-pass"}).status_code == 200
    assert client.get(f"/api/projects/{pid}/artifacts").status_code == 403
    assert _put(client, pid).status_code == 403

    # viewer member: read 200, write 403 (read-only role)
    assert client.post("/api/auth/login",
                       json={"user_id": "u_viewer", "password": "v-pass"}).status_code == 200
    assert client.get(f"/api/projects/{pid}/artifacts").status_code == 200
    assert _put(client, pid).status_code == 403

    # admin (owner): everything passes
    assert client.post("/api/auth/login",
                       json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
    assert _put(client, pid).status_code == 200
    assert client.get(f"/api/projects/{pid}/artifacts").status_code == 200


def test_local_mode_unchanged(client, pid):
    # local mode (default) stays wide open — existing flows unaffected
    assert _put(client, pid).status_code == 200
    assert client.get(f"/api/projects/{pid}/artifacts").status_code == 200
