"""Wayback Machine CDX API wrapper for historical page retrieval."""

from __future__ import annotations

import logging
from typing import Any

from src.tools.base import ScopedTool
from src.tools.web_scraper import create_httpx_client

logger = logging.getLogger(__name__)

CDX_API_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_RAW_URL = "https://web.archive.org/web/{timestamp}id_/{url}"


class WaybackTool(ScopedTool):
    """Query the Wayback Machine for archived snapshots."""

    name = "wayback"
    requires_approval = False
    is_active_scan = False

    async def _execute(
        self,
        *,
        target: str,
        action: str = "search",
        timestamp: str | None = None,
        timestamp_a: str | None = None,
        timestamp_b: str | None = None,
        match_type: str = "domain",
        limit: int = 50,
        output_format: str = "json",
        filters: list[str] | None = None,
        collapse: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Interact with the Wayback Machine.

        Parameters
        ----------
        target:
            URL or domain to query.
        action:
            ``search`` -- list available snapshots via CDX API.
            ``fetch`` -- retrieve the content of a specific snapshot.
            ``diff`` -- compare two snapshots by timestamp using set difference.
        timestamp:
            14-digit Wayback timestamp for ``fetch`` (e.g. ``20230615120000``).
        timestamp_a, timestamp_b:
            Two timestamps for ``diff`` comparison.
        match_type:
            CDX matchType parameter (``exact``, ``prefix``, ``host``, ``domain``).
        limit:
            Maximum number of CDX results.
        output_format:
            CDX output format (``json`` recommended).
        filters:
            CDX filter expressions (e.g. ``["statuscode:200"]``).
        collapse:
            CDX collapse parameter (e.g. ``digest`` to deduplicate).
        """
        if action == "search":
            return await self._search(
                target,
                match_type=match_type,
                limit=limit,
                output_format=output_format,
                filters=filters,
                collapse=collapse,
            )
        elif action == "fetch":
            if not timestamp:
                raise ValueError("timestamp is required for fetch action")
            return await self._fetch(target, timestamp)
        elif action == "diff":
            if not timestamp_a or not timestamp_b:
                raise ValueError("timestamp_a and timestamp_b are required for diff action")
            return await self._diff(target, timestamp_a, timestamp_b)
        else:
            raise ValueError(f"Unknown Wayback action: {action!r}")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _search(
        self,
        url: str,
        *,
        match_type: str,
        limit: int,
        output_format: str,
        filters: list[str] | None,
        collapse: str | None,
    ) -> dict[str, Any]:
        """Query the CDX API for snapshot metadata."""
        params: dict[str, Any] = {
            "url": url,
            "matchType": match_type,
            "limit": limit,
            "output": output_format,
        }
        if filters:
            params["filter"] = filters
        if collapse:
            params["collapse"] = collapse

        async with create_httpx_client(stealth=True) as client:
            response = await client.get(CDX_API_URL, params=params)
            response.raise_for_status()

        if output_format == "json":
            raw = response.json()
            # First row is the header when output=json
            if raw and isinstance(raw, list) and len(raw) > 1:
                header = raw[0]
                snapshots = [dict(zip(header, row)) for row in raw[1:]]
            else:
                snapshots = []
        else:
            snapshots = [{"raw_line": line} for line in response.text.strip().splitlines()]

        return {
            "action": "search",
            "url": url,
            "match_type": match_type,
            "total_snapshots": len(snapshots),
            "snapshots": snapshots,
        }

    async def _fetch(self, url: str, timestamp: str) -> dict[str, Any]:
        """Retrieve the archived page content for a specific timestamp."""
        archive_url = WAYBACK_RAW_URL.format(timestamp=timestamp, url=url)

        async with create_httpx_client(stealth=True) as client:
            response = await client.get(archive_url)
            response.raise_for_status()

        return {
            "action": "fetch",
            "url": url,
            "timestamp": timestamp,
            "archive_url": archive_url,
            "status_code": response.status_code,
            "content_length": len(response.text),
            "content": response.text[:50_000],  # cap to avoid memory issues
        }

    async def _diff(self, url: str, timestamp_a: str, timestamp_b: str) -> dict[str, Any]:
        """Compare two snapshots by computing the set difference of their lines."""
        content_a = await self._fetch(url, timestamp_a)
        content_b = await self._fetch(url, timestamp_b)

        lines_a = set(content_a.get("content", "").splitlines())
        lines_b = set(content_b.get("content", "").splitlines())

        only_in_a = sorted(lines_a - lines_b)
        only_in_b = sorted(lines_b - lines_a)

        return {
            "action": "diff",
            "url": url,
            "timestamp_a": timestamp_a,
            "timestamp_b": timestamp_b,
            "lines_only_in_a": len(only_in_a),
            "lines_only_in_b": len(only_in_b),
            "added": only_in_b[:200],    # lines present in B but not A
            "removed": only_in_a[:200],  # lines present in A but not B
        }
