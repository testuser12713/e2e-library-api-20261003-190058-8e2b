"""Business logic for the members resource.

The router stays free of logic: it validates the request shape and delegates
here. Every database interaction for members lives in this module, including
the uniqueness rule for email addresses.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import raise_api_error
from app.models import Member
from app.schemas import MemberCreate, MemberUpdate


def _email_taken_by_other(session: Session, email: str, member_id: int | None = None) -> bool:
    """Return whether ``email`` is already used by a member other than ``member_id``."""

    statement = select(Member.id).where(Member.email == email)
    if member_id is not None:
        statement = statement.where(Member.id != member_id)
    return session.scalar(statement) is not None


def _get_or_404(session: Session, member_id: int) -> Member:
    member = session.get(Member, member_id)
    if member is None:
        raise_api_error(404, "not_found", f"Member {member_id} not found")
    return member


def list_members(session: Session, limit: int, offset: int) -> tuple[list[Member], int]:
    """Return one page of members (ordered by id) and the total count."""

    total = session.scalar(select(func.count()).select_from(Member)) or 0
    members = list(
        session.scalars(select(Member).order_by(Member.id).limit(limit).offset(offset)).all()
    )
    return members, total


def get_member(session: Session, member_id: int) -> Member:
    """Return a single member or raise ``404 not_found``."""

    return _get_or_404(session, member_id)


def create_member(session: Session, payload: MemberCreate) -> Member:
    """Create a member, rejecting an email that is already in use."""

    if _email_taken_by_other(session, payload.email):
        raise_api_error(
            409,
            "duplicate_email",
            f"A member with email {payload.email} already exists",
        )

    member = Member(
        name=payload.name,
        email=payload.email,
        member_since=payload.member_since,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def update_member(session: Session, member_id: int, payload: MemberUpdate) -> Member:
    """Update the supplied fields of a member, rejecting a duplicate email."""

    member = _get_or_404(session, member_id)
    changes = payload.model_dump(exclude_unset=True)

    new_email = changes.get("email")
    if (
        new_email is not None
        and new_email != member.email
        and _email_taken_by_other(session, new_email, member_id=member.id)
    ):
        raise_api_error(
            409,
            "duplicate_email",
            f"A member with email {new_email} already exists",
        )

    for field, value in changes.items():
        setattr(member, field, value)

    session.commit()
    session.refresh(member)
    return member


def delete_member(session: Session, member_id: int) -> None:
    """Delete a member or raise ``404 not_found`` when the id is unknown."""

    member = _get_or_404(session, member_id)
    session.delete(member)
    session.commit()
