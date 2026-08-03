"""Base class for all scoped OSINT tools."""

from __future__ import annotations

import logging
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from src.db.models import AuditLog
from src.db.postgres import async_session

logger = logging.getLogger(__name__)


class ScopedTool(ABC):
    """Abstract base for every tool the agent can invoke.

    Subclasses must set the class-level attributes and implement
    :meth:`_execute`.  The public :meth:`run` method enforces scope
    validation for active scans, writes an audit-log entry, and catches
    unhandled exceptions so they never crash the agent loop.
    """

    name: str = "unnamed_tool"
    requires_approval: bool = False
    is_active_scan: bool = False

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Validate scope, execute, log, and return the result dict."""
        from src.tools.scope import scope_manager  # deferred to avoid circular import

        # Scope gate for active scans
        if self.is_active_scan:
            in_scope = await scope_manager.is_in_scope(target)
            if not in_scope:
                msg = f"Target {target!r} is not in scope for active tool {self.name!r}"
                logger.warning(msg)
                await self._log_audit(
                    action="scope_denied",
                    target=target,
                    approved=False,
                    details={"reason": msg, **kwargs},
                )
                return {"success": False, "error": msg}

        # Execute
        try:
            result = await self._execute(target=target, **kwargs)
            await self._log_audit(
                action="tool_executed",
                target=target,
                approved=True,
                details={"kwargs": _safe_serializable(kwargs), "summary": _truncate(str(result), 500)},
            )
            return {"success": True, "data": result}
        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("Tool %s failed on target %s", self.name, target)
            await self._log_audit(
                action="tool_failed",
                target=target,
                approved=None,
                details={"error": str(exc), "traceback": tb, **kwargs},
            )
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Abstract implementation hook
    # ------------------------------------------------------------------

    @abstractmethod
    async def _execute(self, *, target: str, **kwargs: Any) -> Any:
        """Run the actual tool logic.  Subclasses must implement this."""
        ...

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    async def _log_audit(
        self,
        *,
        action: str,
        target: str,
        approved: bool | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write a row to the audit_log table."""
        try:
            async with async_session() as session:
                entry = AuditLog(
                    action=action,
                    tool=self.name,
                    target=target,
                    user=None,
                    approved=approved,
                    details=details,
                    timestamp=datetime.now(timezone.utc),
                )
                session.add(entry)
                await session.commit()
        except Exception:
            # Audit logging must never break the tool pipeline
            logger.exception("Failed to write audit log for %s", self.name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _safe_serializable(obj: Any) -> Any:
    """Best-effort conversion of kwargs to JSON-safe types."""
    try:
        import json
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)
