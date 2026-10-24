"""HTTP acceptance checks for the single-laboratory product.

Every test uses an isolated SQLite database and temporary upload directory. All
users and project memberships are created through HTTP except the legacy-upgrade
fixture; external services stay offline, and no running deployment is contacted.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from yantu.app import create_app
from yantu import models as legacy_models
from yantu.models import Base, Member, Resource, Team, User
from yantu.security import hash_password


PASSWORD = "test-laboratory-password-2026"
API = "/api/v1"
LAB = API + "/lab"


class OfflinePlane:
    def configured(self, team):
        return False

    def create_work_item(self, *args, **kwargs):
        return None

    def add_comment(self, *args, **kwargs):
        return None

    def list_work_items(self, *args, **kwargs):
        return {"results": [], "total_results": 0}


def data(response):
    assert response.status_code in (200, 201), response.text
    assert "data" in response.json(), response.text
    return response.json()["data"]


def denied(response, statuses=(403, 404)):
    assert response.status_code in statuses, response.text
    assert response.json().get("message"), response.text


def items(response):
    result = data(response)
    assert isinstance(result["items"], list)
    assert result["total"] == len(result["items"])
    return result["items"]


def register(client, name):
    email = f"{name}@example.com"
    person = data(client.post(API + "/auth/register", json={
        "email": email, "password": PASSWORD, "displayName": name,
    }))
    session = data(client.post(API + "/auth/login", json={"email": email, "password": PASSWORD}))
    # A separate bearer token models each account, with no cookie-jar fallback.
    client.cookies.clear()
    return {"id": person["id"], "email": email, "auth": {
        "Authorization": "Bearer " + session["accessToken"],
    }}


def project(client, owner, name="材料课题"):
    return data(client.post(LAB + "/projects", headers=owner["auth"], json={
        "name": name, "description": "只对批准加入的成员开放资料",
    }))


def approve(client, owner, project_id, person):
    request = data(client.post(f"{LAB}/projects/{project_id}/join-requests",
                               headers=person["auth"], json={"message": "申请参加"}))
    data(client.post(f"{LAB}/projects/{project_id}/join-requests/{request['id']}/decision",
                     headers=owner["auth"], json={"decision": "approved"}))
    return request


def meeting(client, owner, project_id, *, title="周组会", days=2):
    return data(client.post(f"{LAB}/projects/{project_id}/meetings", headers=owner["auth"], json={
        "title": title, "startsAt": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
        "location": "实验室", "agenda": "进展讨论",
    }))


def upload(client, person, project_id, *, meeting_id=None, video=False):
    fields = {"title": "组会录像" if video else "实验记录", "description": "课题内部资料"}
    if meeting_id:
        fields["meetingId"] = meeting_id
    filename, content, mime = ("meeting.mp4", b"\x00\x00\x00\x20ftypisom" + bytes(range(96)), "video/mp4") if video else (
        "notes.txt", "复现实验记录".encode(), "text/plain")
    result = data(client.post(f"{LAB}/projects/{project_id}/materials", headers=person["auth"],
                              data=fields, files={"file": (filename, content, mime)}))
    return result, content


@pytest.fixture
def site(tmp_path, monkeypatch):
    # Direct registration must work even if an old deployment retained this flag.
    monkeypatch.setenv("ALLOW_PUBLIC_SIGNUP", "0")
    monkeypatch.setenv("AI_BASE_URL", "")
    monkeypatch.setenv("AI_MODEL", "")
    app = create_app(f"sqlite:///{tmp_path / 'lab.db'}", tmp_path / "uploads",
                     tmp_path / "no-frontend", plane=OfflinePlane())
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def group(site):
    owner, member, outsider = (register(site, name) for name in ("owner", "member", "outsider"))
    current = project(site, owner)
    approve(site, owner, current["id"], member)
    return {"client": site, "owner": owner, "member": member, "outsider": outsider, "project": current}


def test_direct_registration_does_not_create_or_require_a_project(site):
    person = register(site, "new-member")
    assert data(site.get(API + "/me", headers=person["auth"]))["id"] == person["id"]
    assert items(site.get(LAB + "/projects?scope=joined", headers=person["auth"])) == []
    assert items(site.get(LAB + "/tasks", headers=person["auth"])) == []
    assert data(site.get(LAB + "/next-meeting", headers=person["auth"])) is None
    denied(site.get(LAB + "/projects"), (401,))


def test_project_discovery_approval_rejection_and_pending_request_idempotency(site):
    owner, applicant, stranger = (register(site, name) for name in ("owner", "applicant", "stranger"))
    current = project(site, owner)
    project_id = current["id"]
    assert current["role"] == "owner" and current["membershipStatus"] == "member"
    discovered = items(site.get(LAB + "/projects?scope=all", headers=applicant["auth"]))
    assert [(item["id"], item["membershipStatus"]) for item in discovered] == [(project_id, "none")]
    assert discovered[0]["role"] is None
    assert items(site.get(LAB + "/projects?scope=joined", headers=applicant["auth"])) == []
    basic = data(site.get(f"{LAB}/projects/{project_id}", headers=applicant["auth"]))
    assert basic["name"] == current["name"]
    assert not any(key in basic for key in ("materials", "meetings", "members", "email"))

    endpoint = f"{LAB}/projects/{project_id}/join-requests"
    first = data(site.post(endpoint, headers=applicant["auth"], json={"message": "希望加入"}))
    second = data(site.post(endpoint, headers=applicant["auth"], json={"message": "再次点击"}))
    assert first["id"] == second["id"]
    pending = items(site.get(endpoint, headers=owner["auth"]))
    assert len(pending) == 1 and pending[0]["status"] == "pending"
    assert pending[0]["userId"] == applicant["id"]
    assert pending[0]["email"] == applicant["email"]
    assert data(site.get(f"{LAB}/projects/{project_id}", headers=owner["auth"]))["pendingCount"] == 1
    assert data(site.get(f"{LAB}/projects/{project_id}", headers=stranger["auth"]))["pendingCount"] == 0
    denied(site.get(endpoint, headers=applicant["auth"]))
    decision = endpoint + f"/{first['id']}/decision"
    denied(site.post(decision, headers=applicant["auth"], json={"decision": "approved"}))
    data(site.post(decision, headers=owner["auth"], json={"decision": "rejected"}))
    assert items(site.get(LAB + "/projects?scope=joined", headers=applicant["auth"])) == []
    assert data(site.get(f"{LAB}/projects/{project_id}", headers=applicant["auth"]))["membershipStatus"] == "rejected"

    approve(site, owner, project_id, applicant)
    joined = items(site.get(LAB + "/projects?scope=joined", headers=applicant["auth"]))
    assert [(row["id"], row["role"], row["membershipStatus"]) for row in joined] == [(project_id, "student", "member")]
    members = items(site.get(f"{API}/teams/{project_id}/members", headers=owner["auth"]))
    assert sum(row["id"] == applicant["id"] for row in members) == 1
    denied(site.patch(f"{LAB}/projects/{project_id}", headers=applicant["auth"], json={"name": "冒名修改"}))
    assert data(site.patch(f"{LAB}/projects/{project_id}", headers=owner["auth"],
                           json={"name": "新课题名", "description": "新简介"}))["name"] == "新课题名"


def test_materials_meetings_recordings_comments_and_reader_require_membership(group):
    client, owner, member, outsider = (group[key] for key in ("client", "owner", "member", "outsider"))
    project_id = group["project"]["id"]
    scheduled = meeting(client, owner, project_id)
    generic, text_bytes = upload(client, member, project_id)
    slides, _ = upload(client, member, project_id, meeting_id=scheduled["id"])
    recording, video_bytes = upload(client, member, project_id, meeting_id=scheduled["id"], video=True)
    assert generic["type"] == "document" and generic["meetingId"] is None
    assert recording["type"] == "recording" and recording["previewType"] == "video/mp4"
    assert recording["size"] == len(video_bytes)
    assert {row["id"] for row in items(client.get(f"{LAB}/projects/{project_id}/materials", headers=member["auth"]))} == {generic["id"]}
    detail = data(client.get(f"{LAB}/meetings/{scheduled['id']}", headers=member["auth"]))
    assert {row["id"] for row in detail["materials"]} == {slides["id"]}
    assert {row["id"] for row in detail["recordings"]} == {recording["id"]}
    for kind, target_id in (("meeting", scheduled["id"]), ("resource", generic["id"]), ("resource", recording["id"])):
        endpoint = f"{LAB}/comments/{kind}/{target_id}"
        comment = data(client.post(endpoint, headers=member["auth"], json={"content": "下一次补充对照实验"}))
        assert comment["authorId"] == member["id"]
        assert items(client.get(endpoint, headers=owner["auth"]))[0]["content"] == "下一次补充对照实验"
        denied(client.get(endpoint, headers=outsider["auth"]))
        denied(client.post(endpoint, headers=outsider["auth"], json={"content": "越权评论"}))

    protected_paths = [f"{LAB}/projects/{project_id}/materials", f"{LAB}/projects/{project_id}/meetings",
                       f"{LAB}/meetings/{scheduled['id']}", f"{LAB}/resources/{generic['id']}",
                       f"{API}/teams/{project_id}/members"]
    for resource in (generic, recording):
        protected_paths += [f"{API}/resources/{resource['id']}{suffix}"
                            for suffix in ("", "/download", "/preview", "/reading-progress")]
    for path in protected_paths:
        denied(client.get(path, headers=outsider["auth"]))
        denied(client.get(path), (401,))
    denied(client.patch(f"{API}/resources/{generic['id']}/reading-progress", headers=outsider["auth"], json={"page": 2}))
    denied(client.post(f"{LAB}/projects/{project_id}/materials", headers=outsider["auth"],
                       files={"file": ("outside.txt", b"outsider", "text/plain")}))
    assert client.get(f"{API}/resources/{generic['id']}/download", headers=owner["auth"]).content == text_bytes
    progress = f"{API}/resources/{generic['id']}/reading-progress"
    data(client.patch(progress, headers=member["auth"], json={"page": 3, "notes": "个人阅读笔记"}))
    assert data(client.get(progress, headers=member["auth"]))["notes"] == "个人阅读笔记"
    assert data(client.get(progress, headers=owner["auth"])).get("notes", "") == ""


def test_video_range_and_recording_must_belong_to_same_project_meeting(group):
    client, owner, member = (group[key] for key in ("client", "owner", "member"))
    project_id = group["project"]["id"]
    scheduled = meeting(client, owner, project_id)
    recording, content = upload(client, member, project_id, meeting_id=scheduled["id"], video=True)
    preview = f"{API}/resources/{recording['id']}/preview"
    response = client.get(preview, headers={**member["auth"], "Range": "bytes=4-15"})
    assert response.status_code == 206, response.text
    assert response.content == content[4:16]
    assert response.headers["content-range"] == f"bytes 4-15/{len(content)}"
    assert "video/mp4" in response.headers["content-type"]
    suffix = client.get(preview, headers={**member["auth"], "Range": "bytes=-8"})
    assert suffix.status_code == 206 and suffix.content == content[-8:]
    assert client.get(preview, headers={**member["auth"], "Range": "bytes=99999-"}).status_code == 416
    files = {"file": ("meeting.mp4", content, "video/mp4")}
    denied(client.post(f"{LAB}/projects/{project_id}/materials", headers=member["auth"], files=files), (400,))
    other = project(client, owner, "另一课题")
    other_meeting = meeting(client, owner, other["id"])
    denied(client.post(f"{LAB}/projects/{project_id}/materials", headers=owner["auth"],
                       data={"meetingId": other_meeting["id"]}, files=files), (400, 403, 404))


def test_next_meeting_uses_only_joined_future_scheduled_projects(group):
    client, owner, member, outsider = (group[key] for key in ("client", "owner", "member", "outsider"))
    project_id = group["project"]["id"]
    hidden = project(client, outsider, "未加入的课题")
    meeting(client, outsider, hidden["id"], days=1)
    meeting(client, owner, project_id, days=-1)
    completed = meeting(client, owner, project_id, days=2)
    archived = meeting(client, owner, project_id, days=3)
    data(client.patch(f"{LAB}/meetings/{completed['id']}", headers=owner["auth"], json={"status": "completed"}))
    data(client.patch(f"{LAB}/meetings/{archived['id']}", headers=owner["auth"], json={"status": "archived"}))
    next_one = meeting(client, owner, project_id, days=4)
    later = meeting(client, owner, project_id, days=5)
    assert data(client.get(LAB + "/next-meeting", headers=member["auth"]))["id"] == next_one["id"]
    denied(client.patch(f"{LAB}/meetings/{later['id']}", headers=member["auth"], json={"minutes": "普通成员不能改纪要"}))
    denied(client.post(f"{LAB}/projects/{project_id}/meetings", headers=member["auth"], json={
        "title": "冒名会议", "startsAt": later["startsAt"], "location": "实验室", "agenda": "讨论",
    }))
    approve(client, outsider, hidden["id"], member)
    assert data(client.get(LAB + "/next-meeting", headers=member["auth"]))["projectId"] == hidden["id"]


def test_my_tasks_are_assigned_read_only_and_owner_manages_member_assignments(group):
    client, owner, member, outsider = (group[key] for key in ("client", "owner", "member", "outsider"))
    project_id = group["project"]["id"]
    endpoint = f"{LAB}/projects/{project_id}/tasks"
    payload = {"title": "准备对照实验", "description": "按计划执行", "assigneeId": member["id"],
               "dueAt": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()}
    denied(client.post(endpoint, headers=member["auth"], json=payload))
    denied(client.post(endpoint, headers=owner["auth"], json={**payload, "assigneeId": outsider["id"]}), (400, 403, 404))
    assigned = data(client.post(endpoint, headers=owner["auth"], json=payload))
    own = data(client.post(endpoint, headers=owner["auth"], json={**payload, "assigneeId": owner["id"]}))
    assert {row["id"] for row in items(client.get(endpoint, headers=owner["auth"]))} == {assigned["id"], own["id"]}
    denied(client.get(endpoint, headers=member["auth"]))
    denied(client.patch(endpoint + f"/{assigned['id']}", headers=member["auth"], json={"status": "done"}))
    data(client.patch(endpoint + f"/{assigned['id']}", headers=owner["auth"], json={"status": "doing"}))
    denied(client.patch(endpoint + f"/{assigned['id']}", headers=owner["auth"], json={"status": "review"}), (400,))
    denied(client.patch(endpoint + f"/{assigned['id']}", headers=owner["auth"], json={"assigneeId": outsider["id"]}), (400, 403, 404))

    second = project(client, outsider, "第二个已加入课题")
    approve(client, outsider, second["id"], member)
    another = data(client.post(f"{LAB}/projects/{second['id']}/tasks", headers=outsider["auth"], json=payload))
    denied(client.patch(f"{LAB}/projects/{second['id']}/tasks/{assigned['id']}",
                         headers=outsider["auth"], json={"title": "通过其他课题越权修改"}))
    mine = items(client.get(LAB + "/tasks", headers=member["auth"]))
    assert {row["id"] for row in mine} == {assigned["id"], another["id"]}
    assert all(row["assigneeId"] == member["id"] and row["projectName"] for row in mine)
    assert next(row for row in mine if row["id"] == assigned["id"])["status"] == "doing"
    assert all(not any(key in row for key in ("reviewerId", "submissions", "reviews", "feedback")) for row in mine)
    assert {row["id"] for row in items(client.get(LAB + "/tasks", headers=owner["auth"]))} == {own["id"]}
    for method, path in (("post", f"{API}/tasks/{assigned['id']}/submissions"),
                         ("post", f"{API}/submissions/nonexistent/reviews"),
                         ("post", f"{API}/tasks/{assigned['id']}/resources"),
                         ("patch", f"{LAB}/tasks/{assigned['id']}")):
        response = getattr(client, method)(path, headers=member["auth"], json={})
        assert response.status_code in (404, 405), response.text


def test_browser_history_is_personal_deduplicated_and_rechecks_current_access(group):
    client, owner, member, outsider = (group[key] for key in ("client", "owner", "member", "outsider"))
    project_id = group["project"]["id"]
    scheduled = meeting(client, owner, project_id)
    resource, _ = upload(client, member, project_id)
    target = {"targetType": "resource", "targetId": resource["id"]}
    first = data(client.post(LAB + "/history", headers=member["auth"], json={**target, "title": "伪造标题"}))
    second = data(client.post(LAB + "/history", headers=member["auth"], json=target))
    assert first["id"] == second["id"]
    history = items(client.get(LAB + "/history", headers=member["auth"]))
    assert len(history) == 1 and history[0]["title"] == resource["title"]
    assert history[0]["projectId"] == project_id
    assert items(client.get(LAB + "/history", headers=owner["auth"])) == []
    denied(client.post(LAB + "/history", headers=outsider["auth"], json=target))
    data(client.post(LAB + "/history", headers=owner["auth"], json=target))
    data(client.post(LAB + "/history", headers=member["auth"], json={"targetType": "meeting", "targetId": scheduled["id"]}))
    assert len(items(client.get(LAB + "/history", headers=member["auth"]))) == 2
    data(client.delete(LAB + "/history", headers=member["auth"]))
    assert items(client.get(LAB + "/history", headers=member["auth"])) == []
    assert len(items(client.get(LAB + "/history", headers=owner["auth"]))) == 1

    data(client.post(LAB + "/history", headers=member["auth"], json=target))
    data(client.delete(f"{API}/teams/{project_id}/members/{member['id']}", headers=owner["auth"]))
    assert items(client.get(LAB + "/projects?scope=joined", headers=member["auth"])) == []
    assert items(client.get(LAB + "/history", headers=member["auth"])) == []
    # Being the uploader must not retain access after leaving a project.
    denied(client.get(f"{API}/resources/{resource['id']}/download", headers=member["auth"]))
    denied(client.get(f"{LAB}/comments/resource/{resource['id']}", headers=member["auth"]))


def test_senior_messages_allow_all_logged_in_members_to_publish_and_comment(group):
    client, owner, member, outsider = (group[key] for key in ("client", "owner", "member", "outsider"))
    endpoint = LAB + "/messages"
    payload = {"title": "给新同学的话", "content": "保留原始实验记录，写清参数。"}
    assert data(client.get(endpoint, headers=owner["auth"]))["canPublish"] is True
    assert data(client.get(endpoint, headers=member["auth"]))["canPublish"] is True
    assert data(client.get(endpoint, headers=outsider["auth"]))["canPublish"] is True
    for person in (member, outsider):
        own_message = data(client.post(endpoint, headers=person["auth"], json=payload))
        assert own_message["authorId"] == person["id"]
    published = data(client.post(endpoint, headers=owner["auth"], json=payload))
    assert data(client.get(endpoint + f"/{published['id']}", headers=outsider["auth"]))["content"] == payload["content"]
    comment_path = f"{LAB}/comments/message/{published['id']}"
    comment = data(client.post(comment_path, headers=outsider["auth"], json={"content": "收到，谢谢！"}))
    assert comment["authorId"] == outsider["id"]
    assert items(client.get(comment_path, headers=member["auth"]))[0]["id"] == comment["id"]
    denied(client.get(endpoint), (401,))
    denied(client.post(endpoint, json=payload), (401,))
    denied(client.get(endpoint + f"/{published['id']}"), (401,))
    denied(client.post(comment_path, json={"content": "未登录"}), (401,))
    denied(client.patch(endpoint + f"/{published['id']}", headers=member["auth"], json={"content": "冒名修改"}))
    denied(client.delete(endpoint + f"/{published['id']}", headers=outsider["auth"]))
    updated = data(client.patch(endpoint + f"/{published['id']}", headers=owner["auth"], json={"content": "补充建议"}))
    assert updated["content"] == "补充建议"
    data(client.patch(f"{API}/teams/{group['project']['id']}/members/{member['id']}",
                      headers=owner["auth"], json={"role": "mentor"}))
    assert data(client.get(endpoint, headers=member["auth"]))["canPublish"] is True
    data(client.post(endpoint, headers=member["auth"], json={**payload, "title": "学长建议"}))
    data(client.post(LAB + "/history", headers=outsider["auth"],
                     json={"targetType": "message", "targetId": published["id"]}))
    data(client.delete(endpoint + f"/{published['id']}", headers=owner["auth"]))
    denied(client.get(endpoint + f"/{published['id']}", headers=member["auth"]), (404,))
    denied(client.get(comment_path, headers=member["auth"]), (404,))
    assert items(client.get(LAB + "/history", headers=outsider["auth"])) == []


def test_invalid_input_returns_errors_without_creating_or_changing_records(group):
    client, owner, member, outsider = (group[key] for key in ("client", "owner", "member", "outsider"))
    project_id = group["project"]["id"]
    denied(client.post(LAB + "/projects", headers=owner["auth"], json={"name": ""}), (400,))
    denied(client.post(f"{LAB}/projects/{project_id}/meetings", headers=owner["auth"], json={
        "title": "无效时间", "startsAt": "not-a-date", "location": "实验室", "agenda": "讨论",
    }), (400,))
    assert items(client.get(f"{LAB}/projects/{project_id}/meetings", headers=owner["auth"])) == []
    request_path = f"{LAB}/projects/{project_id}/join-requests"
    request = data(client.post(request_path, headers=outsider["auth"], json={"message": "请求加入"}))
    denied(client.post(request_path + f"/{request['id']}/decision", headers=owner["auth"],
                       json={"decision": "grant-owner"}), (400,))
    assert data(client.get(f"{LAB}/projects/{project_id}", headers=outsider["auth"]))["membershipStatus"] == "pending"
    denied(client.post(f"{LAB}/projects/{project_id}/materials", headers=member["auth"],
                       files={"file": ("program.exe", b"not-a-document", "application/octet-stream")}), (400, 415))
    assert items(client.get(f"{LAB}/projects/{project_id}/materials", headers=member["auth"])) == []
    denied(client.post(LAB + "/history", headers=member["auth"],
                       json={"targetType": "password", "targetId": owner["id"]}), (400,))
    denied(client.post(LAB + "/history", headers=member["auth"],
                       json={"targetType": "resource", "targetId": "does-not-exist"}), (404,))
    assert items(client.get(LAB + "/history", headers=member["auth"])) == []
    denied(client.post(LAB + "/messages", headers=owner["auth"], json={"title": "", "content": "建议"}), (400,))
    message = data(client.post(LAB + "/messages", headers=owner["auth"], json={"title": "建议", "content": "记录原始数据"}))
    comments = f"{LAB}/comments/message/{message['id']}"
    denied(client.post(comments, headers=member["auth"], json={"content": ""}), (400,))
    assert items(client.get(comments, headers=owner["auth"])) == []


def test_obsolete_product_routes_are_not_exposed(site):
    person = register(site, "check-routes")
    paths = [
        ("POST", "/auth/setup"),
        ("POST", "/teams/project/invitations"), ("POST", "/invitations/token/accept"),
        ("GET", "/me/dashboard"), ("GET", "/teams/project/routes"),
        ("GET", "/routes/route"), ("POST", "/routes/route/enrollments"),
        ("GET", "/me/enrollments"), ("POST", "/me/drive/questions"),
        ("POST", "/teams/project/questions"), ("GET", "/teams/project/review-queue"),
        ("GET", "/teams/project/experiences"), ("GET", "/teams/project/meetings"),
        ("GET", "/teams/project/resources"), ("GET", "/me/tasks"),
    ]
    for method, path in paths:
        response = site.request(method, API + path, headers=person["auth"], json={} if method == "POST" else None)
        assert response.status_code in (404, 405), f"{method} {path}: {response.status_code} {response.text}"


def test_cookie_session_logout_and_cross_site_writes(site):
    person = register(site, "cookie-user")
    response = site.post(API + "/auth/login", json={"email": person["email"], "password": PASSWORD})
    session = data(response)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert data(site.get(API + "/me"))["id"] == person["id"]
    denied(site.post(LAB + "/messages", headers={"Origin": "https://other.example"},
                     json={"title": "cross-site", "content": "blocked"}), (403,))
    assert items(site.get(LAB + "/messages")) == []
    data(site.post(API + "/auth/logout"))
    denied(site.get(API + "/me"), (401,))
    denied(site.get(API + "/me", headers={"Authorization": "Bearer " + session["accessToken"]}), (401,))


def test_existing_account_project_and_file_survive_additive_migration_and_restart(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    file_content = "升级前已经上传的资料".encode()
    storage_name = "legacy-resource-content"
    (uploads / storage_name).write_bytes(file_content)
    password_hash = hash_password(PASSWORD)
    engine = create_engine(database_url)
    # Recreate only the pre-redesign schema, even if another test has already
    # imported the new model module into the shared SQLAlchemy metadata.
    old_tables = [model.__table__ for model in vars(legacy_models).values()
                  if isinstance(model, type) and model.__module__ == legacy_models.__name__
                  and hasattr(model, "__table__")]
    Base.metadata.create_all(engine, tables=old_tables)
    original_tables = set(inspect(engine).get_table_names())
    with Session(engine) as db:
        person = User(email="legacy@example.com", display_name="原负责人", password_hash=password_hash)
        current = Team(name="原有课题")
        db.add_all([person, current])
        db.flush()
        person_id, project_id = person.id, current.id
        db.add(Member(team_id=project_id, user_id=person_id, role="owner"))
        resource = Resource(team_id=project_id, owner_id=person_id, title="原资料", type="note",
                            file_name="legacy.txt", storage_name=storage_name, size=len(file_content), visibility="team")
        db.add(resource)
        db.commit()
        resource_id = resource.id
    engine.dispose()

    for _ in range(2):
        app = create_app(database_url, uploads, tmp_path / "no-frontend", plane=OfflinePlane())
        with TestClient(app, raise_server_exceptions=False) as client:
            session = data(client.post(API + "/auth/login", json={"email": "legacy@example.com", "password": PASSWORD}))
            auth = {"Authorization": "Bearer " + session["accessToken"]}
            client.cookies.clear()
            assert data(client.get(API + "/me", headers=auth))["id"] == person_id
            joined = items(client.get(LAB + "/projects?scope=joined", headers=auth))
            assert [(row["id"], row["name"], row["role"]) for row in joined] == [(project_id, "原有课题", "owner")]
            materials = items(client.get(f"{LAB}/projects/{project_id}/materials", headers=auth))
            assert [row["id"] for row in materials] == [resource_id]
            downloaded = client.get(f"{API}/resources/{resource_id}/download", headers=auth)
            assert downloaded.status_code == 200 and downloaded.content == file_content

    engine = create_engine(database_url)
    assert original_tables < set(inspect(engine).get_table_names())
    with Session(engine) as db:
        assert db.get(User, person_id).password_hash == password_hash
        assert db.get(Resource, resource_id).storage_name == storage_name
    engine.dispose()
