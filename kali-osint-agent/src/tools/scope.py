"""Scope enforcement for active scanning tools."""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

from sqlalchemy import select

from src.db.models import ScopeTarget
from src.db.postgres import async_session

logger = logging.getLogger(__name__)


class ScopeManager:
    """Check whether a given target (domain, IP, CIDR) is in scope."""

    # ------------------------------------------------------------------
    # Core query
    # ------------------------------------------------------------------

    async def is_in_scope(self, target: str) -> bool:
        """Return True if *target* matches any active scope entry."""
        targets = await self._active_targets()
        if not targets:
            return False

        for scope_entry in targets:
            entry_type = scope_entry.target_type.lower()
            entry_value = scope_entry.value

            if entry_type == "domain":
                if self._match_domain(target, entry_value):
                    return True
            elif entry_type == "ip":
                if self._match_ip(target, entry_value):
                    return True
            elif entry_type == "cidr":
                if self._match_cidr(target, entry_value):
                    return True

        return False

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    async def add_target(
        self,
        target_type: str,
        value: str,
        added_by: str | None = None,
    ) -> ScopeTarget:
        """Add a new scope target (domain, ip, or cidr)."""
        async with async_session() as session:
            entry = ScopeTarget(
                target_type=target_type.lower(),
                value=value,
                added_by=added_by,
                active=True,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            logger.info("Scope target added: %s (%s) by %s", value, target_type, added_by)
            return entry

    async def list_targets(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        """Return all scope targets, optionally filtered to active ones."""
        async with async_session() as session:
            stmt = select(ScopeTarget)
            if active_only:
                stmt = stmt.where(ScopeTarget.active.is_(True))
            stmt = stmt.order_by(ScopeTarget.created_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "target_type": r.target_type,
                    "value": r.value,
                    "added_by": r.added_by,
                    "active": r.active,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    async def remove_target(self, target_id: int) -> bool:
        """Soft-remove a scope target by setting active=False."""
        async with async_session() as session:
            stmt = select(ScopeTarget).where(ScopeTarget.id == target_id)
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()
            if entry is None:
                return False
            entry.active = False
            await session.commit()
            logger.info("Scope target deactivated: id=%d value=%s", target_id, entry.value)
            return True

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_domain(target: str, scope_domain: str) -> bool:
        """Exact match or subdomain match.

        ``example.com`` matches both ``example.com`` and ``sub.example.com``.
        """
        target = target.lower().strip().rstrip(".")
        scope_domain = scope_domain.lower().strip().rstrip(".")

        if target == scope_domain:
            return True
        # Subdomain check: target ends with .scope_domain
        if target.endswith(f".{scope_domain}"):
            return True
        return False

    @staticmethod
    def _match_ip(target: str, scope_ip: str) -> bool:
        """Exact IP address match."""
        try:
            return ipaddress.ip_address(target) == ipaddress.ip_address(scope_ip)
        except ValueError:
            return False

    @staticmethod
    def _match_cidr(target: str, scope_cidr: str) -> bool:
        """Check if *target* IP falls within a CIDR network."""
        try:
            network = ipaddress.ip_network(scope_cidr, strict=False)
            addr = ipaddress.ip_address(target)
            return addr in network
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _active_targets(self) -> list[ScopeTarget]:
        async with async_session() as session:
            stmt = select(ScopeTarget).where(ScopeTarget.active.is_(True))
            result = await session.execute(stmt)
            return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

scope_manager = ScopeManager()
