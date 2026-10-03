"""Tests for the running skeleton delivered by ticket KAN-123.

These cover only what the skeleton itself promises: startup, the health check,
the OpenAPI page, schema creation and the unified error body. Routes owned by
other tickets (books, members, loans) are deliberately not asserted here.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.config import Settings
from app.errors import APIError, register_exception_handlers
from app.security import require_api_key


def test_health_after_startup(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_documentation_is_served(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "City Library API"


def test_tables_are_created(engine: Engine) -> None:
    names = set(inspect(engine).get_table_names())
    assert {"books", "members", "loans"} <= names


def test_unknown_path_returns_unified_error_body(client: TestClient) -> None:
    response = client.get("/definitely-not-a-route")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "not_found"


def test_validation_error_returns_unified_error_body() -> None:
    class Payload(BaseModel):
        value: int

    probe = FastAPI()
    register_exception_handlers(probe)

    @probe.post("/echo")
    def echo(payload: Payload) -> Payload:
        return payload

    with TestClient(probe) as client:
        response = client.post("/echo", json={"value": "not-an-int"})

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "validation_error"


def test_require_api_key_accepts_the_configured_key(api_key: str) -> None:
    settings = Settings(library_database_url="sqlite://", library_api_key=api_key)
    assert require_api_key(x_api_key=api_key, settings=settings) == api_key


def test_require_api_key_rejects_missing_or_wrong_key(api_key: str) -> None:
    settings = Settings(library_database_url="sqlite://", library_api_key=api_key)

    for supplied in (None, "wrong-key"):
        with pytest.raises(APIError) as exc_info:
            require_api_key(x_api_key=supplied, settings=settings)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"
