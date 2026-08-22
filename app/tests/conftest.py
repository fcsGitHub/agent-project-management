"""Shared fixtures: isolated data dir + live FastAPI test client."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `apm` importable when pytest runs from the app/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from apm import config
from apm.core import db


@pytest.fixture()
def tmp_data(tmp_path, monkeypatch) -> Path:
    """Isolated storage root; resets the DB singleton for the test."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(config.settings, "data_dir", data_dir)
    monkeypatch.setattr(config.settings, "provider_mode", "replay")
    db.reset_for_tests(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "fixtures").mkdir(parents=True, exist_ok=True)
    (data_dir / "content").mkdir(parents=True, exist_ok=True)
    from apm.core.db import init_db

    init_db()
    from apm.runtime.engine import reset_saver_for_tests

    reset_saver_for_tests()
    return data_dir


@pytest.fixture()
def client(tmp_data) -> TestClient:
    from apm.main import create_app

    with TestClient(create_app()) as c:
        yield c


def wait_for(fn, timeout: float = 15.0, interval: float = 0.05):
    """Poll fn() until truthy; raises AssertionError with last value on timeout."""
    import time

    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"wait_for timeout, last={last!r}")
