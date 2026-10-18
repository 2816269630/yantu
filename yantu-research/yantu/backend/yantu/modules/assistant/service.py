"""modules.assistant.service business operations."""

from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.orm import Session
from ...core.models import User
from ...integrations.ollama import AssistantUnavailable


def questions(
    payload: dict = None, team_id: str = "", user: User = None, db: Session = None, *, services
):
    from ...core.permissions import team_member
    from ...modules.drive.service import available_rows
    from ...modules.drive.permissions import resource_for
    from ...core.presentation import result
    from ...core.validation import text_value

    if team_id:
        team_member(db, team_id, user)
    question = text_value(payload, "question", required=True, maximum=500)
    ids = payload.get("resourceIds", [])
    if not isinstance(ids, list) or len(ids) > 100 or any((not isinstance(x, str) for x in ids)):
        raise HTTPException(400, "最多选择 100 份资料")
    if ids:
        rows = [resource_for(db, rid, user)[0] for rid in dict.fromkeys(ids)]
        if team_id and any((r.team_id != team_id for r in rows)):
            raise HTTPException(404, "资料不属于当前课题组")
    else:
        rows = available_rows(db, user, "all", "")
        if team_id:
            rows = [r for r in rows if r.team_id == team_id]
    rows = [r for r in rows if r.extracted_text]
    if len(rows) > 100:
        raise HTTPException(400, "可检索资料超过 100 份，请明确选择本次使用的文件")
    try:
        return result(services.assistant.answer(question, rows))
    except AssistantUnavailable as error:
        raise HTTPException(503, str(error)) from error
