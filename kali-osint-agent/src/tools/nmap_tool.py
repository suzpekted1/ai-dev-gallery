"""Nmap wrapper with multiple scan profiles and structured output parsing."""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
from typing import Any

from src.tools.base import ScopedTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scan profiles
# ---------------------------------------------------------------------------

SCAN_PROFILES: dict[str, list[str]] = {
    "quick": ["-sV", "-T4", "--top-ports", "100"],
    "full": ["-sV", "-sC", "-p-", "-T3"],
    "stealth": ["-sS", "-Pn", "-T2"],          # run through proxychains4
    "udp": ["-sU", "--top-ports", "50"],
}


class NmapTool(ScopedTool):
    """Run nmap scans against in-scope targets."""

    name = "nmap"
    requires_approval = True
    is_active_scan = True

    async def _execute(
        self,
        *,
        target: str,
        scan_type: str = "quick",
        extra_args: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run an nmap scan and return parsed results.

        Parameters
        ----------
        target:
            IP, hostname, or CIDR to scan.
        scan_type:
            One of ``quick``, ``full``, ``stealth``, ``udp``.
        extra_args:
            Additional CLI flags appended to the command.
        """
        profile = SCAN_PROFILES.get(scan_type)
        if profile is None:
            raise ValueError(
                f"Unknown scan_type {scan_type!r}.  "
                f"Choose from: {', '.join(SCAN_PROFILES)}"
            )

        cmd_parts = list(profile)
        if extra_args:
            cmd_parts.extend(extra_args)

        # Always quote the target to prevent shell injection
        safe_target = shlex.quote(target)
        cmd_parts.append(safe_target)

        # Stealth scans route through proxychains4
        if scan_type == "stealth":
            command = f"proxychains4 nmap {' '.join(cmd_parts)}"
        else:
            command = f"nmap {' '.join(cmd_parts)}"

        logger.info("Running nmap: %s", command)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")

        if proc.returncode != 0:
            logger.warning("nmap exited %d: %s", proc.returncode, stderr)

        ports = _parse_nmap_output(stdout)

        return {
            "target": target,
            "scan_type": scan_type,
            "return_code": proc.returncode,
            "ports": ports,
            "raw_stdout": stdout,
            "raw_stderr": stderr,
        }


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------

# Matches lines like:  80/tcp  open  http  Apache httpd 2.4.52
_PORT_RE = re.compile(
    r"^(?P<port>\d+)/(?P<proto>\w+)\s+"
    r"(?P<state>\w+)\s+"
    r"(?P<service>\S+)"
    r"(?:\s+(?P<version>.+))?$",
    re.MULTILINE,
)


def _parse_nmap_output(raw: str) -> list[dict[str, str | int]]:
    """Extract structured port information from nmap text output."""
    results: list[dict[str, str | int]] = []
    for m in _PORT_RE.finditer(raw):
        results.append(
            {
                "port": int(m.group("port")),
                "protocol": m.group("proto"),
                "state": m.group("state"),
                "service": m.group("service"),
                "version": (m.group("version") or "").strip(),
            }
        )
    return results
