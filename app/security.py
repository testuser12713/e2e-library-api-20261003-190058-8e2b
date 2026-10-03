"""Static API-key authentication for the write endpoints.

Read endpoints are public; every write endpoint depends on :func:`require_api_key`
and is rejected with ``401 unauthorized`` in the unified error body when the
``X-API-Key`` header is missing or wrong.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header

from app.config import Settings, get_settings
from app.errors import raise_api_error


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate the ``X-API-Key`` header against the configured key."""

    if not x_api_key or not hmac.compare_digest(x_api_key, settings.library_api_key):
        raise_api_error(401, "unauthorized", "Missing or invalid API key")
    return x_api_key
