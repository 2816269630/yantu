"""Application error responses and same-origin mutation policy."""

import os
from urllib.parse import urlparse
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


def register_errors(app):
    @app.exception_handler(HTTPException)
    async def http_error(_request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": "REQUEST_FAILED", "message": str(exc.detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _exc):
        return JSONResponse(
            status_code=400, content={"code": "INVALID_INPUT", "message": "输入字段格式不正确"}
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request, _error):
        return JSONResponse(
            status_code=409,
            content={"code": "CONFLICT", "message": "记录已存在或状态已变化，请刷新后重试"},
        )

    @app.middleware("http")
    async def same_origin_mutations(request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            allowed_origin = os.getenv("APP_ORIGIN", "").rstrip("/")
            if (
                urlparse(origin).netloc != request.headers.get("host")
                and origin.rstrip("/") != allowed_origin
            ):
                return JSONResponse(
                    status_code=403, content={"code": "FORBIDDEN", "message": "不允许跨站写入"}
                )
        return await call_next(request)
