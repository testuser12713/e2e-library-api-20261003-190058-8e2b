"""Members router (stub).

The endpoints are implemented by ticket #3 "Implement the members API with CRUD
and pagination". This module only registers the agreed prefix and tags so
main.py can include it.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/members", tags=["members"])
