"""modules.drive.service business operations."""

from __future__ import annotations
from fastapi.responses import FileResponse
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from pathlib import Path
from fastapi import Request
from sqlalchemy.orm import Session
from fastapi import UploadFile
from datetime import datetime
import hashlib
import json
import mimetypes
import os
from urllib.parse import quote
from sqlalchemy import select
from datetime import timedelta
from datetime import timezone
from uuid import uuid4
from ...core.models import (
    DriveFolder,
    Meeting,
    Member,
    Resource,
    ResourceReference,
    ResourceShare,
    ResourceVersion,
    Task,
    UploadReceipt,
    User,
    utcnow,
)
from ...integrations.ollama import extract_document_text
from ...modules.drive.schemas import EXTENSIONS


def preview_media_type(filename):
    media_type = mimetypes.guess_type(filename or "")[0] or ""
    if (
        media_type == "application/pdf"
        or media_type.startswith(("image/", "audio/", "video/"))
        or media_type in ("text/plain", "text/markdown", "text/csv")
    ):
        if media_type not in ("image/svg+xml",):
            return media_type
    return None


def resource_json(db, resource, user):
    from ...core.metadata import get_meta
    from ...core.presentation import user_name

    meta = get_meta(db, "resource", resource.id)
    membership = db.scalar(
        select(Member).where(Member.team_id == resource.team_id, Member.user_id == user.id)
    )
    return {
        "id": resource.id,
        "title": resource.title,
        "type": resource.type,
        "description": resource.description,
        "ownerId": resource.owner_id,
        "owner": user_name(db, resource.owner_id),
        "fileName": resource.file_name,
        "size": resource.size,
        "version": resource.version,
        "visibility": resource.visibility,
        "tags": meta.get("tags", []),
        "meetingId": resource.meeting_id,
        "taskId": resource.task_id,
        "previewable": bool(preview_media_type(resource.file_name)),
        "previewType": preview_media_type(resource.file_name),
        "folderId": resource.folder_id,
        "canEdit": resource.owner_id == user.id,
        "permissions": {
            "canRead": True,
            "canDownload": True,
            "canEdit": resource.owner_id == user.id,
            "canShare": resource.owner_id == user.id,
        },
        "references": [
            {"id": ref.id, "targetType": ref.target_type, "targetId": ref.target_id}
            for ref in db.scalars(
                select(ResourceReference).where(ResourceReference.resource_id == resource.id)
            )
        ],
    }


def resource_versions(
    resource_id: str, page: int = 1, pageSize: int = 100, user: User = None, db: Session = None
):
    from ...core.presentation import iso
    from ...modules.drive.permissions import resource_for
    from ...core.presentation import user_name
    from ...core.presentation import page_data

    resource_for(db, resource_id, user)
    rows = db.scalars(
        select(ResourceVersion)
        .where(ResourceVersion.resource_id == resource_id)
        .order_by(ResourceVersion.version)
    ).all()
    items = [
        {
            "id": r.id,
            "version": r.version,
            "note": r.note,
            "size": r.size,
            "createdAt": iso(r.created_at),
            "author": user_name(db, r.author_id),
        }
        for r in rows
    ]
    return page_data(items, page, pageSize)


def rich_resources(
    team_id: str, page: int = 1, pageSize: int = 20, user: User = None, db: Session = None
):
    from ...core.permissions import team_member
    from ...modules.drive.permissions import resource_visible
    from ...core.presentation import page_data

    team_member(db, team_id, user)
    rows = db.scalars(
        select(Resource).where(Resource.team_id == team_id).order_by(Resource.title, Resource.id)
    ).all()
    items = [resource_json(db, r, user) for r in rows if resource_visible(db, r, user)]
    return page_data(items, page, pageSize)


def rich_resource(resource_id: str, user: User = None, db: Session = None):
    from ...modules.drive.permissions import resource_for

    row, _ = resource_for(db, resource_id, user)
    return {"data": resource_json(db, row, user)}


def versioned_download(
    resource_id: str, versionId: str = "", user: User = None, db: Session = None, *, services
):
    from ...modules.drive.permissions import resource_for

    row, _ = resource_for(db, resource_id, user)
    filename = row.file_name
    storage = row.storage_name
    if versionId:
        version = db.get(ResourceVersion, versionId)
        if not version or version.resource_id != row.id:
            raise HTTPException(404, "资料版本不存在")
        filename = version.file_name
        storage = version.storage_name
    location = services.uploads / storage
    if not location.is_file():
        raise HTTPException(404, "文件暂时不可用")
    return FileResponse(location, media_type="application/octet-stream", filename=filename)


def preview_resource(resource_id: str, user: User = None, db: Session = None, *, services):
    from ...modules.drive.permissions import resource_for

    row, _ = resource_for(db, resource_id, user)
    media_type = preview_media_type(row.file_name)
    if not media_type:
        raise HTTPException(415, "该文件格式不支持浏览器在线预览，请下载后查看")
    location = services.uploads / row.storage_name
    if not location.is_file():
        raise HTTPException(404, "文件暂时不可用")
    safe_name = quote(row.file_name.encode("utf-8"))
    return FileResponse(
        location,
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{safe_name}",
            "X-Content-Type-Options": "nosniff",
        },
    )


def get_reading_progress(resource_id: str, user: User = None, db: Session = None):
    from ...modules.drive.permissions import resource_for
    from ...core.metadata import get_meta

    resource_for(db, resource_id, user)
    return {"data": get_meta(db, "reading", f"{resource_id}:{user.id}")}


def save_reading_progress(
    resource_id: str, payload: dict = None, user: User = None, db: Session = None
):
    from ...core.presentation import iso
    from ...modules.drive.permissions import resource_for
    from ...core.metadata import put_meta

    resource_for(db, resource_id, user)
    values = {}
    if "ratio" in payload:
        values["ratio"] = max(0.0, min(1.0, float(payload["ratio"])))
    if "page" in payload:
        values["page"] = max(1, min(100000, int(payload["page"])))
    if "time" in payload:
        values["time"] = max(0.0, float(payload["time"]))
    if "notes" in payload:
        values["notes"] = str(payload["notes"])[:50000]
    values["updatedAt"] = iso(datetime.now(timezone.utc))
    put_meta(db, "reading", f"{resource_id}:{user.id}", values)
    db.commit()
    return {"data": values}


def referenced_resources(db, kind, ident):
    ids = db.scalars(
        select(ResourceReference.resource_id).where(
            ResourceReference.target_type == kind, ResourceReference.target_id == ident
        )
    ).all()
    return list(db.scalars(select(Resource).where(Resource.id.in_(ids)))) if ids else []


def validate_name(value):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > 200
        or any((c in value for c in '/\\:*?"<>|'))
        or any((ord(c) < 32 for c in value))
        or (value.strip() in (".", ".."))
    ):
        raise HTTPException(400, "名称不能为空，最多 200 字，不能包含路径符号或控制字符")
    return value.strip()


def folder_for(db, folder_id, user):
    if not folder_id:
        return None
    row = db.get(DriveFolder, folder_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "目录不存在或无权访问")
    return row


def folder_json(row):
    from ...core.presentation import iso

    return {
        "id": row.id,
        "name": row.name,
        "parentId": row.parent_id,
        "ownerId": row.owner_id,
        "createdAt": iso(row.created_at),
    }


def breadcrumbs(db, folder_id, user):
    items, seen = ([], set())
    while folder_id:
        if folder_id in seen:
            raise HTTPException(409, "目录层级异常")
        seen.add(folder_id)
        row = folder_for(db, folder_id, user)
        items.insert(0, folder_json(row))
        folder_id = row.parent_id
    return [{"id": None, "name": "我的文件"}] + items


def file_json(db, row, user):
    from ...modules.drive.permissions import member_of
    from ...modules.drive.permissions import valid_share

    item = resource_json(db, row, user)
    item["folderId"] = row.folder_id
    item["location"] = breadcrumbs(db, row.folder_id, user) if row.owner_id == user.id else []
    item["permissions"] = {
        "canRead": True,
        "canDownload": True,
        "canEdit": row.owner_id == user.id,
        "canShare": row.owner_id == user.id,
        "canMove": row.owner_id == user.id,
    }
    item["accessSources"] = (["owner"] if row.owner_id == user.id else []) + (
        ["legacyTeam"] if row.visibility == "team" and member_of(db, row.team_id, user.id) else []
    )
    if any(
        (
            valid_share(db, s, row)
            for s in db.scalars(
                select(ResourceShare).where(
                    ResourceShare.resource_id == row.id, ResourceShare.user_id == user.id
                )
            )
        )
    ):
        item["accessSources"].append("direct")
    return item


def check_duplicate(db, user, parent, title, exclude=None):
    if db.scalar(
        select(DriveFolder.id).where(
            DriveFolder.owner_id == user.id,
            DriveFolder.parent_id == parent,
            DriveFolder.name == title,
            DriveFolder.id != (exclude or ""),
        )
    ):
        raise HTTPException(409, "该目录下已存在同名文件夹")


def config(user: User = None):
    from ...core.presentation import result

    return result(
        {
            "maxUploadBytes": int(os.getenv("MAX_UPLOAD_BYTES", 20 * 1024 * 1024)),
            "allowedExtensions": EXTENSIONS,
            "extractableExtensions": [".pdf", ".docx", ".txt", ".md"],
            "maxQuestionResources": 100,
            "maxQuestionLength": 500,
        }
    )


def tree(user: User = None, db: Session = None):
    from ...core.presentation import result

    rows = db.scalars(
        select(DriveFolder).where(DriveFolder.owner_id == user.id).order_by(DriveFolder.name)
    ).all()
    return result({"items": [folder_json(r) for r in rows]})


def children(
    folderId: str = "", page: int = 1, pageSize: int = 100, user: User = None, db: Session = None
):
    from ...core.presentation import result

    folder_for(db, folderId, user)
    folders = db.scalars(
        select(DriveFolder)
        .where(DriveFolder.owner_id == user.id, DriveFolder.parent_id == (folderId or None))
        .order_by(DriveFolder.name)
    ).all()
    files = db.scalars(
        select(Resource)
        .where(
            Resource.owner_id == user.id,
            Resource.folder_id == (folderId or None),
            Resource.archived.is_(False),
        )
        .order_by(Resource.title)
    ).all()
    items = [{**folder_json(r), "kind": "folder"} for r in folders] + [
        {**file_json(db, r, user), "kind": "file"} for r in files
    ]
    return result(
        {
            "items": items[(page - 1) * pageSize : page * pageSize],
            "total": len(items),
            "page": page,
            "pageSize": pageSize,
            "breadcrumbs": breadcrumbs(db, folderId, user),
        }
    )


def create_folder(payload: dict = None, user: User = None, db: Session = None):
    from ...core.presentation import result

    parent = payload.get("parentId") or None
    folder_for(db, parent, user)
    title = validate_name(payload.get("name"))
    check_duplicate(db, user, parent, title)
    row = DriveFolder(owner_id=user.id, parent_id=parent, name=title)
    db.add(row)
    db.commit()
    return result(folder_json(row))


def edit_folder(folder_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...core.presentation import result

    row = folder_for(db, folder_id, user)
    parent = payload.get("parentId", row.parent_id) or None
    folder_for(db, parent, user)
    if any((x["id"] == row.id for x in breadcrumbs(db, parent, user))):
        raise HTTPException(409, "不能移动到自身或子目录")
    title = validate_name(payload.get("name", row.name))
    check_duplicate(db, user, parent, title, row.id)
    row.name, row.parent_id = (title, parent)
    db.commit()
    return result(folder_json(row))


def delete_folder(folder_id: str, user: User = None, db: Session = None):
    from ...core.presentation import result

    row = folder_for(db, folder_id, user)
    if db.scalar(select(DriveFolder.id).where(DriveFolder.parent_id == row.id)) or db.scalar(
        select(Resource.id).where(Resource.folder_id == row.id)
    ):
        raise HTTPException(409, "只能删除空文件夹，请先移走文件和子目录")
    db.delete(row)
    db.commit()
    return result(None)


def available_rows(db, user, scope, q):
    from ...modules.drive.permissions import resource_visible

    if scope not in ("mine", "shared", "all"):
        raise HTTPException(400, "搜索范围无效")
    query = (
        select(Resource).where(Resource.archived.is_(False)).order_by(Resource.title, Resource.id)
    )
    if scope == "mine":
        query = query.where(Resource.owner_id == user.id)
    elif scope == "shared":
        query = query.where(Resource.owner_id != user.id)
    return [
        r
        for r in db.scalars(query)
        if resource_visible(db, r, user) and q.casefold() in r.title.casefold()
    ]


def target_for(db, kind, ident, user):
    from ...core.permissions import task_for
    from ...core.permissions import team_member

    if kind == "task":
        row, _, _ = task_for(db, ident, user)
        users = [row.assignee_id, row.reviewer_id]
    elif kind == "meeting":
        row = db.get(Meeting, ident)
        if not row:
            raise HTTPException(404, "组会不存在")
        team_member(db, row.team_id, user)
        users = list(db.scalars(select(Member.user_id).where(Member.team_id == row.team_id)))
    else:
        raise HTTPException(400, "引用类型无效")
    return (row, list(dict.fromkeys(users)))


def available(
    request: Request,
    scope: str = "all",
    q: str = "",
    page: int = 1,
    pageSize: int = 100,
    targetType: str = "",
    targetId: str = "",
    user: User = None,
    db: Session = None,
):
    from ...core.presentation import paginate
    from ...modules.drive.permissions import resource_visible
    from ...core.presentation import user_name

    if request.url.path.endswith("/shared"):
        scope = "shared"
    audience = target_for(db, targetType, targetId, user)[1] if targetType else []
    rows = available_rows(db, user, scope, q)
    items = [file_json(db, r, user) for r in rows]
    if audience:
        for item, row in zip(items, rows):
            item["audience"] = [
                {
                    "userId": uid,
                    "displayName": user_name(db, uid),
                    "canRead": resource_visible(db, row, db.get(User, uid)),
                }
                for uid in audience
            ]
    return paginate(items, page, pageSize)


def edit_file(resource_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...modules.drive.permissions import resource_for
    from ...core.presentation import result
    from ...core.metadata import put_meta
    from ...core.validation import tags
    from ...core.validation import text_value

    row, _ = resource_for(db, resource_id, user, True)
    if "visibility" in payload and payload["visibility"] != row.visibility:
        raise HTTPException(400, "请通过指定成员共享管理授权，不能扩大旧课题组可见范围")
    if "title" in payload:
        row.title = validate_name(payload["title"])
    if "description" in payload:
        row.description = text_value(payload, "description")
    if "folderId" in payload:
        folder_for(db, payload["folderId"], user)
        row.folder_id = payload["folderId"] or None
    if "tags" in payload:
        put_meta(db, "resource", row.id, {"tags": tags(payload)})
    db.commit()
    return result(file_json(db, row, user))


def validate_file(filename, content):
    filename = (
        (filename or "").replace("\\", "/").split("/")[-1].replace("\r", "").replace("\n", "")[:255]
    )
    if not content:
        raise HTTPException(400, "不能上传空文件")
    if len(content) > int(os.getenv("MAX_UPLOAD_BYTES", 20 * 1024 * 1024)):
        raise HTTPException(413, "文件超过上传大小限制")
    if Path(filename).suffix.lower() not in EXTENSIONS:
        raise HTTPException(415, "不支持的文件格式")
    return filename


async def save_upload(
    db,
    user,
    file,
    folder_id,
    title,
    category,
    description,
    key,
    version_resource=None,
    note="",
    legacy_team=None,
    *,
    services,
):
    folder_for(db, folder_id, user)
    content = await file.read(int(os.getenv("MAX_UPLOAD_BYTES", 20 * 1024 * 1024)) + 1)
    filename = validate_file(file.filename, content)
    if category not in ("paper", "note", "slides", "other", "tutorial", "experience", "template"):
        raise HTTPException(400, "资料分类无效")
    title = validate_name(title or filename[:200])
    scope = version_resource.id if version_resource else "file"
    receipt_key = f"{user.id}:{scope}:{key}" if key else ""
    fingerprint = hashlib.sha256(
        content
        + json.dumps(
            [filename, folder_id, title, category, description, note], ensure_ascii=False
        ).encode()
    ).hexdigest()
    if receipt_key:
        receipt = db.get(UploadReceipt, receipt_key)
        if receipt and receipt.created_at.replace(tzinfo=utcnow().tzinfo) > utcnow() - timedelta(
            hours=24
        ):
            if receipt.fingerprint != fingerprint:
                raise HTTPException(409, "同一上传标识不能用于不同内容")
            return receipt.result
        if receipt:
            db.delete(receipt)
            db.flush()
    storage = str(uuid4())
    destination = services.uploads / storage
    destination.write_bytes(content)
    try:
        if version_resource:
            row = version_resource
            if not db.scalar(
                select(ResourceVersion.id).where(
                    ResourceVersion.resource_id == row.id, ResourceVersion.version == row.version
                )
            ):
                db.add(
                    ResourceVersion(
                        resource_id=row.id,
                        version=row.version,
                        file_name=row.file_name,
                        storage_name=row.storage_name,
                        size=row.size,
                        note="初始版本",
                        author_id=row.owner_id,
                    )
                )
            row.version += 1
            row.file_name, row.storage_name, row.size = (filename, storage, len(content))
            row.extracted_text = extract_document_text(filename, content)
        else:
            base, index = (title, 1)
            while db.scalar(
                select(Resource.id).where(
                    Resource.owner_id == user.id,
                    Resource.folder_id == (folder_id or None),
                    Resource.title == title,
                )
            ):
                index += 1
                title = f"{base[:185]} ({index})"
            row = Resource(
                owner_id=user.id,
                team_id=legacy_team,
                folder_id=folder_id or None,
                title=title,
                type=category,
                description=description,
                visibility="private",
                file_name=filename,
                storage_name=storage,
                size=len(content),
                extracted_text=extract_document_text(filename, content),
            )
            db.add(row)
            db.flush()
        version = ResourceVersion(
            resource_id=row.id,
            version=row.version,
            file_name=filename,
            storage_name=storage,
            size=len(content),
            note=note,
            author_id=user.id,
        )
        db.add(version)
        db.flush()
        value = (
            {"id": version.id, "resourceId": row.id, "version": row.version}
            if version_resource
            else file_json(db, row, user)
        )
        if receipt_key:
            db.add(UploadReceipt(key=receipt_key, fingerprint=fingerprint, result=value))
        db.commit()
        return value
    except IntegrityError:
        db.rollback()
        destination.unlink(missing_ok=True)
        receipt = db.get(UploadReceipt, receipt_key) if receipt_key else None
        if receipt and receipt.fingerprint == fingerprint:
            return receipt.result
        raise HTTPException(409, "上传状态已变化，请刷新后重试")
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise


async def upload(
    file: UploadFile = None,
    folderId: str = "",
    title: str = "",
    type: str = "other",
    description: str = "",
    idempotency_key: str = "",
    user: User = None,
    db: Session = None,
    *,
    services,
):
    from ...core.presentation import result

    return result(
        await save_upload(
            db, user, file, folderId, title, type, description, idempotency_key, services=services
        )
    )


async def legacy_upload(
    team_id: str,
    file: UploadFile = None,
    title: str = "",
    type: str = "other",
    description: str = "",
    meetingId: str = "",
    taskId: str = "",
    user: User = None,
    db: Session = None,
    *,
    services,
):
    from ...core.permissions import team_member
    from ...core.presentation import result

    team_member(db, team_id, user)
    for kind, ident in [("meeting", meetingId), ("task", taskId)]:
        if ident:
            target = db.get(Meeting if kind == "meeting" else Task, ident)
            if not target or target.team_id != team_id:
                raise HTTPException(400, "关联内容不属于当前课题组")
            target_for(db, kind, ident, user)
    value = await save_upload(
        db, user, file, "", title, type, description, "", legacy_team=team_id, services=services
    )
    row = db.get(Resource, value["id"])
    row.meeting_id, row.task_id = (meetingId or None, taskId or None)
    db.commit()
    return result(value)


async def version_upload(
    resource_id: str,
    file: UploadFile = None,
    note: str = "",
    idempotency_key: str = "",
    user: User = None,
    db: Session = None,
    *,
    services,
):
    from ...modules.drive.permissions import resource_for
    from ...core.presentation import result

    row, _ = resource_for(db, resource_id, user, True)
    db.refresh(row, with_for_update=True)
    return result(
        await save_upload(
            db,
            user,
            file,
            row.folder_id,
            row.title,
            row.type,
            row.description,
            idempotency_key,
            row,
            note,
            services=services,
        )
    )


def shares(resource_id: str, user: User = None, db: Session = None):
    from ...core.presentation import iso
    from ...modules.drive.permissions import resource_for
    from ...core.presentation import result
    from ...modules.drive.permissions import valid_share
    from ...core.presentation import user_name

    row, _ = resource_for(db, resource_id, user, True)
    items = [
        {
            "id": s.id,
            "userId": s.user_id,
            "displayName": user_name(db, s.user_id),
            "teamId": s.team_id,
            "permission": "read",
            "active": bool(valid_share(db, s, row)),
            "createdAt": iso(s.created_at),
        }
        for s in db.scalars(select(ResourceShare).where(ResourceShare.resource_id == row.id))
    ]
    return result(
        {
            "direct": {"items": items},
            "legacyAccess": {"teamId": row.team_id, "active": row.visibility == "team"},
        }
    )


def share(
    resource_id: str, user_id: str, payload: dict = None, user: User = None, db: Session = None
):
    from ...modules.drive.permissions import member_of
    from ...modules.drive.permissions import resource_for
    from ...core.presentation import result

    row, _ = resource_for(db, resource_id, user, True)
    team_id = payload.get("teamId")
    if (
        payload.get("permission") != "read"
        or user_id == user.id
        or (not member_of(db, team_id, user.id))
        or (not member_of(db, team_id, user_id))
    ):
        raise HTTPException(400, "只能只读共享给同课题组的有效成员")
    s = db.scalar(
        select(ResourceShare).where(
            ResourceShare.resource_id == row.id,
            ResourceShare.user_id == user_id,
            ResourceShare.team_id == team_id,
        )
    )
    if not s:
        s = ResourceShare(resource_id=row.id, user_id=user_id, team_id=team_id)
        db.add(s)
    s.active = True
    db.commit()
    return result(
        {"id": s.id, "userId": user_id, "teamId": team_id, "permission": "read", "active": True}
    )


def revoke(resource_id: str, user_id: str, user: User = None, db: Session = None):
    from ...modules.drive.permissions import resource_for
    from ...core.presentation import result

    row, _ = resource_for(db, resource_id, user, True)
    for s in db.scalars(
        select(ResourceShare).where(
            ResourceShare.resource_id == row.id, ResourceShare.user_id == user_id
        )
    ):
        s.active = False
    db.commit()
    return result(None)


def reference(
    target_id: str, request: Request, payload: dict = None, user: User = None, db: Session = None
):
    from ...core.presentation import iso
    from ...modules.drive.permissions import resource_for
    from ...core.presentation import result

    kind = "task" if "/tasks/" in request.url.path else "meeting"
    target_for(db, kind, target_id, user)
    row, _ = resource_for(db, str(payload.get("resourceId", "")), user)
    ref = db.scalar(
        select(ResourceReference).where(
            ResourceReference.target_type == kind,
            ResourceReference.target_id == target_id,
            ResourceReference.resource_id == row.id,
        )
    )
    if not ref:
        ref = ResourceReference(target_type=kind, target_id=target_id, resource_id=row.id)
        db.add(ref)
        db.commit()
    return result(
        {
            "id": ref.id,
            "resourceId": ref.resource_id,
            "targetType": kind,
            "targetId": target_id,
            "createdAt": iso(ref.created_at),
        }
    )


def remove_reference(
    target_id: str, reference_id: str, request: Request, user: User = None, db: Session = None
):
    from ...core.presentation import result

    kind = "task" if "/tasks/" in request.url.path else "meeting"
    target_for(db, kind, target_id, user)
    row = db.get(ResourceReference, reference_id)
    if not row or row.target_type != kind or row.target_id != target_id:
        raise HTTPException(404, "引用不存在")
    db.delete(row)
    db.commit()
    return result(None)
