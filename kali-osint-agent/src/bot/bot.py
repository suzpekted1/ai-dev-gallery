"""Telegram bot application setup."""

from __future__ import annotations

import structlog
from telegram.ext import ApplicationBuilder, CommandHandler

from configs.settings import settings
from src.bot.handlers import (
    approve_handler,
    cctv_handler,
    deny_handler,
    identity_handler,
    opsec_handler,
    scan_handler,
    scope_handler,
    start_handler,
    status_handler,
    wayback_handler,
)

logger = structlog.get_logger(__name__)


def create_telegram_app():
    """Create and configure the Telegram bot application.

    Returns ``None`` if the bot token is not set in settings, allowing
    the system to run without Telegram integration.
    """
    if not settings.telegram_bot_token:
        logger.warning("telegram.bot_token_not_configured")
        return None

    logger.info("telegram.building_app")
    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Register all command handlers
    commands = [
        ("start", start_handler),
        ("scan", scan_handler),
        ("status", status_handler),
        ("approve", approve_handler),
        ("deny", deny_handler),
        ("cctv", cctv_handler),
        ("wayback", wayback_handler),
        ("scope", scope_handler),
        ("opsec", opsec_handler),
        ("identity", identity_handler),
    ]

    for name, handler in commands:
        app.add_handler(CommandHandler(name, handler))

    logger.info("telegram.app_configured", commands=len(commands))
    return app
