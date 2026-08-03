from __future__ import annotations

import structlog
from telegram.ext import ApplicationBuilder, CommandHandler

from configs.settings import settings
from src.bot.handlers import (
    approve_handler, cctv_handler, deny_handler, identity_handler,
    opsec_handler, scan_handler, scope_handler, start_handler,
    status_handler, wayback_handler,
)

logger = structlog.get_logger()


def create_telegram_app():
    if not settings.telegram_bot_token:
        logger.warning("telegram_bot_token_not_set")
        return None

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()
    for name, handler in [("start", start_handler), ("scan", scan_handler), ("status", status_handler), ("approve", approve_handler), ("deny", deny_handler), ("cctv", cctv_handler), ("wayback", wayback_handler), ("scope", scope_handler), ("opsec", opsec_handler), ("identity", identity_handler)]:
        app.add_handler(CommandHandler(name, handler))
    return app
