"""Deterministic, aggregate-only dry run and explicit Company World backfill."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.company_world_models import (
    PERSON_ORIGIN_FOUNDER_CONFIRMATION,
    PERSON_ORIGIN_MEMBERSHIP,
    PROFILE_STATUS_ACTIVE,
    Affiliation,
    Organization,
    Person,
)
from app.services.company_map_read_service import _normalize_email
from app.services.company_world_confirmation_service import (
    lock_company_world_workspace,
    materialize_person_interactions,
)
from app.services.identity_service import list_workspace_members


async def backfill_company_world(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Plan or apply safe durable rows without exposing private source content.

    Projected external candidates are intentionally ignored. Only memberships
    and already founder-confirmed external people can become durable rows here.
    """

    if apply:
        await lock_company_world_workspace(session=session, workspace_id=workspace_id)

    memberships = await list_workspace_members(session, workspace_id=workspace_id)
    people = list(
        (await session.execute(select(Person).where(Person.workspace_id == workspace_id))).scalars()
    )
    organizations = list(
        (
            await session.execute(
                select(Organization).where(Organization.workspace_id == workspace_id)
            )
        ).scalars()
    )
    affiliations = list(
        (
            await session.execute(
                select(Affiliation).where(Affiliation.workspace_id == workspace_id)
            )
        ).scalars()
    )
    people_by_user = {person.user_id: person for person in people if person.user_id}
    people_by_email = {person.normalized_email: person for person in people}

    proposed_memberships = []
    conflicts = 0
    warnings: list[str] = []
    for membership in memberships:
        email = _normalize_email(membership.user.email)
        by_user = people_by_user.get(membership.user.id)
        by_email = people_by_email.get(email)
        if by_user is not None:
            if by_user.normalized_email != email:
                conflicts += 1
            continue
        if by_email is not None:
            conflicts += 1
            continue
        proposed_memberships.append(membership)

    confirmed_external = [
        person
        for person in people
        if person.origin == PERSON_ORIGIN_FOUNDER_CONFIRMATION
        and person.user_id is None
        and person.status == PROFILE_STATUS_ACTIVE
    ]
    affiliations_by_person = {affiliation.person_id: affiliation for affiliation in affiliations}
    organizations_by_id = {organization.id: organization for organization in organizations}
    interaction_proposals: dict[UUID, int] = {}
    for person in confirmed_external:
        affiliation = affiliations_by_person.get(person.id)
        organization = (
            organizations_by_id.get(affiliation.organization_id)
            if affiliation is not None
            else None
        )
        interaction_proposals[person.id] = await materialize_person_interactions(
            session=session,
            workspace_id=workspace_id,
            person=person,
            organization=organization,
            apply=False,
        )

    people_written = 0
    interactions_written = 0
    if apply:
        for membership in proposed_memberships:
            session.add(
                Person(
                    id=uuid4(),
                    workspace_id=workspace_id,
                    user_id=membership.user.id,
                    normalized_email=_normalize_email(membership.user.email),
                    display_name=membership.user.name,
                    origin=PERSON_ORIGIN_MEMBERSHIP,
                    status=PROFILE_STATUS_ACTIVE,
                )
            )
            people_written += 1
        if people_written:
            await session.flush()
        for person in confirmed_external:
            affiliation = affiliations_by_person.get(person.id)
            organization = (
                organizations_by_id.get(affiliation.organization_id)
                if affiliation is not None
                else None
            )
            interactions_written += await materialize_person_interactions(
                session=session,
                workspace_id=workspace_id,
                person=person,
                organization=organization,
                apply=True,
            )

    if conflicts:
        warnings.append(
            "Some membership identities conflict with existing durable people; "
            "no conflicting row was changed."
        )
    counts = {
        "memberships_seen": len(memberships),
        "confirmed_external_people_seen": len(confirmed_external),
        "people_proposed": len(proposed_memberships),
        "organizations_proposed": 0,
        "affiliations_proposed": 0,
        "interactions_proposed": sum(interaction_proposals.values()),
        "people_written": people_written,
        "organizations_written": 0,
        "affiliations_written": 0,
        "interactions_written": interactions_written,
        "conflicts": conflicts,
    }
    return {
        "workspace_id": str(workspace_id),
        "mode": "apply" if apply else "dry_run",
        "counts": counts,
        "writes_performed": bool(people_written or interactions_written),
        "capabilities": {
            "provider_calls": False,
            "external_write": False,
            "llm_used": False,
        },
        "warnings": warnings,
    }
