"""Application configuration.

Configuration is read lazily: importing this module never touches the
environment and never fails. ``get_settings()`` is the single access point and
is cached, so the generated API key stays stable for the lifetime of a process.

If ``LIBRARY_API_KEY`` is not set, a random key is generated, persisted to a
runtime file next to the application and its path is logged. The application
therefore boots with no pre-configuration at all.
"""

from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

DATABASE_URL_ENV = "LIBRARY_DATABASE_URL"
API_KEY_ENV = "LIBRARY_API_KEY"
API_KEY_FILE_ENV = "LIBRARY_API_KEY_FILE"

# A working development default so a freshly cloned repository starts without
# anybody creating a database first. The generated API key file ends in
# ``.local`` so the repository's ignore rules keep it out of version control.
DEFAULT_DATABASE_URL = "sqlite:///./library.db"
DEFAULT_API_KEY_FILE = "library_api_key.local"


class Settings(BaseModel):
    """Resolved runtime configuration."""

    library_database_url: str
    library_api_key: str
    api_key_generated: bool = False
    api_key_file: str | None = None


def _load_existing_key(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _persist_key(path: Path, key: str) -> bool:
    try:
        path.write_text(key, encoding="utf-8")
    except OSError as exc:  # pragma: no cover - depends on the filesystem
        logger.warning("Could not persist generated API key to %s: %s", path, exc)
        return False
    return True


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings, generating an API key when none is set."""

    database_url = os.environ.get(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)

    env_key = os.environ.get(API_KEY_ENV)
    if env_key:
        return Settings(library_database_url=database_url, library_api_key=env_key)

    key_file = Path(os.environ.get(API_KEY_FILE_ENV, DEFAULT_API_KEY_FILE))

    existing = _load_existing_key(key_file)
    if existing:
        logger.warning(
            "%s is not set; reusing the runtime API key stored at %s",
            API_KEY_ENV,
            key_file.resolve(),
        )
        return Settings(
            library_database_url=database_url,
            library_api_key=existing,
            api_key_file=str(key_file),
        )

    generated_key = secrets.token_urlsafe(32)
    persisted = _persist_key(key_file, generated_key)
    if persisted:
        logger.warning(
            "%s is not set; generated a runtime API key and stored it at %s",
            API_KEY_ENV,
            key_file.resolve(),
        )
    else:
        logger.warning(
            "%s is not set; generated an in-memory API key for this run only",
            API_KEY_ENV,
        )
    return Settings(
        library_database_url=database_url,
        library_api_key=generated_key,
        api_key_generated=True,
        api_key_file=str(key_file) if persisted else None,
    )
