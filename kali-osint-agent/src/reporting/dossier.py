from __future__ import annotations

import json
from datetime import datetime

from langchain_core.messages import HumanMessage
from sqlalchemy import func, select

from src.db.models import Report
from src.db.neo4j_client import neo4j_client
from src.db.postgres import async_session
from src.llm.router import model_router


async def generate_dossier(target: str, task_results: list[dict] | None = None) -> dict:
    graph_data = await neo4j_client.get_target_graph(target)
    graph_summary = json.dumps(graph_data[:50], default=str)[:3000] if graph_data else "No graph data."

    model = model_router.route("summarize report dossier", is_sensitive=True)
    prompt = f"""Generate an intelligence dossier for: {target}

Graph data: {graph_summary}
{f"Tool results: {json.dumps(task_results, default=str)[:3000]}" if task_results else ""}

Sections: Executive Summary, Target Overview, Network Infrastructure, Digital Footprint, Vulnerabilities, Associated Entities, Risk Assessment, Recommendations.
Be factual - only include information supported by the data."""

    response = await model.ainvoke([HumanMessage(content=prompt)])

    dossier = {"target": target, "generated_at": datetime.utcnow().isoformat(), "content": response.content, "raw_findings": task_results or []}

    async with async_session() as session:
        max_v = (await session.execute(select(func.coalesce(func.max(Report.version), 0)).where(Report.target == target))).scalar()
        report = Report(target=target, version=max_v + 1, content_json=json.dumps(dossier, default=str))
        session.add(report)
        await session.commit()
        dossier["version"] = max_v + 1

    return dossier
