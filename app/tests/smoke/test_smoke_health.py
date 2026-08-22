"""Smoke baseline entry (I0): the service starts and reports healthy."""
import pytest


@pytest.mark.smoke
def test_smoke_service_up(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
