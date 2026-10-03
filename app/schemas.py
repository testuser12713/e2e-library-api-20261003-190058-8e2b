"""Pydantic v2 schemas and the pagination envelope shared by all routers.

Dates are serialised as ``YYYY-MM-DD`` (the default ISO representation for
:class:`datetime.date`).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class BookBase(BaseModel):
    title: str
    author: str
    isbn: str
    publication_year: int
    copies: int


class BookCreate(BookBase):
    pass


class BookUpdate(BaseModel):
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publication_year: int | None = None
    copies: int | None = None


class BookRead(BookBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class MemberBase(BaseModel):
    name: str
    email: str
    member_since: date


class MemberCreate(MemberBase):
    pass


class MemberUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    member_since: date | None = None


class MemberRead(MemberBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class LoanCreate(BaseModel):
    book_id: int
    member_id: int


class LoanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    member_id: int
    lent_at: date
    due_at: date
    returned_at: date | None = None


class BookPage(BaseModel):
    items: list[BookRead]
    total: int
    limit: int
    offset: int


class MemberPage(BaseModel):
    items: list[MemberRead]
    total: int
    limit: int
    offset: int


class LoanPage(BaseModel):
    items: list[LoanRead]
    total: int
    limit: int
    offset: int
