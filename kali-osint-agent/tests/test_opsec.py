from __future__ import annotations

import time
import pytest

from src.opsec.traffic_analyzer import RequestMetrics, TrafficAnalyzer


@pytest.fixture
def analyzer():
    return TrafficAnalyzer()


class TestTrafficAnalyzer:
    def test_captcha_detection(self, analyzer):
        m = RequestMetrics(url="http://test.com", status_code=200, response_time_ms=100, headers={}, body_snippet="please solve the captcha below")
        alerts = analyzer.analyze(m)
        assert "captcha_detected" in alerts

    def test_rate_limit_detection(self, analyzer):
        m = RequestMetrics(url="http://test.com", status_code=429, response_time_ms=100, headers={}, body_snippet="")
        alerts = analyzer.analyze(m)
        assert "rate_limited" in alerts

    def test_tarpit_detection(self, analyzer):
        m = RequestMetrics(url="http://test.com", status_code=200, response_time_ms=35000, headers={}, body_snippet="")
        alerts = analyzer.analyze(m)
        assert "tarpit_detected" in alerts

    def test_honeypot_detection(self, analyzer):
        m = RequestMetrics(url="http://test.com", status_code=200, response_time_ms=100, headers={"server": "honeypot-server"}, body_snippet="")
        alerts = analyzer.analyze(m)
        assert "honeypot_suspected" in alerts

    def test_should_rotate_after_alerts(self, analyzer):
        for _ in range(4):
            m = RequestMetrics(url="http://test.com", status_code=429, response_time_ms=100, headers={}, body_snippet="", timestamp=time.time())
            analyzer.analyze(m)
        assert analyzer.should_rotate_identity()

    def test_no_rotate_when_clean(self, analyzer):
        m = RequestMetrics(url="http://test.com", status_code=200, response_time_ms=100, headers={}, body_snippet="normal page")
        analyzer.analyze(m)
        assert not analyzer.should_rotate_identity()


class TestProxyManager:
    def test_stealth_returns_tor(self):
        from src.opsec.proxy_manager import ProxyManager
        pm = ProxyManager()
        from configs.settings import ProxyMode
        pm.mode = ProxyMode.STEALTH
        proxy = pm.get_proxy()
        assert "socks5://" in proxy
        assert "9050" in proxy

    def test_direct_returns_none(self):
        from src.opsec.proxy_manager import ProxyManager
        pm = ProxyManager()
        from configs.settings import ProxyMode
        pm.mode = ProxyMode.DIRECT
        assert pm.get_proxy() is None

    def test_whonix_returns_gateway(self):
        from src.opsec.proxy_manager import ProxyManager
        pm = ProxyManager()
        from configs.settings import ProxyMode
        pm.mode = ProxyMode.WHONIX
        proxy = pm.get_proxy()
        assert "10.152.152.10" in proxy
