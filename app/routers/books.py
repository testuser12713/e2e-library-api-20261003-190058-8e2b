"""HTTP layer for the books resource.

Read endpoints are public; POST, PUT, PATCH and DELETE depend on
:func:`app.security.require_api_key`. All behaviour lives in
:mod:`app.services.books`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas import BookCreate, BookPage, BookRead, BookUpdate
from app.security import require_api_key
from app.services import books as books_service

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=BookPage)
def list_books(
    q: str | None = None,
    limit: int = Query(default=books_service.DEFAULT_LIMIT),
    offset: int = Query(default=0),
    session: Session = Depends(get_session),
) -> BookPage:
    items, total, limit, offset = books_service.list_books(session, q, limit, offset)
    return BookPage(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=BookRead, status_code=status.HTTP_201_CREATED)
def create_book(
    payload: BookCreate,
    session: Session = Depends(get_session),
    _api_key: str = Depends(require_api_key),
) -> BookRead:
    return books_service.create_book(session, payload)


@router.get("/{book_id}", response_model=BookRead)
def get_book(book_id: int, session: Session = Depends(get_session)) -> BookRead:
    return books_service.get_book(session, book_id)


@router.put("/{book_id}", response_model=BookRead)
def replace_book(
    book_id: int,
    payload: BookUpdate,
    session: Session = Depends(get_session),
    _api_key: str = Depends(require_api_key),
) -> BookRead:
    return books_service.update_book(session, book_id, payload)


@router.patch("/{book_id}", response_model=BookRead)
def update_book(
    book_id: int,
    payload: BookUpdate,
    session: Session = Depends(get_session),
    _api_key: str = Depends(require_api_key),
) -> BookRead:
    return books_service.update_book(session, book_id, payload)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: int,
    session: Session = Depends(get_session),
    _api_key: str = Depends(require_api_key),
) -> None:
    books_service.delete_book(session, book_id)
