"""Proxy routing manager supporting multiple anonymity modes."""

from __future__ import annotations

import itertools
from collections import defaultdict

import structlog

from configs.settings import ProxyMode, settings

logger = structlog.get_logger(__name__)


class ProxyManager:
    """Manages proxy selection and rotation based on the configured mode."""

    def __init__(self) -> None:
        self._mode = settings.proxy_mode
        self._failures: dict[str, int] = defaultdict(int)

        # Build an iterator that cycles through every available proxy for
        # ROTATING mode.  For other modes this is unused.
        all_proxies: list[str] = []
        all_proxies.append(settings.tor_socks_url)
        all_proxies.extend(settings.socks5_proxies)
        all_proxies.append(settings.whonix_socks_url)
        self._rotating_cycle = itertools.cycle(all_proxies) if all_proxies else None

        logger.info("proxy_manager.init", mode=self._mode.value)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_proxy(self) -> str | None:
        """Return a proxy URL string appropriate for the current mode, or
        ``None`` when running in DIRECT mode."""

        match self._mode:
            case ProxyMode.STEALTH:
                proxy = settings.tor_socks_url
            case ProxyMode.FAST:
                proxy = self._pick_socks5()
            case ProxyMode.DIRECT:
                return None
            case ProxyMode.ROTATING:
                proxy = self._next_rotating()
            case ProxyMode.WHONIX:
                proxy = f"socks5://{settings.whonix_gateway_ip}:{settings.whonix_socks_port}"
            case _:
                logger.warning("proxy_manager.unknown_mode", mode=self._mode)
                return None

        logger.debug("proxy_manager.selected", proxy=proxy)
        return proxy

    def get_httpx_proxy_config(self) -> dict:
        """Return a dict suitable for passing as ``proxy`` to an httpx client."""

        proxy = self.get_proxy()
        if proxy is None:
            return {}
        return {"proxy": proxy}

    def report_failure(self, url: str) -> None:
        """Record a failed request through the current proxy."""

        self._failures[url] += 1
        logger.warning(
            "proxy_manager.failure_reported",
            url=url,
            total_failures=self._failures[url],
        )

    def reset_failures(self) -> None:
        """Clear the failure counters."""

        self._failures.clear()
        logger.info("proxy_manager.failures_reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pick_socks5(self) -> str | None:
        pool = settings.socks5_proxies
        if not pool:
            logger.warning("proxy_manager.empty_socks5_pool")
            return None
        # Simple round-robin: return the entry with fewest recorded failures.
        return min(pool, key=lambda p: self._failures.get(p, 0))

    def _next_rotating(self) -> str | None:
        if self._rotating_cycle is None:
            logger.warning("proxy_manager.no_proxies_for_rotating")
            return None
        return next(self._rotating_cycle)


proxy_manager = ProxyManager()
