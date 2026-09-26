"""M60-I180 备份/恢复演练（docs/01 §BE.1）：在线备份 API 取 WAL 一致快照
（绝不直接拷活库文件）；演练闭环=备份→（等价于系统已毁的）全新空目录恢复
→文件级校验——event_count 对账 + integrity_check + content 工件与本体文件
在位。「备份会自己跑，演练是为了证明恢复仍然有效。」"""
from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

import pytest

from apm import config
from apm.ops import create_backup, restore_backup


def test_backup_restore_drill(client, tmp_data, isolated_ontologies, tmp_path):
    # 造真实数据：项目 + 工件（content 仓含 Git 历史）
    p = client.post("/api/projects",
                    json={"name": "灾备演练", "ontology": "software-dev",
                          "requirement": "drill"}).json()
    r = client.put(f"/api/projects/{p['id']}/artifacts/docs/note.md",
                   json={"content": "# 演练工件", "message": "docs: note"})
    assert r.status_code == 200, r.text

    out = tmp_path / "apm-backup.zip"
    result = create_backup(out)
    manifest = result["manifest"]
    assert manifest["format"] == "apm-backup-1"
    assert manifest["event_count"] > 0

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "manifest.json" in names and "apm.db" in names
        assert any(n.startswith("content/") for n in names)
        assert any(n.startswith("ontologies/") for n in names)
        assert any("software-dev.yaml" in n for n in names)

    # 演练第②步：向全新空目录恢复（等价于原系统已毁）——含本体目标
    fresh = tmp_path / "restored-data"
    fresh_ont = tmp_path / "restored-ontologies"
    restored = restore_backup(out, fresh, fresh_ont)
    assert restored["restored"] is True
    assert restored["files"]["apm.db"] == 1  # 单独计数
    assert restored["files"]["content/"] > 0
    assert restored["files"]["ontologies/"] > 0

    # 文件级校验：事件数对账 + sqlite 完整性 + 工件与本体在位
    conn = sqlite3.connect(fresh / "apm.db")
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    assert count == manifest["event_count"]
    assert integrity == "ok"
    assert (fresh / "content" / p["id"] / "artifacts" / "docs" / "note.md").exists()
    assert (fresh_ont / "software-dev.yaml").exists()


def test_restore_rejects_foreign_zip(client, tmp_data, isolated_ontologies, tmp_path):
    foreign = tmp_path / "foreign.zip"
    with zipfile.ZipFile(foreign, "w") as z:
        z.writestr("readme.txt", "not an apm backup")
    with pytest.raises(ValueError, match="not an apm backup"):
        restore_backup(foreign, tmp_path / "target")
