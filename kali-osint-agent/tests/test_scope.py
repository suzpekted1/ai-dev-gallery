from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.tools.scope import ScopeManager


@pytest.fixture
def scope():
    return ScopeManager()


class TestDomainMatching:
    def test_exact_domain(self, scope):
        assert scope._match_domain("example.com", "example.com")

    def test_subdomain(self, scope):
        assert scope._match_domain("sub.example.com", "example.com")

    def test_no_match(self, scope):
        assert not scope._match_domain("other.com", "example.com")

    def test_case_insensitive(self, scope):
        assert scope._match_domain("SUB.Example.COM", "example.com")


class TestIPMatching:
    def test_exact_ip(self, scope):
        assert scope._match_ip("192.168.1.1", "192.168.1.1")

    def test_different_ip(self, scope):
        assert not scope._match_ip("192.168.1.2", "192.168.1.1")

    def test_invalid_ip(self, scope):
        assert not scope._match_ip("not-an-ip", "192.168.1.1")


class TestCIDRMatching:
    def test_in_range(self, scope):
        assert scope._match_cidr("192.168.1.50", "192.168.1.0/24")

    def test_out_of_range(self, scope):
        assert not scope._match_cidr("10.0.0.1", "192.168.1.0/24")

    def test_broad_cidr(self, scope):
        assert scope._match_cidr("10.0.5.1", "10.0.0.0/16")
