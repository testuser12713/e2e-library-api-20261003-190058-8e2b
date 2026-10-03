"""Tests for the loans API: lending rules, returns, overdue list and auth.

Books and members are seeded directly through the ORM because their routers are
delivered by separate tickets; the loans endpoints themselves are exercised
through the FastAPI ``TestClient``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import Book, Loan, Member

TODAY = date.today()
LOAN_PERIOD = timedelta(days=14)


def seed_book(
    engine: Engine,
    *,
    copies: int = 1,
    isbn: str = "978-0-000000-00-0",
    title: str = "A Book",
    author: str = "An Author",
    publication_year: int = 2000,
) -> int:
    with Session(engine) as session:
        book = Book(
            title=title,
            author=author,
            isbn=isbn,
            publication_year=publication_year,
            copies=copies,
        )
        session.add(book)
        session.commit()
        session.refresh(book)
        return book.id


def seed_member(engine: Engine, *, email: str = "member@example.org", name: str = "Member") -> int:
    with Session(engine) as session:
        member = Member(name=name, email=email, member_since=date(2020, 1, 1))
        session.add(member)
        session.commit()
        session.refresh(member)
        return member.id


def seed_loan(
    engine: Engine,
    *,
    book_id: int,
    member_id: int,
    lent_at: date,
    due_at: date,
    returned_at: date | None = None,
) -> int:
    with Session(engine) as session:
        loan = Loan(
            book_id=book_id,
            member_id=member_id,
            lent_at=lent_at,
            due_at=due_at,
            returned_at=returned_at,
        )
        session.add(loan)
        session.commit()
        session.refresh(loan)
        return loan.id


def auth(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def test_create_loan_uses_today_and_14_day_due_date(
    client: TestClient, engine: Engine, api_key: str
) -> None:
    book_id = seed_book(engine, copies=1)
    member_id = seed_member(engine)

    response = client.post(
        "/loans",
        json={"book_id": book_id, "member_id": member_id},
        headers=auth(api_key),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["book_id"] == book_id
    assert body["member_id"] == member_id
    assert body["lent_at"] == TODAY.isoformat()
    assert body["due_at"] == (TODAY + LOAN_PERIOD).isoformat()
    assert body["returned_at"] is None


def test_unknown_book_and_member_return_404(
    client: TestClient, engine: Engine, api_key: str
) -> None:
    member_id = seed_member(engine)
    book_id = seed_book(engine)

    response = client.post(
        "/loans",
        json={"book_id": 999999, "member_id": member_id},
        headers=auth(api_key),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

    response = client.post(
        "/loans",
        json={"book_id": book_id, "member_id": 999999},
        headers=auth(api_key),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_member_loan_limit_rejects_fourth_and_stores_nothing(
    client: TestClient, engine: Engine, api_key: str
) -> None:
    book_id = seed_book(engine, copies=5)
    member_id = seed_member(engine)

    for _ in range(3):
        response = client.post(
            "/loans",
            json={"book_id": book_id, "member_id": member_id},
            headers=auth(api_key),
        )
        assert response.status_code == 201

    response = client.post(
        "/loans",
        json={"book_id": book_id, "member_id": member_id},
        headers=auth(api_key),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "loan_limit_reached"

    listing = client.get("/loans", params={"member_id": member_id})
    assert listing.status_code == 200
    assert listing.json()["total"] == 3


def test_copy_availability_rule_and_re_lending_after_return(
    client: TestClient, engine: Engine, api_key: str
) -> None:
    book_id = seed_book(engine, copies=1)
    first_member = seed_member(engine, email="first@example.org")
    second_member = seed_member(engine, email="second@example.org")

    first = client.post(
        "/loans",
        json={"book_id": book_id, "member_id": first_member},
        headers=auth(api_key),
    )
    assert first.status_code == 201
    loan_id = first.json()["id"]

    blocked = client.post(
        "/loans",
        json={"book_id": book_id, "member_id": second_member},
        headers=auth(api_key),
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "no_copy_available"

    returned = client.post(f"/loans/{loan_id}/return", headers=auth(api_key))
    assert returned.status_code == 200

    relend = client.post(
        "/loans",
        json={"book_id": book_id, "member_id": second_member},
        headers=auth(api_key),
    )
    assert relend.status_code == 201
    assert relend.json()["book_id"] == book_id


def test_return_flow_stamps_date_and_rejects_double_return(
    client: TestClient, engine: Engine, api_key: str
) -> None:
    book_id = seed_book(engine, copies=1)
    member_id = seed_member(engine)

    created = client.post(
        "/loans",
        json={"book_id": book_id, "member_id": member_id},
        headers=auth(api_key),
    ).json()
    loan_id = created["id"]

    returned = client.post(f"/loans/{loan_id}/return", headers=auth(api_key))
    assert returned.status_code == 200
    body = returned.json()
    assert body["returned_at"] == TODAY.isoformat()

    again = client.post(f"/loans/{loan_id}/return", headers=auth(api_key))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "loan_already_returned"

    unknown = client.post("/loans/999999/return", headers=auth(api_key))
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"


def test_overdue_returns_only_open_loans_past_due(
    client: TestClient, engine: Engine, api_key: str
) -> None:
    book_id = seed_book(engine, copies=10)
    member_id = seed_member(engine)

    overdue_id = seed_loan(
        engine,
        book_id=book_id,
        member_id=member_id,
        lent_at=TODAY - timedelta(days=20),
        due_at=TODAY - timedelta(days=6),
    )
    seed_loan(
        engine,
        book_id=book_id,
        member_id=member_id,
        lent_at=TODAY - timedelta(days=14),
        due_at=TODAY,
    )
    seed_loan(
        engine,
        book_id=book_id,
        member_id=member_id,
        lent_at=TODAY - timedelta(days=30),
        due_at=TODAY - timedelta(days=16),
        returned_at=TODAY - timedelta(days=10),
    )

    response = client.get("/loans/overdue")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [overdue_id]
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_list_loans_filters_and_reads_without_key(
    client: TestClient, engine: Engine, api_key: str
) -> None:
    book_id = seed_book(engine, copies=5)
    other_book = seed_book(engine, copies=5, isbn="other-isbn")
    member_id = seed_member(engine)
    other_member = seed_member(engine, email="other@example.org")

    open_loan = seed_loan(
        engine,
        book_id=book_id,
        member_id=member_id,
        lent_at=TODAY,
        due_at=TODAY + LOAN_PERIOD,
    )
    seed_loan(
        engine,
        book_id=other_book,
        member_id=other_member,
        lent_at=TODAY,
        due_at=TODAY + LOAN_PERIOD,
        returned_at=TODAY,
    )

    open_only = client.get("/loans", params={"status": "open"})
    assert open_only.status_code == 200
    assert [item["id"] for item in open_only.json()["items"]] == [open_loan]

    returned_only = client.get("/loans", params={"status": "returned"})
    assert returned_only.status_code == 200
    assert returned_only.json()["total"] == 1

    by_book = client.get("/loans", params={"book_id": book_id})
    assert by_book.json()["total"] == 1

    paged = client.get("/loans", params={"limit": 1, "offset": 1})
    assert paged.status_code == 200
    assert paged.json()["total"] == 2
    assert len(paged.json()["items"]) == 1

    capped = client.get("/loans", params={"limit": 500})
    assert capped.status_code == 200
    assert capped.json()["limit"] == 100


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key"}])
def test_create_loan_requires_valid_api_key(
    client: TestClient, engine: Engine, headers: dict[str, str]
) -> None:
    book_id = seed_book(engine)
    member_id = seed_member(engine)

    response = client.post(
        "/loans",
        json={"book_id": book_id, "member_id": member_id},
        headers=headers,
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_return_requires_valid_api_key(client: TestClient, engine: Engine, api_key: str) -> None:
    book_id = seed_book(engine)
    member_id = seed_member(engine)
    loan_id = seed_loan(
        engine,
        book_id=book_id,
        member_id=member_id,
        lent_at=TODAY,
        due_at=TODAY + LOAN_PERIOD,
    )

    missing = client.post(f"/loans/{loan_id}/return")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "unauthorized"

    wrong = client.post(f"/loans/{loan_id}/return", headers={"X-API-Key": "wrong-key"})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "unauthorized"


def test_get_loan_returns_404_for_unknown_id(client: TestClient) -> None:
    response = client.get("/loans/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
