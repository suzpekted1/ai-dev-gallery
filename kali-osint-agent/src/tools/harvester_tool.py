"""theHarvester wrapper for email, subdomain, and IP discovery."""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
from typing import Any

from src.tools.base import ScopedTool

logger = logging.getLogger(__name__)

# Default data sources to query
DEFAULT_SOURCES = "baidu,bing,crtsh,dnsdumpster,duckduckgo,hackertarget,rapiddns,urlscan"


class HarvesterTool(ScopedTool):
    """Run theHarvester to collect emails, hostnames, and IPs."""

    name = "theharvester"
    requires_approval = False
    is_active_scan = False

    async def _execute(
        self,
        *,
        target: str,
        sources: str = DEFAULT_SOURCES,
        limit: int = 500,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run theHarvester and return parsed results.

        Parameters
        ----------
        target:
            Domain to enumerate.
        sources:
            Comma-separated data source list (see theHarvester -b).
        limit:
            Maximum results to request per source.
        """
        safe_target = shlex.quote(target)
        safe_sources = shlex.quote(sources)

        command = (
            f"theHarvester -d {safe_target} "
            f"-b {safe_sources} "
            f"-l {int(limit)}"
        )

        logger.info("Running theHarvester: %s", command)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")

        if proc.returncode != 0:
            logger.warning("theHarvester exited %d: %s", proc.returncode, stderr)

        emails, hosts, ips = _parse_harvester_output(stdout)

        return {
            "target": target,
            "sources": sources,
            "emails": emails,
            "hosts": hosts,
            "ips": ips,
            "email_count": len(emails),
            "host_count": len(hosts),
            "ip_count": len(ips),
            "raw_stdout": stdout,
        }


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _parse_harvester_output(raw: str) -> tuple[list[str], list[str], list[str]]:
    """Parse theHarvester stdout into (emails, hosts, ips)."""
    emails: list[str] = []
    hosts: list[str] = []
    ips: list[str] = []

    section: str | None = None

    for line in raw.splitlines():
        stripped = line.strip()
        lower = stripped.lower()

        # Detect section headers produced by theHarvester
        if "emails found" in lower or "emails:" in lower:
            section = "emails"
            continue
        elif "hosts found" in lower or "hosts:" in lower:
            section = "hosts"
            continue
        elif "ips found" in lower or "ip addresses" in lower:
            section = "ips"
            continue
        elif stripped.startswith("[*]") or stripped.startswith("---"):
            # Possible new section or separator -- keep current section
            continue
        elif not stripped:
            continue

        if section == "emails":
            found = _EMAIL_RE.findall(stripped)
            emails.extend(found)
        elif section == "hosts":
            # Host lines may look like: sub.domain.com:1.2.3.4
            host_part = stripped.split(":")[0].strip()
            if host_part and "." in host_part:
                hosts.append(host_part)
        elif section == "ips":
            found = _IP_RE.findall(stripped)
            ips.extend(found)

    # Deduplicate while preserving order
    emails = list(dict.fromkeys(emails))
    hosts = list(dict.fromkeys(hosts))
    ips = list(dict.fromkeys(ips))

    return emails, hosts, ips
