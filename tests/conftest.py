"""Shared pytest fixtures for the library API test suite.

Every test runs against its own isolated in-memory SQLite database with the
schema created per test. Configuration is overridden so the API key is known and
no runtime key file is generated during the test run.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

TEST_API_KEY = "test-api-key"


def pytest_configure(config: pytest.Config) -> None:
    os.environ.setdefault("LIBRARY_DATABASE_URL", "sqlite://")
    os.environ.setdefault("LIBRARY_API_KEY", TEST_API_KEY)


@pytest.fixture()
def api_key() -> str:
    return TEST_API_KEY


@pytest.fixture()
def engine() -> Generator[Engine]:
    from app import models

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        models.Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(engine: Engine, api_key: str) -> Generator[TestClient]:
    from app.config import Settings, get_settings
    from app.database import get_session
    from app.main import app

    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_session() -> Generator:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    test_settings = Settings(library_database_url="sqlite://", library_api_key=api_key)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
