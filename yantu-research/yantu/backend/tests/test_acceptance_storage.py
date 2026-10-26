"""Acceptance copies must keep SQLite records and upload blobs together."""

import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from run_acceptance import snapshot, verify_storage


def test_snapshot_copies_database_and_referenced_files(tmp_path):
    source = tmp_path / "source"
    uploads = source / "uploads"
    uploads.mkdir(parents=True)
    names = [str(uuid4()), str(uuid4())]
    contents = [b"current document", b"previous version"]
    with sqlite3.connect(source / "acceptance.db") as db:
        for table in ("yt_resources", "yt_resource_versions"):
            db.execute(f"CREATE TABLE {table} (storage_name TEXT, size INTEGER)")
        for table, name, content in zip(("yt_resources", "yt_resource_versions"), names, contents):
            db.execute(f"INSERT INTO {table} VALUES (?, ?)", (name, len(content)))
            (uploads / name).write_bytes(content)

    target = tmp_path / "target"
    assert snapshot(source, target) == {"yt_resources": 1, "yt_resource_versions": 1, "files": 2}
    assert [(target / "uploads" / name).read_bytes() for name in names] == contents
    with pytest.raises(ValueError, match="不会覆盖"):
        snapshot(source, target)

    (target / "uploads" / names[0]).unlink()
    with pytest.raises(ValueError, match="缺少文件"):
        verify_storage(target / "acceptance.db", target / "uploads")


def test_serve_refuses_incomplete_acceptance_copy(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    with sqlite3.connect(tmp_path / "acceptance.db") as db:
        db.execute("CREATE TABLE yt_resources (storage_name TEXT, size INTEGER)")
        db.execute("CREATE TABLE yt_resource_versions (storage_name TEXT, size INTEGER)")
        db.execute("INSERT INTO yt_resources VALUES (?, ?)", (str(uuid4()), 8))
    script = Path(__file__).resolve().parents[2] / "run_acceptance.py"
    result = subprocess.run(
        [sys.executable, str(script), "serve", str(tmp_path), "--port", "8780"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "缺少文件" in result.stderr
