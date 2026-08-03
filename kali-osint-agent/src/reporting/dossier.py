"""Intelligence dossier generation using LLM synthesis of graph data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from sqlalchemy import func, select

from src.db.models import Report
from src.db.neo4j_client import neo4j_client
from src.db.postgres import async_session
from src.llm.router import model_router

logger = structlog.get_logger(__name__)

# The dossier sections that the LLM is asked to produce
DOSSIER_SECTIONS = [
    "Executive Summary",
    "Target Overview",
    "Network Infrastructure",
    "Digital Footprint",
    "Vulnerabilities",
    "Associated Entities",
    "Timeline",
    "Risk Assessment",
    "Recommendations",
]


async def generate_dossier(
    target: str,
    task_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a structured intelligence dossier for *target*.

    1. Pulls all related graph data from Neo4j.
    2. Uses :pydata:`model_router` to select an LLM (routed as sensitive
       so data stays local).
    3. Asks the LLM to synthesise findings into a structured dossier
       with standard sections.
    4. Saves the result to the ``reports`` table with an auto-incremented
       version number.

    Parameters
    ----------
    target:
        The primary investigation target (domain, IP, org name).
    task_results:
        Optional list of raw tool result dicts to include.

    Returns
    -------
    dict containing the generated dossier, metadata, and DB version.
    """
    # ── Gather graph data ────────────────────────────────────────────────
    graph_data: list[dict[str, Any]] = []
    try:
        graph_data = await neo4j_client.get_target_graph(target)
    except Exception as exc:
        logger.warning("dossier.graph_fetch_failed", error=str(exc))

    graph_summary = ""
    if graph_data:
        # Truncate to avoid exceeding context limits
        graph_summary = json.dumps(graph_data[:50], default=str)[:4000]

    # ── Build prompt ─────────────────────────────────────────────────────
    sections_list = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(DOSSIER_SECTIONS))

    task_results_summary = ""
    if task_results:
        task_results_summary = (
            "\n\nTool Results:\n"
            + json.dumps(task_results, default=str)[:4000]
        )

    prompt = f"""Generate a comprehensive intelligence dossier for target: {target}

Knowledge Graph Data:
{graph_summary or "No graph data available."}
{task_results_summary}

Structure the report with these sections:
{sections_list}

Guidelines:
- Be factual -- only include information supported by the data provided.
- Use bullet points for clarity.
- Flag uncertainties explicitly.
- Include severity ratings where applicable.
- Provide actionable recommendations.
"""

    # ── Invoke LLM ───────────────────────────────────────────────────────
    model = model_router.route("summarize report dossier", is_sensitive=True)
    response = await model.ainvoke([HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)

    now = datetime.now(timezone.utc)

    dossier: dict[str, Any] = {
        "target": target,
        "generated_at": now.isoformat(),
        "content": content,
        "sections": DOSSIER_SECTIONS,
        "raw_findings": task_results or [],
    }

    # ── Persist to database ──────────────────────────────────────────────
    async with async_session() as session:
        # Determine next version number
        max_version_result = await session.execute(
            select(func.coalesce(func.max(Report.version), 0)).where(
                Report.target == target
            )
        )
        max_version = max_version_result.scalar() or 0
        new_version = max_version + 1

        report = Report(
            target=target,
            version=new_version,
            content_json=dossier,
            content_html=content,
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)

        dossier["version"] = new_version
        dossier["report_id"] = report.id

    logger.info(
        "dossier.generated",
        target=target,
        version=new_version,
        content_length=len(content),
    )
    return dossier
