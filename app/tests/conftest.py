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
def tmp_data(tmp_path, monkeypatch):
    """Isolated storage root; resets the DB singleton for the test."""
    # Drain engine threads from previous tests before swapping the database.
    from apm.runtime.engine import wait_quiescent

    wait_quiescent()
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
    yield data_dir
    # Drain again before monkeypatch restores the real data_dir: lingering
    # engine threads must never touch the developer's actual storage.
    wait_quiescent()


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


@pytest.fixture()
def isolated_ontologies(tmp_path, monkeypatch):
    """Copy the real ontologies/ into tmp and point settings at the copy.

    Ontology learning (M4-I14) writes back ontology YAML; tests and smoke must
    never mutate the repository's source files. Reload clears the name cache.
    """
    import shutil

    from apm import config

    dst = tmp_path / "ontologies"
    shutil.copytree(config.settings.ontology_dir, dst)
    monkeypatch.setattr(config.settings, "ontology_dir_override", dst)
    # Ontology pack import writes role/prompt files here too — isolate agents/.
    agents_dst = tmp_path / "agents"
    shutil.copytree(config.settings.agents_dir, agents_dst)
    monkeypatch.setattr(config.settings, "agents_dir_override", agents_dst)
    from apm.domains import ontology as ontology_mod
    from apm.runtime import roles as roles_mod

    ontology_mod.reload_all()
    roles_mod.reset_roles()
    yield dst
    # Undo overrides BEFORE reloading: teardown finalizers run reverse to setup,
    # so monkeypatch would otherwise restore the paths *after* this reload and
    # leave the cache holding the isolated copy.
    config.settings.ontology_dir_override = None
    config.settings.agents_dir_override = None
    ontology_mod.reload_all()
    roles_mod.reset_roles()
