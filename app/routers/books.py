"""Books router (stub).

The endpoints are implemented by ticket KAN-124 "Implement the books API with
CRUD, search and pagination". This module only registers the agreed prefix and
tags so main.py can include it.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/books", tags=["books"])
