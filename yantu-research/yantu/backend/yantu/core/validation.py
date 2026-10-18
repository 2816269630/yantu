"""core.validation business operations."""

from __future__ import annotations
from fastapi import HTTPException
from datetime import datetime
from datetime import timezone


def text_value(payload, key, default="", maximum=50000, required=False):
    value = payload.get(key, default)
    if not isinstance(value, str) or len(value) > maximum or (required and (not value.strip())):
        raise HTTPException(400, f"{key} 不能为空或超过长度限制")
    return value.strip()


def timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise HTTPException(400, "时间必须包含时区")


def tags(payload):
    value = payload.get("tags", [])
    if isinstance(value, str):
        value = [x.strip() for x in value.split(",") if x.strip()]
    if (
        not isinstance(value, list)
        or len(value) > 30
        or any((not isinstance(x, str) or len(x) > 60 for x in value))
    ):
        raise HTTPException(400, "标签格式错误")
    return list(dict.fromkeys(value))
