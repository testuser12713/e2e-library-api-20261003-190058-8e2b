"""Loans router (stub).

The endpoints are implemented by ticket #4 "Implement the loans API with
lending rules, returns and overdue list". This module only registers the agreed
prefix and tags so main.py can include it.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/loans", tags=["loans"])
