"""Scope enforcement -- ensures operations stay within approved targets."""

from __future__ import annotations

import ipaddress
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ScopeTarget

logger = structlog.get_logger(__name__)


class ScopeManager:
    """Validates that a given target (IP, domain, CIDR) falls within the
    list of approved scope targets stored in the database."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cache: list[ScopeTarget] | None = None

    async def _load_targets(self) -> list[ScopeTarget]:
        """Load active scope targets from the database."""
        if self._cache is not None:
            return self._cache
        result = await self._session.execute(
            select(ScopeTarget).where(ScopeTarget.active.is_(True))
        )
        self._cache = list(result.scalars().all())
        return self._cache

    def invalidate_cache(self) -> None:
        """Clear cached targets so the next check re-reads from the DB."""
        self._cache = None

    async def is_in_scope(self, target: str) -> bool:
        """Return ``True`` if *target* matches any active scope entry.

        Matching rules:
        - **domain**: exact match or subdomain match (``sub.example.com``
          matches scope entry ``example.com``).
        - **ip**: exact match or membership in a CIDR scope entry.
        - **cidr**: the provided CIDR must be a subnet of (or equal to)
          a CIDR scope entry.
        """
        scope_targets = await self._load_targets()

        for scope in scope_targets:
            if scope.target_type == "domain":
                if _domain_matches(target, scope.value):
                    logger.debug("scope.match", target=target, scope_value=scope.value, type="domain")
                    return True
            elif scope.target_type == "ip":
                if _ip_matches(target, scope.value):
                    logger.debug("scope.match", target=target, scope_value=scope.value, type="ip")
                    return True
            elif scope.target_type == "cidr":
                if _cidr_matches(target, scope.value):
                    logger.debug("scope.match", target=target, scope_value=scope.value, type="cidr")
                    return True

        logger.warning("scope.out_of_scope", target=target)
        return False

    async def add_target(
        self,
        value: str,
        target_type: str,
        added_by: str = "admin",
    ) -> ScopeTarget:
        """Add a new scope target to the database."""
        entry = ScopeTarget(value=value, target_type=target_type, added_by=added_by)
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        self.invalidate_cache()
        logger.info("scope.target_added", value=value, type=target_type)
        return entry

    async def deactivate_target(self, target_id: int) -> bool:
        """Mark a scope target as inactive."""
        result = await self._session.execute(
            select(ScopeTarget).where(ScopeTarget.id == target_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return False
        entry.active = False
        await self._session.commit()
        self.invalidate_cache()
        logger.info("scope.target_deactivated", target_id=target_id)
        return True


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _domain_matches(target: str, scope_domain: str) -> bool:
    """Check if *target* is exactly *scope_domain* or a subdomain of it."""
    target = target.lower().strip(".")
    scope_domain = scope_domain.lower().strip(".")

    if target == scope_domain:
        return True
    if target.endswith(f".{scope_domain}"):
        return True
    return False


def _ip_matches(target: str, scope_ip: str) -> bool:
    """Check if *target* IP equals *scope_ip* or falls within it as CIDR."""
    try:
        target_addr = ipaddress.ip_address(target)
        # scope_ip might be a single IP
        try:
            scope_addr = ipaddress.ip_address(scope_ip)
            return target_addr == scope_addr
        except ValueError:
            # scope_ip might be CIDR
            try:
                network = ipaddress.ip_network(scope_ip, strict=False)
                return target_addr in network
            except ValueError:
                return False
    except ValueError:
        return False


def _cidr_matches(target: str, scope_cidr: str) -> bool:
    """Check if *target* (IP or CIDR) falls within *scope_cidr*."""
    try:
        scope_network = ipaddress.ip_network(scope_cidr, strict=False)
    except ValueError:
        return False

    # Target might be an IP
    try:
        target_addr = ipaddress.ip_address(target)
        return target_addr in scope_network
    except ValueError:
        pass

    # Target might be a CIDR
    try:
        target_network = ipaddress.ip_network(target, strict=False)
        return target_network.subnet_of(scope_network)
    except ValueError:
        return False
