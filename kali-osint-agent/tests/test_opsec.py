"""Tests for ProxyManager modes, failure tracking, rotation, and TrafficAnalyzer."""

from __future__ import annotations

import time

import pytest

from configs.settings import ProxyMode
from src.opsec.traffic_analyzer import AlertType, RequestMetrics, TrafficAnalyzer


# ===========================================================================
# ProxyManager tests
# ===========================================================================


class TestProxyManager:
    """Test each proxy mode returns the correct proxy URL."""

    def _make_manager(self):
        from src.opsec.proxy_manager import ProxyManager

        return ProxyManager()

    def test_stealth_mode_returns_tor_proxy(self):
        pm = self._make_manager()
        pm._mode = ProxyMode.STEALTH
        proxy = pm.get_proxy()
        assert proxy is not None
        assert "socks5://" in proxy
        assert "9050" in proxy

    def test_fast_mode_returns_socks5(self):
        pm = self._make_manager()
        pm._mode = ProxyMode.FAST
        proxy = pm.get_proxy()
        # May return None if pool is empty, otherwise should be socks5
        if proxy is not None:
            assert "socks5://" in proxy

    def test_direct_mode_returns_none(self):
        pm = self._make_manager()
        pm._mode = ProxyMode.DIRECT
        assert pm.get_proxy() is None

    def test_rotating_mode_returns_proxy(self):
        pm = self._make_manager()
        pm._mode = ProxyMode.ROTATING
        proxy = pm.get_proxy()
        # Rotating cycles through all available proxies
        if proxy is not None:
            assert "socks5://" in proxy

    def test_whonix_mode_returns_gateway(self):
        pm = self._make_manager()
        pm._mode = ProxyMode.WHONIX
        proxy = pm.get_proxy()
        assert proxy is not None
        assert "10.152.152.10" in proxy

    def test_failure_tracking(self):
        pm = self._make_manager()
        pm.report_failure("http://example.com")
        pm.report_failure("http://example.com")
        assert pm._failures["http://example.com"] == 2

    def test_failure_reset(self):
        pm = self._make_manager()
        pm.report_failure("http://example.com")
        pm.reset_failures()
        assert len(pm._failures) == 0

    def test_rotating_cycles(self):
        pm = self._make_manager()
        pm._mode = ProxyMode.ROTATING
        if pm._rotating_cycle is not None:
            proxies = [pm.get_proxy() for _ in range(5)]
            # Should not all be None
            assert any(p is not None for p in proxies)

    def test_httpx_proxy_config_direct(self):
        pm = self._make_manager()
        pm._mode = ProxyMode.DIRECT
        config = pm.get_httpx_proxy_config()
        assert config == {}

    def test_httpx_proxy_config_stealth(self):
        pm = self._make_manager()
        pm._mode = ProxyMode.STEALTH
        config = pm.get_httpx_proxy_config()
        assert "proxy" in config
        assert "socks5://" in config["proxy"]


# ===========================================================================
# TrafficAnalyzer tests
# ===========================================================================


@pytest.fixture
def analyzer():
    """Create a fresh TrafficAnalyzer for each test."""
    return TrafficAnalyzer()


class TestTrafficAnalyzerCaptcha:
    def test_captcha_detected_in_body(self, analyzer):
        metrics = RequestMetrics(
            url="http://test.com",
            status_code=200,
            response_time_ms=500,
            body_snippet="Please solve the captcha to continue",
        )
        alerts = analyzer.analyze(metrics)
        assert AlertType.CAPTCHA in alerts

    def test_recaptcha_detected(self, analyzer):
        metrics = RequestMetrics(
            url="http://test.com",
            status_code=200,
            response_time_ms=500,
            body_snippet="<div class='g-recaptcha'></div>",
        )
        alerts = analyzer.analyze(metrics)
        assert AlertType.CAPTCHA in alerts

    def test_no_captcha_in_normal_page(self, analyzer):
        metrics = RequestMetrics(
            url="http://test.com",
            status_code=200,
            response_time_ms=200,
            body_snippet="Welcome to our normal website with lots of content here",
        )
        alerts = analyzer.analyze(metrics)
        assert AlertType.CAPTCHA not in alerts


class TestTrafficAnalyzerRateLimit:
    def test_429_detected(self, analyzer):
        metrics = RequestMetrics(
            url="http://test.com",
            status_code=429,
            response_time_ms=100,
        )
        alerts = analyzer.analyze(metrics)
        assert AlertType.RATE_LIMIT in alerts

    def test_retry_after_header_detected(self, analyzer):
        metrics = RequestMetrics(
            url="http://test.com",
            status_code=200,
            response_time_ms=100,
            headers={"Retry-After": "60"},
        )
        alerts = analyzer.analyze(metrics)
        assert AlertType.RATE_LIMIT in alerts


class TestTrafficAnalyzerTarpit:
    def test_slow_response_detected(self, analyzer):
        metrics = RequestMetrics(
            url="http://test.com",
            status_code=200,
            response_time_ms=15000,
            body_snippet="some content",
        )
        alerts = analyzer.analyze(metrics)
        assert AlertType.TARPIT in alerts

    def test_normal_response_not_tarpit(self, analyzer):
        metrics = RequestMetrics(
            url="http://test.com",
            status_code=200,
            response_time_ms=500,
            body_snippet="normal page content",
        )
        alerts = analyzer.analyze(metrics)
        assert AlertType.TARPIT not in alerts


class TestTrafficAnalyzerHoneypot:
    def test_fast_empty_response_detected(self, analyzer):
        metrics = RequestMetrics(
            url="http://test.com",
            status_code=200,
            response_time_ms=10,
            body_snippet="OK",
        )
        alerts = analyzer.analyze(metrics)
        assert AlertType.HONEYPOT in alerts


class TestShouldRotateIdentity:
    def test_should_rotate_after_threshold_alerts(self, analyzer):
        """After >= 3 alerts in the window, rotation should be recommended."""
        for _ in range(4):
            metrics = RequestMetrics(
                url="http://test.com",
                status_code=429,
                response_time_ms=100,
                timestamp=time.time(),
            )
            analyzer.analyze(metrics)
        assert analyzer.should_rotate_identity() is True

    def test_no_rotate_when_clean(self, analyzer):
        metrics = RequestMetrics(
            url="http://test.com",
            status_code=200,
            response_time_ms=200,
            body_snippet="Normal page with sufficient content to avoid honeypot detection",
        )
        analyzer.analyze(metrics)
        assert analyzer.should_rotate_identity() is False

    def test_old_alerts_pruned(self, analyzer):
        """Alerts older than the window should be pruned."""
        old_time = time.time() - 400  # older than 300s window
        analyzer._alerts = [(old_time, AlertType.RATE_LIMIT)] * 5
        assert analyzer.should_rotate_identity() is False
