from __future__ import annotations

import json
from difflib import unified_diff

from sqlalchemy import select

from src.db.models import Report
from src.db.postgres import async_session


async def compare_dossiers(target: str, version_a: int, version_b: int) -> dict:
    async with async_session() as session:
        ra = (await session.execute(select(Report).where(Report.target == target, Report.version == version_a))).scalar_one_or_none()
        rb = (await session.execute(select(Report).where(Report.target == target, Report.version == version_b))).scalar_one_or_none()

    if not ra or not rb:
        return {"error": "One or both versions not found"}

    def extract(r):
        try:
            return json.loads(r.content_json).get("content", r.content_json)
        except (json.JSONDecodeError, TypeError):
            return r.content_json

    ca, cb = extract(ra), extract(rb)
    diff = list(unified_diff(ca.splitlines(keepends=True), cb.splitlines(keepends=True), fromfile=f"v{version_a}", tofile=f"v{version_b}"))
    added = [l.rstrip() for l in diff if l.startswith("+") and not l.startswith("+++")]
    removed = [l.rstrip() for l in diff if l.startswith("-") and not l.startswith("---")]

    return {"target": target, "version_a": version_a, "version_b": version_b, "diff": "".join(diff), "added": len(added), "removed": len(removed), "added_sample": added[:20], "removed_sample": removed[:20]}
