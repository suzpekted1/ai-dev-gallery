"""Passive traffic analysis for detecting adversarial responses."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)

# Window (in seconds) over which alerts are aggregated to decide whether
# to rotate identity.
_ALERT_WINDOW = 300  # 5 minutes
_ALERT_THRESHOLD = 3


class AlertType(str, Enum):
    CAPTCHA = "captcha"
    HONEYPOT = "honeypot"
    TARPIT = "tarpit"
    RATE_LIMIT = "rate_limit"


@dataclass
class RequestMetrics:
    """Telemetry captured for a single HTTP request/response cycle."""

    url: str
    status_code: int
    response_time_ms: float
    headers: dict[str, str] = field(default_factory=dict)
    body_snippet: str = ""
    timestamp: float = field(default_factory=time.time)


class TrafficAnalyzer:
    """Inspects response metrics for signs of detection or interference."""

    def __init__(self) -> None:
        self._alerts: list[tuple[float, AlertType]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, metrics: RequestMetrics) -> list[AlertType]:
        """Examine *metrics* and return a list of triggered alerts.

        The method checks for common indicators of:
        * **CAPTCHA** -- challenge pages or known CAPTCHA body markers.
        * **HONEYPOT** -- suspiciously fast 200 responses with near-empty
          bodies (canary pages).
        * **TARPIT** -- abnormally slow responses suggesting intentional
          delay.
        * **RATE_LIMIT** -- HTTP 429 or ``Retry-After`` header.
        """

        alerts: list[AlertType] = []
        now = time.time()

        # --- CAPTCHA detection ---
        captcha_markers = ["captcha", "recaptcha", "hcaptcha", "cf-challenge", "challenge-platform"]
        body_lower = metrics.body_snippet.lower()
        if any(marker in body_lower for marker in captcha_markers):
            alerts.append(AlertType.CAPTCHA)

        # --- Rate-limit detection ---
        if metrics.status_code == 429:
            alerts.append(AlertType.RATE_LIMIT)
        if "retry-after" in {k.lower() for k in metrics.headers}:
            alerts.append(AlertType.RATE_LIMIT)

        # --- Tarpit detection (response > 10 s) ---
        if metrics.response_time_ms > 10_000:
            alerts.append(AlertType.TARPIT)

        # --- Honeypot detection ---
        if (
            metrics.status_code == 200
            and metrics.response_time_ms < 50
            and len(metrics.body_snippet) < 64
        ):
            alerts.append(AlertType.HONEYPOT)

        # Record alerts for rotation heuristic.
        for alert in alerts:
            self._alerts.append((now, alert))
            logger.warning(
                "traffic_analyzer.alert",
                alert=alert.value,
                url=metrics.url,
                status=metrics.status_code,
            )

        return alerts

    def should_rotate_identity(self) -> bool:
        """Return ``True`` if enough alerts have fired within the recent
        window to warrant a Tor identity rotation."""

        now = time.time()
        cutoff = now - _ALERT_WINDOW
        # Prune old entries.
        self._alerts = [(ts, a) for ts, a in self._alerts if ts >= cutoff]
        rotate = len(self._alerts) >= _ALERT_THRESHOLD
        if rotate:
            logger.warning(
                "traffic_analyzer.rotation_recommended",
                recent_alerts=len(self._alerts),
            )
        return rotate


traffic_analyzer = TrafficAnalyzer()
