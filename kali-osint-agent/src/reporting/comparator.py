"""Dossier version comparison using line-based diff."""

from __future__ import annotations

import json
from difflib import unified_diff
from typing import Any

import structlog
from sqlalchemy import select

from src.db.models import Report
from src.db.postgres import async_session

logger = structlog.get_logger(__name__)


async def compare_dossiers(
    target: str,
    version_a: int,
    version_b: int,
) -> dict[str, Any]:
    """Compare two dossier versions for the same target.

    Uses :func:`difflib.unified_diff` to produce a structured diff
    with counts and samples of added/removed lines.

    Parameters
    ----------
    target:
        The target both reports refer to.
    version_a:
        The earlier version number.
    version_b:
        The later version number.

    Returns
    -------
    dict with ``target``, ``version_a``, ``version_b``, ``diff``,
    ``added``, ``removed``, ``added_sample``, ``removed_sample``.
    Returns an ``error`` key if either version is not found.
    """
    async with async_session() as session:
        result_a = await session.execute(
            select(Report).where(
                Report.target == target,
                Report.version == version_a,
            )
        )
        report_a = result_a.scalar_one_or_none()

        result_b = await session.execute(
            select(Report).where(
                Report.target == target,
                Report.version == version_b,
            )
        )
        report_b = result_b.scalar_one_or_none()

    if not report_a or not report_b:
        missing = []
        if not report_a:
            missing.append(f"v{version_a}")
        if not report_b:
            missing.append(f"v{version_b}")
        return {
            "error": f"Version(s) not found: {', '.join(missing)}",
            "target": target,
            "version_a": version_a,
            "version_b": version_b,
        }

    # Extract content for diffing
    content_a = _extract_content(report_a)
    content_b = _extract_content(report_b)

    lines_a = content_a.splitlines(keepends=True)
    lines_b = content_b.splitlines(keepends=True)

    diff_lines = list(
        unified_diff(
            lines_a,
            lines_b,
            fromfile=f"v{version_a}",
            tofile=f"v{version_b}",
        )
    )

    added = [
        line[1:].rstrip()
        for line in diff_lines
        if line.startswith("+") and not line.startswith("+++")
    ]
    removed = [
        line[1:].rstrip()
        for line in diff_lines
        if line.startswith("-") and not line.startswith("---")
    ]

    result = {
        "target": target,
        "version_a": version_a,
        "version_b": version_b,
        "diff": "".join(diff_lines),
        "added": len(added),
        "removed": len(removed),
        "added_sample": added[:20],
        "removed_sample": removed[:20],
    }

    logger.info(
        "comparator.diff_complete",
        target=target,
        versions=f"{version_a}->{version_b}",
        added=len(added),
        removed=len(removed),
    )
    return result


def _extract_content(report: Report) -> str:
    """Extract the textual content from a Report for diffing."""
    # Prefer content_html (the raw LLM output)
    if report.content_html:
        return report.content_html

    # Fall back to content_json
    if report.content_json:
        if isinstance(report.content_json, dict):
            return report.content_json.get("content", json.dumps(report.content_json, indent=2))
        return str(report.content_json)

    return ""
