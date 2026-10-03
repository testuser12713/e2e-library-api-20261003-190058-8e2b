"""Persistence logic for the books resource.

The router stays thin and delegates every decision to this module: uniqueness of
the ISBN, pagination clamping into the shared envelope, filtering by a
case-insensitive substring of the title or author, and the open-loan guard that
refuses to delete a book that is still on loan.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import raise_api_error
from app.models import Book, Loan
from app.schemas import BookCreate, BookUpdate

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def clamp_pagination(limit: int, offset: int) -> tuple[int, int]:
    """Clamp ``limit`` to ``1..MAX_LIMIT`` and ``offset`` to a non-negative value."""

    clamped_limit = max(1, min(limit, MAX_LIMIT))
    clamped_offset = max(0, offset)
    return clamped_limit, clamped_offset


def _isbn_in_use(session: Session, isbn: str, exclude_id: int | None = None) -> bool:
    stmt = select(Book.id).where(Book.isbn == isbn)
    if exclude_id is not None:
        stmt = stmt.where(Book.id != exclude_id)
    return session.execute(stmt).first() is not None


def _open_loan_count(session: Session, book_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(Loan)
        .where(Loan.book_id == book_id, Loan.returned_at.is_(None))
    )
    return int(session.execute(stmt).scalar_one())


def create_book(session: Session, data: BookCreate) -> Book:
    """Create a book, rejecting a duplicate ISBN with ``409 duplicate_isbn``."""

    if _isbn_in_use(session, data.isbn):
        raise_api_error(
            409,
            "duplicate_isbn",
            f"A book with ISBN {data.isbn} already exists",
        )

    book = Book(**data.model_dump())
    session.add(book)
    session.commit()
    session.refresh(book)
    return book


def get_book(session: Session, book_id: int) -> Book:
    """Return the book or raise ``404 not_found``."""

    book = session.get(Book, book_id)
    if book is None:
        raise_api_error(404, "not_found", f"Book {book_id} not found")
    return book


def list_books(
    session: Session,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Book], int, int, int]:
    """Return ``(items, total, limit, offset)`` for the paginated book list."""

    limit, offset = clamp_pagination(limit, offset)

    filters = []
    if q:
        pattern = f"%{q}%"
        filters.append(or_(Book.title.ilike(pattern), Book.author.ilike(pattern)))

    total_stmt = select(func.count()).select_from(Book)
    if filters:
        total_stmt = total_stmt.where(*filters)
    total = int(session.execute(total_stmt).scalar_one())

    items_stmt = select(Book)
    if filters:
        items_stmt = items_stmt.where(*filters)
    items_stmt = items_stmt.order_by(Book.id).limit(limit).offset(offset)
    items = list(session.execute(items_stmt).scalars().all())

    return items, total, limit, offset


def update_book(session: Session, book_id: int, data: BookUpdate) -> Book:
    """Update the mutable fields of a book, rejecting a duplicate ISBN."""

    book = get_book(session, book_id)

    changes = {
        field: value
        for field, value in data.model_dump(exclude_unset=True).items()
        if value is not None
    }

    new_isbn = changes.get("isbn")
    if (
        new_isbn is not None
        and new_isbn != book.isbn
        and _isbn_in_use(session, new_isbn, exclude_id=book.id)
    ):
        raise_api_error(
            409,
            "duplicate_isbn",
            f"A book with ISBN {new_isbn} already exists",
        )

    for field, value in changes.items():
        setattr(book, field, value)

    session.commit()
    session.refresh(book)
    return book


def delete_book(session: Session, book_id: int) -> None:
    """Delete a book, refusing the deletion while it has open loans."""

    book = get_book(session, book_id)
    if _open_loan_count(session, book.id) > 0:
        raise_api_error(
            409,
            "book_has_open_loans",
            f"Book {book_id} still has open loans",
        )

    session.delete(book)
    session.commit()
