"""Censys API wrapper for host lookups and searches."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from configs.settings import settings
from src.tools.base import ScopedTool

logger = logging.getLogger(__name__)


class CensysTool(ScopedTool):
    """Query the Censys Hosts API."""

    name = "censys"
    requires_approval = False
    is_active_scan = False

    def __init__(self) -> None:
        self._hosts_api = None

    def _ensure_api(self) -> Any:
        """Lazily initialise the Censys client."""
        if self._hosts_api is None:
            if not settings.censys_api_id or not settings.censys_api_secret:
                raise RuntimeError(
                    "Censys credentials are not configured "
                    "(settings.censys_api_id / censys_api_secret)"
                )
            from censys.search import CensysHosts

            self._hosts_api = CensysHosts(
                api_id=settings.censys_api_id,
                api_secret=settings.censys_api_secret,
            )
        return self._hosts_api

    async def _execute(
        self,
        *,
        target: str,
        action: str = "host",
        query: str | None = None,
        per_page: int = 25,
        pages: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run a Censys query.

        Parameters
        ----------
        target:
            IP address for ``host`` lookups.
        action:
            ``host`` -- look up a single host.
            ``search`` -- run a Censys search query.
        query:
            Censys search query string (for ``search``).
        per_page:
            Results per page.
        pages:
            Maximum number of pages to retrieve.
        """
        api = self._ensure_api()
        loop = asyncio.get_running_loop()

        if action == "host":
            return await self._host_lookup(loop, api, target)
        elif action == "search":
            return await self._search(loop, api, query or target, per_page, pages)
        else:
            raise ValueError(f"Unknown Censys action: {action!r}")

    # ------------------------------------------------------------------
    # Action implementations
    # ------------------------------------------------------------------

    async def _host_lookup(
        self,
        loop: asyncio.AbstractEventLoop,
        api: Any,
        ip: str,
    ) -> dict[str, Any]:
        """View details for a single host."""
        result = await loop.run_in_executor(None, api.view, ip)
        return {
            "action": "host",
            "ip": result.get("ip"),
            "autonomous_system": result.get("autonomous_system", {}),
            "location": result.get("location", {}),
            "operating_system": result.get("operating_system", {}),
            "services": [
                {
                    "port": svc.get("port"),
                    "service_name": svc.get("service_name"),
                    "transport_protocol": svc.get("transport_protocol"),
                    "software": svc.get("software", []),
                    "banner": (svc.get("banner") or "")[:500],
                }
                for svc in result.get("services", [])
            ],
            "last_updated": result.get("last_updated_at"),
        }

    async def _search(
        self,
        loop: asyncio.AbstractEventLoop,
        api: Any,
        query: str,
        per_page: int,
        pages: int,
    ) -> dict[str, Any]:
        """Run a Censys search query across all hosts."""

        def _do_search() -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            page_count = 0
            for hosts in api.search(query, per_page=per_page, pages=pages):
                for host in hosts:
                    results.append(
                        {
                            "ip": host.get("ip"),
                            "services": [
                                {
                                    "port": svc.get("port"),
                                    "service_name": svc.get("service_name"),
                                    "transport_protocol": svc.get("transport_protocol"),
                                }
                                for svc in host.get("services", [])
                            ],
                            "location": host.get("location", {}),
                            "autonomous_system": host.get("autonomous_system", {}),
                        }
                    )
                page_count += 1
                if page_count >= pages:
                    break
            return results

        matches = await loop.run_in_executor(None, _do_search)

        return {
            "action": "search",
            "query": query,
            "total_matches": len(matches),
            "matches": matches,
        }
