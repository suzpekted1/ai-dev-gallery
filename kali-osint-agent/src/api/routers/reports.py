"""Report management endpoints."""

from __future__ import annotations

import difflib

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from src.api.auth import get_current_user
from src.db.models import Report
from src.db.postgres import async_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReportResponse(BaseModel):
    id: int
    target: str
    version: int
    content_html: str | None = None
    content_json: dict | None = None
    created_at: str


class ReportDiff(BaseModel):
    target: str
    version_a: int
    version_b: int
    added_count: int
    removed_count: int
    added_samples: list[str]
    removed_samples: list[str]
    unified_diff: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def list_reports(
    target: str | None = None,
    limit: int = Query(default=50, le=200),
    user: dict = Depends(get_current_user),
):
    """List reports, optionally filtered by target."""
    async with async_session() as session:
        query = select(Report).order_by(Report.created_at.desc()).limit(limit)
        if target:
            query = query.where(Report.target == target)
        result = await session.execute(query)
        reports = result.scalars().all()
        return [
            ReportResponse(
                id=r.id,
                target=r.target,
                version=r.version,
                content_html=r.content_html,
                created_at=str(r.created_at),
            )
            for r in reports
        ]


@router.get("/{report_id}")
async def get_report(report_id: int, user: dict = Depends(get_current_user)):
    """Return a single report by ID."""
    async with async_session() as session:
        result = await session.execute(select(Report).where(Report.id == report_id))
        report = result.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        return ReportResponse(
            id=report.id,
            target=report.target,
            version=report.version,
            content_html=report.content_html,
            content_json=report.content_json,
            created_at=str(report.created_at),
        )


@router.get("/{report_id}/diff")
async def diff_reports(
    report_id: int,
    compare_to: int = Query(..., description="ID of the report to compare against"),
    user: dict = Depends(get_current_user),
):
    """Compare two reports using line-based diff.

    Returns a structured diff with added/removed line counts and
    samples of changed lines.
    """
    async with async_session() as session:
        result_a = await session.execute(select(Report).where(Report.id == report_id))
        report_a = result_a.scalar_one_or_none()
        if not report_a:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        result_b = await session.execute(select(Report).where(Report.id == compare_to))
        report_b = result_b.scalar_one_or_none()
        if not report_b:
            raise HTTPException(status_code=404, detail=f"Report {compare_to} not found")

    # Use content_html for diffing, fall back to stringified content_json
    content_a = report_a.content_html or str(report_a.content_json or "")
    content_b = report_b.content_html or str(report_b.content_json or "")

    lines_a = content_a.splitlines(keepends=True)
    lines_b = content_b.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=f"v{report_a.version}",
            tofile=f"v{report_b.version}",
            lineterm="",
        )
    )

    added = [line[1:].rstrip() for line in diff_lines if line.startswith("+") and not line.startswith("+++")]
    removed = [line[1:].rstrip() for line in diff_lines if line.startswith("-") and not line.startswith("---")]

    return ReportDiff(
        target=report_a.target,
        version_a=report_a.version,
        version_b=report_b.version,
        added_count=len(added),
        removed_count=len(removed),
        added_samples=added[:20],
        removed_samples=removed[:20],
        unified_diff="\n".join(diff_lines),
    )
