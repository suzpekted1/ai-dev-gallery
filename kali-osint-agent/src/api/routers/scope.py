"""Scope target management endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from src.api.auth import get_current_user
from src.db.models import ScopeTarget
from src.db.postgres import async_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/scope", tags=["scope"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ScopeTargetCreate(BaseModel):
    value: str
    target_type: str

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, v: str) -> str:
        allowed = {"ip", "domain", "cidr"}
        if v.lower() not in allowed:
            raise ValueError(f"target_type must be one of: {', '.join(sorted(allowed))}")
        return v.lower()


class ScopeTargetResponse(BaseModel):
    id: int
    value: str
    target_type: str
    active: bool
    added_by: str | None = None
    created_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ScopeTargetResponse])
async def list_scope_targets(
    active_only: bool = True,
    user: dict = Depends(get_current_user),
):
    """List scope targets, optionally including deactivated ones."""
    async with async_session() as session:
        query = select(ScopeTarget).order_by(ScopeTarget.created_at.desc())
        if active_only:
            query = query.where(ScopeTarget.active.is_(True))
        result = await session.execute(query)
        targets = result.scalars().all()
        return [
            ScopeTargetResponse(
                id=t.id,
                value=t.value,
                target_type=t.target_type,
                active=t.active,
                added_by=t.added_by,
                created_at=str(t.created_at),
            )
            for t in targets
        ]


@router.post("", response_model=ScopeTargetResponse)
async def add_scope_target(
    target_in: ScopeTargetCreate,
    user: dict = Depends(get_current_user),
):
    """Add a new scope target (validates type is ip/domain/cidr)."""
    async with async_session() as session:
        # Check for duplicates
        existing = await session.execute(
            select(ScopeTarget).where(
                ScopeTarget.value == target_in.value,
                ScopeTarget.active.is_(True),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Target already in scope")

        entry = ScopeTarget(
            value=target_in.value,
            target_type=target_in.target_type,
            added_by=user["username"],
            active=True,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

        logger.info(
            "scope.target_added",
            value=entry.value,
            type=entry.target_type,
            by=user["username"],
        )

        return ScopeTargetResponse(
            id=entry.id,
            value=entry.value,
            target_type=entry.target_type,
            active=entry.active,
            added_by=entry.added_by,
            created_at=str(entry.created_at),
        )


@router.delete("/{target_id}")
async def deactivate_scope_target(
    target_id: int,
    user: dict = Depends(get_current_user),
):
    """Deactivate (soft-delete) a scope target."""
    async with async_session() as session:
        result = await session.execute(
            select(ScopeTarget).where(ScopeTarget.id == target_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(status_code=404, detail="Scope target not found")
        if not entry.active:
            raise HTTPException(status_code=400, detail="Target already deactivated")

        entry.active = False
        await session.commit()

        logger.info("scope.target_deactivated", target_id=target_id, value=entry.value)
        return {"status": "deactivated", "target_id": target_id}
