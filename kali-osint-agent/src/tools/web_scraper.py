"""Stealthy web scraper with Tor integration and traffic analysis."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from configs.settings import settings
from src.tools.base import ScopedTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stealth HTTP client factory
# ---------------------------------------------------------------------------


def create_httpx_client(*, stealth: bool = True) -> httpx.AsyncClient:
    """Create an httpx async client, optionally routed through Tor."""
    proxies: str | None = None

    if stealth:
        proxies = settings.tor_socks_url

    headers = _random_headers() if stealth else {}

    return httpx.AsyncClient(
        proxy=proxies,
        headers=headers,
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        verify=True,
    )


def _random_headers() -> dict[str, str]:
    """Generate plausible browser-like headers."""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    ]
    return {
        "User-Agent": random.choice(user_agents),  # noqa: S311
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


# ---------------------------------------------------------------------------
# Tor identity rotation
# ---------------------------------------------------------------------------


async def _rotate_tor_identity() -> None:
    """Send NEWNYM signal to Tor control port for a fresh circuit."""
    try:
        from stem import Signal  # noqa: F811
        from stem.control import Controller  # noqa: F811

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            _sync_rotate_tor,
            settings.tor_control_port,
            settings.tor_control_password,
        )
        logger.info("Tor identity rotated")
    except Exception:
        logger.warning("Failed to rotate Tor identity", exc_info=True)


def _sync_rotate_tor(control_port: int, password: str) -> None:
    from stem import Signal
    from stem.control import Controller

    with Controller.from_port(port=control_port) as ctrl:
        ctrl.authenticate(password=password)
        ctrl.signal(Signal.NEWNYM)


# ---------------------------------------------------------------------------
# Traffic analyser
# ---------------------------------------------------------------------------


class TrafficAnalyzer:
    """Minimal traffic analyser that watches for anomalies in responses."""

    def __init__(self) -> None:
        self._request_count = 0
        self._alert_threshold = 50

    def record(self, response: httpx.Response) -> bool:
        """Record a response and return True if an anomaly is detected."""
        self._request_count += 1

        # Heuristic: captcha / block pages
        if response.status_code in (403, 429, 503):
            logger.warning(
                "Traffic alert: HTTP %d from %s",
                response.status_code,
                response.url,
            )
            return True

        # Periodic rotation after N requests
        if self._request_count >= self._alert_threshold:
            self._request_count = 0
            return True

        return False


# Module-level instance
traffic_analyzer = TrafficAnalyzer()

# ---------------------------------------------------------------------------
# Scraper tool
# ---------------------------------------------------------------------------


class WebScraperTool(ScopedTool):
    """Crawl web pages with stealth and extract structured content."""

    name = "web_scraper"
    requires_approval = False
    is_active_scan = False

    async def _execute(
        self,
        *,
        target: str,
        max_pages: int = 10,
        stealth: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Scrape *target* URL (and linked pages up to *max_pages*).

        Parameters
        ----------
        target:
            Starting URL to scrape.
        max_pages:
            Maximum number of pages to crawl.
        stealth:
            Route traffic through Tor and use random headers.
        """
        if not target.startswith(("http://", "https://")):
            target = f"https://{target}"

        base_domain = urlparse(target).netloc
        visited: set[str] = set()
        queue: list[str] = [target]
        pages: list[dict[str, Any]] = []

        async with create_httpx_client(stealth=stealth) as client:
            while queue and len(pages) < max_pages:
                url = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)

                page_data = await self._fetch_page(client, url, stealth)
                if page_data is None:
                    continue
                pages.append(page_data)

                # Enqueue same-domain links
                for link in page_data.get("links", []):
                    abs_link = urljoin(url, link)
                    parsed = urlparse(abs_link)
                    if parsed.netloc == base_domain and abs_link not in visited:
                        queue.append(abs_link)

                # Random delay between requests
                delay = random.uniform(1.0, 3.0)  # noqa: S311
                await asyncio.sleep(delay)

        return {
            "start_url": target,
            "pages_scraped": len(pages),
            "pages": pages,
        }

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        url: str,
        stealth: bool,
    ) -> dict[str, Any] | None:
        """Fetch a single page and extract structured data."""
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return None

        # Traffic analysis -- rotate Tor on anomaly
        alert = traffic_analyzer.record(response)
        if alert and stealth:
            await _rotate_tor_identity()
            # Refresh headers for subsequent requests
            client.headers.update(_random_headers())

        if response.status_code >= 400:
            return {
                "url": url,
                "status_code": response.status_code,
                "error": f"HTTP {response.status_code}",
            }

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return {
                "url": url,
                "status_code": response.status_code,
                "content_type": content_type,
                "note": "non-HTML content skipped",
            }

        html = response.text
        soup = BeautifulSoup(html, "lxml")

        return {
            "url": url,
            "status_code": response.status_code,
            "title": soup.title.string.strip() if soup.title and soup.title.string else None,
            "content_hash": hashlib.sha256(html.encode()).hexdigest(),
            "scripts": [s.get("src") for s in soup.find_all("script", src=True)],
            "styles": [link_tag.get("href") for link_tag in soup.find_all("link", rel="stylesheet")],
            "images": [img.get("src") for img in soup.find_all("img", src=True)],
            "links": [a.get("href") for a in soup.find_all("a", href=True)],
            "forms": [
                {
                    "action": form.get("action"),
                    "method": form.get("method", "get").upper(),
                    "inputs": [
                        {"name": inp.get("name"), "type": inp.get("type", "text")}
                        for inp in form.find_all("input")
                        if inp.get("name")
                    ],
                }
                for form in soup.find_all("form")
            ],
        }
