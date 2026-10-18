"""Real HTTP/database/filesystem acceptance for personal ownership and revocation."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from yantu.app import create_app
from yantu.migrations import migrate
from yantu.core.models import Base


def data(response, status=200):
    assert response.status_code == status, response.text
    return response.json()["data"]


@pytest.fixture
def drive(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_PUBLIC_SIGNUP", "1")
    app = create_app(f'sqlite:///{tmp_path / "drive.db"}', tmp_path / "uploads", tmp_path / "front")
    with TestClient(app) as client:
        actors = []
        for index in range(4):
            email = f"drive{index}@example.com"
            uid = data(
                client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": email,
                        "password": "cloud-password-2026",
                        "displayName": f"成员{index}",
                    },
                )
            )["id"]
            token = data(
                client.post(
                    "/api/v1/auth/login", json={"email": email, "password": "cloud-password-2026"}
                )
            )["accessToken"]
            actors.append((uid, {"Authorization": "Bearer " + token}))
            client.cookies.clear()
        team = data(
            client.post("/api/v1/teams", headers=actors[0][1], json={"name": "云盘测试组"})
        )["id"]
        for index in (1, 2):
            invitation = data(
                client.post(
                    f"/api/v1/teams/{team}/invitations",
                    headers=actors[0][1],
                    json={"email": f"drive{index}@example.com", "role": "student"},
                )
            )
            data(
                client.post(
                    f'/api/v1/invitations/{invitation["inviteToken"]}/accept',
                    headers=actors[index][1],
                    json={},
                )
            )
        yield client, actors, team, app


def upload(
    client,
    actor,
    folder="",
    key="file-1",
    content=b"Cloud research evidence",
    filename="研究笔记.txt",
):
    return client.post(
        "/api/v1/me/drive/files",
        headers={**actor, "Idempotency-Key": key},
        data={"folderId": folder, "type": "note"},
        files={"file": (filename, content)},
    )


def test_folders_files_isolation_and_idempotency(drive):
    c, actors, team, app = drive
    a, b, _, solo = [x[1] for x in actors]
    parent = None
    folders = []
    for title in ["课题 A", "参考论文", "方法"]:
        parent = data(
            c.post("/api/v1/me/drive/folders", headers=a, json={"name": title, "parentId": parent}),
            201,
        )["id"]
        folders.append(parent)
    assert (
        c.get("/api/v1/me/drive/children", headers=b, params={"folderId": parent}).status_code
        == 404
    )
    assert (
        c.patch(
            "/api/v1/me/drive/folders/" + folders[0], headers=a, json={"parentId": parent}
        ).status_code
        == 409
    )
    assert c.delete("/api/v1/me/drive/folders/" + folders[0], headers=a).status_code == 409
    assert (
        c.post(
            "/api/v1/me/drive/folders", headers=a, json={"name": "方法", "parentId": folders[1]}
        ).status_code
        == 409
    )
    assert (
        c.post("/api/v1/me/drive/folders", headers=a, json={"name": "../invalid"}).status_code
        == 400
    )
    file = data(upload(c, a, parent), 201)
    assert data(upload(c, a, parent), 201)["id"] == file["id"]
    assert upload(c, a, parent, content=b"different").status_code == 409
    assert upload(c, b, parent).status_code == 404
    assert upload(c, a, key="empty", content=b"").status_code == 400
    assert upload(c, a, key="exe", filename="bad.exe").status_code == 415
    assert c.get("/api/v1/resources/" + file["id"], headers=b).status_code == 404
    assert c.get("/api/v1/resources/" + file["id"] + "/download", headers=b).status_code == 404
    data(
        c.patch(
            "/api/v1/resources/" + file["id"],
            headers=a,
            json={"title": "已重命名", "folderId": folders[0]},
        )
    )
    found = data(
        c.get("/api/v1/me/drive/search", headers=a, params={"scope": "mine", "q": "已重命名"})
    )["items"]
    assert found[0]["id"] == file["id"] and found[0]["location"][-1]["id"] == folders[0]
    assert (
        data(c.get("/api/v1/me/drive/children", headers=a, params={"folderId": parent}))["total"]
        == 0
    )
    data(c.delete("/api/v1/me/drive/folders/" + parent, headers=a))
    # A user without any team can upload, preview, read and download.
    personal = data(upload(c, solo), 201)
    assert (
        c.get("/api/v1/resources/" + personal["id"] + "/download", headers=solo).content
        == b"Cloud research evidence"
    )
    assert data(c.get("/api/v1/me/drive/children", headers=solo))["total"] == 1
    assert data(c.get("/api/v1/me/drive/children", headers=a))["total"] == 1
    keys = [(r.path, m) for r in app.routes for m in (getattr(r, "methods", None) or [])]
    assert len(keys) == len(set(keys))
    assert "/api/v1/me/drive/files" in app.openapi()["paths"]


def test_shares_versions_references_questions_and_departure(drive):
    c, actors, team, _ = drive
    aid, a = actors[0]
    bid, b = actors[1]
    cid, third = actors[2]
    file = data(upload(c, a), 201)
    rid = file["id"]
    endpoint = "/api/v1/resources/" + rid
    data(c.put(endpoint + "/shares/" + bid, headers=a, json={"permission": "read", "teamId": team}))
    assert data(c.get("/api/v1/me/drive/search?scope=shared", headers=b))["items"][0]["id"] == rid
    for suffix in ["", "/preview", "/download", "/versions", "/reading-progress"]:
        assert c.get(endpoint + suffix, headers=third).status_code == 404
        assert c.get(endpoint + suffix, headers=b).status_code == 200
    assert c.patch(endpoint, headers=b, json={"title": "stolen"}).status_code == 403
    data(c.patch(endpoint + "/reading-progress", headers=b, json={"page": 7, "notes": "乙的笔记"}))
    assert data(c.get(endpoint + "/reading-progress", headers=a)) == {}
    data(
        c.post(
            endpoint + "/versions",
            headers=a,
            files={"file": ("新版本.txt", b"Cloud research updated evidence")},
        )
    )
    versions = data(c.get(endpoint + "/versions", headers=b))["items"]
    assert len(versions) == 2
    assert c.get(endpoint + "/download", headers=b).content == b"Cloud research updated evidence"
    assert (
        c.get(endpoint + "/download", headers=b, params={"versionId": versions[0]["id"]}).content
        == b"Cloud research evidence"
    )
    task = data(
        c.post(
            f"/api/v1/teams/{team}/tasks",
            headers=a,
            json={"title": "科研任务", "assigneeId": bid, "reviewerId": aid},
        )
    )["id"]
    reference = data(c.post(f"/api/v1/tasks/{task}/resources", headers=a, json={"resourceId": rid}))
    assert (
        data(c.post(f"/api/v1/tasks/{task}/resources", headers=a, json={"resourceId": rid}))["id"]
        == reference["id"]
    )
    assert data(c.get(f"/api/v1/tasks/{task}", headers=b))["resources"][0]["id"] == rid
    answer = data(
        c.post(
            "/api/v1/me/drive/questions",
            headers=b,
            json={"question": "Cloud research", "resourceIds": [rid]},
        )
    )
    assert answer["sources"][0]["resourceId"] == rid
    assert (
        c.post(
            "/api/v1/me/drive/questions",
            headers=third,
            json={"question": "Cloud research", "resourceIds": [rid]},
        ).status_code
        == 404
    )
    data(c.delete(endpoint + "/shares/" + bid, headers=a))
    assert data(c.get("/api/v1/me/drive/search?scope=shared", headers=b))["items"] == []
    assert data(c.get(f"/api/v1/tasks/{task}", headers=b))["resources"] == []
    assert c.get(endpoint + "/download", headers=b).status_code == 404
    assert (
        c.post(
            "/api/v1/me/drive/questions",
            headers=b,
            json={"question": "Cloud research", "resourceIds": [rid]},
        ).status_code
        == 404
    )
    # Shares issued in a team never revive after departure/rejoining.
    data(c.put(endpoint + "/shares/" + cid, headers=a, json={"permission": "read", "teamId": team}))
    data(c.delete(f"/api/v1/teams/{team}/members/{cid}", headers=a))
    invitation = data(
        c.post(
            f"/api/v1/teams/{team}/invitations",
            headers=a,
            json={"email": "drive2@example.com", "role": "student"},
        )
    )
    data(
        c.post(
            "/api/v1/invitations/" + invitation["inviteToken"] + "/accept", headers=third, json={}
        )
    )
    assert c.get(endpoint, headers=third).status_code == 404
    # Legacy upload compatibility is private too, and search cannot bypass it.
    legacy = data(
        c.post(
            f"/api/v1/teams/{team}/resources",
            headers=a,
            data={"title": "私密兼容资料", "type": "note", "visibility": "team"},
            files={"file": ("legacy.txt", b"legacy")},
        )
    )
    assert c.get("/api/v1/resources/" + legacy["id"], headers=b).status_code == 404
    assert not data(c.get(f"/api/v1/teams/{team}/search?q=私密兼容资料", headers=b))["items"]


def test_legacy_sqlite_upgrade_is_repeatable_and_preserves_content(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO yt_users (id,email,password_hash,display_name,direction) VALUES ('u','u@x','hash','甲','')"
            )
        )
        db.execute(text("INSERT INTO yt_teams (id,name) VALUES ('t','旧课题组')"))
        # Simulate the prior NOT NULL schema without changing any resource ID.
        db.exec_driver_sql("DROP TABLE yt_resources")
        db.exec_driver_sql(
            """CREATE TABLE yt_resources (id VARCHAR(36) PRIMARY KEY, team_id VARCHAR(36) NOT NULL REFERENCES yt_teams(id), owner_id VARCHAR(36) NOT NULL REFERENCES yt_users(id), title VARCHAR(200) NOT NULL, type VARCHAR(20) NOT NULL, description TEXT NOT NULL, extracted_text TEXT NOT NULL, meeting_id VARCHAR(36), task_id VARCHAR(36), file_name VARCHAR(255) NOT NULL, storage_name VARCHAR(36) UNIQUE NOT NULL, size INTEGER NOT NULL, visibility VARCHAR(20) NOT NULL DEFAULT 'team', archived BOOLEAN NOT NULL DEFAULT 'false', version INTEGER NOT NULL DEFAULT '1')"""
        )
        db.exec_driver_sql(
            "INSERT INTO yt_resources VALUES ('r','t','u','旧资料','note','','旧文本',NULL,NULL,'旧笔记.txt','original-storage',3,'team',0,1)"
        )
        db.exec_driver_sql(
            "INSERT INTO yt_resource_versions (id,resource_id,version,file_name,storage_name,size,note,author_id,created_at) VALUES ('v','r',1,'旧笔记.txt','original-storage',3,'','u',CURRENT_TIMESTAMP)"
        )
        db.exec_driver_sql(
            'INSERT INTO yt_entity_data (key,data) VALUES (\'reading:r:u\',\'{"page":7,"notes":"saved"}\')'
        )
    # Exercise an actual pre-upgrade snapshot and restore on a separate copy.
    import shutil
    import sqlite3

    source_files = tmp_path / "files"
    source_files.mkdir()
    (source_files / "original-storage").write_bytes(b"old")
    with sqlite3.connect(tmp_path / "legacy.db") as source, sqlite3.connect(
        tmp_path / "backup.db"
    ) as backup:
        source.backup(backup)
    shutil.copytree(source_files, tmp_path / "backup-files")
    migrate(engine)
    migrate(engine)
    assert next(c for c in inspect(engine).get_columns("yt_resources") if c["name"] == "team_id")[
        "nullable"
    ]
    with engine.connect() as db:
        row = db.execute(
            text("SELECT id,owner_id,team_id,folder_id,storage_name,visibility FROM yt_resources")
        ).one()
        assert tuple(row) == ("r", "u", "t", None, "original-storage", "team")
        assert db.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert db.execute(text("SELECT resource_id FROM yt_resource_versions")).scalar_one() == "r"
    shutil.copy2(tmp_path / "backup.db", tmp_path / "restored.db")
    shutil.copytree(tmp_path / "backup-files", tmp_path / "restored-files")
    restored = create_engine(f'sqlite:///{tmp_path / "restored.db"}')
    migrate(restored)
    with restored.connect() as db:
        assert (
            db.execute(text("SELECT storage_name FROM yt_resources WHERE id='r'")).scalar_one()
            == "original-storage"
        )
        assert (
            "saved"
            in db.execute(
                text("SELECT data FROM yt_entity_data WHERE key='reading:r:u'")
            ).scalar_one()
        )
        assert db.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    assert (tmp_path / "restored-files" / "original-storage").read_bytes() == b"old"
    restored.dispose()
