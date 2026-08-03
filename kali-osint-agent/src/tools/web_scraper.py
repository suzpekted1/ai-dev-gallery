"""Stealth web scraper using httpx through the proxy layer."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import structlog
from bs4 import BeautifulSoup

from src.opsec.session_factory import create_httpx_client

logger = structlog.get_logger(__name__)


async def web_scraper_tool(
    url: str,
    *,
    extract_emails: bool = True,
    extract_links: bool = True,
    extract_text: bool = False,
    max_pages: int = 1,
) -> dict:
    """Scrape *url* through the active proxy and return extracted data.

    Parameters
    ----------
    url:
        Starting URL to scrape.
    extract_emails:
        Pull email addresses from page content.
    extract_links:
        Collect all ``<a href>`` links.
    extract_text:
        Include the full visible text of the page.
    max_pages:
        Maximum number of pages to follow (breadth-first).

    Returns
    -------
    dict with keys ``emails``, ``links``, ``text``, ``title``, ``status_code``.
    """
    logger.info("web_scraper.start", url=url, max_pages=max_pages)

    results: dict = {
        "emails": [],
        "links": [],
        "text": "",
        "title": "",
        "status_code": 0,
        "pages_scraped": 0,
    }

    visited: set[str] = set()
    queue: list[str] = [url]

    async with create_httpx_client(stealth=True) as client:
        while queue and results["pages_scraped"] < max_pages:
            current_url = queue.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                response = await client.get(current_url, follow_redirects=True)
                results["status_code"] = response.status_code
                results["pages_scraped"] += 1

                if response.status_code != 200:
                    logger.warning("web_scraper.non_200", url=current_url, status=response.status_code)
                    continue

                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue

                soup = BeautifulSoup(response.text, "lxml")

                # Title
                if soup.title and soup.title.string:
                    results["title"] = soup.title.string.strip()

                # Emails
                if extract_emails:
                    import re
                    email_pattern = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
                    page_text = soup.get_text()
                    found_emails = email_pattern.findall(page_text)
                    results["emails"].extend(found_emails)

                    # Also check mailto: links
                    for mailto in soup.select("a[href^='mailto:']"):
                        href = mailto.get("href", "")
                        email = href.replace("mailto:", "").split("?")[0].strip()
                        if email and email not in results["emails"]:
                            results["emails"].append(email)

                # Links
                if extract_links:
                    base_domain = urlparse(current_url).netloc
                    for a_tag in soup.find_all("a", href=True):
                        href = a_tag["href"]
                        full_url = urljoin(current_url, href)
                        parsed = urlparse(full_url)
                        if parsed.scheme in ("http", "https"):
                            results["links"].append(full_url)
                            if parsed.netloc == base_domain and full_url not in visited:
                                queue.append(full_url)

                # Text
                if extract_text:
                    results["text"] = soup.get_text(separator="\n", strip=True)[:10000]

            except Exception as exc:
                logger.error("web_scraper.page_error", url=current_url, error=str(exc))

    # Deduplicate
    results["emails"] = list(set(results["emails"]))
    results["links"] = list(set(results["links"]))

    logger.info(
        "web_scraper.complete",
        emails=len(results["emails"]),
        links=len(results["links"]),
        pages=results["pages_scraped"],
    )
    return results
