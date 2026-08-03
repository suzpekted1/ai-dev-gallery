"""Human-in-the-loop approval node using LangGraph interrupt."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from src.agent.state import AgentState

logger = structlog.get_logger(__name__)


async def hitl_approve_node(state: dict[str, Any]) -> dict[str, Any]:
    """Pause the graph and wait for human approval.

    Creates an Approval record in PostgreSQL, sends an ``interrupt``
    with the approval details, then processes the decision when the
    graph is resumed.
    """
    pending = state.get("pending_action")
    if not pending:
        return {"approval_status": "not_needed"}

    # Persist the approval request
    approval_id = await _create_approval_record(
        task_id=state.get("task_id", 0),
        action=pending,
    )

    logger.info(
        "hitl.awaiting_approval",
        approval_id=approval_id,
        tool=pending.get("tool"),
        target=pending.get("target"),
    )

    # Pause execution -- the graph will not proceed until resumed
    decision = interrupt({
        "type": "approval_required",
        "approval_id": approval_id,
        "action": pending.get("description", "Unknown action"),
        "tool": pending.get("tool", "unknown"),
        "target": pending.get("target", state.get("target", "")),
        "args": pending.get("args", {}),
        "message": f"APPROVAL REQUIRED: {pending.get('description', '')}",
    })

    # Process the decision
    approved = decision.get("approved", False) if isinstance(decision, dict) else bool(decision)
    decided_by = decision.get("decided_by", "unknown") if isinstance(decision, dict) else "unknown"

    await _update_approval_record(approval_id, approved, decided_by=decided_by)

    if approved:
        logger.info("hitl.approved", approval_id=approval_id, decided_by=decided_by)
        return {
            "approval_status": "approved",
            "approval_id": approval_id,
            "messages": [AIMessage(content=f"Action approved by {decided_by} (ID: {approval_id})")],
        }
    else:
        logger.info("hitl.denied", approval_id=approval_id, decided_by=decided_by)
        return {
            "approval_status": "denied",
            "approval_id": approval_id,
            "error": f"Action denied by {decided_by}",
            "messages": [AIMessage(content=f"Action denied by {decided_by} (ID: {approval_id})")],
        }


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


async def _create_approval_record(task_id: int, action: dict[str, Any]) -> int:
    """Insert a new Approval row and return its ID."""
    from src.db.models import Approval
    from src.db.postgres import async_session

    async with async_session() as session:
        approval = Approval(
            task_id=task_id,
            action_description=action.get("description", ""),
            tool_name=action.get("tool", "unknown"),
            tool_args=action.get("args"),
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)
        logger.info("hitl.record_created", approval_id=approval.id, task_id=task_id)
        return approval.id


async def _update_approval_record(
    approval_id: int,
    approved: bool,
    decided_by: str = "unknown",
) -> None:
    """Update an existing Approval row with the decision."""
    from sqlalchemy import select

    from src.db.models import Approval, TaskStatus
    from src.db.postgres import async_session

    async with async_session() as session:
        result = await session.execute(
            select(Approval).where(Approval.id == approval_id)
        )
        approval = result.scalar_one_or_none()
        if approval is not None:
            approval.status = TaskStatus.APPROVED if approved else TaskStatus.DENIED
            approval.decided_by = decided_by
            approval.decided_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info(
                "hitl.record_updated",
                approval_id=approval_id,
                status="approved" if approved else "denied",
            )
