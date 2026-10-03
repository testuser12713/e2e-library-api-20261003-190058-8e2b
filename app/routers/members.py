"""Members endpoints: CRUD behind the API-key guard, public reads.

All business logic lives in :mod:`app.services.members`; this module only wires
HTTP paths, request bodies and the shared pagination envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas import MemberCreate, MemberPage, MemberRead, MemberUpdate
from app.security import require_api_key
from app.services import members as member_service

router = APIRouter(prefix="/members", tags=["members"])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _page_params(
    limit: int = Query(default=DEFAULT_LIMIT, description="Maximum number of items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
) -> tuple[int, int]:
    """Clamp the pagination query parameters to the agreed bounds."""

    clamped_limit = max(1, min(limit, MAX_LIMIT))
    return clamped_limit, offset


@router.post(
    "",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_member(payload: MemberCreate, session: Session = Depends(get_session)) -> MemberRead:
    """Create a member and return the stored resource."""

    return member_service.create_member(session, payload)


@router.get("", response_model=MemberPage)
def list_members(
    session: Session = Depends(get_session),
    page: tuple[int, int] = Depends(_page_params),
) -> MemberPage:
    """Return a page of members in the shared envelope."""

    limit, offset = page
    items, total = member_service.list_members(session, limit=limit, offset=offset)
    return MemberPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{member_id}", response_model=MemberRead)
def get_member(member_id: int, session: Session = Depends(get_session)) -> MemberRead:
    """Return a single member or ``404`` when the id is unknown."""

    return member_service.get_member(session, member_id)


@router.put(
    "/{member_id}",
    response_model=MemberRead,
    dependencies=[Depends(require_api_key)],
)
def replace_member(
    member_id: int,
    payload: MemberUpdate,
    session: Session = Depends(get_session),
) -> MemberRead:
    """Update the supplied member fields."""

    return member_service.update_member(session, member_id, payload)


@router.patch(
    "/{member_id}",
    response_model=MemberRead,
    dependencies=[Depends(require_api_key)],
)
def update_member(
    member_id: int,
    payload: MemberUpdate,
    session: Session = Depends(get_session),
) -> MemberRead:
    """Partially update the supplied member fields."""

    return member_service.update_member(session, member_id, payload)


@router.delete(
    "/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_api_key)],
)
def delete_member(member_id: int, session: Session = Depends(get_session)) -> Response:
    """Delete a member and answer ``204``."""

    member_service.delete_member(session, member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
