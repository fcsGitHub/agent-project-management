#!/usr/bin/env python
"""Restore an AgentPM backup zip (M60-I180, docs/01 §BE.1).

Usage: python tools/restore.py backups/apm-20260927.zip --data-dir data [--ontologies-dir ontologies]
Stop the server (or point it elsewhere) before restoring: the restore replaces
apm.db, content/ and assets-repo/ under the target data dir and strips stale
WAL/SHM sidecars. Ontologies restore only when --ontologies-dir is given —
overwriting the live ontology tree is a decision, not a side effect."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))

from apm.ops import restore_backup  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="restore AgentPM data from a backup zip")
    ap.add_argument("zip", help="backup zip path")
    ap.add_argument("--data-dir", required=True, help="target data dir")
    ap.add_argument("--ontologies-dir", default=None,
                    help="target ontologies dir (omit to keep live ontologies)")
    args = ap.parse_args()
    r = restore_backup(Path(args.zip), Path(args.data_dir),
                       Path(args.ontologies_dir) if args.ontologies_dir else None)
    print(f"restored → {r['data_dir']} (files: {r['files']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
