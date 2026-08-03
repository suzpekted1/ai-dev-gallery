"""Shodan API wrapper for host lookups, searches, and geo queries."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import shodan

from configs.settings import settings
from src.tools.base import ScopedTool

logger = logging.getLogger(__name__)


class ShodanTool(ScopedTool):
    """Query the Shodan API for host information and search results."""

    name = "shodan"
    requires_approval = False
    is_active_scan = False

    def __init__(self) -> None:
        self._api = shodan.Shodan(settings.shodan_api_key) if settings.shodan_api_key else None

    def _ensure_api(self) -> shodan.Shodan:
        if self._api is None:
            raise RuntimeError("Shodan API key is not configured (settings.shodan_api_key)")
        return self._api

    async def _execute(
        self,
        *,
        target: str,
        action: str = "host",
        query: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: int = 50,
        page: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run a Shodan query.

        Parameters
        ----------
        target:
            IP address for ``host`` lookups.
        action:
            ``host`` -- look up a single host.
            ``search`` -- run a Shodan search query.
            ``geo`` -- search within a geographic radius.
        query:
            Shodan search query string (for ``search`` / ``geo``).
        lat, lng:
            Coordinates for ``geo`` search.
        radius_km:
            Radius in km for ``geo`` search.
        page:
            Pagination page number.
        """
        api = self._ensure_api()
        loop = asyncio.get_running_loop()

        if action == "host":
            return await self._host_lookup(loop, api, target)
        elif action == "search":
            return await self._search(loop, api, query or target, page)
        elif action == "geo":
            return await self._geo_search(loop, api, lat, lng, radius_km, query, page)
        else:
            raise ValueError(f"Unknown Shodan action: {action!r}")

    # ------------------------------------------------------------------
    # Action implementations
    # ------------------------------------------------------------------

    async def _host_lookup(
        self,
        loop: asyncio.AbstractEventLoop,
        api: shodan.Shodan,
        ip: str,
    ) -> dict[str, Any]:
        """Look up a single host by IP."""
        result = await loop.run_in_executor(None, api.host, ip)
        return {
            "action": "host",
            "ip": result.get("ip_str"),
            "os": result.get("os"),
            "org": result.get("org"),
            "isp": result.get("isp"),
            "country": result.get("country_name"),
            "city": result.get("city"),
            "ports": result.get("ports", []),
            "vulns": result.get("vulns", []),
            "hostnames": result.get("hostnames", []),
            "services": [
                {
                    "port": svc.get("port"),
                    "transport": svc.get("transport"),
                    "product": svc.get("product"),
                    "version": svc.get("version"),
                    "banner": (svc.get("data") or "")[:500],
                }
                for svc in result.get("data", [])
            ],
        }

    async def _search(
        self,
        loop: asyncio.AbstractEventLoop,
        api: shodan.Shodan,
        query: str,
        page: int,
    ) -> dict[str, Any]:
        """Run a Shodan search query."""
        result = await loop.run_in_executor(None, api.search, query, page)
        return {
            "action": "search",
            "query": query,
            "total": result.get("total", 0),
            "matches": [
                {
                    "ip": m.get("ip_str"),
                    "port": m.get("port"),
                    "org": m.get("org"),
                    "product": m.get("product"),
                    "hostnames": m.get("hostnames", []),
                    "location": {
                        "country": m.get("location", {}).get("country_name"),
                        "city": m.get("location", {}).get("city"),
                        "latitude": m.get("location", {}).get("latitude"),
                        "longitude": m.get("location", {}).get("longitude"),
                    },
                }
                for m in result.get("matches", [])
            ],
        }

    async def _geo_search(
        self,
        loop: asyncio.AbstractEventLoop,
        api: shodan.Shodan,
        lat: float | None,
        lng: float | None,
        radius_km: int,
        query: str | None,
        page: int,
    ) -> dict[str, Any]:
        """Search Shodan by geographic coordinates using geo:{lat},{lng},{radius}."""
        if lat is None or lng is None:
            raise ValueError("lat and lng are required for geo search")

        geo_filter = f"geo:{lat},{lng},{radius_km}"
        full_query = f"{query} {geo_filter}" if query else geo_filter

        return await self._search(loop, api, full_query, page)
