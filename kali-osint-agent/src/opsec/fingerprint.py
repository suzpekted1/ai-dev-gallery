"""Browser fingerprint generation for stealth HTTP requests."""

from __future__ import annotations

import random

from fake_useragent import UserAgent

_ua = UserAgent()

_ACCEPT_VALUES = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
]

_ACCEPT_LANGUAGE_VALUES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.5",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-US,en;q=0.9,de;q=0.7",
]

_SEC_FETCH_DEST = ["document", "empty"]
_SEC_FETCH_MODE = ["navigate", "cors", "no-cors"]
_SEC_FETCH_SITE = ["none", "same-origin", "cross-site"]


def generate_headers() -> dict[str, str]:
    """Return a dict of HTTP headers that mimic a real browser session.

    Each call produces a slightly different fingerprint by randomising the
    User-Agent string and secondary header values.
    """

    return {
        "User-Agent": _ua.random,
        "Accept": random.choice(_ACCEPT_VALUES),
        "Accept-Language": random.choice(_ACCEPT_LANGUAGE_VALUES),
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": random.choice(["1", "0"]),
        "Sec-Fetch-Dest": random.choice(_SEC_FETCH_DEST),
        "Sec-Fetch-Mode": random.choice(_SEC_FETCH_MODE),
        "Sec-Fetch-Site": random.choice(_SEC_FETCH_SITE),
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }
