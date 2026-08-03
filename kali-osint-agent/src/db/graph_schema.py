"""Neo4j knowledge-graph schema documentation.

This module is the single source of truth for node labels, their expected
properties, and relationship types used throughout the OSINT graph.
"""

from __future__ import annotations

NODE_LABELS: dict[str, dict] = {
    "Target": {
        "description": "Top-level investigation target (domain, IP, or organization).",
        "properties": {
            "domain": "Primary domain name (unique key).",
            "ip": "IP address if target is an IP.",
            "org": "Organization name if known.",
            "added_at": "ISO-8601 timestamp when the target was added.",
            "notes": "Free-text notes.",
        },
    },
    "Port": {
        "description": "An open network port discovered via scanning.",
        "properties": {
            "number": "Port number (int).",
            "protocol": "Transport protocol (tcp/udp).",
            "state": "Port state (open, filtered, closed).",
            "service": "Detected service name.",
            "version": "Detected service version string.",
            "banner": "Raw banner text if captured.",
        },
    },
    "Email": {
        "description": "An email address associated with a target.",
        "properties": {
            "address": "Full email address (unique key).",
            "source": "How the email was discovered (harvester, scraper, etc.).",
            "verified": "Boolean indicating if the address has been verified.",
        },
    },
    "Subdomain": {
        "description": "A subdomain related to a target domain.",
        "properties": {
            "name": "Fully-qualified subdomain name (unique key).",
            "ip": "Resolved IP address.",
            "source": "Discovery source (harvester, dns, ct-logs, etc.).",
        },
    },
    "Camera": {
        "description": "An internet-connected camera (CCTV / IP cam).",
        "properties": {
            "ip": "Camera IP address (part of composite key).",
            "port": "Camera port (part of composite key).",
            "brand": "Manufacturer (hikvision, dahua, axis, etc.).",
            "model": "Camera model if detected.",
            "location": "Lat/lng string if geo-located.",
            "country": "Country code.",
            "city": "City name.",
            "source": "Discovery source (shodan, censys).",
            "distance_km": "Distance from search origin in km.",
        },
    },
    "Person": {
        "description": "A person linked to the investigation.",
        "properties": {
            "name": "Full name.",
            "email": "Primary email if known.",
            "role": "Job title or role.",
            "source": "How the person was identified.",
        },
    },
    "Organization": {
        "description": "A company or organization.",
        "properties": {
            "name": "Organization name.",
            "domain": "Primary domain.",
            "industry": "Industry sector.",
            "country": "Country of registration.",
        },
    },
    "Vulnerability": {
        "description": "A vulnerability found on a service or host.",
        "properties": {
            "cve": "CVE identifier (e.g. CVE-2024-1234).",
            "title": "Short vulnerability title.",
            "severity": "CVSS severity (critical, high, medium, low, info).",
            "cvss_score": "Numeric CVSS score.",
            "description": "Detailed description.",
            "source": "Discovery source (nmap scripts, shodan, manual).",
        },
    },
    "WebPage": {
        "description": "A scraped or archived web page.",
        "properties": {
            "url": "Full page URL.",
            "title": "HTML title.",
            "status_code": "HTTP status code.",
            "content_hash": "SHA-256 hash of the page body.",
            "snapshot_ts": "Wayback Machine timestamp if applicable.",
            "scraped_at": "ISO-8601 timestamp of the scrape.",
        },
    },
    "ScanResult": {
        "description": "A generic scan result blob stored as a node.",
        "properties": {
            "tool": "Tool that produced the result.",
            "scan_type": "Type of scan (quick, full, stealth, etc.).",
            "target": "Target of the scan.",
            "timestamp": "ISO-8601 timestamp.",
            "summary": "Human-readable summary.",
            "raw_data": "JSON-encoded raw output.",
        },
    },
}


RELATIONSHIP_TYPES: dict[str, dict] = {
    "HAS_PORT": {
        "description": "A Target or Subdomain has an open port.",
        "from": ["Target", "Subdomain"],
        "to": ["Port"],
    },
    "HAS_EMAIL": {
        "description": "A Target or Organization has an associated email address.",
        "from": ["Target", "Organization"],
        "to": ["Email"],
    },
    "HAS_SUBDOMAIN": {
        "description": "A Target has a subdomain.",
        "from": ["Target"],
        "to": ["Subdomain"],
    },
    "HAS_CAMERA": {
        "description": "A Target or Subdomain hosts a camera.",
        "from": ["Target", "Subdomain"],
        "to": ["Camera"],
    },
    "BELONGS_TO": {
        "description": "A Person or Email belongs to an Organization.",
        "from": ["Person", "Email"],
        "to": ["Organization"],
    },
    "WORKS_FOR": {
        "description": "A Person works for an Organization.",
        "from": ["Person"],
        "to": ["Organization"],
    },
    "OWNS": {
        "description": "An Organization or Person owns a Target domain.",
        "from": ["Organization", "Person"],
        "to": ["Target"],
    },
    "RESOLVES_TO": {
        "description": "A Subdomain resolves to a Target IP.",
        "from": ["Subdomain"],
        "to": ["Target"],
    },
    "HAS_VULNERABILITY": {
        "description": "A Port or service has a known vulnerability.",
        "from": ["Port", "Target", "Subdomain"],
        "to": ["Vulnerability"],
    },
    "LINKS_TO": {
        "description": "A WebPage links to another WebPage or Target.",
        "from": ["WebPage"],
        "to": ["WebPage", "Target", "Subdomain"],
    },
    "SCANNED_BY": {
        "description": "A Target or Subdomain was scanned, producing a ScanResult.",
        "from": ["Target", "Subdomain"],
        "to": ["ScanResult"],
    },
    "ARCHIVED_AS": {
        "description": "A Target or Subdomain has a Wayback Machine snapshot.",
        "from": ["Target", "Subdomain"],
        "to": ["WebPage"],
    },
}
