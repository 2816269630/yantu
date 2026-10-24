"""Seed a disposable local UI preview through its real HTTP API.

Run only inside a preview container with DATABASE_URL pointing to /tmp/lab-preview.db.
The deployment database is never contacted by this helper.
"""
import os
from datetime import datetime, timedelta, timezone

import httpx


def main():
    if os.environ.get("DATABASE_URL") != "sqlite:////tmp/lab-preview.db":
        raise SystemExit("Only the disposable UI preview may be seeded")
    password = "PreviewOnly2026!"
    with httpx.Client(base_url="http://127.0.0.1:8000/api/v1", timeout=20) as client:
        def call(method, endpoint, **kwargs):
            response = client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response.json()["data"]

        def account(name, label):
            email = f"{name}@preview.test"
            call("POST", "/auth/register", json={"email": email, "password": password, "displayName": label})
            session = call("POST", "/auth/login", json={"email": email, "password": password})
            client.cookies.clear()
            return session["user"]["id"], {"Authorization": "Bearer " + session["accessToken"]}

        owner_id, owner = account("owner", "课题负责人")
        member_id, member = account("member", "普通成员")
        pending_id, pending = account("pending", "待审批成员")
        project = call("POST", "/lab/projects", headers=owner, json={"name": "实验室课题验收", "description": "独立预览容器中的测试内容"})
        other = call("POST", "/lab/projects", headers=owner, json={"name": "尚未加入的课题"})
        ident = project["id"]
        request = call("POST", f"/lab/projects/{ident}/join-requests", headers=member, json={"message": "申请参加课题"})
        call("POST", f"/lab/projects/{ident}/join-requests/{request['id']}/decision", headers=owner, json={"decision": "approved"})
        call("POST", f"/lab/projects/{ident}/join-requests", headers=pending, json={"message": "浏览器审批验收"})
        now = datetime.now(timezone.utc)
        meeting = call("POST", f"/lab/projects/{ident}/meetings", headers=owner, json={"title": "本周进展组会", "startsAt": (now + timedelta(days=2)).isoformat(), "location": "实验室", "agenda": "讨论实验进展和下一步安排"})
        call("POST", f"/lab/projects/{ident}/tasks", headers=owner, json={"title": "整理本周实验记录", "description": "汇总参数与原始数据", "assigneeId": member_id, "dueAt": (now + timedelta(days=3)).isoformat()})
        call("POST", f"/lab/projects/{ident}/materials", headers=member, data={"title": "实验记录", "meetingId": meeting["id"]}, files={"file": ("notes.txt", "请保留原始实验参数。".encode(), "text/plain")})
        call("POST", "/lab/messages", headers=member, json={"title": "给新同学的建议", "content": "记录每次实验的参数，保留原始数据。"})
        parent = None
        for name in ("科研资料", "论文阅读", "方法"):
            folder = call("POST", "/me/drive/folders", headers=member, json={"name": name, "parentId": parent})
            parent = folder['id']
        call("POST", "/me/drive/files", headers=member, data={"type":"note", "title":"个人研究笔记"}, files={"file":("research.txt", b"Personal research notes", "text/plain")})
        call("POST", "/me/drive/files", headers=member, data={"type":"paper", "title":"方法文献", "folderId":parent}, files={"file":("methods.txt", b"Experimental methods", "text/plain")})
        shared = call("POST", "/me/drive/files", headers=owner, data={"type":"note", "title":"共享实验记录"}, files={"file":("shared.txt", b"Shared laboratory evidence", "text/plain")})
        call("PUT", f"/resources/{shared['id']}/shares/{member_id}", headers=owner, json={"permission":"read", "teamId":ident})
        print("Disposable UI preview seeded: owner@preview.test, member@preview.test, pending@preview.test")


if __name__ == "__main__":
    main()
