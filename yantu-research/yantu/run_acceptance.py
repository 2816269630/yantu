"""Create and run an isolated SQLite acceptance copy with its upload files."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from uuid import UUID


DATABASE_NAME = "acceptance.db"
UPLOADS_NAME = "uploads"
TABLES = ("yt_resources", "yt_resource_versions")


def storage_rows(database: Path) -> tuple[list[tuple[str, int]], dict[str, int]]:
    if not database.is_file():
        raise ValueError(f"数据库不存在：{database}")
    connection = sqlite3.connect(database)
    try:
        rows: list[tuple[str, int]] = []
        counts: dict[str, int] = {}
        for table in TABLES:
            entries = connection.execute(f"SELECT storage_name, size FROM {table}").fetchall()
            counts[table] = len(entries)
            rows.extend(entries)
        return rows, counts
    finally:
        connection.close()


def verify_storage(database: Path, uploads: Path) -> dict[str, int]:
    rows, counts = storage_rows(database)
    if not uploads.is_dir():
        raise ValueError(f"附件目录不存在：{uploads}")
    problems: list[str] = []
    for name, expected_size in rows:
        try:
            if str(UUID(name)) != name:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            problems.append(f"无效存储名：{name!r}")
            continue
        file = uploads / name
        if not file.is_file():
            problems.append(f"缺少文件：{name}")
        elif file.stat().st_size != expected_size:
            problems.append(f"文件大小不符：{name}（记录 {expected_size}，实际 {file.stat().st_size}）")
    if problems:
        details = "\n".join(problems[:10])
        if len(problems) > 10:
            details += f"\n另有 {len(problems) - 10} 项"
        raise ValueError(f"存储检查失败，拒绝启动验收服务：\n{details}")
    counts["files"] = len({name for name, _ in rows})
    return counts


def snapshot(source: Path, target: Path) -> dict[str, int]:
    source = source.resolve()
    target = target.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("源目录与目标目录不能相同或互相包含")
    if target.exists():
        raise ValueError(f"目标目录已存在，不会覆盖：{target}")
    source_database = source / DATABASE_NAME
    source_uploads = source / UPLOADS_NAME
    if not source_database.is_file() or not source_uploads.is_dir():
        raise ValueError("源目录必须同时包含 acceptance.db 和 uploads")

    target.mkdir(parents=True)
    target_uploads = target / UPLOADS_NAME
    target_uploads.mkdir()
    source_connection = sqlite3.connect(source_database)
    target_connection = sqlite3.connect(target / DATABASE_NAME)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()

    rows, _ = storage_rows(target / DATABASE_NAME)
    for name in {name for name, _ in rows}:
        try:
            if str(UUID(name)) != name:
                raise ValueError
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError(f"数据库含无效存储名：{name!r}") from error
        file = source_uploads / name
        if not file.is_file():
            raise ValueError(f"源目录缺少文件：{name}")
        shutil.copy2(file, target_uploads / name)
    return verify_storage(target / DATABASE_NAME, target_uploads)


def main() -> int:
    parser = argparse.ArgumentParser(description="成套复制并核验研途 SQLite 验收数据")
    subcommands = parser.add_subparsers(dest="command", required=True)
    copy_command = subcommands.add_parser("snapshot", help="复制数据库及其引用的文件到新目录")
    copy_command.add_argument("source", type=Path)
    copy_command.add_argument("target", type=Path)
    verify_command = subcommands.add_parser("verify", help="只读检查现有验收目录")
    verify_command.add_argument("directory", type=Path)
    serve_command = subcommands.add_parser("serve", help="检查通过后启动验收服务")
    serve_command.add_argument("directory", type=Path)
    serve_command.add_argument("--port", type=int, required=True)
    serve_command.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            counts = snapshot(args.source, args.target)
        else:
            directory = args.directory.resolve()
            counts = verify_storage(directory / DATABASE_NAME, directory / UPLOADS_NAME)
        print(f"存储检查通过：{counts['yt_resources']} 份资源、{counts['yt_resource_versions']} 份历史版本、{counts['files']} 个文件")
        if args.command == "serve":
            os.environ["DATABASE_URL"] = "sqlite:///" + (directory / DATABASE_NAME).as_posix()
            os.environ["UPLOAD_DIR"] = str(directory / UPLOADS_NAME)
            sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
            import uvicorn

            uvicorn.run("yantu.app:app", host=args.host, port=args.port)
        return 0
    except (OSError, sqlite3.DatabaseError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
