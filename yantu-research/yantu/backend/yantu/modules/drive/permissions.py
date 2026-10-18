"""modules.drive.permissions business operations."""

from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy import select
from ...core.models import Member, Resource, ResourceShare


def member_of(db, team_id, user_id):
    return (
        db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == user_id))
        if team_id
        else None
    )


def valid_share(db, share, resource):
    return (
        share.active
        and member_of(db, share.team_id, share.user_id)
        and member_of(db, share.team_id, resource.owner_id)
    )


def resource_visible(db, resource, user, membership=None):
    if resource.archived:
        return False
    if resource.owner_id == user.id:
        return True
    if resource.visibility == "team" and member_of(db, resource.team_id, user.id):
        return True
    return any(
        (
            valid_share(db, s, resource)
            for s in db.scalars(
                select(ResourceShare).where(
                    ResourceShare.resource_id == resource.id,
                    ResourceShare.user_id == user.id,
                    ResourceShare.active.is_(True),
                )
            )
        )
    )


def resource_for(db, resource_id, user, write=False):
    resource = db.get(Resource, resource_id)
    if not resource or not resource_visible(db, resource, user):
        raise HTTPException(404, "资料不存在或无权访问")
    if write and resource.owner_id != user.id:
        raise HTTPException(403, "只有文件所有者可以修改")
    return (resource, member_of(db, resource.team_id, user.id))
