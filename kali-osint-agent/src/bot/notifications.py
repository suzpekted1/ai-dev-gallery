"""Telegram notification functions for agent events."""

from __future__ import annotations

import structlog
from telegram import Bot

from configs.settings import settings

logger = structlog.get_logger(__name__)

_bot: Bot | None = None


def _get_bot() -> Bot | None:
    """Lazily create the Telegram Bot instance."""
    global _bot
    if not settings.telegram_bot_token:
        return None
    if _bot is None:
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


async def send_notification(message: str, chat_id: str | None = None) -> bool:
    """Send a Markdown-formatted message to a Telegram chat.

    Parameters
    ----------
    message:
        The message text (supports Markdown formatting).
    chat_id:
        Target chat ID.  Defaults to the admin chat ID from settings.

    Returns ``True`` if the message was sent successfully.
    """
    bot = _get_bot()
    if bot is None:
        logger.debug("notifications.bot_not_configured")
        return False

    target = chat_id or settings.telegram_admin_chat_id
    if not target:
        logger.warning("notifications.no_chat_id")
        return False

    try:
        await bot.send_message(chat_id=target, text=message, parse_mode="Markdown")
        logger.info("notifications.sent", chat_id=target)
        return True
    except Exception as exc:
        logger.error("notifications.send_failed", error=str(exc), chat_id=target)
        return False


async def send_approval_request(
    approval_id: int,
    action: str,
    target: str,
    tool: str,
) -> bool:
    """Send an approval request notification to the admin."""
    message = (
        "*APPROVAL REQUIRED*\n\n"
        f"ID: `{approval_id}`\n"
        f"Tool: `{tool}`\n"
        f"Target: `{target}`\n"
        f"Action: {action}\n\n"
        f"Reply with:\n"
        f"`/approve {approval_id}` or `/deny {approval_id}`"
    )
    return await send_notification(message)


async def send_task_complete(
    task_id: int,
    target: str,
    summary: str,
) -> bool:
    """Send a task completion notification."""
    message = (
        "*Task Complete*\n\n"
        f"ID: `{task_id}`\n"
        f"Target: `{target}`\n\n"
        f"{summary[:500]}"
    )
    return await send_notification(message)


async def send_opsec_alert(alert_type: str, details: str) -> bool:
    """Send an OPSEC alert notification.

    Parameters
    ----------
    alert_type:
        Type of alert (e.g. "captcha", "rate_limit", "identity_rotated").
    details:
        Human-readable description of what triggered the alert.
    """
    message = (
        "*OPSEC ALERT*\n\n"
        f"Type: `{alert_type}`\n"
        f"Details: {details}"
    )
    return await send_notification(message)
