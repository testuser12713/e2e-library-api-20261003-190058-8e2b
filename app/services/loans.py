"""Business logic for loans: lending rules, returns and overdue evaluation.

The router stays thin; every rule lives here:

* a member may hold at most :data:`MAX_OPEN_LOANS_PER_MEMBER` open loans;
* a book is lendable only while its open loans are fewer than its copies;
* ``due_at`` is exactly :data:`LOAN_PERIOD_DAYS` days after ``lent_at``;
* returning a loan stamps ``returned_at`` and frees the copy.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import raise_api_error
from app.models import Book, Loan, Member
from app.schemas import LoanCreate

LOAN_PERIOD_DAYS = 14
MAX_OPEN_LOANS_PER_MEMBER = 3

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def normalize_pagination(limit: int, offset: int) -> tuple[int, int]:
    """Clamp ``limit`` to ``1..MAX_LIMIT`` and ``offset`` to at least 0."""

    return min(max(limit, 1), MAX_LIMIT), max(offset, 0)


def _open_loan_filter(*columns: object) -> list:
    conditions = [Loan.returned_at.is_(None)]
    conditions.extend(columns)
    return conditions


def create_loan(session: Session, payload: LoanCreate) -> Loan:
    """Create a loan after enforcing existence and both lending rules.

    Raises ``404 not_found`` for an unknown book or member, ``409
    loan_limit_reached`` when the member already holds the maximum number of
    open loans, and ``409 no_copy_available`` when every copy of the book is on
    loan. Nothing is written unless all checks pass.
    """

    member = session.get(Member, payload.member_id)
    if member is None:
        raise_api_error(404, "not_found", f"Member {payload.member_id} not found")

    book = session.get(Book, payload.book_id)
    if book is None:
        raise_api_error(404, "not_found", f"Book {payload.book_id} not found")

    member_open = session.scalar(
        select(func.count(Loan.id)).where(*_open_loan_filter(Loan.member_id == member.id))
    )
    if (member_open or 0) >= MAX_OPEN_LOANS_PER_MEMBER:
        raise_api_error(
            409,
            "loan_limit_reached",
            f"Member {member.id} already holds {MAX_OPEN_LOANS_PER_MEMBER} open loans",
        )

    book_open = session.scalar(
        select(func.count(Loan.id)).where(*_open_loan_filter(Loan.book_id == book.id))
    )
    if (book_open or 0) >= book.copies:
        raise_api_error(
            409,
            "no_copy_available",
            f"No copy of book {book.id} is available",
        )

    today = date.today()
    loan = Loan(
        book_id=book.id,
        member_id=member.id,
        lent_at=today,
        due_at=today + timedelta(days=LOAN_PERIOD_DAYS),
        returned_at=None,
    )
    session.add(loan)
    session.commit()
    session.refresh(loan)
    return loan


def get_loan(session: Session, loan_id: int) -> Loan:
    """Return a loan or raise ``404 not_found``."""

    loan = session.get(Loan, loan_id)
    if loan is None:
        raise_api_error(404, "not_found", f"Loan {loan_id} not found")
    return loan


def return_loan(session: Session, loan_id: int) -> Loan:
    """Stamp ``returned_at`` on an open loan, freeing its copy.

    An unknown id raises ``404 not_found``; a loan that is already returned
    raises ``409 loan_already_returned``.
    """

    loan = get_loan(session, loan_id)
    if loan.returned_at is not None:
        raise_api_error(409, "loan_already_returned", f"Loan {loan_id} is already returned")

    loan.returned_at = date.today()
    session.commit()
    session.refresh(loan)
    return loan


def _apply_filters(stmt, member_id: int | None, book_id: int | None, status: str | None):
    if member_id is not None:
        stmt = stmt.where(Loan.member_id == member_id)
    if book_id is not None:
        stmt = stmt.where(Loan.book_id == book_id)
    if status == "open":
        stmt = stmt.where(Loan.returned_at.is_(None))
    elif status == "returned":
        stmt = stmt.where(Loan.returned_at.isnot(None))
    return stmt


def list_loans(
    session: Session,
    *,
    member_id: int | None = None,
    book_id: int | None = None,
    status: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[Loan], int, int, int]:
    """Return ``(items, total, limit, offset)`` for the filtered loan list."""

    limit, offset = normalize_pagination(limit, offset)

    count_stmt = _apply_filters(select(func.count(Loan.id)), member_id, book_id, status)
    total = session.scalar(count_stmt) or 0

    stmt = _apply_filters(select(Loan), member_id, book_id, status)
    items = list(
        session.scalars(stmt.order_by(Loan.id).limit(limit).offset(offset)).all(),
    )
    return items, total, limit, offset


def list_overdue(
    session: Session,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[Loan], int, int, int]:
    """Return the open loans whose ``due_at`` lies before today."""

    limit, offset = normalize_pagination(limit, offset)
    today = date.today()

    condition = _open_loan_filter(Loan.due_at < today)
    count_stmt = select(func.count(Loan.id)).where(*condition)
    total = session.scalar(count_stmt) or 0

    stmt = select(Loan).where(*condition).order_by(Loan.id).limit(limit).offset(offset)
    items = list(session.scalars(stmt).all())
    return items, total, limit, offset
