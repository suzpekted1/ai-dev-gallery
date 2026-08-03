"""Wrapper around theHarvester for email and subdomain enumeration."""

from __future__ import annotations

import asyncio
import json

import structlog

logger = structlog.get_logger(__name__)


async def theharvester_tool(
    domain: str,
    sources: list[str] | None = None,
    limit: int = 500,
) -> dict:
    """Run theHarvester against *domain* and return parsed results.

    Parameters
    ----------
    domain:
        Target domain to enumerate.
    sources:
        Data sources to query (default: ``["bing", "crtsh", "dnsdumpster"]``).
    limit:
        Maximum number of results per source.

    Returns
    -------
    dict with keys ``emails``, ``subdomains``, ``ips``, ``raw_output``.
    """
    if sources is None:
        sources = ["bing", "crtsh", "dnsdumpster"]

    source_str = ",".join(sources)
    cmd = [
        "theHarvester",
        "-d", domain,
        "-b", source_str,
        "-l", str(limit),
        "-f", "/tmp/theharvester_output",
    ]

    logger.info("theharvester.start", domain=domain, sources=source_str)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        raw_output = stdout.decode(errors="replace")

        results = {
            "emails": [],
            "subdomains": [],
            "ips": [],
            "raw_output": raw_output,
        }

        # Attempt to parse the JSON output file
        try:
            with open("/tmp/theharvester_output.json") as f:
                data = json.load(f)
            results["emails"] = data.get("emails", [])
            results["subdomains"] = data.get("hosts", [])
            results["ips"] = data.get("ips", [])
        except (FileNotFoundError, json.JSONDecodeError):
            # Fall back to parsing stdout
            results = _parse_stdout(raw_output, results)

        logger.info(
            "theharvester.complete",
            emails=len(results["emails"]),
            subdomains=len(results["subdomains"]),
            ips=len(results["ips"]),
        )
        return results

    except asyncio.TimeoutError:
        logger.error("theharvester.timeout", domain=domain)
        return {"emails": [], "subdomains": [], "ips": [], "raw_output": "", "error": "timeout"}
    except FileNotFoundError:
        logger.error("theharvester.not_installed")
        return {"emails": [], "subdomains": [], "ips": [], "raw_output": "", "error": "theHarvester not installed"}


def _parse_stdout(output: str, results: dict) -> dict:
    """Best-effort parsing of theHarvester stdout."""
    in_emails = False
    in_hosts = False

    for line in output.splitlines():
        stripped = line.strip()
        if "[*] Emails found:" in line:
            in_emails = True
            in_hosts = False
            continue
        if "[*] Hosts found:" in line:
            in_hosts = True
            in_emails = False
            continue
        if stripped.startswith("[*]"):
            in_emails = False
            in_hosts = False
            continue

        if in_emails and "@" in stripped:
            results["emails"].append(stripped)
        elif in_hosts and stripped:
            parts = stripped.split(":")
            host = parts[0].strip()
            if host:
                results["subdomains"].append(host)
            if len(parts) > 1:
                ip = parts[1].strip()
                if ip:
                    results["ips"].append(ip)

    return results
