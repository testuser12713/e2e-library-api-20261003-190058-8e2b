"""Database engine, declarative base and session dependency.

SQLAlchemy 2.0 style: a shared :class:`Base` every model inherits from, a
module-level engine built from the configured database URL, a session factory
and the ``get_session`` FastAPI dependency.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

_connect_args = (
    {"check_same_thread": False} if settings.library_database_url.startswith("sqlite") else {}
)

engine = create_engine(settings.library_database_url, connect_args=_connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    """Declarative base for every ORM model of the library API."""


def get_session() -> Generator[Session]:
    """Yield a database session, closing it when the request is done."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
