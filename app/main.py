"""FastAPI application entry point for the city library API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.database import Base, engine, get_session
from app.errors import register_exception_handlers
from app.routers import books, loans, members

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "Starting library API against %s (api key %s)",
        settings.library_database_url,
        "generated" if settings.api_key_generated else "from environment",
    )
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ready: %s", ", ".join(sorted(models.Base.metadata.tables)))
    yield


app = FastAPI(title="City Library API", version="1.0.0", lifespan=lifespan)

register_exception_handlers(app)

app.include_router(books.router)
app.include_router(members.router)
app.include_router(loans.router)


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, str]:
    """Report service health after checking the database connection."""

    session.execute(text("SELECT 1"))
    return {"status": "ok"}
