"""Independent HTTP acceptance checks against real database/file business logic.

Only the external Plane service is replaced. Every user, membership, invitation,
route, submission, review and file is created through the public HTTP interface.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from urllib.parse import quote

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from yantu.app import create_app
from yantu.core.models import Handover, Invitation, Notification, Resource, SessionToken, Task
from yantu.core.security import token_digest

PASSWORD = "a-real-test-password-2026"


class OfflinePlane:
    """An intentionally disconnected external service; local behavior stays real."""

    def configured(self, team):
        return False

    def create_work_item(self, team, title, description, external_id=None):
        return None

    def add_comment(self, team, work_item_id, content):
        return None

    def list_work_items(self, team):
        return {"results": [], "total_results": 0}


def data(response, status=200):
    assert response.status_code == status, response.text
    assert "data" in response.json(), response.text
    return response.json()["data"]


def reject(response, statuses):
    if isinstance(statuses, int):
        statuses = {statuses}
    assert response.status_code in statuses, response.text
    error = response.json()
    assert isinstance(error.get("message"), str) and error["message"]


def login(client, email):
    body = data(client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}))
    # These helpers represent separate users through bearer headers. A shared
    # TestClient cookie jar must not accidentally authenticate a different user.
    client.cookies.clear()
    return {"Authorization": f"Bearer {body['accessToken']}"}


def signup(client, email, **extra):
    body = data(
        client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "displayName": email.split("@")[0],
                **extra,
            },
        )
    )
    return body["id"], login(client, email)


def team(client, owner, name):
    return data(client.post("/api/v1/teams", headers=owner, json={"name": name}))["id"]


def invite(client, owner, team_id, email, role="student"):
    return data(
        client.post(
            f"/api/v1/teams/{team_id}/invitations",
            headers=owner,
            json={"email": email, "role": role},
        )
    )["inviteToken"]


def join(client, owner, team_id, email, member, role="student"):
    token = invite(client, owner, team_id, email, role)
    return data(client.post(f"/api/v1/invitations/{token}/accept", headers=member, json={}))


def create_task(client, lab, *, assignee=None, reviewer=None, **extra):
    body = {
        "title": "复现实验",
        "description": "运行基线并记录结果",
        "acceptanceCriteria": "记录随机种子",
        "assigneeId": assignee or lab["student_id"],
        "reviewerId": reviewer or lab["owner_id"],
        **extra,
    }
    return data(client.post(f"/api/v1/teams/{lab['team']}/tasks", headers=lab["owner"], json=body))[
        "id"
    ]


def create_route(client, lab, title="文献阅读路线"):
    body = {
        "title": title,
        "description": "适用于刚加入课题组的学生",
        "stages": [
            {
                "title": "阅读阶段",
                "description": "先读原论文",
                "tasks": [
                    {
                        "title": "阅读论文",
                        "description": "旧版描述",
                        "acceptanceCriteria": "完成文献笔记",
                    },
                    {"title": "复现结果", "acceptanceCriteria": "保存实验日志"},
                ],
            },
        ],
    }
    return data(
        client.post(f"/api/v1/teams/{lab['team']}/routes", headers=lab["owner"], json=body)
    )["id"]


def concurrent_requests(action, count=2):
    barrier = Barrier(count)

    def worker():
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(worker) for _ in range(count)]
        return [future.result(timeout=30) for future in futures]


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_PUBLIC_SIGNUP", "1")
    monkeypatch.setenv("AI_BASE_URL", "")
    monkeypatch.setenv("AI_MODEL", "")
    database_url = f"sqlite:///{tmp_path / 'acceptance.db'}"
    uploads = tmp_path / "uploads"
    app = create_app(database_url, uploads, tmp_path / "no-frontend", plane=OfflinePlane())
    with TestClient(app, raise_server_exceptions=False) as client:
        yield {"client": client, "uploads": uploads, "database_url": database_url}


@pytest.fixture
def lab(site):
    client = site["client"]
    owner_id, owner = signup(client, "owner@example.com")
    student_id, student = signup(client, "student@example.com")
    peer_id, peer = signup(client, "peer@example.com")
    mentor_id, mentor = signup(client, "mentor@example.com")
    outsider_id, outsider = signup(client, "outsider@example.com")
    team_id = team(client, owner, "可信科研实验室")
    join(client, owner, team_id, "student@example.com", student)
    join(client, owner, team_id, "peer@example.com", peer)
    join(client, owner, team_id, "mentor@example.com", mentor, "mentor")
    return {
        **site,
        "team": team_id,
        "owner_id": owner_id,
        "owner": owner,
        "student_id": student_id,
        "student": student,
        "peer_id": peer_id,
        "peer": peer,
        "mentor_id": mentor_id,
        "mentor": mentor,
        "outsider_id": outsider_id,
        "outsider": outsider,
    }


def handover_request(lab, **extra):
    return lab["client"].post(
        f"/api/v1/teams/{lab['team']}/handovers",
        headers=lab["student"],
        json={
            "title": "实验资料交接",
            "content": "记录实验条件和下一步问题",
            "toUserId": lab["peer_id"],
            **extra,
        },
    )


def handover_records(lab):
    return data(lab["client"].get(f"/api/v1/teams/{lab['team']}/handovers", headers=lab["owner"]))[
        "items"
    ]


def handover_resource(lab):
    return data(
        lab["client"].post(
            "/api/v1/me/drive/files",
            headers={**lab["student"], "Idempotency-Key": "handover-file"},
            data={"type": "note"},
            files={"file": ("实验笔记.txt", b"Handover experiment notes")},
        ),
        201,
    )["id"]


def share_handover_resource(lab, resource_id):
    return data(
        lab["client"].put(
            f"/api/v1/resources/{resource_id}/shares/{lab['peer_id']}",
            headers=lab["student"],
            json={"permission": "read", "teamId": lab["team"]},
        )
    )


def test_handover_references_notifications_and_idempotent_acceptance(lab):
    client = lab["client"]
    task_id = create_task(client, lab)
    resource_id = handover_resource(lab)
    share_handover_resource(lab, resource_id)
    handover_id = data(
        handover_request(lab, taskIds=[task_id, task_id], resourceIds=[resource_id, resource_id])
    )["id"]
    record = handover_records(lab)[0]
    assert record["taskIds"] == [task_id] and record["resourceIds"] == [resource_id]
    with client.app.state.session_factory() as db:
        notification = db.scalar(select(Notification).where(Notification.target_id == handover_id))
        assert notification.user_id == lab["peer_id"]
        assert notification.target_type == "handover"
    endpoint = f"/api/v1/handovers/{handover_id}/accept"
    reject(client.post(endpoint, headers=lab["student"], json={}), 403)
    first = data(client.post(endpoint, headers=lab["peer"], json={}))
    second = data(client.post(endpoint, headers=lab["peer"], json={}))
    assert first == second and first["acceptedAt"]
    with client.app.state.session_factory() as db:
        notices = db.scalars(
            select(Notification).where(Notification.target_id == handover_id)
        ).all()
        assert len(notices) == 2
        assert {notice.user_id for notice in notices} == {lab["student_id"], lab["peer_id"]}
        assert db.get(Resource, resource_id).owner_id == lab["student_id"]
        assert db.get(Task, task_id).assignee_id == lab["student_id"]


def test_handover_failed_acceptance_keeps_pending_until_explicit_share(lab):
    client = lab["client"]
    resource_id = handover_resource(lab)
    handover_id = data(handover_request(lab, resourceIds=[resource_id]))["id"]
    endpoint = f"/api/v1/handovers/{handover_id}/accept"
    reject(client.post(endpoint, headers=lab["peer"], json={}), 403)
    assert handover_records(lab)[0]["status"] == "pending"
    assert handover_records(lab)[0]["acceptedAt"] is None
    reject(client.get(f"/api/v1/resources/{resource_id}", headers=lab["peer"]), 404)
    with client.app.state.session_factory() as db:
        assert (
            len(db.scalars(select(Notification).where(Notification.target_id == handover_id)).all())
            == 1
        )
    share_handover_resource(lab, resource_id)
    assert data(client.post(endpoint, headers=lab["peer"], json={}))["status"] == "accepted"


def test_handover_rejects_malformed_reference_arrays_without_writing(lab):
    invalid_values = [None, "id", {}, [None], [3], [{}], [""], [" "], ["x" * 37], ["x"] * 101]
    for key in ("taskIds", "resourceIds"):
        for value in invalid_values:
            reject(handover_request(lab, **{key: value}), 400)
    assert handover_records(lab) == []
    with lab["client"].app.state.session_factory() as db:
        assert db.scalar(select(Notification).where(Notification.target_type == "handover")) is None


def test_handover_rejects_cross_team_tasks_even_for_owner_of_both(lab):
    client = lab["client"]
    other_team = team(client, lab["owner"], "另一个课题组")
    join(client, lab["owner"], other_team, "mentor@example.com", lab["mentor"], "mentor")
    task_id = create_task(
        client, {**lab, "team": other_team}, assignee=lab["owner_id"], reviewer=lab["mentor_id"]
    )
    reject(
        client.post(
            f"/api/v1/teams/{lab['team']}/handovers",
            headers=lab["owner"],
            json={
                "title": "跨组夹带",
                "content": "不能关联其他组任务",
                "toUserId": lab["peer_id"],
                "taskIds": [task_id],
            },
        ),
        400,
    )
    assert handover_records(lab) == []


def test_handover_rejects_inaccessible_tasks_resources_and_outsiders(lab):
    client = lab["client"]
    task_id = create_task(client, lab, assignee=lab["peer_id"])
    reject(handover_request(lab, taskIds=[task_id]), 403)
    resource_id = data(
        client.post(
            "/api/v1/me/drive/files",
            headers=lab["owner"],
            data={"type": "note"},
            files={"file": ("私有.txt", b"private notes")},
        ),
        201,
    )["id"]
    reject(handover_request(lab, resourceIds=[resource_id]), 404)
    reject(handover_request(lab, toUserId=lab["outsider_id"]), 400)
    reject(handover_request(lab, toUserId=lab["student_id"]), 400)
    assert handover_records(lab) == []


def test_handover_revalidates_missing_archived_and_cross_team_references(lab):
    client = lab["client"]
    resource_id = handover_resource(lab)
    share_handover_resource(lab, resource_id)
    handover_id = data(handover_request(lab, resourceIds=[resource_id]))["id"]
    endpoint = f"/api/v1/handovers/{handover_id}/accept"
    # Simulate a file archived after the record was sent.
    with client.app.state.session_factory() as db:
        db.get(Resource, resource_id).archived = True
        db.commit()
    reject(client.post(endpoint, headers=lab["peer"], json={}), 403)
    # Old records can contain stale references; they must not silently succeed.
    with client.app.state.session_factory() as db:
        row = db.get(Handover, handover_id)
        row.resource_ids = ["missing-resource"]
        db.commit()
    reject(client.post(endpoint, headers=lab["peer"], json={}), 403)
    other_team = team(client, lab["owner"], "历史记录校验组")
    join(client, lab["owner"], other_team, "mentor@example.com", lab["mentor"], "mentor")
    foreign_task = create_task(
        client, {**lab, "team": other_team}, assignee=lab["owner_id"], reviewer=lab["mentor_id"]
    )
    for task_id in ["missing-task", foreign_task]:
        with client.app.state.session_factory() as db:
            row = db.get(Handover, handover_id)
            row.resource_ids = []
            row.task_ids = [task_id]
            db.commit()
        reject(client.post(endpoint, headers=lab["peer"], json={}), 409)
    assert handover_records(lab)[0]["status"] == "pending"


def test_handover_concurrent_acceptance_sends_one_confirmation(lab):
    client = lab["client"]
    handover_id = data(handover_request(lab))["id"]
    responses = concurrent_requests(
        lambda: client.post(f"/api/v1/handovers/{handover_id}/accept", headers=lab["peer"], json={})
    )
    records = [data(response) for response in responses]
    assert records[0] == records[1] and records[0]["status"] == "accepted"
    with client.app.state.session_factory() as db:
        notices = db.scalars(
            select(Notification).where(Notification.target_id == handover_id)
        ).all()
        assert len(notices) == 2


def test_registration_normalization_password_validation_and_session_logout(site):
    client = site["client"]
    reject(
        client.post(
            "/api/v1/auth/register", json={"email": "bad", "password": "short", "displayName": "甲"}
        ),
        400,
    )
    user_id, first = signup(client, "  Mixed.Case@Example.COM  ")
    me = data(client.get("/api/v1/me", headers=first))
    assert me["id"] == user_id and me["email"] == "mixed.case@example.com"
    reject(
        client.post(
            "/api/v1/auth/register",
            json={"email": "mixed.case@example.com", "password": PASSWORD, "displayName": "重名"},
        ),
        409,
    )
    second = login(client, "mixed.case@example.com")
    assert data(client.post("/api/v1/auth/logout", headers=first)) is None
    reject(client.get("/api/v1/me", headers=first), 401)
    assert data(client.get("/api/v1/me", headers=second))["id"] == user_id
    reject(client.get("/api/v1/me", headers={"Authorization": "Bearer invented-token"}), 401)


def test_expired_session_cannot_access_data(site):
    client = site["client"]
    _, auth = signup(client, "expired@example.com")
    engine = create_engine(site["database_url"])
    with Session(engine) as db:
        token = db.get(SessionToken, token_digest(auth["Authorization"].split()[1]))
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    engine.dispose()
    reject(client.get("/api/v1/me", headers=auth), 401)


def test_cookie_session_refresh_rotates_token_and_logout_revokes_it(site):
    client = site["client"]
    user_id, first = signup(client, "cookie@example.com")
    response = client.post(
        "/api/v1/auth/login", json={"email": "cookie@example.com", "password": PASSWORD}
    )
    old_token = data(response)["accessToken"]
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert data(client.get("/api/v1/me"))["id"] == user_id
    renewed = data(client.post("/api/v1/auth/refresh", json={}))
    assert renewed["accessToken"] != old_token
    assert data(client.get("/api/v1/me"))["id"] == user_id
    reject(client.get("/api/v1/me", headers={"Authorization": "Bearer " + old_token}), 401)
    reject(
        client.post(
            "/api/v1/auth/refresh", headers={"Authorization": "Bearer " + old_token}, json={}
        ),
        401,
    )
    assert data(client.post("/api/v1/auth/logout")) is None
    reject(client.get("/api/v1/me"), 401)
    reject(
        client.get("/api/v1/me", headers={"Authorization": "Bearer " + renewed["accessToken"]}), 401
    )
    assert data(client.get("/api/v1/me", headers=first))["id"] == user_id


def test_cross_origin_cookie_mutation_is_denied(site):
    client = site["client"]
    signup(client, "cookie@example.com")
    data(
        client.post(
            "/api/v1/auth/login", json={"email": "cookie@example.com", "password": PASSWORD}
        )
    )
    reject(
        client.patch(
            "/api/v1/me",
            headers={"Origin": "https://untrusted.example"},
            json={"displayName": "跨站改名", "direction": "攻击"},
        ),
        403,
    )
    assert data(client.get("/api/v1/me"))["displayName"] == "cookie"
    data(
        client.patch(
            "/api/v1/me",
            headers={"Origin": "http://testserver"},
            json={"displayName": "本人改名", "direction": "安全"},
        )
    )
    assert data(client.get("/api/v1/me"))["displayName"] == "本人改名"


def test_roles_are_scoped_to_each_team(lab):
    client = lab["client"]
    own_team = team(client, lab["student"], "学生自己创建的组")
    own_roles = {
        item["id"]: item["role"]
        for item in data(client.get("/api/v1/me/teams", headers=lab["student"]))["items"]
    }
    assert own_roles == {lab["team"]: "student", own_team: "owner"}
    meeting = {
        "title": "组会",
        "startsAt": "2030-10-01T08:00:00+08:00",
        "location": "线上",
        "agenda": "汇报",
    }
    reject(
        client.post(f"/api/v1/teams/{lab['team']}/meetings", headers=lab["student"], json=meeting),
        403,
    )
    assert (
        client.post(
            f"/api/v1/teams/{own_team}/meetings", headers=lab["student"], json=meeting
        ).status_code
        == 200
    )
    reject(
        client.post(
            f"/api/v1/teams/{lab['team']}/invitations",
            headers=lab["mentor"],
            json={"email": "new@example.com", "role": "student"},
        ),
        403,
    )
    reject(
        client.post(
            f"/api/v1/teams/{lab['team']}/invitations",
            headers=lab["owner"],
            json={"email": "new@example.com", "role": "owner"},
        ),
        400,
    )
    changed = data(
        client.patch(
            "/api/v1/me",
            headers=lab["student"],
            json={
                "displayName": "学生甲",
                "direction": "计算机视觉",
                "role": "owner",
                "email": "owner@example.com",
            },
        )
    )
    assert changed["email"] == "student@example.com"
    assert data(client.get("/api/v1/me", headers=lab["owner"]))["displayName"] == "owner"


def test_cross_team_lists_details_and_mutations_are_denied(lab):
    client, outsider = lab["client"], lab["outsider"]
    route_id = create_route(client, lab)
    task_id = create_task(client, lab)
    experience_id = data(
        client.post(
            f"/api/v1/teams/{lab['team']}/experiences",
            headers=lab["owner"],
            json={"title": "组内经验", "startingPoint": "入门", "content": "内部细节"},
        )
    )["id"]
    resource_id = data(
        client.post(
            f"/api/v1/teams/{lab['team']}/resources",
            headers=lab["student"],
            data={"title": "组内资料", "type": "note"},
            files={"file": ("private.txt", b"private", "text/plain")},
        )
    )["id"]
    paths = [
        f"/teams/{lab['team']}/{kind}"
        for kind in ("members", "routes", "experiences", "meetings", "resources")
    ]
    paths += [
        f"/routes/{route_id}",
        f"/tasks/{task_id}",
        f"/experiences/{experience_id}",
        f"/resources/{resource_id}",
        f"/resources/{resource_id}/download",
        f"/me/tasks?teamId={lab['team']}",
        f"/me/dashboard?teamId={lab['team']}",
        f"/teams/{lab['team']}/search?q=内部",
    ]
    for path in paths:
        reject(
            client.get("/api/v1" + path, headers=outsider),
            404 if path.startswith("/resources/") else 403,
        )
    reject(client.post(f"/api/v1/routes/{route_id}/enrollments", headers=outsider, json={}), 403)
    reject(
        client.post(
            f"/api/v1/tasks/{task_id}/submissions", headers=outsider, json={"summary": "冒领"}
        ),
        403,
    )
    reject(
        client.post(
            f"/api/v1/teams/{lab['team']}/questions",
            headers=outsider,
            json={"question": "内部细节是什么"},
        ),
        403,
    )


def test_invitation_identity_expiry_single_use_and_concurrent_acceptance(lab, monkeypatch):
    client = lab["client"]
    token = invite(client, lab["owner"], lab["team"], "outsider@example.com")
    reject(client.post(f"/api/v1/invitations/{token}/accept", headers=lab["peer"], json={}), 403)
    responses = concurrent_requests(
        lambda: client.post(f"/api/v1/invitations/{token}/accept", headers=lab["outsider"], json={})
    )
    assert sorted(response.status_code for response in responses)[0] == 200
    assert sum(response.status_code == 200 for response in responses) == 1
    assert all(response.status_code in (200, 403, 404, 409) for response in responses), [
        r.text for r in responses
    ]
    members = data(client.get(f"/api/v1/teams/{lab['team']}/members", headers=lab["owner"]))[
        "items"
    ]
    assert sum(item["id"] == lab["outsider_id"] for item in members) == 1
    reject(
        client.post(f"/api/v1/invitations/{token}/accept", headers=lab["outsider"], json={}),
        {403, 404, 409},
    )

    expired = invite(client, lab["owner"], lab["team"], "expired-invite@example.com")
    engine = create_engine(lab["database_url"])
    with Session(engine) as db:
        row = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(expired)))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    engine.dispose()
    monkeypatch.setenv("ALLOW_PUBLIC_SIGNUP", "0")
    reject(
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "expired-invite@example.com",
                "password": PASSWORD,
                "displayName": "过期邀请",
                "invitationToken": expired,
            },
        ),
        403,
    )
    valid = invite(client, lab["owner"], lab["team"], "invited@example.com", "mentor")
    reject(
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "wrong@example.com",
                "password": PASSWORD,
                "displayName": "错误邮箱",
                "invitationToken": valid,
            },
        ),
        403,
    )
    _, invited_auth = signup(client, "invited@example.com", invitationToken=valid)
    roles = data(client.get("/api/v1/me/teams", headers=invited_auth))["items"]
    assert [(item["id"], item["name"], item["role"]) for item in roles] == [
        (lab["team"], "可信科研实验室", "mentor")
    ]


def test_route_updates_preserve_existing_plan_tasks_and_submissions(lab):
    client = lab["client"]
    route_id = create_route(client, lab)
    enrollment = data(
        client.post(f"/api/v1/routes/{route_id}/enrollments", headers=lab["student"], json={})
    )
    old_tasks = data(client.get(f"/api/v1/me/tasks?teamId={lab['team']}", headers=lab["student"]))
    assert old_tasks["total"] == 2
    old_task_id = next(item["id"] for item in old_tasks["items"] if item["title"] == "阅读论文")
    submission_id = data(
        client.post(
            f"/api/v1/tasks/{old_task_id}/submissions",
            headers=lab["student"],
            json={"summary": "基于第一版要求的产出"},
        )
    )["id"]
    edit = {
        "title": "升级路线",
        "description": "新版描述",
        "stages": [
            {"title": "新阶段", "tasks": [{"title": "新任务", "acceptanceCriteria": "新版标准"}]}
        ],
    }
    reject(client.patch(f"/api/v1/routes/{route_id}", headers=lab["student"], json=edit), 403)
    data(client.patch(f"/api/v1/routes/{route_id}", headers=lab["owner"], json=edit))
    repeated = data(
        client.post(f"/api/v1/routes/{route_id}/enrollments", headers=lab["student"], json={})
    )
    assert repeated["id"] == enrollment["id"]
    current = data(client.get(f"/api/v1/tasks/{old_task_id}", headers=lab["student"]))
    assert (current["title"], current["description"], current["acceptanceCriteria"]) == (
        "阅读论文",
        "旧版描述",
        "完成文献笔记",
    )
    assert current["submissions"][0]["id"] == submission_id
    assert (
        data(client.get(f"/api/v1/me/tasks?teamId={lab['team']}", headers=lab["student"]))["total"]
        == 2
    )
    data(client.post(f"/api/v1/routes/{route_id}/enrollments", headers=lab["peer"], json={}))
    new_tasks = data(client.get(f"/api/v1/me/tasks?teamId={lab['team']}", headers=lab["peer"]))
    assert new_tasks["total"] == 1 and new_tasks["items"][0]["title"] == "新任务"


def test_concurrent_enrollment_has_one_plan_and_one_copy_of_each_task(lab):
    client = lab["client"]
    route_id = create_route(client, lab)
    responses = concurrent_requests(
        lambda: client.post(
            f"/api/v1/routes/{route_id}/enrollments", headers=lab["student"], json={}
        )
    )
    enrollments = [data(response) for response in responses]
    assert len({item["id"] for item in enrollments}) == 1
    tasks = data(client.get(f"/api/v1/me/tasks?teamId={lab['team']}", headers=lab["student"]))
    assert tasks["total"] == 2
    assert {item["title"] for item in tasks["items"]} == {"阅读论文", "复现结果"}


def test_task_submission_revisions_reviewer_authority_and_state_transitions(lab):
    client = lab["client"]
    task_id = create_task(client, lab, reviewer=lab["mentor_id"])
    reject(client.get(f"/api/v1/tasks/{task_id}", headers=lab["peer"]), 403)
    reject(
        client.post(
            f"/api/v1/tasks/{task_id}/submissions",
            headers=lab["mentor"],
            json={"summary": "代替提交"},
        ),
        403,
    )
    reject(
        client.patch(f"/api/v1/tasks/{task_id}", headers=lab["student"], json={"status": "done"}),
        400,
    )
    blocked = data(
        client.patch(
            f"/api/v1/tasks/{task_id}",
            headers=lab["student"],
            json={"status": "blocked", "blocker": "缺少实验环境"},
        )
    )
    assert blocked["blocker"] == "缺少实验环境"
    reject(
        client.post(
            f"/api/v1/tasks/{task_id}/submissions",
            headers=lab["student"],
            json={"summary": "成果", "url": "javascript:alert(1)"},
        ),
        400,
    )
    first = data(
        client.post(
            f"/api/v1/tasks/{task_id}/submissions",
            headers=lab["student"],
            json={"summary": "第一版", "url": "https://example.com/result"},
        )
    )["id"]
    reject(
        client.post(
            f"/api/v1/tasks/{task_id}/submissions",
            headers=lab["student"],
            json={"summary": "重复提交"},
        ),
        409,
    )
    reject(
        client.post(
            f"/api/v1/submissions/{first}/reviews",
            headers=lab["student"],
            json={"decision": "approved", "comment": "自评"},
        ),
        403,
    )
    feedback = data(
        client.post(
            f"/api/v1/submissions/{first}/reviews",
            headers=lab["mentor"],
            json={"decision": "changes_requested", "comment": "增加对照组"},
        )
    )
    assert feedback["taskStatus"] == "doing"
    second = data(
        client.post(
            f"/api/v1/tasks/{task_id}/submissions",
            headers=lab["student"],
            json={"summary": "第二版"},
        )
    )["id"]
    reject(
        client.post(
            f"/api/v1/submissions/{first}/reviews",
            headers=lab["owner"],
            json={"decision": "approved", "comment": "过期审批"},
        ),
        409,
    )
    approved = data(
        client.post(
            f"/api/v1/submissions/{second}/reviews",
            headers=lab["owner"],
            json={"decision": "approved", "comment": "验收通过"},
        )
    )
    assert approved["taskStatus"] == "done"
    reject(
        client.post(
            f"/api/v1/submissions/{second}/reviews",
            headers=lab["mentor"],
            json={"decision": "approved", "comment": "重复审批"},
        ),
        409,
    )
    detail = data(client.get(f"/api/v1/tasks/{task_id}", headers=lab["student"]))
    assert detail["status"] == "done" and len(detail["submissions"]) == 2
    assert [len(item["reviews"]) for item in detail["submissions"]] == [1, 1]


def test_owner_cannot_approve_their_own_submission(lab):
    client = lab["client"]
    task_id = create_task(client, lab, assignee=lab["owner_id"], reviewer=lab["mentor_id"])
    submission_id = data(
        client.post(
            f"/api/v1/tasks/{task_id}/submissions",
            headers=lab["owner"],
            json={"summary": "本人产出"},
        )
    )["id"]
    reject(
        client.post(
            f"/api/v1/submissions/{submission_id}/reviews",
            headers=lab["owner"],
            json={"decision": "approved", "comment": "负责人也不能自审"},
        ),
        403,
    )
    assert data(client.get(f"/api/v1/tasks/{task_id}", headers=lab["mentor"]))["status"] == "review"
    assert (
        data(
            client.post(
                f"/api/v1/submissions/{submission_id}/reviews",
                headers=lab["mentor"],
                json={"decision": "approved", "comment": "独立验收"},
            )
        )["taskStatus"]
        == "done"
    )


def test_concurrent_submit_and_review_do_not_create_duplicate_history(lab):
    client = lab["client"]
    task_id = create_task(client, lab)
    submitted = concurrent_requests(
        lambda: client.post(
            f"/api/v1/tasks/{task_id}/submissions",
            headers=lab["student"],
            json={"summary": "同一次成果双击提交"},
        )
    )
    assert sorted(response.status_code for response in submitted) == [200, 409], [
        r.text for r in submitted
    ]
    submission_id = next(
        data(response)["id"] for response in submitted if response.status_code == 200
    )
    reviewed = concurrent_requests(
        lambda: client.post(
            f"/api/v1/submissions/{submission_id}/reviews",
            headers=lab["owner"],
            json={"decision": "approved", "comment": "同一次审批双击"},
        )
    )
    assert sorted(response.status_code for response in reviewed) == [200, 409], [
        r.text for r in reviewed
    ]
    detail = data(client.get(f"/api/v1/tasks/{task_id}", headers=lab["student"]))
    assert len(detail["submissions"]) == 1 and len(detail["submissions"][0]["reviews"]) == 1


def test_upload_link_authority_download_integrity_and_rejected_upload_cleanup(lab, monkeypatch):
    client = lab["client"]
    task_id = create_task(client, lab)
    original_files = set(lab["uploads"].iterdir())
    reject(
        client.post(
            f"/api/v1/teams/{lab['team']}/resources",
            headers=lab["peer"],
            data={"title": "冒关联", "type": "note", "taskId": task_id},
            files={"file": ("unowned.txt", b"injection", "text/plain")},
        ),
        403,
    )
    assert set(lab["uploads"].iterdir()) == original_files
    resource_id = data(
        client.post(
            f"/api/v1/teams/{lab['team']}/resources",
            headers=lab["student"],
            data={"title": "实验记录", "type": "note", "taskId": task_id},
            files={"file": ("../实验记录.txt", "可验证原始内容".encode(), "text/plain")},
        )
    )["id"]
    metadata = data(client.get(f"/api/v1/resources/{resource_id}", headers=lab["student"]))
    assert metadata["fileName"] == "实验记录.txt" and metadata["taskId"] == task_id
    download = client.get(f"/api/v1/resources/{resource_id}/download", headers=lab["student"])
    assert download.status_code == 200 and download.content == "可验证原始内容".encode()
    assert "attachment" in download.headers["content-disposition"]
    assert quote("实验记录.txt") in download.headers["content-disposition"]
    preview = client.get(f"/api/v1/resources/{resource_id}/preview", headers=lab["student"])
    assert preview.status_code == 200 and preview.content == "可验证原始内容".encode()
    assert preview.headers["content-type"].startswith("text/plain")
    assert "inline" in preview.headers["content-disposition"]
    saved = data(
        client.patch(
            f"/api/v1/resources/{resource_id}/reading-progress",
            headers=lab["student"],
            json={"ratio": 0.42, "page": 7, "notes": "关键结论"},
        )
    )
    assert saved["ratio"] == 0.42 and saved["page"] == 7 and saved["notes"] == "关键结论"
    restored = data(
        client.get(f"/api/v1/resources/{resource_id}/reading-progress", headers=lab["student"])
    )
    assert restored["ratio"] == 0.42 and restored["page"] == 7 and restored["notes"] == "关键结论"
    stored = list(lab["uploads"].iterdir())
    assert len(stored) == 1 and stored[0].name != "实验记录.txt"
    reject(client.get(f"/api/v1/resources/{resource_id}/download"), 401)
    reject(client.get(f"/api/v1/resources/{resource_id}/download", headers=lab["outsider"]), 404)
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "3")
    reject(
        client.post(
            f"/api/v1/teams/{lab['team']}/resources",
            headers=lab["student"],
            data={"title": "超过限制", "type": "note"},
            files={"file": ("huge.txt", b"1234", "text/plain")},
        ),
        413,
    )
    assert set(lab["uploads"].iterdir()) == set(stored)
    assert (
        data(client.get(f"/api/v1/teams/{lab['team']}/resources", headers=lab["owner"]))["total"]
        == 0
    )
    assert (
        data(client.get(f"/api/v1/teams/{lab['team']}/resources", headers=lab["student"]))["total"]
        == 1
    )


def test_cross_team_task_and_meeting_links_are_rejected(lab):
    client = lab["client"]
    other_team = team(client, lab["outsider"], "外部实验室")
    meeting_id = data(
        client.post(
            f"/api/v1/teams/{other_team}/meetings",
            headers=lab["outsider"],
            json={
                "title": "外组会议",
                "startsAt": "2030-10-01T08:00:00Z",
                "location": "线上",
                "agenda": "外组",
            },
        )
    )["id"]
    reject(
        client.post(
            f"/api/v1/teams/{lab['team']}/resources",
            headers=lab["owner"],
            data={"title": "跨组资料", "type": "note", "meetingId": meeting_id},
            files={"file": ("notes.txt", b"notes", "text/plain")},
        ),
        400,
    )
    reject(
        client.post(
            f"/api/v1/teams/{lab['team']}/tasks",
            headers=lab["owner"],
            json={
                "title": "跨组任务",
                "assigneeId": lab["student_id"],
                "reviewerId": lab["owner_id"],
                "meetingId": meeting_id,
            },
        ),
        400,
    )
    reject(
        client.post(
            f"/api/v1/teams/{lab['team']}/tasks",
            headers=lab["owner"],
            json={
                "title": "跨组指派",
                "assigneeId": lab["outsider_id"],
                "reviewerId": lab["owner_id"],
            },
        ),
        400,
    )


def test_list_and_search_pagination_keep_total_and_do_not_leak_tasks(lab):
    client = lab["client"]
    expected_ids = set()
    for index in range(23):
        expected_ids.add(
            data(
                client.post(
                    f"/api/v1/teams/{lab['team']}/experiences",
                    headers=lab["student"],
                    json={
                        "title": f"可检索经验{index:02}",
                        "startingPoint": "入门",
                        "content": "可检索内容",
                    },
                )
            )["id"]
        )
    pages = [
        data(
            client.get(
                f"/api/v1/teams/{lab['team']}/experiences?page={page}&pageSize=7",
                headers=lab["student"],
            )
        )
        for page in range(1, 5)
    ]
    assert [len(page["items"]) for page in pages] == [7, 7, 7, 2]
    assert all(page["total"] == 23 for page in pages)
    assert {item["id"] for page in pages for item in page["items"]} == expected_ids
    assert sum(len(page["items"]) for page in pages) == len(expected_ids)
    reject(
        client.get(f"/api/v1/teams/{lab['team']}/experiences?pageSize=101", headers=lab["student"]),
        400,
    )
    reject(
        client.get(f"/api/v1/teams/{lab['team']}/experiences?page=0", headers=lab["student"]), 400
    )
    beyond = data(
        client.get(
            f"/api/v1/teams/{lab['team']}/experiences?page=10&pageSize=7", headers=lab["student"]
        )
    )
    assert beyond == {"items": [], "total": 23}
    create_task(client, lab, assignee=lab["peer_id"], title="可检索秘密任务")
    search_pages = [
        data(
            client.get(
                f"/api/v1/teams/{lab['team']}/search?q=可检索&page={page}&pageSize=7",
                headers=lab["student"],
            )
        )
        for page in range(1, 5)
    ]
    assert all(page["total"] == 23 for page in search_pages)
    assert [len(page["items"]) for page in search_pages] == [7, 7, 7, 2]
    assert {item["id"] for page in search_pages for item in page["items"]} == expected_ids


def test_meeting_time_preserves_the_instant_and_minutes_require_manager(lab):
    client = lab["client"]
    response = client.post(
        f"/api/v1/teams/{lab['team']}/meetings",
        headers=lab["mentor"],
        json={
            "title": "中国时间上午八点",
            "startsAt": "2030-10-01T08:00:00+08:00",
            "location": "线上",
            "agenda": "文献分享",
        },
    )
    meeting_id = data(response)["id"]
    detail = data(client.get(f"/api/v1/meetings/{meeting_id}", headers=lab["student"]))
    actual = datetime.fromisoformat(detail["startsAt"].replace("Z", "+00:00"))
    assert actual == datetime(2030, 10, 1, 0, 0, tzinfo=timezone.utc)
    assert detail["minutes"] is None
    reject(
        client.put(
            f"/api/v1/meetings/{meeting_id}/minutes",
            headers=lab["student"],
            json={"content": "越权编辑"},
        ),
        403,
    )
    data(
        client.put(
            f"/api/v1/meetings/{meeting_id}/minutes",
            headers=lab["mentor"],
            json={"content": "会议结论"},
        )
    )
    assert (
        data(client.get(f"/api/v1/meetings/{meeting_id}", headers=lab["student"]))["minutes"][
            "content"
        ]
        == "会议结论"
    )


def test_notifications_belong_to_recipient_and_can_be_marked_read(lab):
    client = lab["client"]
    create_task(client, lab)
    notifications = data(
        client.get("/api/v1/me/notifications?page=1&pageSize=1", headers=lab["student"])
    )
    assert notifications["total"] >= 1 and len(notifications["items"]) == 1
    notification_id = notifications["items"][0]["id"]
    reject(
        client.patch(
            f"/api/v1/me/notifications/{notification_id}", headers=lab["peer"], json={"read": True}
        ),
        404,
    )
    assert (
        data(
            client.patch(
                f"/api/v1/me/notifications/{notification_id}",
                headers=lab["student"],
                json={"read": True},
            )
        )["read"]
        is True
    )
    fresh = data(client.get("/api/v1/me/notifications", headers=lab["student"]))
    assert next(item for item in fresh["items"] if item["id"] == notification_id)["read"] is True


def test_additive_startup_migration_preserves_plane_and_legacy_extension_data(tmp_path):
    """Exercise upgrading an existing deployment, including a second restart."""
    database_url = f"sqlite:///{tmp_path / 'old-deployment.db'}"
    engine = create_engine(database_url)
    with engine.begin() as db:
        # A sentinel Plane table is deliberately outside the extension namespace.
        db.execute(text("CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT NOT NULL)"))
        db.execute(
            text("INSERT INTO workspaces VALUES ('plane-existing', 'Existing Plane workspace')")
        )
        db.execute(
            text(
                "CREATE TABLE yt_routes (id VARCHAR(36) PRIMARY KEY, team_id VARCHAR(36) NOT NULL, "
                "author_id VARCHAR(36) NOT NULL, title VARCHAR(200) NOT NULL, "
                "description TEXT NOT NULL, stages JSON NOT NULL)"
            )
        )
        db.execute(
            text(
                "INSERT INTO yt_routes VALUES ('legacy-route', 'legacy-team', 'legacy-user', "
                "'Legacy research route', 'Original route data', '[]')"
            )
        )
    for _ in range(2):
        app = create_app(
            database_url, tmp_path / "files", tmp_path / "no-frontend", plane=OfflinePlane()
        )
        with TestClient(app) as client:
            assert client.get("/healthz").status_code == 200
        with engine.connect() as db:
            assert db.execute(text("SELECT id, name FROM workspaces")).all() == [
                ("plane-existing", "Existing Plane workspace")
            ]
            assert db.execute(
                text("SELECT title, description, version FROM yt_routes WHERE id='legacy-route'")
            ).one() == ("Legacy research route", "Original route data", 1)
        assert [column["name"] for column in inspect(engine).get_columns("workspaces")] == [
            "id",
            "name",
        ]
    engine.dispose()
