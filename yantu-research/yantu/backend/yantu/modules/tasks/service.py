"""modules.tasks.service business operations."""

from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import update
from urllib.parse import urlparse
from uuid import uuid4
from ...core.models import Meeting, Member, Resource, Review, Submission, Task, Team, User
from ...integrations.plane import PlaneError


def task_summary(db: Session, task: Task) -> dict:
    reviewer = db.get(User, task.reviewer_id)
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "reviewer": reviewer.display_name if reviewer else "—",
    }


def team_review_queue(team_id: str, user: User = None, db: Session = None):
    from ...core.permissions import can_manage
    from ...core.permissions import team_member

    _, membership = team_member(db, team_id, user)
    can_manage(membership)
    clause = [Task.team_id == team_id, Task.status == "review"]
    if membership.role != "owner":
        clause.append(Task.reviewer_id == user.id)
    items = db.scalars(select(Task).where(*clause).order_by(Task.id.desc()).limit(100)).all()
    return {"data": {"items": [task_summary(db, t) for t in items], "total": len(items)}}


def plane_tasks(team_id: str, user: User = None, db: Session = None, *, services):
    from ...core.permissions import team_member

    team, _ = team_member(db, team_id, user)
    try:
        raw = services.plane.list_work_items(team)
    except PlaneError as exc:
        raise HTTPException(502, str(exc)) from exc
    items = []
    for item in raw.get("results", []):
        state = item.get("state")
        items.append(
            {
                "id": item.get("id"),
                "title": item.get("name", ""),
                "status": state.get("name", "—") if isinstance(state, dict) else "—",
                "reviewer": "—",
            }
        )
    return {"data": {"items": items, "total": raw.get("total_results", len(items))}}


def task_visible(task, membership, user):
    return task.assignee_id == user.id or task.reviewer_id == user.id or membership.role == "owner"


def task_json(db, task):
    from ...core.metadata import get_meta
    from ...core.presentation import user_name

    info = get_meta(db, "task", task.id)
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "description": task.description,
        "acceptanceCriteria": task.acceptance_criteria,
        "assigneeId": task.assignee_id,
        "assignee": user_name(db, task.assignee_id),
        "reviewerId": task.reviewer_id,
        "reviewer": user_name(db, task.reviewer_id),
        "blocker": task.blocker,
        "meetingId": task.meeting_id,
        "enrollmentId": task.enrollment_id,
        "stageId": task.route_stage_id,
        "stageTitle": task.route_stage_title,
        "revision": task.revision,
        "latestSubmissionId": task.latest_submission_id,
        "planeSync": task.plane_sync,
        "planeWorkItemId": task.plane_work_item_id,
        "dueAt": info.get("dueAt"),
        "priority": info.get("priority", "normal"),
    }


def sync_task(db, task, team, comment=None, *, services):
    from ...core.metadata import get_meta

    if not services.plane.configured(team):
        task.plane_sync = "not_configured"
        db.commit()
        return
    try:
        if not task.plane_work_item_id:
            task.plane_work_item_id = services.plane.create_work_item(
                team, task.title, task.description, external_id=task.id
            )
        elif hasattr(services.plane, "update_work_item"):
            meta = get_meta(db, "task", task.id)
            services.plane.update_work_item(
                team,
                task.plane_work_item_id,
                task.title,
                task.description,
                task.status,
                priority=meta.get("priority", "none"),
                due_at=meta.get("dueAt"),
            )
        if comment and task.plane_work_item_id:
            services.plane.add_comment(team, task.plane_work_item_id, comment)
        task.plane_sync = "linked" if task.plane_work_item_id else "retry_needed"
    except PlaneError:
        task.plane_sync = "retry_needed"
    db.commit()


def validate_assignment(db, team_id, assignee_id, reviewer_id):
    members = {
        m.user_id: m for m in db.scalars(select(Member).where(Member.team_id == team_id)).all()
    }
    if (
        assignee_id not in members
        or reviewer_id not in members
        or members[reviewer_id].role not in ("mentor", "owner")
    ):
        raise HTTPException(400, "执行人与审核人须在本组，审核人须为前辈或负责人")
    if assignee_id == reviewer_id:
        raise HTTPException(400, "执行人与审核人不能相同")


def task_metadata(payload):
    from ...core.presentation import iso
    from ...core.validation import timestamp

    priority = payload.get("priority", "normal")
    if priority not in ("none", "low", "normal", "medium", "high", "urgent"):
        raise HTTPException(400, "优先级无效")
    return {"priority": priority, "dueAt": iso(timestamp(payload.get("dueAt")))}


def create_task(
    team_id: str, payload: dict = None, user: User = None, db: Session = None, *, services
):
    from ...core.permissions import can_manage
    from ...core.permissions import team_member
    from ...modules.notifications.service import notify
    from ...core.metadata import put_meta
    from ...core.validation import text_value

    team, member = team_member(db, team_id, user)
    can_manage(member)
    validate_assignment(db, team_id, payload.get("assigneeId"), payload.get("reviewerId"))
    meeting_id = payload.get("meetingId") or None
    if meeting_id:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or meeting.team_id != team_id or meeting.status == "archived":
            raise HTTPException(400, "组会不属于本组或已归档")
    task = Task(
        team_id=team_id,
        title=text_value(payload, "title", maximum=200, required=True),
        description=text_value(payload, "description"),
        acceptance_criteria=text_value(payload, "acceptanceCriteria"),
        assignee_id=payload["assigneeId"],
        reviewer_id=payload["reviewerId"],
        meeting_id=meeting_id,
    )
    db.add(task)
    db.flush()
    put_meta(db, "task", task.id, task_metadata(payload))
    notify(db, task.assignee_id, f"新任务：{task.title}", team_id, "task", task.id)
    db.commit()
    sync_task(db, task, team, services=services)
    return {"data": task_json(db, task)}


def my_tasks(
    teamId: str,
    status: str | None = None,
    page: int = 1,
    pageSize: int = 20,
    user: User = None,
    db: Session = None,
):
    from ...core.permissions import team_member
    from ...core.presentation import page_data

    team_member(db, teamId, user)
    query = select(Task).where(Task.team_id == teamId, Task.assignee_id == user.id)
    if status:
        query = query.where(Task.status == status)
    return page_data(
        [task_json(db, t) for t in db.scalars(query.order_by(Task.id)).all()], page, pageSize
    )


def team_tasks(
    team_id: str,
    status: str | None = None,
    page: int = 1,
    pageSize: int = 20,
    user: User = None,
    db: Session = None,
):
    from ...core.permissions import team_member
    from ...core.presentation import page_data

    _, member = team_member(db, team_id, user)
    rows = db.scalars(select(Task).where(Task.team_id == team_id).order_by(Task.id)).all()
    return page_data(
        [
            task_json(db, t)
            for t in rows
            if task_visible(t, member, user) and (not status or t.status == status)
        ],
        page,
        pageSize,
    )


def review_queue(
    teamId: str, page: int = 1, pageSize: int = 20, user: User = None, db: Session = None
):
    from ...core.permissions import can_manage
    from ...core.permissions import team_member
    from ...core.presentation import page_data

    _, member = team_member(db, teamId, user)
    can_manage(member)
    rows = db.scalars(
        select(Task).where(
            Task.team_id == teamId, Task.status == "review", Task.assignee_id != user.id
        )
    ).all()
    return page_data(
        [task_json(db, t) for t in rows if t.reviewer_id == user.id or member.role == "owner"],
        page,
        pageSize,
    )


def task_detail(db, task, user):
    from ...core.presentation import iso
    from ...modules.drive.permissions import resource_visible
    from ...core.metadata import get_meta
    from ...core.presentation import user_name
    from ...modules.drive.service import referenced_resources
    from ...modules.drive.service import resource_json

    submissions = db.scalars(
        select(Submission)
        .where(Submission.task_id == task.id)
        .order_by(Submission.created_at.desc(), Submission.id)
    ).all()
    resource_ids = get_meta(db, "task", task.id).get("resourceIds", [])
    resources = db.scalars(
        select(Resource).where(or_(Resource.task_id == task.id, Resource.id.in_(resource_ids)))
    ).all()
    resources = list(
        {r.id: r for r in resources + referenced_resources(db, "task", task.id)}.values()
    )
    return {
        **task_json(db, task),
        "resources": [
            resource_json(db, r, user) for r in resources if resource_visible(db, r, user)
        ],
        "submissions": [
            {
                "id": s.id,
                "summary": s.summary,
                "url": s.url,
                "createdAt": iso(s.created_at),
                "userId": s.user_id,
                "reviews": [
                    {
                        "id": r.id,
                        "decision": r.decision,
                        "comment": r.comment,
                        "reviewer": user_name(db, r.reviewer_id),
                        "createdAt": iso(r.created_at),
                    }
                    for r in db.scalars(
                        select(Review)
                        .where(Review.submission_id == s.id)
                        .order_by(Review.created_at)
                    ).all()
                ],
            }
            for s in submissions
        ],
    }


def get_task(task_id: str, user: User = None, db: Session = None):
    from ...core.permissions import task_for

    task, _, _ = task_for(db, task_id, user)
    return {"data": task_detail(db, task, user)}


def edit_task(
    task_id: str, payload: dict = None, user: User = None, db: Session = None, *, services
):
    from ...core.permissions import can_manage
    from ...core.permissions import task_for
    from ...core.metadata import get_meta
    from ...core.metadata import put_meta
    from ...core.validation import text_value

    task, _, member = task_for(db, task_id, user)
    expected = task.revision
    if "revision" in payload and payload["revision"] != expected:
        raise HTTPException(409, "任务已更新，请刷新")
    values = {"revision": expected + 1}
    if "status" in payload:
        if payload["status"] not in ("todo", "doing", "blocked"):
            raise HTTPException(400, "完成状态必须通过成果审核变更")
        if task.status in ("review", "done"):
            raise HTTPException(409, "待审或已完成任务不可直接修改状态")
        values["status"] = payload["status"]
    if "blocker" in payload:
        values["blocker"] = text_value(payload, "blocker")
    management_fields = {
        "title",
        "description",
        "acceptanceCriteria",
        "reviewerId",
        "dueAt",
        "priority",
    } & payload.keys()
    if management_fields:
        can_manage(member)
        if task.status in ("review", "done"):
            raise HTTPException(409, "待审或已完成任务的验收要求不可修改")
        for key, column in (
            ("title", "title"),
            ("description", "description"),
            ("acceptanceCriteria", "acceptance_criteria"),
        ):
            if key in payload:
                values[column] = text_value(
                    payload, key, maximum=200 if key == "title" else 50000, required=key == "title"
                )
        if "reviewerId" in payload:
            validate_assignment(db, task.team_id, task.assignee_id, payload["reviewerId"])
            values["reviewer_id"] = payload["reviewerId"]
    if (
        db.execute(
            update(Task).where(Task.id == task.id, Task.revision == expected).values(**values)
        ).rowcount
        != 1
    ):
        raise HTTPException(409, "任务已更新，请刷新")
    if management_fields:
        put_meta(db, "task", task.id, task_metadata({**get_meta(db, "task", task.id), **payload}))
    db.commit()
    db.refresh(task)
    sync_task(db, task, db.get(Team, task.team_id), services=services)
    return {"data": task_json(db, task)}


def submit_task(
    task_id: str, payload: dict = None, user: User = None, db: Session = None, *, services
):
    from ...core.permissions import task_for
    from ...modules.notifications.service import notify
    from ...core.validation import text_value

    task, _, _ = task_for(db, task_id, user)
    if task.assignee_id != user.id:
        raise HTTPException(403, "只有任务执行人可以提交")
    summary = text_value(payload, "summary", required=True)
    url = text_value(payload, "url", maximum=2048)
    if url and (urlparse(url).scheme not in ("https", "http") or not urlparse(url).netloc):
        raise HTTPException(400, "成果链接必须是有效的 HTTP(S) 地址")
    ident = str(uuid4())
    result = db.execute(
        update(Task)
        .where(
            Task.id == task.id,
            Task.revision == task.revision,
            Task.status.in_(("todo", "doing", "blocked")),
        )
        .values(status="review", blocker="", latest_submission_id=ident, revision=Task.revision + 1)
    )
    if result.rowcount != 1:
        raise HTTPException(409, "已有待审提交或任务已完成，请刷新")
    db.add(Submission(id=ident, task_id=task.id, user_id=user.id, summary=summary, url=url))
    notify(db, task.reviewer_id, f"待审核：{task.title}", task.team_id, "task", task.id)
    db.commit()
    db.refresh(task)
    sync_task(
        db, task, db.get(Team, task.team_id), f"提交成果：{summary}\n{url}", services=services
    )
    return {"data": {"id": ident, "taskStatus": "review"}}


def review_submission(
    submission_id: str, payload: dict = None, user: User = None, db: Session = None, *, services
):
    from ...core.permissions import can_manage
    from ...core.permissions import task_for
    from ...modules.notifications.service import notify
    from ...core.validation import text_value

    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(404, "成果提交不存在")
    task, _, member = task_for(db, submission.task_id, user)
    can_manage(member)
    if (
        user.id == submission.user_id
        or user.id == task.assignee_id
        or (task.reviewer_id != user.id and member.role != "owner")
    ):
        raise HTTPException(403, "只能由独立审核人或负责人审批，禁止自审")
    decision = payload.get("decision")
    if decision not in ("approved", "changes_requested"):
        raise HTTPException(400, "审批决定无效")
    comment = text_value(payload, "comment", required=True)
    latest = task.latest_submission_id
    if not latest:
        latest = db.scalar(
            select(Submission.id)
            .where(Submission.task_id == task.id)
            .order_by(Submission.created_at.desc(), Submission.id.desc())
            .limit(1)
        )
    if latest != submission_id:
        raise HTTPException(409, "只能审批最新提交")
    state = "done" if decision == "approved" else "doing"
    result = db.execute(
        update(Task)
        .where(
            Task.id == task.id,
            Task.revision == task.revision,
            Task.status == "review",
            Task.latest_submission_id == task.latest_submission_id,
        )
        .values(status=state, revision=Task.revision + 1)
    )
    if result.rowcount != 1 or db.scalar(
        select(Review.id).where(Review.submission_id == submission_id)
    ):
        raise HTTPException(409, "该成果已被审批，请刷新")
    review = Review(
        submission_id=submission_id, reviewer_id=user.id, comment=comment, decision=decision
    )
    db.add(review)
    notify(
        db,
        task.assignee_id,
        f"{('审核通过' if state == 'done' else '需要修改')}：{task.title}",
        task.team_id,
        "task",
        task.id,
    )
    db.commit()
    db.refresh(task)
    sync_task(db, task, db.get(Team, task.team_id), f"{decision}：{comment}", services=services)
    return {"data": {"id": review.id, "taskStatus": state}}
