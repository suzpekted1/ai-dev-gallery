"""Tests for ScopeManager: domain matching, IP matching, CIDR matching."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.tools.scope import ScopeManager


@pytest.fixture
def scope():
    """Create a ScopeManager instance for testing static methods."""
    return ScopeManager()


# ---------------------------------------------------------------------------
# Domain matching
# ---------------------------------------------------------------------------


class TestDomainMatching:
    def test_exact_domain_match(self, scope):
        assert scope._match_domain("example.com", "example.com") is True

    def test_subdomain_match(self, scope):
        assert scope._match_domain("sub.example.com", "example.com") is True

    def test_deep_subdomain_match(self, scope):
        assert scope._match_domain("a.b.c.example.com", "example.com") is True

    def test_different_domain_no_match(self, scope):
        assert scope._match_domain("other.com", "example.com") is False

    def test_partial_name_no_match(self, scope):
        """'notexample.com' should NOT match 'example.com'."""
        assert scope._match_domain("notexample.com", "example.com") is False

    def test_case_insensitive(self, scope):
        assert scope._match_domain("SUB.Example.COM", "example.com") is True

    def test_trailing_dot_handling(self, scope):
        assert scope._match_domain("example.com.", "example.com.") is True


# ---------------------------------------------------------------------------
# IP matching
# ---------------------------------------------------------------------------


class TestIPMatching:
    def test_exact_ip_match(self, scope):
        assert scope._match_ip("192.168.1.1", "192.168.1.1") is True

    def test_different_ip_no_match(self, scope):
        assert scope._match_ip("192.168.1.2", "192.168.1.1") is False

    def test_invalid_target_no_match(self, scope):
        assert scope._match_ip("not-an-ip", "192.168.1.1") is False

    def test_invalid_scope_ip_no_match(self, scope):
        assert scope._match_ip("192.168.1.1", "not-an-ip") is False


# ---------------------------------------------------------------------------
# CIDR matching
# ---------------------------------------------------------------------------


class TestCIDRMatching:
    def test_ip_in_cidr_range(self, scope):
        assert scope._match_cidr("192.168.1.50", "192.168.1.0/24") is True

    def test_ip_outside_cidr_range(self, scope):
        assert scope._match_cidr("10.0.0.1", "192.168.1.0/24") is False

    def test_broad_cidr(self, scope):
        assert scope._match_cidr("10.0.5.1", "10.0.0.0/16") is True

    def test_host_cidr(self, scope):
        """A /32 should match exactly one IP."""
        assert scope._match_cidr("10.0.0.1", "10.0.0.1/32") is True
        assert scope._match_cidr("10.0.0.2", "10.0.0.1/32") is False

    def test_invalid_target_no_match(self, scope):
        assert scope._match_cidr("not-valid", "192.168.1.0/24") is False

    def test_invalid_cidr_no_match(self, scope):
        assert scope._match_cidr("192.168.1.1", "not-a-cidr") is False


# ---------------------------------------------------------------------------
# Out-of-scope rejection (integration-style with mocked DB)
# ---------------------------------------------------------------------------


class TestIsInScope:
    @pytest.mark.asyncio
    async def test_out_of_scope_rejection(self, scope):
        """Targets not matching any scope entry should be rejected."""
        mock_target = MagicMock()
        mock_target.target_type = "domain"
        mock_target.value = "allowed.com"
        mock_target.active = True

        with patch.object(scope, "_active_targets", new_callable=AsyncMock, return_value=[mock_target]):
            # This domain is not in scope
            assert await scope.is_in_scope("evil.org") is False
            # This domain IS in scope
            assert await scope.is_in_scope("sub.allowed.com") is True
            assert await scope.is_in_scope("allowed.com") is True

    @pytest.mark.asyncio
    async def test_empty_scope_rejects_all(self, scope):
        """When no scope entries exist, everything is out of scope."""
        with patch.object(scope, "_active_targets", new_callable=AsyncMock, return_value=[]):
            assert await scope.is_in_scope("example.com") is False
