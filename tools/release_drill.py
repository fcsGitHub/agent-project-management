#!/usr/bin/env python
"""One-command release drill (M88-I267, docs/01 §CG.2).

Runs the full backup/restore cycle against a throwaway data dir:
seed -> baseline -> backup -> wipe (gated on backup EXIT=0) -> restore
-> rebuild -> reconcile (projects / events / FTS / artifact content)
-> per-step timings. Exit 0 only when every reconciled item matches.

M86 drill disciplines baked in: the wipe only happens after the backup
succeeded; Windows read-only git object attributes are cleared on delete;
the reconcile ledger is the four-item one from docs/11 §5.2.1.

Usage: python tools/release_drill.py [--port 8141] [--keep]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def sh(cmd: list[str], env_extra: dict[str, str] | None = None) -> tuple[int, str]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def wait_health(port: int, deadline_s: float = 30.0) -> None:
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"http://localhost:{port}/api/health", timeout=2) as r:
                if json.load(r).get("status") == "ok":
                    return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f"server on :{port} never became healthy")


def start_server(port: int, data_dir: Path, log: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["APM_DATA_DIR"] = str(data_dir)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apm.main:app", "--port", str(port)],
        cwd=REPO / "app", env=env,
        stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    wait_health(port)
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def force_remove(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get(port: int, path: str):
    with urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=10) as r:
        return json.load(r)


def post(port: int, path: str):
    req = urllib.request.Request(f"http://localhost:{port}{path}", method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def snapshot(port: int, data_dir: Path) -> dict:
    projects = len(get(port, "/api/projects")["projects"])
    import sqlite3
    # sqlite3 connections must be closed explicitly — `with` only manages
    # transactions, and a leaked handle makes the later wipe fail (WinError 32).
    con = sqlite3.connect(data_dir / "apm.db")
    try:
        events = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        con.close()
    fts = get(port, "/api/search?q=" + urllib.parse.quote("周报"))
    fts_hits = len(fts.get("results", fts)) if isinstance(fts, dict) else len(fts)
    files = sorted(glob.glob(str(data_dir / "content" / "**" / "*.md"),
                             recursive=True))
    h = hashlib.sha256()
    for f in files:
        h.update(Path(f).read_bytes())
    return {"projects": projects, "events": events, "fts_hits": fts_hits,
            "artifact_files": len(files), "content_sha": h.hexdigest()[:16]}


def rmtree_retry(path: Path, attempts: int = 5) -> None:
    # Windows can hold file handles briefly after a process exits.
    for i in range(attempts):
        try:
            shutil.rmtree(path, onerror=force_remove)
            return
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(1.0)


def main() -> int:
    ap = argparse.ArgumentParser(description="one-command backup/restore drill")
    ap.add_argument("--port", type=int, default=8141,
                    help="port for the throwaway drill server")
    ap.add_argument("--keep", action="store_true",
                    help="keep the drill data dir and backup zip for inspection")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="apm-drill-"))
    data_dir = tmp / "data"
    zip_path = tmp / "drill.zip"
    log = tmp / "uvicorn.log"
    t = {}

    print(f"drill dir: {tmp}")
    t["start"] = time.perf_counter()
    proc = start_server(args.port, data_dir, log)
    try:
        code, out = sh([sys.executable, "tools/seed.py", "--api",
                        f"http://localhost:{args.port}"])
        if code != 0:
            raise SystemExit(f"seed failed ({code}):\n{out[-500:]}")
        t["seed"] = time.perf_counter()
        print(f"seed ok ({t['seed'] - t['start']:.1f}s)")

        baseline = snapshot(args.port, data_dir)
        print("baseline:", json.dumps(baseline, ensure_ascii=False))

        code, out = sh([sys.executable, "tools/backup.py", "-o", str(zip_path)],
                       {"APM_DATA_DIR": str(data_dir)})
        if code != 0:
            raise SystemExit(f"backup failed ({code}) — drill stops before wipe:\n{out[-500:]}")
        t["backup"] = time.perf_counter()
        print(f"backup ok ({t['backup'] - t['seed']:.1f}s) — wipe gate passed")

        stop_server(proc)
        rmtree_retry(data_dir)
        if data_dir.exists():
            raise SystemExit("wipe failed — data dir still present")
        t["wipe"] = time.perf_counter()
        print(f"wiped ({t['wipe'] - t['backup']:.1f}s)")

        code, out = sh([sys.executable, "tools/restore.py", str(zip_path),
                        "--data-dir", str(data_dir)])
        if code != 0:
            raise SystemExit(f"restore failed ({code}):\n{out[-500:]}")
        t["restore"] = time.perf_counter()
        print(f"restore ok ({t['restore'] - t['wipe']:.1f}s)")

        proc = start_server(args.port, data_dir, log)
        r = post(args.port, "/api/system/rebuild-projections")
        t["rebuild"] = time.perf_counter()
        print(f"rebuild ok: events_replayed={r.get('events_replayed')} "
              f"({t['rebuild'] - t['restore']:.1f}s)")

        after = snapshot(args.port, data_dir)
        t["done"] = time.perf_counter()
        print("after   :", json.dumps(after, ensure_ascii=False))
        ok = baseline == after
        print("reconciled:", ok)
        print(f"RTO (wipe -> reconciled): {t['done'] - t['wipe']:.1f}s")
        if not ok:
            diff = {k: (baseline.get(k), after.get(k))
                    for k in set(baseline) | set(after)
                    if baseline.get(k) != after.get(k)}
            print("MISMATCH:", json.dumps(diff, ensure_ascii=False))
        return 0 if ok else 1
    finally:
        stop_server(proc)
        if not args.keep:
            rmtree_retry(tmp)
            print("drill dir cleaned")


if __name__ == "__main__":
    sys.exit(main())
