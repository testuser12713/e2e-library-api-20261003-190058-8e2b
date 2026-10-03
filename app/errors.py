"""Unified error handling for the library API.

Every failure — a raised :class:`APIError`, a plain ``HTTPException``, a
Pydantic request-validation failure or a database integrity error — is rendered
as ``{"error": {"code", "message", "details"}}`` with an appropriate status
code. No bare FastAPI ``detail`` object ever reaches a client.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    500: "internal_error",
}


class APIError(StarletteHTTPException):
    """An :class:`HTTPException` carrying the unified error fields."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details


def error_body(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    """Build the unified error body."""

    return {"error": {"code": code, "message": message, "details": details}}


def raise_api_error(
    status: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> None:
    """Raise an error that the API renders in the unified body shape."""

    raise APIError(status_code=status, code=code, message=message, details=details)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    details = getattr(exc, "details", None)

    if message is None:
        if isinstance(exc.detail, str):
            message = exc.detail
        elif isinstance(exc.detail, dict):
            code = code or exc.detail.get("code")
            message = exc.detail.get("message", "Error")
            if details is None:
                details = exc.detail.get("details")
        else:
            message = "Error"

    if code is None:
        code = _STATUS_CODES.get(exc.status_code, "error")

    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, str(message), details),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "Request validation failed",
            jsonable_encoder(exc.errors()),
        ),
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Database integrity error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=409,
        content=error_body("conflict", "The request conflicts with existing data", None),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "Internal Server Error", None),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the unified handlers to a FastAPI application."""

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
