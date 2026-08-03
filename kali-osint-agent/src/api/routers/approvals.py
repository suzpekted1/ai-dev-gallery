"""Approval management endpoints for human-in-the-loop workflows."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from src.agent.graph import agent
from src.api.auth import get_current_user
from src.db.models import Approval, TaskStatus
from src.db.postgres import async_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ApprovalDecision(BaseModel):
    approved: bool


class ApprovalResponse(BaseModel):
    id: int
    task_id: int
    action: str
    tool: str
    status: str
    decided_by: str | None = None
    created_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/pending")
async def list_pending(user: dict = Depends(get_current_user)):
    """List all approvals that are still pending."""
    async with async_session() as session:
        result = await session.execute(
            select(Approval)
            .where(Approval.status == TaskStatus.PENDING)
            .order_by(Approval.created_at.desc())
        )
        approvals = result.scalars().all()
        return [
            ApprovalResponse(
                id=a.id,
                task_id=a.task_id,
                action=a.action_description,
                tool=a.tool_name,
                status=a.status.value if hasattr(a.status, "value") else str(a.status),
                decided_by=a.decided_by,
                created_at=str(a.created_at),
            )
            for a in approvals
        ]


@router.post("/{approval_id}")
async def decide_approval(
    approval_id: int,
    decision: ApprovalDecision,
    user: dict = Depends(get_current_user),
):
    """Approve or deny a pending action and resume the agent graph."""
    async with async_session() as session:
        result = await session.execute(
            select(Approval).where(Approval.id == approval_id)
        )
        approval = result.scalar_one_or_none()

        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        current_status = approval.status.value if hasattr(approval.status, "value") else str(approval.status)
        if current_status != TaskStatus.PENDING.value:
            raise HTTPException(
                status_code=400,
                detail=f"Approval already decided: {current_status}",
            )

        approval.status = TaskStatus.APPROVED if decision.approved else TaskStatus.DENIED
        approval.decided_by = user["username"]
        approval.decided_at = datetime.now(timezone.utc)
        task_id = approval.task_id
        await session.commit()

    # Resume the agent graph with the decision
    try:
        config = {"configurable": {"thread_id": f"task-{task_id}"}}
        resume_value = {
            "approved": decision.approved,
            "decided_by": user["username"],
        }
        await agent.ainvoke(None, config=config, interrupt_resume_value=resume_value)
        logger.info(
            "approval.resumed",
            approval_id=approval_id,
            approved=decision.approved,
        )
    except Exception as exc:
        logger.error("approval.resume_failed", approval_id=approval_id, error=str(exc))

    return {
        "status": "approved" if decision.approved else "denied",
        "approval_id": approval_id,
    }
