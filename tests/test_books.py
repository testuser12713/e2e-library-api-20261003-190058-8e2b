"""Tests for the books API: CRUD, search, pagination and the API-key guard."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Loan, Member

BOOK = {
    "title": "The Hobbit",
    "author": "J.R.R. Tolkien",
    "isbn": "9780261102217",
    "publication_year": 1937,
    "copies": 3,
}


def _create(client: TestClient, api_key: str, **overrides: object) -> dict:
    payload = {**BOOK, **overrides}
    response = client.post("/books", json=payload, headers={"X-API-Key": api_key})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_book_returns_201_with_stored_resource(client: TestClient, api_key: str) -> None:
    body = _create(client, api_key)
    assert body["id"] > 0
    assert body["title"] == BOOK["title"]
    assert body["author"] == BOOK["author"]
    assert body["isbn"] == BOOK["isbn"]
    assert body["publication_year"] == BOOK["publication_year"]
    assert body["copies"] == BOOK["copies"]


def test_created_book_is_visible_in_detail_and_list(client: TestClient, api_key: str) -> None:
    body = _create(client, api_key)

    detail = client.get(f"/books/{body['id']}")
    assert detail.status_code == 200
    assert detail.json() == body

    listed = client.get("/books")
    assert listed.status_code == 200
    page = listed.json()
    assert page["total"] == 1
    assert [item["id"] for item in page["items"]] == [body["id"]]


def test_get_unknown_book_returns_404_unified_body(client: TestClient) -> None:
    response = client.get("/books/9999")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"


def test_duplicate_isbn_on_create_returns_409(client: TestClient, api_key: str) -> None:
    _create(client, api_key)
    response = client.post(
        "/books",
        json={**BOOK, "title": "Another title"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_isbn"


def test_put_updates_mutable_fields(client: TestClient, api_key: str) -> None:
    body = _create(client, api_key)
    response = client.put(
        f"/books/{body['id']}",
        json={"title": "There and Back Again", "copies": 5},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == body["id"]
    assert updated["title"] == "There and Back Again"
    assert updated["copies"] == 5
    assert updated["author"] == BOOK["author"]


def test_patch_updates_mutable_fields(client: TestClient, api_key: str) -> None:
    body = _create(client, api_key)
    response = client.patch(
        f"/books/{body['id']}",
        json={"publication_year": 1954},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["publication_year"] == 1954


def test_duplicate_isbn_on_update_returns_409(client: TestClient, api_key: str) -> None:
    first = _create(client, api_key)
    second = _create(client, api_key, isbn="9780000000001", title="Second")
    response = client.patch(
        f"/books/{second['id']}",
        json={"isbn": first["isbn"]},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_isbn"


def test_update_unknown_book_returns_404(client: TestClient, api_key: str) -> None:
    response = client.put(
        "/books/9999",
        json={"title": "Ghost"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_search_is_case_insensitive_substring_of_title_or_author(
    client: TestClient, api_key: str
) -> None:
    _create(client, api_key, isbn="9780000000002", title="Dune", author="Frank Herbert")
    _create(client, api_key, isbn="9780000000003", title="Neuromancer", author="William Gibson")

    by_title = client.get("/books", params={"q": "dun"})
    assert by_title.status_code == 200
    assert [item["title"] for item in by_title.json()["items"]] == ["Dune"]

    by_author = client.get("/books", params={"q": "GIBSON"})
    assert [item["title"] for item in by_author.json()["items"]] == ["Neuromancer"]

    no_match = client.get("/books", params={"q": "zzz"})
    assert no_match.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_pagination_envelope_and_bounds(client: TestClient, api_key: str) -> None:
    for index in range(5):
        _create(client, api_key, isbn=f"97800000010{index:02d}", title=f"Book {index}")

    page = client.get("/books", params={"limit": 2, "offset": 1}).json()
    assert page["total"] == 5
    assert page["limit"] == 2
    assert page["offset"] == 1
    assert len(page["items"]) == 2

    capped = client.get("/books", params={"limit": 1000}).json()
    assert capped["limit"] == 100

    floored = client.get("/books", params={"offset": -5}).json()
    assert floored["offset"] == 0


def test_delete_removes_book_and_returns_204(client: TestClient, api_key: str) -> None:
    body = _create(client, api_key)
    response = client.delete(f"/books/{body['id']}", headers={"X-API-Key": api_key})
    assert response.status_code == 204
    assert client.get(f"/books/{body['id']}").status_code == 404


def test_delete_unknown_book_returns_404(client: TestClient, api_key: str) -> None:
    response = client.delete("/books/9999", headers={"X-API-Key": api_key})
    assert response.status_code == 404


def test_delete_book_with_open_loan_returns_409(
    client: TestClient, api_key: str, engine: Engine
) -> None:
    body = _create(client, api_key)

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session: Session = factory()
    try:
        member = Member(name="Ada", email="ada@example.com", member_since=date(2020, 1, 1))
        session.add(member)
        session.commit()
        session.add(
            Loan(
                book_id=body["id"],
                member_id=member.id,
                lent_at=date.today(),
                due_at=date.today(),
            )
        )
        session.commit()
    finally:
        session.close()

    response = client.delete(f"/books/{body['id']}", headers={"X-API-Key": api_key})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "book_has_open_loans"


def test_delete_book_after_all_loans_returned_returns_204(client: TestClient, api_key: str) -> None:
    book = _create(client, api_key, copies=1)

    member_response = client.post(
        "/members",
        json={"name": "Grace", "email": "grace@example.com", "member_since": "2020-01-01"},
        headers={"X-API-Key": api_key},
    )
    assert member_response.status_code == 201, member_response.text
    member = member_response.json()

    loan_response = client.post(
        "/loans",
        json={"book_id": book["id"], "member_id": member["id"]},
        headers={"X-API-Key": api_key},
    )
    assert loan_response.status_code == 201, loan_response.text
    loan = loan_response.json()

    refused = client.delete(f"/books/{book['id']}", headers={"X-API-Key": api_key})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "book_has_open_loans"

    returned = client.post(f"/loans/{loan['id']}/return", headers={"X-API-Key": api_key})
    assert returned.status_code == 200, returned.text

    deleted = client.delete(f"/books/{book['id']}", headers={"X-API-Key": api_key})
    assert deleted.status_code == 204

    assert client.get(f"/books/{book['id']}").status_code == 404
    assert client.get(f"/loans/{loan['id']}").status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/books", BOOK),
        ("put", "/books/1", {"title": "x"}),
        ("patch", "/books/1", {"title": "x"}),
        ("delete", "/books/1", None),
    ],
)
def test_write_endpoints_reject_missing_or_wrong_key(
    client: TestClient, api_key: str, method: str, path: str, json_body: dict | None
) -> None:
    call = getattr(client, method)
    kwargs = {"json": json_body} if json_body is not None else {}

    missing = call(path, **kwargs)
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "unauthorized"

    wrong = call(path, headers={"X-API-Key": "not-the-key"}, **kwargs)
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "unauthorized"


def test_read_endpoints_are_public(client: TestClient) -> None:
    assert client.get("/books").status_code == 200
    assert client.get("/books/9999").status_code == 404
