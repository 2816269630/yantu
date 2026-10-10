from pathlib import Path
import json
from io import BytesIO

import httpx
import pytest
from docx import Document
from fastapi.testclient import TestClient

from yantu.app import create_app
from yantu.models import Team
from yantu.plane_client import PlaneClient, PlaneError
from yantu.research_assistant import OllamaResearchAssistant, extract_document_text


class FakePlane:
    def __init__(self):
        self.created = []
        self.comments = []
        self.fail_next_create = False

    def configured(self, team):
        return bool(team.plane_workspace_slug and team.plane_project_id)

    def create_work_item(self, team, title, description, external_id=None):
        if not self.configured(team):
            return None
        if self.fail_next_create:
            self.fail_next_create = False
            raise PlaneError("Plane 暂时不可用")
        self.created.append(title)
        return "77777777-7777-4777-8777-777777777777"

    def list_work_items(self, team):
        return {"results": [{"id": "77777777-7777-4777-8777-777777777777", "name": "Plane 中的任务",
                             "state": {"name": "进行中"}}], "total_results": 1}

    def add_comment(self, team, work_item_id, content):
        self.comments.append(content)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_PUBLIC_SIGNUP", "1")
    monkeypatch.setenv("PLANE_ALLOWED_PROJECTS", "research-lab:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    plane = FakePlane()
    def answer(request):
        assert request.url.path == "/api/chat"
        prompt = json.loads(request.content)["messages"][1]["content"]
        assert "读论文" in prompt
        return httpx.Response(200, json={"message": {"content": "建议先读摘要 [1]"}})
    assistant = OllamaResearchAssistant("http://ollama:11434", "qwen2.5:3b", httpx.MockTransport(answer))
    front = Path(__file__).parents[2] / "frontend"
    app = create_app(
        f"sqlite:///{tmp_path / 'test.db'}", tmp_path / "uploads", front, plane, assistant
    )
    with TestClient(app) as client:
        yield client, plane


def register(client, email, password="strong-password-123"):
    result = client.post("/api/v1/auth/register", json={"email": email,
                         "password": password, "displayName": email.split("@")[0]})
    assert result.status_code == 200, result.text
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["data"]["accessToken"]
    return result.json()["data"]["id"], {"Authorization": f"Bearer {token}"}


def test_public_signup_is_closed_without_invitation(tmp_path, monkeypatch):
    monkeypatch.delenv("ALLOW_PUBLIC_SIGNUP", raising=False)
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}", tmp_path / "files", tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/register", json={"email": "u@example.com",
                               "password": "strong-password-123", "displayName": "U"})
        assert response.status_code == 403


def test_complete_team_and_workflow(site, monkeypatch):
    client, plane = site
    assert client.get("/").status_code == 200
    owner_id, owner = register(client, "owner@example.com")
    team = client.post("/api/v1/teams", headers=owner, json={"name": "大模型安全实验室",
                        "planeWorkspaceSlug": "research-lab",
                        "planeProjectId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}).json()["data"]
    team_id = team["id"]

    experience = client.post(f"/api/v1/teams/{team_id}/experiences", headers=owner,
                             json={"title": "读论文的方法", "startingPoint": "零基础", "content": "先读摘要"})
    assert experience.status_code == 200
    experience_id = experience.json()["data"]["id"]
    assert client.get(f"/api/v1/teams/{team_id}/experiences", headers=owner).json()["data"]["total"] == 1

    # Only the intended email can accept an invitation, and it is usable once.
    invite = client.post(f"/api/v1/teams/{team_id}/invitations", headers=owner,
                         json={"email": "student@example.com", "role": "student"}).json()["data"]["inviteToken"]
    monkeypatch.setenv("ALLOW_PUBLIC_SIGNUP", "0")
    student_signup = client.post("/api/v1/auth/register", json={"email": "student@example.com",
                          "password": "strong-password-123", "displayName": "学生", "invitationToken": invite})
    assert student_signup.status_code == 200
    student_id = student_signup.json()["data"]["id"]
    student_token = client.post("/api/v1/auth/login", json={"email": "student@example.com",
                                "password": "strong-password-123"}).json()["data"]["accessToken"]
    student = {"Authorization": f"Bearer {student_token}"}
    assert client.post("/api/v1/auth/register", json={"email": "third@example.com",
                          "password": "strong-password-123", "displayName": "Third",
                          "invitationToken": invite}).status_code == 403
    assert client.get(f"/api/v1/experiences/{experience_id}", headers=student).status_code == 200
    assert client.post(f"/api/v1/teams/{team_id}/meetings", headers=student,
                       json={"title": "不能创建", "startsAt": "2026-10-01T08:00:00Z",
                             "location": "线上", "agenda": "讨论"}).status_code == 403

    route = client.post(f"/api/v1/teams/{team_id}/routes", headers=owner,
                        json={"title": "差分隐私入门", "stages": [{"title": "阅读",
                        "tasks": [{"title": "精读论文", "acceptanceCriteria": "形成笔记"}]}]})
    assert route.status_code == 200
    route_id = route.json()["data"]["id"]
    enrollment = client.post(f"/api/v1/routes/{route_id}/enrollments", json={}, headers=student)
    assert enrollment.status_code == 200
    again = client.post(f"/api/v1/routes/{route_id}/enrollments", json={}, headers=student)
    assert again.json()["data"]["id"] == enrollment.json()["data"]["id"]
    mine = client.get(f"/api/v1/me/tasks?teamId={team_id}", headers=student).json()["data"]
    assert mine["total"] == 1

    meeting = client.post(f"/api/v1/teams/{team_id}/meetings", headers=owner,
                          json={"title": "组会", "startsAt": "2026-10-01T08:00:00Z",
                                "location": "实验室", "agenda": "文献分享"})
    assert meeting.status_code == 200
    meeting_id = meeting.json()["data"]["id"]
    assert client.put(f"/api/v1/meetings/{meeting_id}/minutes", headers=owner,
                      json={"content": "下一周读论文"}).status_code == 200
    upload = client.post(f"/api/v1/teams/{team_id}/resources", headers=owner,
                         data={"title": "论文", "type": "paper", "meetingId": meeting_id},
                         files={"file": ("paper.pdf", b"%PDF-test", "application/pdf")})
    assert upload.status_code == 200, upload.text
    resource_id = upload.json()["data"]["id"]
    download = client.get(f"/api/v1/resources/{resource_id}/download", headers=student)
    assert download.status_code == 200 and download.content == b"%PDF-test"
    notes = client.post(f"/api/v1/teams/{team_id}/resources", headers=owner,
                        data={"title": "读论文的方法", "type": "note"},
                        files={"file": ("guide.txt", "读论文时先读摘要，再看方法。".encode(), "text/plain")})
    note_id = notes.json()["data"]["id"]
    answer = client.post(f"/api/v1/teams/{team_id}/questions", headers=student,
                         json={"question": "读论文应该先读什么？"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["data"]["answer"] == "建议先读摘要 [1]"
    assert answer.json()["data"]["sources"][0]["resourceId"] == note_id
    no_sources = client.post(f"/api/v1/teams/{team_id}/questions", headers=student,
                             json={"question": "量子计算机有哪些硬件架构？"})
    assert no_sources.status_code == 200 and no_sources.json()["data"]["sources"] == []

    task = client.post(f"/api/v1/teams/{team_id}/tasks", headers=owner,
                       json={"title": "完成复现实验", "description": "复现基线", "assigneeId": student_id,
                             "reviewerId": owner_id})
    assert task.status_code == 200, task.text
    assert client.post(f"/api/v1/teams/{team_id}/tasks", headers=owner,
                       json={"title": "错误的反馈人", "assigneeId": owner_id,
                             "reviewerId": student_id}).status_code == 400
    assert task.json()["data"]["planeSync"] == "linked"
    task_id = task.json()["data"]["id"]
    assert plane.created == ["精读论文", "完成复现实验"]
    assert client.get(f"/api/v1/teams/{team_id}/plane-work-items", headers=student).json()["data"]["total"] == 1

    submission = client.post(f"/api/v1/tasks/{task_id}/submissions", headers=student,
                             json={"summary": "附上复现结果"})
    assert submission.status_code == 200
    submission_id = submission.json()["data"]["id"]
    assert client.post(f"/api/v1/submissions/{submission_id}/reviews", headers=student,
                       json={"decision": "approved", "comment": "可以"}).status_code == 403
    review = client.post(f"/api/v1/submissions/{submission_id}/reviews", headers=owner,
                         json={"decision": "approved", "comment": "可以"})
    assert review.json()["data"]["taskStatus"] == "done"
    assert client.post(f"/api/v1/submissions/{submission_id}/reviews", headers=owner,
                       json={"decision": "approved", "comment": "重复"}).status_code == 409
    assert len(plane.comments) == 2
    assert client.get(f"/api/v1/me/dashboard?teamId={team_id}", headers=student).json()["data"]["progress"]["completed"] == 1
    assert client.get(f"/api/v1/teams/{team_id}/search?q=论文", headers=student).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=student).status_code == 200
    assert client.get("/api/v1/me", headers=student).status_code == 401


def test_team_isolation_and_upload_limit(site, monkeypatch):
    client, _ = site
    _, alice = register(client, "alice@example.com")
    _, bob = register(client, "bob@example.com")
    team_id = client.post("/api/v1/teams", headers=alice, json={"name": "A"}).json()["data"]["id"]
    assert client.get(f"/api/v1/teams/{team_id}/experiences", headers=bob).status_code == 403
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "3")
    response = client.post(f"/api/v1/teams/{team_id}/resources", headers=alice,
                           data={"title": "过大", "type": "paper"},
                           files={"file": ("a.txt", b"1234")})
    assert response.status_code == 413


def test_plane_binding_allowlist_and_retry_without_false_success(site):
    client, plane = site
    _, owner = register(client, "owner@example.com")
    team_id = client.post("/api/v1/teams", headers=owner, json={"name": "实验室"}).json()["data"]["id"]
    forbidden = client.patch(f"/api/v1/teams/{team_id}/plane", headers=owner,
                             json={"planeWorkspaceSlug": "elsewhere",
                                   "planeProjectId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"})
    assert forbidden.status_code == 403
    allowed = client.patch(f"/api/v1/teams/{team_id}/plane", headers=owner,
                           json={"planeWorkspaceSlug": "research-lab",
                                 "planeProjectId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"})
    assert allowed.status_code == 200
    route = client.post(f"/api/v1/teams/{team_id}/routes", headers=owner,
                        json={"title": "学习", "stages": [{"title": "入门", "tasks": [{"title": "读论文"}]}]})
    plane.fail_next_create = True
    route_id = route.json()["data"]["id"]
    first = client.post(f"/api/v1/routes/{route_id}/enrollments", headers=owner, json={})
    assert first.json()["data"]["planeSync"] == "retry_needed"
    assert plane.created == []
    again = client.post(f"/api/v1/routes/{route_id}/enrollments", headers=owner, json={})
    assert again.json()["data"]["id"] == first.json()["data"]["id"]
    assert again.json()["data"]["planeSync"] == "linked"
    assert plane.created == ["读论文"]


def test_login_is_temporarily_locked_after_five_failures(site):
    client, _ = site
    register(client, "u@example.com")
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"email": "u@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "u@example.com",
                       "password": "strong-password-123"}).status_code == 429


def test_plane_public_api_auth_and_work_item_idempotency():
    requests = []
    def respond(request):
        requests.append(request)
        assert request.headers["X-API-Key"] == "server-only-key"
        if request.method == "GET":
            return httpx.Response(200, json={"results": [], "total_results": 0})
        return httpx.Response(201, json={"id": "plane-work-item-id"})

    client = PlaneClient("http://api:8000", "server-only-key", httpx.MockTransport(respond))
    team = Team(plane_workspace_slug="research-lab", plane_project_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    item = client.create_work_item(team, "精读论文", "内容", external_id="local-task-id")
    assert item == "plane-work-item-id"
    assert requests[0].url.path.endswith("/work-items/")
    assert requests[0].url.params["external_id"] == "local-task-id"
    assert json.loads(requests[1].content)["external_source"] == "yantu"
    client.add_comment(team, item, "评论 <script>")
    assert requests[2].url.path.endswith("/work-items/plane-work-item-id/comments/")
    assert "&lt;script&gt;" in json.loads(requests[2].content)["comment_html"]


def test_document_extraction_for_pdf_docx_and_text():
    doc = Document()
    doc.add_paragraph("差分隐私保护训练数据")
    payload = BytesIO()
    doc.save(payload)
    assert "差分隐私" in extract_document_text("methods.docx", payload.getvalue())
    assert extract_document_text("methods.md", "先读摘要".encode()) == "先读摘要"
    assert extract_document_text("scanned.pdf", b"%PDF-invalid") == ""
