#!/usr/bin/env python
"""Backup AgentPM data to a single zip (M60-I180, docs/01 §BE.1).

Usage: python tools/backup.py -o backups/apm-20260927.zip
Safe against a live server: the db is snapshotted via the online backup API
(WAL frames folded in), never a raw file copy. Pair with tools/restore.py —
run the drill (backup → wipe → restore → verify) regularly; a backup is only
real once a restore has proven it."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))

from apm.ops import create_backup  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="backup AgentPM data to one zip")
    ap.add_argument("-o", "--out", required=True, help="output zip path")
    args = ap.parse_args()
    r = create_backup(Path(args.out))
    m = r["manifest"]
    print(f"backup → {r['path']}")
    print(f"  created_at={m['created_at']} events={m['event_count']}")
    print(f"  data_dir={m['data_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
