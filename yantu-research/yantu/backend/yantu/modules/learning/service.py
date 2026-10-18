"""modules.learning.service business operations."""

from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime
from copy import deepcopy
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy import update
from uuid import uuid4
from ...core.models import (
    Bookmark,
    Enrollment,
    Experience,
    Member,
    Resource,
    Route,
    RouteVersion,
    Task,
    Team,
    User,
)
from ...modules.learning.schemas import ExperienceInput


def list_experiences(
    team_id: str, page: int = 1, pageSize: int = 20, user: User = None, db: Session = None
):
    from ...core.presentation import iso
    from ...core.presentation import item_page
    from ...core.permissions import team_member

    team_member(db, team_id, user)
    items, total = item_page(db, Experience, team_id, page, pageSize)
    return {
        "data": {
            "items": [
                {
                    "id": e.id,
                    "title": e.title,
                    "author": db.get(User, e.author_id).display_name,
                    "createdAt": iso(e.created_at),
                }
                for e in items
            ],
            "total": total,
        }
    }


def create_experience(
    team_id: str, payload: ExperienceInput, user: User = None, db: Session = None
):
    from ...core.permissions import team_member

    team_member(db, team_id, user)
    experience = Experience(
        team_id=team_id,
        author_id=user.id,
        title=payload.title.strip(),
        starting_point=payload.startingPoint,
        content=payload.content,
    )
    db.add(experience)
    db.commit()
    return {"data": {"id": experience.id}}


def get_experience(experience_id: str, user: User = None, db: Session = None):
    from ...core.presentation import iso
    from ...core.permissions import team_member

    item = db.get(Experience, experience_id)
    if item is None:
        raise HTTPException(404, "经验不存在")
    team_member(db, item.team_id, user)
    return {
        "data": {
            "id": item.id,
            "title": item.title,
            "startingPoint": item.starting_point,
            "content": item.content,
            "author": db.get(User, item.author_id).display_name,
            "createdAt": iso(item.created_at),
        }
    }


def route_for(db, route_id, user, write=False):
    from ...core.permissions import can_manage
    from ...core.permissions import team_member

    route = db.get(Route, route_id)
    if route is None or route.archived:
        raise HTTPException(404, "路线不存在")
    _, member = team_member(db, route.team_id, user)
    if write:
        can_manage(member)
    return route


def filter_materials(db, snapshot, user):
    from ...modules.drive.permissions import resource_visible

    value = deepcopy(snapshot)
    if user:
        for stage in value.get("stages", []):
            stage["resources"] = [
                item
                for item in stage.get("resources", [])
                if (r := db.get(Resource, item.get("id"))) and resource_visible(db, r, user)
            ]
    return value


def route_json(db, route, user=None):
    from ...core.metadata import get_meta
    from ...core.presentation import user_name

    meta = get_meta(db, "route", route.id)
    enrollment = (
        db.scalar(
            select(Enrollment).where(Enrollment.route_id == route.id, Enrollment.user_id == user.id)
        )
        if user
        else None
    )
    return {
        "id": route.id,
        "teamId": route.team_id,
        "title": route.title,
        "description": route.description,
        "authorId": route.author_id,
        "author": user_name(db, route.author_id),
        "version": route.version,
        "direction": meta.get("direction", ""),
        "difficulty": meta.get("difficulty", "入门"),
        "tags": meta.get("tags", []),
        "stages": filter_materials(db, {"stages": route.stages}, user)["stages"],
        "enrolled": enrollment is not None,
        "enrollmentId": enrollment.id if enrollment else None,
    }


def route_stages(db, team_id, stages, user):
    from ...modules.drive.permissions import resource_for
    from ...core.validation import text_value

    if not isinstance(stages, list) or len(stages) > 40:
        raise HTTPException(400, "路线最多包含 40 个阶段")
    result, seen = ([], set())
    for stage in stages:
        if not isinstance(stage, dict):
            raise HTTPException(400, "阶段格式错误")
        sid = str(stage.get("id") or uuid4())
        if sid in seen or len(sid) > 36:
            raise HTTPException(400, "阶段编号重复或过长")
        seen.add(sid)
        resources = []
        for value in stage.get("resources", []):
            rid = value.get("id") if isinstance(value, dict) else value
            resource, _ = resource_for(db, rid, user)
            if resource.team_id != team_id or resource.visibility != "team":
                raise HTTPException(400, "公共路线仅能引用本组共享资料")
            resources.append({"id": resource.id, "title": resource.title})
        task_values = stage.get("tasks", [])
        if not isinstance(task_values, list) or len(task_values) > 100:
            raise HTTPException(400, "每个阶段最多包含 100 个任务")
        tasks = []
        for item in task_values:
            if not isinstance(item, dict):
                raise HTTPException(400, "任务格式错误")
            tasks.append(
                {
                    "id": str(item.get("id") or uuid4()),
                    "title": text_value(item, "title", maximum=200, required=True),
                    "description": text_value(item, "description"),
                    "acceptanceCriteria": text_value(item, "acceptanceCriteria"),
                }
            )
        result.append(
            {
                "id": sid,
                "title": text_value(stage, "title", maximum=200, required=True),
                "description": text_value(stage, "description"),
                "resources": resources,
                "tasks": tasks,
            }
        )
    return result


def route_metadata(payload):
    from ...core.validation import tags
    from ...core.validation import text_value

    return {
        "direction": text_value(payload, "direction", maximum=255),
        "difficulty": text_value(payload, "difficulty", "入门", 60),
        "tags": tags(payload),
    }


def routes(team_id: str, page: int = 1, pageSize: int = 20, user: User = None, db: Session = None):
    from ...core.permissions import team_member
    from ...core.presentation import page_data

    team_member(db, team_id, user)
    rows = db.scalars(
        select(Route).where(Route.team_id == team_id, Route.archived.is_(False)).order_by(Route.id)
    ).all()
    return page_data([route_json(db, row, user) for row in rows], page, pageSize)


def create_route(team_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...core.permissions import can_manage
    from ...core.permissions import team_member
    from ...core.metadata import put_meta
    from ...modules.notifications.service import team_notify
    from ...core.validation import text_value

    _, member = team_member(db, team_id, user)
    can_manage(member)
    row = Route(
        team_id=team_id,
        author_id=user.id,
        title=text_value(payload, "title", maximum=200, required=True),
        description=text_value(payload, "description"),
        stages=route_stages(db, team_id, payload.get("stages", []), user),
    )
    db.add(row)
    db.flush()
    put_meta(db, "route", row.id, route_metadata(payload))
    db.flush()
    db.add(
        RouteVersion(route_id=row.id, version=1, snapshot=route_json(db, row), author_id=user.id)
    )
    team_notify(db, team_id, f"新路线：{row.title}", user.id, "route", row.id)
    db.commit()
    return {"data": route_json(db, row, user)}


def get_route(route_id: str, user: User = None, db: Session = None):
    return {"data": route_json(db, route_for(db, route_id, user), user)}


def edit_route(route_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...core.metadata import get_meta
    from ...core.metadata import put_meta
    from ...core.validation import text_value

    route = route_for(db, route_id, user, True)
    expected = route.version
    if "version" in payload and payload["version"] != expected:
        raise HTTPException(409, "路线已有新版本，请刷新后编辑")
    before = route_json(db, route)
    values = {"version": expected + 1}
    for key in ("title", "description"):
        if key in payload:
            values[key] = text_value(
                payload, key, maximum=200 if key == "title" else 50000, required=key == "title"
            )
    if "stages" in payload:
        values["stages"] = route_stages(db, route.team_id, payload["stages"], user)
    if (
        db.execute(
            update(Route).where(Route.id == route.id, Route.version == expected).values(**values)
        ).rowcount
        != 1
    ):
        raise HTTPException(409, "路线已有新版本，请刷新后编辑")
    if not db.scalar(
        select(RouteVersion.id).where(
            RouteVersion.route_id == route.id, RouteVersion.version == expected
        )
    ):
        db.add(
            RouteVersion(
                route_id=route.id, version=expected, snapshot=before, author_id=route.author_id
            )
        )
    meta = get_meta(db, "route", route.id)
    put_meta(db, "route", route.id, route_metadata({**meta, **payload}))
    db.flush()
    db.refresh(route)
    db.add(
        RouteVersion(
            route_id=route.id,
            version=route.version,
            snapshot=route_json(db, route),
            author_id=user.id,
        )
    )
    db.commit()
    return {"data": route_json(db, route, user)}


def route_versions(route_id: str, user: User = None, db: Session = None):
    from ...core.presentation import iso
    from ...core.presentation import user_name

    route = route_for(db, route_id, user)
    rows = db.scalars(
        select(RouteVersion)
        .where(RouteVersion.route_id == route_id)
        .order_by(RouteVersion.version.desc())
    ).all()
    items = [
        {
            "id": r.id,
            "version": r.version,
            "snapshot": filter_materials(db, r.snapshot, user),
            "author": user_name(db, r.author_id),
            "createdAt": iso(r.created_at),
        }
        for r in rows
    ]
    if not items:
        items = [
            {
                "id": route.id,
                "version": route.version,
                "snapshot": route_json(db, route),
                "author": user_name(db, route.author_id),
                "createdAt": None,
            }
        ]
    return {"data": {"items": items, "total": len(items)}}


def archive_route(route_id: str, user: User = None, db: Session = None):
    route_for(db, route_id, user, True).archived = True
    db.commit()
    return {"data": None}


def enrollment_for(db, enrollment_id, user):
    from ...core.permissions import team_member

    row = db.get(Enrollment, enrollment_id)
    if row is None:
        raise HTTPException(404, "个人计划不存在")
    route = db.get(Route, row.route_id)
    _, member = team_member(db, route.team_id, user)
    if row.user_id != user.id and member.role != "owner":
        raise HTTPException(403, "无权查看该个人计划")
    return (row, route)


def enrollment_json(db, row, user):
    from ...core.metadata import get_meta
    from ...modules.tasks.service import task_json

    route = db.get(Route, row.route_id)
    snapshot = filter_materials(db, row.snapshot or route_json(db, route), user)
    tasks = db.scalars(select(Task).where(Task.enrollment_id == row.id).order_by(Task.id)).all()
    stages, completed = ([], 0)
    for stage in snapshot.get("stages", []):
        members = [
            t
            for t in tasks
            if t.route_stage_id == stage.get("id")
            or (not t.route_stage_id and t.route_stage_title == stage.get("title"))
        ]
        done = bool(members) and all((t.status == "done" for t in members))
        completed += int(done)
        stages.append({**stage, "tasks": [task_json(db, t) for t in members], "completed": done})
    meta = get_meta(db, "enrollment", row.id)
    return {
        "id": row.id,
        "routeId": row.route_id,
        "routeVersion": row.route_version,
        "title": snapshot.get("title", route.title),
        "description": snapshot.get("description", ""),
        "status": row.status,
        "stages": stages,
        "progress": {"completed": completed, "total": len(stages)},
        "note": meta.get("note", ""),
        "targetDate": meta.get("targetDate"),
        "userId": row.user_id,
        "planeSync": (
            "retry_needed"
            if any((t.plane_sync == "retry_needed" for t in tasks))
            else "linked" if any((t.plane_sync == "linked" for t in tasks)) else "not_configured"
        ),
    }


def enroll(route_id: str, user: User = None, db: Session = None, *, services):
    from ...core.metadata import put_meta
    from ...modules.tasks.service import sync_task

    route = route_for(db, route_id, user)
    row = db.scalar(
        select(Enrollment).where(Enrollment.route_id == route_id, Enrollment.user_id == user.id)
    )
    if row is None:
        snapshot = route_json(db, route)
        row = Enrollment(
            route_id=route_id, user_id=user.id, snapshot=snapshot, route_version=route.version
        )
        try:
            db.add(row)
            db.flush()
            reviewer = route.author_id
            if reviewer == user.id:
                other = db.scalar(
                    select(Member).where(
                        Member.team_id == route.team_id,
                        Member.role.in_(("mentor", "owner")),
                        Member.user_id != user.id,
                    )
                )
                if other:
                    reviewer = other.user_id
            for stage in snapshot["stages"]:
                for source in stage.get("tasks", []):
                    task = Task(
                        team_id=route.team_id,
                        title=source["title"],
                        description=source.get("description", ""),
                        acceptance_criteria=source.get("acceptanceCriteria", ""),
                        assignee_id=user.id,
                        reviewer_id=reviewer,
                        enrollment_id=row.id,
                        route_stage_title=stage["title"],
                        route_stage_id=stage.get("id"),
                    )
                    db.add(task)
                    db.flush()
                    put_meta(
                        db,
                        "task",
                        task.id,
                        {"resourceIds": [r["id"] for r in stage.get("resources", [])]},
                    )
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.scalar(
                select(Enrollment).where(
                    Enrollment.route_id == route_id, Enrollment.user_id == user.id
                )
            )
            if row is None:
                raise
    team = db.get(Team, route.team_id)
    tasks = db.scalars(select(Task).where(Task.enrollment_id == row.id)).all()
    for task in tasks:
        if task.plane_sync != "linked":
            sync_task(db, task, team, services=services)
    return {"data": enrollment_json(db, row, user)}


def my_enrollments(teamId: str, user: User = None, db: Session = None):
    from ...core.permissions import team_member

    team_member(db, teamId, user)
    rows = db.scalars(
        select(Enrollment)
        .join(Route)
        .where(Route.team_id == teamId, Enrollment.user_id == user.id)
        .order_by(Enrollment.id)
    ).all()
    return {"data": {"items": [enrollment_json(db, row, user) for row in rows], "total": len(rows)}}


def get_enrollment(enrollment_id: str, user: User = None, db: Session = None):
    row, _ = enrollment_for(db, enrollment_id, user)
    return {"data": enrollment_json(db, row, user)}


def edit_enrollment(
    enrollment_id: str, payload: dict = None, user: User = None, db: Session = None
):
    from ...core.metadata import put_meta
    from ...core.validation import text_value

    row, _ = enrollment_for(db, enrollment_id, user)
    if row.user_id != user.id:
        raise HTTPException(403, "只有计划本人可调整")
    if "status" in payload:
        if payload["status"] not in ("active", "paused"):
            raise HTTPException(400, "计划状态无效")
        row.status = payload["status"]
    changes = {}
    if "note" in payload:
        changes["note"] = text_value(payload, "note")
    if "targetDate" in payload:
        raw = payload["targetDate"]
        try:
            changes["targetDate"] = (
                datetime.strptime(raw, "%Y-%m-%d").date().isoformat() if raw else None
            )
        except (ValueError, TypeError):
            raise HTTPException(400, "目标日期格式应为 YYYY-MM-DD")
    put_meta(db, "enrollment", row.id, changes)
    db.commit()
    return {"data": enrollment_json(db, row, user)}


def plan_task(
    enrollment_id: str, payload: dict = None, user: User = None, db: Session = None, *, services
):
    from ...core.metadata import put_meta
    from ...modules.tasks.service import sync_task
    from ...modules.tasks.service import task_json
    from ...modules.tasks.service import task_metadata
    from ...core.validation import text_value
    from ...modules.tasks.service import validate_assignment

    row, route = enrollment_for(db, enrollment_id, user)
    if row.user_id != user.id:
        raise HTTPException(403, "只有计划本人可添加任务")
    stages = (row.snapshot or route_json(db, route)).get("stages", [])
    stage = next((s for s in stages if s.get("id") == payload.get("stageId")), None)
    if stage is None:
        raise HTTPException(400, "请选择个人计划中的阶段")
    reviewer = payload.get("reviewerId") or route.author_id
    validate_assignment(db, route.team_id, user.id, reviewer)
    task = Task(
        team_id=route.team_id,
        title=text_value(payload, "title", maximum=200, required=True),
        description=text_value(payload, "description"),
        acceptance_criteria=text_value(payload, "acceptanceCriteria"),
        assignee_id=user.id,
        reviewer_id=reviewer,
        enrollment_id=row.id,
        route_stage_id=stage["id"],
        route_stage_title=stage["title"],
    )
    db.add(task)
    db.flush()
    put_meta(db, "task", task.id, task_metadata(payload))
    db.commit()
    sync_task(db, task, db.get(Team, route.team_id), services=services)
    return {"data": task_json(db, task)}


def edit_experience(
    experience_id: str, payload: dict = None, user: User = None, db: Session = None
):
    from ...core.permissions import team_member
    from ...core.metadata import put_meta
    from ...core.validation import tags
    from ...core.validation import text_value

    row = db.get(Experience, experience_id)
    if row is None:
        raise HTTPException(404, "经验不存在")
    _, member = team_member(db, row.team_id, user)
    if row.author_id != user.id and member.role != "owner":
        raise HTTPException(403, "无权编辑")
    row.title = text_value(payload, "title", row.title, 100, True)
    row.starting_point = text_value(payload, "startingPoint", row.starting_point, 3000, True)
    row.content = text_value(payload, "content", row.content, 50000, True)
    put_meta(db, "experience", row.id, {"tags": tags(payload)})
    db.commit()
    return {"data": {"id": row.id}}


def bookmark(experience_id: str, user: User = None, db: Session = None):
    from ...core.permissions import team_member

    row = db.get(Experience, experience_id)
    if row is None:
        raise HTTPException(404, "经验不存在")
    team_member(db, row.team_id, user)
    if not db.scalar(
        select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.experience_id == experience_id)
    ):
        db.add(Bookmark(user_id=user.id, experience_id=experience_id))
        db.commit()
    return {"data": {"experienceId": experience_id}}


def unbookmark(experience_id: str, user: User = None, db: Session = None):
    db.execute(
        delete(Bookmark).where(Bookmark.user_id == user.id, Bookmark.experience_id == experience_id)
    )
    db.commit()
    return {"data": None}


def bookmarks(teamId: str, user: User = None, db: Session = None):
    from ...core.permissions import team_member

    team_member(db, teamId, user)
    rows = db.scalars(
        select(Bookmark)
        .join(Experience, Experience.id == Bookmark.experience_id)
        .where(Bookmark.user_id == user.id, Experience.team_id == teamId)
    ).all()
    return {
        "data": {
            "items": [{"id": r.id, "experienceId": r.experience_id} for r in rows],
            "total": len(rows),
        }
    }
