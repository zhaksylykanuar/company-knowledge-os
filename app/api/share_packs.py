"""Share pack endpoints: generate / review / approve / export / revoke.

Pack management is founder-only (the founder prepares updates for other
audiences); the pack's own ``audience`` drives content redaction, and
export refuses anything that fails the redaction manifest. Every endpoint
takes a ``view`` and enforces it backend-side. Mutations are audited and
hash-guarded inside the service layer.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.view_guard import require_founder
from app.db.base import AsyncSessionLocal
from app.services import share_packs as sp
from app.services.visibility import SCOPE_FOUNDER, SCOPES

router = APIRouter(prefix="/api/v1/share-packs", tags=["share-packs"])


class GeneratePackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_type: str
    created_by: str = Field(default="founder", max_length=120)


class EditSectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_key: str = Field(min_length=1, max_length=120)
    text: str = Field(max_length=2000)
    reviewer_id: str = Field(default="founder", max_length=120)


class ToggleSectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_key: str = Field(min_length=1, max_length=120)
    included: bool
    reviewer_id: str = Field(default="founder", max_length=120)


class ToggleFindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(min_length=1, max_length=255)
    included: bool
    reviewer_id: str = Field(default="founder", max_length=120)


class NoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=2000)
    reviewer_id: str = Field(default="founder", max_length=120)


class ApprovePackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(min_length=8, max_length=128)
    reviewer_id: str = Field(default="founder", max_length=120)


class DecisionNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)
    reviewer_id: str = Field(default="founder", max_length=120)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pack not found")


async def _run(coro_factory) -> dict[str, Any]:
    """Run a service mutation, commit, map ValueError -> 409, None -> 404."""

    async with AsyncSessionLocal() as session:
        try:
            result = await coro_factory(session)
            await session.commit()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
    if result is None:
        raise _not_found()
    return result


@router.get("")
async def get_share_packs(
    audience: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    if audience is not None and audience not in SCOPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown audience: {audience}",
        )
    async with AsyncSessionLocal() as session:
        packs = await sp.list_packs(
            session, audience=audience, status=status_filter
        )
    return {"packs": packs, "counts": {"total": len(packs)}}


@router.get("/{pack_id:path}/preview")
async def get_pack_preview(
    pack_id: str,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    async with AsyncSessionLocal() as session:
        preview = await sp.build_pack_preview(session, pack_id=pack_id)
    if preview is None:
        raise _not_found()
    return preview


@router.get("/{pack_id:path}")
async def get_share_pack(
    pack_id: str,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    async with AsyncSessionLocal() as session:
        pack = await sp.read_pack(session, pack_id=pack_id)
    if pack is None:
        raise _not_found()
    return pack


@router.post("/generate")
async def post_generate_pack(
    request: GeneratePackRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    if request.pack_type not in sp.PACK_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown pack_type: {request.pack_type}",
        )
    return await _run(
        lambda s: sp.generate_pack(
            s, pack_type=request.pack_type, created_by=request.created_by
        )
    )


@router.post("/{pack_id:path}/regenerate")
async def post_regenerate_pack(
    pack_id: str,
    request: DecisionNoteRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    return await _run(
        lambda s: sp.regenerate_pack(
            s, pack_id=pack_id, reviewer_id=request.reviewer_id
        )
    )


@router.post("/{pack_id:path}/section")
async def post_edit_section(
    pack_id: str,
    request: EditSectionRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    return await _run(
        lambda s: sp.edit_section(
            s,
            pack_id=pack_id,
            section_key=request.section_key,
            text=request.text,
            reviewer_id=request.reviewer_id,
        )
    )


@router.post("/{pack_id:path}/section/include")
async def post_toggle_section(
    pack_id: str,
    request: ToggleSectionRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    return await _run(
        lambda s: sp.set_section_included(
            s,
            pack_id=pack_id,
            section_key=request.section_key,
            included=request.included,
            reviewer_id=request.reviewer_id,
        )
    )


@router.post("/{pack_id:path}/finding")
async def post_toggle_finding(
    pack_id: str,
    request: ToggleFindingRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    return await _run(
        lambda s: sp.set_finding_included(
            s,
            pack_id=pack_id,
            finding_id=request.finding_id,
            included=request.included,
            reviewer_id=request.reviewer_id,
        )
    )


@router.post("/{pack_id:path}/note")
async def post_add_note(
    pack_id: str,
    request: NoteRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    return await _run(
        lambda s: sp.add_public_note(
            s, pack_id=pack_id, note=request.note, reviewer_id=request.reviewer_id
        )
    )


@router.post("/{pack_id:path}/approve")
async def post_approve_pack(
    pack_id: str,
    request: ApprovePackRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    return await _run(
        lambda s: sp.approve_pack(
            s,
            pack_id=pack_id,
            content_hash=request.content_hash,
            reviewer_id=request.reviewer_id,
        )
    )


@router.post("/{pack_id:path}/reject")
async def post_reject_pack(
    pack_id: str,
    request: DecisionNoteRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    return await _run(
        lambda s: sp.reject_pack(
            s, pack_id=pack_id, reviewer_id=request.reviewer_id, reason=request.reason
        )
    )


@router.post("/{pack_id:path}/export")
async def post_export_pack(
    pack_id: str,
    request: DecisionNoteRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    return await _run(
        lambda s: sp.export_pack(
            s, pack_id=pack_id, reviewer_id=request.reviewer_id
        )
    )


@router.post("/{pack_id:path}/revoke")
async def post_revoke_pack(
    pack_id: str,
    request: DecisionNoteRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    require_founder(view)
    return await _run(
        lambda s: sp.revoke_pack(
            s, pack_id=pack_id, reviewer_id=request.reviewer_id, reason=request.reason
        )
    )
