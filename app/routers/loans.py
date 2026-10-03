"""Loans router: creation, listing, lookup and return.

All business rules live in :mod:`app.services.loans`; this module only maps
HTTP requests onto the service layer and shapes the paginated response
envelopes. Both write endpoints require the ``X-API-Key`` header.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Loan
from app.schemas import LoanCreate, LoanPage, LoanRead
from app.security import require_api_key
from app.services import loans as service

router = APIRouter(prefix="/loans", tags=["loans"])

LoanStatus = Literal["open", "returned"]


def _page(items: list[Loan], total: int, limit: int, offset: int) -> LoanPage:
    return LoanPage(
        items=[LoanRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=201, response_model=LoanRead, dependencies=[Depends(require_api_key)])
def create_loan(payload: LoanCreate, session: Session = Depends(get_session)) -> Loan:
    """Create a loan, enforcing the member limit and copy availability."""

    return service.create_loan(session, payload)


@router.get("", response_model=LoanPage)
def list_loans(
    member_id: int | None = Query(default=None),
    book_id: int | None = Query(default=None),
    status: LoanStatus | None = Query(default=None),
    limit: int = Query(default=service.DEFAULT_LIMIT),
    offset: int = Query(default=0),
    session: Session = Depends(get_session),
) -> LoanPage:
    """List loans, optionally filtered by member, book and status."""

    items, total, limit, offset = service.list_loans(
        session,
        member_id=member_id,
        book_id=book_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return _page(items, total, limit, offset)


@router.get("/overdue", response_model=LoanPage)
def list_overdue(
    limit: int = Query(default=service.DEFAULT_LIMIT),
    offset: int = Query(default=0),
    session: Session = Depends(get_session),
) -> LoanPage:
    """List the open loans whose due date has already passed."""

    items, total, limit, offset = service.list_overdue(session, limit=limit, offset=offset)
    return _page(items, total, limit, offset)


@router.get("/{loan_id}", response_model=LoanRead)
def get_loan(loan_id: int, session: Session = Depends(get_session)) -> Loan:
    """Read a single loan."""

    return service.get_loan(session, loan_id)


@router.post(
    "/{loan_id}/return",
    response_model=LoanRead,
    dependencies=[Depends(require_api_key)],
)
def return_loan(loan_id: int, session: Session = Depends(get_session)) -> Loan:
    """Close an open loan and free its copy."""

    return service.return_loan(session, loan_id)
