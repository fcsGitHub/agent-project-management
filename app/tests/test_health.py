"""I0 smoke baseline: service is up and answers health checks."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["provider_mode"] == "replay"
