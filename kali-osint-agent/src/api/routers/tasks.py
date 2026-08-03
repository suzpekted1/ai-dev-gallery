"""Task management endpoints."""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from src.agent.graph import agent
from src.api.auth import get_current_user
from src.db.models import Task, TaskStatus, TaskType
from src.db.postgres import async_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class TaskCreate(BaseModel):
    task_type: str
    target: str
    description: str = ""
    proxy_mode: str = "stealth"


class TaskResponse(BaseModel):
    id: int
    task_type: str
    target: str
    status: str
    description: str | None = None
    result_summary: str | None = None
    created_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=TaskResponse)
async def create_task(
    task_in: TaskCreate,
    user: dict = Depends(get_current_user),
):
    """Create a new task, persist it, and launch the agent in the background."""
    try:
        task_type_enum = TaskType(task_in.task_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task type: {task_in.task_type}. "
            f"Valid types: {[t.value for t in TaskType]}",
        )

    async with async_session() as session:
        task = Task(
            task_type=task_type_enum,
            target=task_in.target,
            description=task_in.description,
            status=TaskStatus.PENDING,
            created_by=user["username"],
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id
        created_at = str(task.created_at)

    # Launch the agent graph in the background
    asyncio.create_task(_run_agent(task_id, task_in))

    return TaskResponse(
        id=task_id,
        task_type=task_in.task_type,
        target=task_in.target,
        status=TaskStatus.PENDING.value,
        description=task_in.description,
        created_at=created_at,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, user: dict = Depends(get_current_user)):
    """Return a single task by ID."""
    async with async_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskResponse(
            id=task.id,
            task_type=task.task_type.value,
            target=task.target,
            status=task.status.value,
            description=task.description,
            result_summary=task.result_summary,
            created_at=str(task.created_at),
        )


@router.get("")
async def list_tasks(
    status: str | None = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """List tasks with optional status filter."""
    async with async_session() as session:
        query = select(Task).order_by(Task.created_at.desc()).limit(limit)
        if status:
            try:
                status_enum = TaskStatus(status.upper())
                query = query.where(Task.status == status_enum)
            except ValueError:
                raise HTTPException(400, f"Invalid status: {status}")
        result = await session.execute(query)
        tasks = result.scalars().all()
        return [
            TaskResponse(
                id=t.id,
                task_type=t.task_type.value,
                target=t.target,
                status=t.status.value,
                description=t.description,
                result_summary=t.result_summary,
                created_at=str(t.created_at),
            )
            for t in tasks
        ]


# ---------------------------------------------------------------------------
# Background agent runner
# ---------------------------------------------------------------------------


async def _run_agent(task_id: int, task_in: TaskCreate) -> None:
    """Execute the LangGraph agent for a given task."""
    try:
        # Mark as running
        async with async_session() as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            t = result.scalar_one()
            t.status = TaskStatus.RUNNING
            await session.commit()

        config = {"configurable": {"thread_id": f"task-{task_id}"}}
        input_state = {
            "task_id": task_id,
            "task_type": task_in.task_type.lower(),
            "target": task_in.target,
            "description": task_in.description,
            "proxy_mode": task_in.proxy_mode,
            "messages": [],
        }

        final_state = None
        async for event in agent.astream(input_state, config=config):
            final_state = event

        # Mark as completed
        async with async_session() as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            t = result.scalar_one()
            t.status = TaskStatus.COMPLETED
            if final_state:
                t.result_summary = str(final_state.get("report", ""))[:5000]
            await session.commit()

        logger.info("agent.task_completed", task_id=task_id)

    except Exception as exc:
        logger.error("agent.task_failed", task_id=task_id, error=str(exc))
        async with async_session() as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            t = result.scalar_one()
            t.status = TaskStatus.FAILED
            t.result_summary = str(exc)[:1000]
            await session.commit()
