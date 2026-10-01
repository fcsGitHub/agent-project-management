"""Backup & restore (M60-I180, docs/01 §BE.1): one zip carrying a WAL-consistent
SQLite snapshot (online backup API — copying a live .db file loses unchecked
WAL frames), the per-project content repos, the assets repo, and the effective
ontologies directory, plus a manifest for integrity checks. Restore strips
stale WAL/SHM sidecars so they can't corrupt the restored snapshot.

The restore drill (backup → wipe → restore → verify) is the point: "backups
run themselves; the drill exists to prove the RESTORE still works." Thin CLIs
live in tools/backup.py and tools/restore.py."""
from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from apm import config

BACKUP_FORMAT = "apm-backup-1"


def create_backup(out_path: Path) -> dict:
    """Snapshot the whole data dir + live ontologies into one zip. Returns the
    manifest so callers (CLIs, tests) can assert on what was captured."""
    s = config.settings
    data: Path = s.data_dir
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "format": BACKUP_FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "data_dir": str(data),
        "ontology_dir": str(s.ontology_dir),
        "includes": ["apm.db", "content/", "assets-repo/", "ontologies/"],
    }
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        # online backup API: consistent snapshot with WAL frames folded in
        tmp_db = data / "apm.backup.tmp.db"
        tmp_db.parent.mkdir(parents=True, exist_ok=True)
        # 源库必须存在——sqlite3.connect 对缺失路径静默建空库，备份出"空成功"
        # 会让毁库闸失效（M86-I261 演练实录：未设 APM_DATA_DIR 时静默连默认路径）。
        if not Path(s.db_path).exists():
            raise SystemExit(
                f"backup: source db not found at {s.db_path} — "
                "check APM_DATA_DIR before wiping anything")
        src = sqlite3.connect(s.db_path)
        dst = sqlite3.connect(tmp_db)
        src.backup(dst)
        manifest["event_count"] = dst.execute(
            "SELECT COUNT(*) FROM events").fetchone()[0]
        dst.close()
        src.close()
        z.write(tmp_db, "apm.db")
        tmp_db.unlink()
        for prefix, root in (("content/", s.content_root),
                             ("assets-repo/", s.assets_repo_path),
                             ("ontologies/", s.ontology_dir)):
            if not Path(root).exists():
                continue
            for f in sorted(Path(root).rglob("*")):
                if f.is_file():
                    z.write(f, prefix + str(f.relative_to(root)))
        z.writestr("manifest.json",
                   json.dumps(manifest, ensure_ascii=False, indent=2))
    return {"path": str(out_path), "manifest": manifest}


def restore_backup(zip_path: Path, data_dir: Path,
                   ontologies_dir: Path | None = None) -> dict:
    """Restore a backup zip into `data_dir` (db + content + assets-repo).
    Ontologies restore only when an explicit target is given — overwriting the
    live ontology tree is a decision, not a side effect. Raises on a foreign or
    truncated archive; stale -wal/-shm sidecars are removed first."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        if "manifest.json" not in names or "apm.db" not in names:
            raise ValueError("not an apm backup zip: manifest.json/apm.db missing")
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("format") != BACKUP_FORMAT:
            raise ValueError(f"unsupported backup format: {manifest.get('format')}")
        for suffix in ("-wal", "-shm"):
            sidecar = data_dir / f"apm.db{suffix}"
            if sidecar.exists():
                sidecar.unlink()
        restored = {"apm.db": 0, "content/": 0, "assets-repo/": 0, "ontologies/": 0}
        for info in z.infolist():
            name = info.filename
            if name.endswith("/") or name == "manifest.json":
                continue
            if name == "apm.db":
                target = data_dir / "apm.db"
            elif name.startswith("content/"):
                target = data_dir / name
            elif name.startswith("assets-repo/"):
                target = data_dir / name
            elif name.startswith("ontologies/") and ontologies_dir is not None:
                target = Path(ontologies_dir) / name[len("ontologies/"):]
            else:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
            for prefix in restored:
                if name == "apm.db" or name.startswith(prefix):
                    restored[prefix] += 1
                    break
    return {"restored": True, "data_dir": str(data_dir),
            "ontologies_dir": str(ontologies_dir) if ontologies_dir else None,
            "files": restored, "manifest": manifest}
