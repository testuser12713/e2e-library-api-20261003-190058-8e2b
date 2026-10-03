"""Tests for the members API delivered by this ticket.

Covering create/read/update/delete, the email uniqueness rule on create and
update, pagination and the API-key guard for every write endpoint. Reads stay
public.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

API_KEY_HEADER = "X-API-Key"


def _member_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "member_since": "2024-01-15",
    }
    payload.update(overrides)
    return payload


def _create(client: TestClient, api_key: str, **overrides: object) -> dict:
    response = client.post(
        "/members", json=_member_payload(**overrides), headers={API_KEY_HEADER: api_key}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_member_returns_201_and_is_listed(client: TestClient, api_key: str) -> None:
    body = _create(client, api_key)

    assert isinstance(body["id"], int)
    assert body["name"] == "Ada Lovelace"
    assert body["email"] == "ada@example.com"
    assert body["member_since"] == "2024-01-15"

    listed = client.get("/members")
    assert listed.status_code == 200
    page = listed.json()
    assert page["total"] == 1
    assert page["limit"] == 20
    assert page["offset"] == 0
    assert page["items"][0]["id"] == body["id"]


def test_duplicate_email_on_create_returns_409(client: TestClient, api_key: str) -> None:
    _create(client, api_key)

    response = client.post(
        "/members",
        json=_member_payload(name="Grace Hopper"),
        headers={API_KEY_HEADER: api_key},
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "duplicate_email"
    assert set(error) == {"code", "message", "details"}


def test_get_member_by_id_and_unknown_id(client: TestClient, api_key: str) -> None:
    created = _create(client, api_key)

    found = client.get(f"/members/{created['id']}")
    assert found.status_code == 200
    assert found.json()["id"] == created["id"]

    missing = client.get("/members/999999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_put_and_patch_update_a_member(client: TestClient, api_key: str) -> None:
    created = _create(client, api_key)

    put = client.put(
        f"/members/{created['id']}",
        json={"name": "Ada Byron", "member_since": "2023-06-01"},
        headers={API_KEY_HEADER: api_key},
    )
    assert put.status_code == 200
    assert put.json()["name"] == "Ada Byron"
    assert put.json()["member_since"] == "2023-06-01"
    assert put.json()["email"] == "ada@example.com"

    patch = client.patch(
        f"/members/{created['id']}",
        json={"email": "ada.byron@example.com"},
        headers={API_KEY_HEADER: api_key},
    )
    assert patch.status_code == 200
    assert patch.json()["email"] == "ada.byron@example.com"
    assert patch.json()["name"] == "Ada Byron"


def test_update_to_an_email_of_another_member_returns_409(client: TestClient, api_key: str) -> None:
    first = _create(client, api_key, email="first@example.com")
    second = _create(client, api_key, name="Grace Hopper", email="second@example.com")

    response = client.patch(
        f"/members/{second['id']}",
        json={"email": first["email"]},
        headers={API_KEY_HEADER: api_key},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_email"

    unchanged = client.get(f"/members/{second['id']}").json()
    assert unchanged["email"] == "second@example.com"


def test_updating_a_member_with_its_own_email_is_allowed(client: TestClient, api_key: str) -> None:
    created = _create(client, api_key)

    response = client.patch(
        f"/members/{created['id']}",
        json={"email": created["email"], "name": "Ada L."},
        headers={API_KEY_HEADER: api_key},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Ada L."


def test_delete_member_returns_204_then_404(client: TestClient, api_key: str) -> None:
    created = _create(client, api_key)

    deleted = client.delete(f"/members/{created['id']}", headers={API_KEY_HEADER: api_key})
    assert deleted.status_code == 204
    assert deleted.content == b""

    assert client.get(f"/members/{created['id']}").status_code == 404
    assert client.get("/members").json()["total"] == 0


def test_delete_unknown_member_returns_404(client: TestClient, api_key: str) -> None:
    response = client.delete("/members/999999", headers={API_KEY_HEADER: api_key})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_members_is_paginated(client: TestClient, api_key: str) -> None:
    for index in range(3):
        _create(client, api_key, name=f"Member {index}", email=f"member{index}@example.com")

    first_page = client.get("/members", params={"limit": 2, "offset": 0}).json()
    assert first_page["total"] == 3
    assert first_page["limit"] == 2
    assert first_page["offset"] == 0
    assert len(first_page["items"]) == 2

    second_page = client.get("/members", params={"limit": 2, "offset": 2}).json()
    assert second_page["total"] == 3
    assert len(second_page["items"]) == 1

    ids_first = {item["id"] for item in first_page["items"]}
    ids_second = {item["id"] for item in second_page["items"]}
    assert ids_first.isdisjoint(ids_second)


def test_list_limit_is_capped_at_100(client: TestClient) -> None:
    response = client.get("/members", params={"limit": 500})
    assert response.status_code == 200
    assert response.json()["limit"] == 100


def test_write_endpoints_reject_missing_or_wrong_api_key(client: TestClient, api_key: str) -> None:
    created = _create(client, api_key)
    member_id = created["id"]

    calls = [
        ("post", "/members", {"json": _member_payload(email="new@example.com")}),
        ("put", f"/members/{member_id}", {"json": {"name": "X"}}),
        ("patch", f"/members/{member_id}", {"json": {"name": "X"}}),
        ("delete", f"/members/{member_id}", {}),
    ]

    for method, path, kwargs in calls:
        for bad_headers in ({}, {API_KEY_HEADER: "definitely-wrong"}):
            response = getattr(client, method)(path, headers=bad_headers, **kwargs)
            assert response.status_code == 401, f"{method.upper()} {path}"
            error = response.json()["error"]
            assert error["code"] == "unauthorized"
            assert set(error) == {"code", "message", "details"}


def test_read_endpoints_work_without_an_api_key(client: TestClient, api_key: str) -> None:
    created = _create(client, api_key)

    assert client.get("/members").status_code == 200
    assert client.get(f"/members/{created['id']}").status_code == 200
