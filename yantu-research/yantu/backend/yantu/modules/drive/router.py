"""HTTP endpoints for drive."""

from __future__ import annotations
from fastapi import Body
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import Header
from fastapi import Query
from fastapi import Request
from sqlalchemy.orm import Session
from fastapi import UploadFile
from ...core.models import User

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.get("/api/v1/resources/{resource_id}/versions")
def resource_versions(
    resource_id: str,
    page: int = 1,
    pageSize: int = 100,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.resource_versions(
        resource_id=resource_id, page=page, pageSize=pageSize, user=user, db=db
    )


@router.get("/api/v1/teams/{team_id}/resources")
def rich_resources(
    team_id: str,
    page: int = 1,
    pageSize: int = 20,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.rich_resources(team_id=team_id, page=page, pageSize=pageSize, user=user, db=db)


@router.get("/api/v1/resources/{resource_id}")
def rich_resource(
    resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.rich_resource(resource_id=resource_id, user=user, db=db)


@router.get("/api/v1/resources/{resource_id}/download")
def versioned_download(
    resource_id: str,
    versionId: str = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.versioned_download(
        resource_id=resource_id, versionId=versionId, user=user, db=db, services=services
    )


@router.get("/api/v1/resources/{resource_id}/preview")
def preview_resource(
    resource_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.preview_resource(resource_id=resource_id, user=user, db=db, services=services)


@router.get("/api/v1/resources/{resource_id}/reading-progress")
def get_reading_progress(
    resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.get_reading_progress(resource_id=resource_id, user=user, db=db)


@router.patch("/api/v1/resources/{resource_id}/reading-progress")
def save_reading_progress(
    resource_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.save_reading_progress(resource_id=resource_id, payload=payload, user=user, db=db)


@router.get("/api/v1/me/drive/config")
def config(user: User = Depends(current_user)):
    return service.config(user=user)


@router.get("/api/v1/me/drive/folders/tree")
def tree(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.tree(user=user, db=db)


@router.get("/api/v1/me/drive/children")
def children(
    folderId: str = "",
    page: int = Query(1, ge=1),
    pageSize: int = Query(100, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.children(folderId=folderId, page=page, pageSize=pageSize, user=user, db=db)


@router.post("/api/v1/me/drive/folders", status_code=201)
def create_folder(
    payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.create_folder(payload=payload, user=user, db=db)


@router.patch("/api/v1/me/drive/folders/{folder_id}")
def edit_folder(
    folder_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.edit_folder(folder_id=folder_id, payload=payload, user=user, db=db)


@router.delete("/api/v1/me/drive/folders/{folder_id}")
def delete_folder(
    folder_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.delete_folder(folder_id=folder_id, user=user, db=db)


@router.get("/api/v1/me/drive/search")
@router.get("/api/v1/me/drive/shared")
@router.get("/api/v1/me/drive/available-resources")
def available(
    request: Request,
    scope: str = "all",
    q: str = "",
    page: int = Query(1, ge=1),
    pageSize: int = Query(100, ge=1, le=100),
    targetType: str = "",
    targetId: str = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.available(
        request=request,
        scope=scope,
        q=q,
        page=page,
        pageSize=pageSize,
        targetType=targetType,
        targetId=targetId,
        user=user,
        db=db,
    )


@router.patch("/api/v1/resources/{resource_id}")
def edit_file(
    resource_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.edit_file(resource_id=resource_id, payload=payload, user=user, db=db)


@router.post("/api/v1/me/drive/files", status_code=201)
async def upload(
    file: UploadFile = File(),
    folderId: str = Form(""),
    title: str = Form(""),
    type: str = Form("other"),
    description: str = Form("", max_length=50000),
    idempotency_key: str = Header("", alias="Idempotency-Key", max_length=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return await service.upload(
        file=file,
        folderId=folderId,
        title=title,
        type=type,
        description=description,
        idempotency_key=idempotency_key,
        user=user,
        db=db,
        services=services,
    )


@router.post("/api/v1/teams/{team_id}/resources")
async def legacy_upload(
    team_id: str,
    file: UploadFile = File(),
    title: str = Form(""),
    type: str = Form("other"),
    description: str = Form(""),
    meetingId: str = Form(""),
    taskId: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return await service.legacy_upload(
        team_id=team_id,
        file=file,
        title=title,
        type=type,
        description=description,
        meetingId=meetingId,
        taskId=taskId,
        user=user,
        db=db,
        services=services,
    )


@router.post("/api/v1/resources/{resource_id}/versions")
async def version_upload(
    resource_id: str,
    file: UploadFile = File(),
    note: str = Form("", max_length=50000),
    idempotency_key: str = Header("", alias="Idempotency-Key", max_length=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return await service.version_upload(
        resource_id=resource_id,
        file=file,
        note=note,
        idempotency_key=idempotency_key,
        user=user,
        db=db,
        services=services,
    )


@router.get("/api/v1/resources/{resource_id}/shares")
def shares(resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.shares(resource_id=resource_id, user=user, db=db)


@router.put("/api/v1/resources/{resource_id}/shares/{user_id}")
def share(
    resource_id: str,
    user_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.share(
        resource_id=resource_id, user_id=user_id, payload=payload, user=user, db=db
    )


@router.delete("/api/v1/resources/{resource_id}/shares/{user_id}")
def revoke(
    resource_id: str,
    user_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.revoke(resource_id=resource_id, user_id=user_id, user=user, db=db)


@router.post("/api/v1/tasks/{target_id}/resources")
@router.post("/api/v1/meetings/{target_id}/resources")
def reference(
    target_id: str,
    request: Request,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.reference(
        target_id=target_id, request=request, payload=payload, user=user, db=db
    )


@router.delete("/api/v1/tasks/{target_id}/resources/{reference_id}")
@router.delete("/api/v1/meetings/{target_id}/resources/{reference_id}")
def remove_reference(
    target_id: str,
    reference_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.remove_reference(
        target_id=target_id, reference_id=reference_id, request=request, user=user, db=db
    )
