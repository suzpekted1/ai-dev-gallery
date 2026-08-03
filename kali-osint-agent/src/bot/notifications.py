from __future__ import annotations

import structlog
from telegram import Bot

from configs.settings import settings

logger = structlog.get_logger()
_bot: Bot | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


async def send_notification(message: str, chat_id: str | None = None) -> bool:
    target = chat_id or settings.telegram_admin_chat_id
    if not target or not settings.telegram_bot_token:
        return False
    try:
        await get_bot().send_message(chat_id=target, text=message, parse_mode="Markdown")
        return True
    except Exception as e:
        logger.error("telegram_send_failed", error=str(e))
        return False


async def send_approval_request(approval_id: int, action: str, target: str, tool: str) -> bool:
    return await send_notification(f"*APPROVAL REQUIRED*\n\nID: `{approval_id}`\nTool: `{tool}`\nTarget: `{target}`\nAction: {action}\n\n`/approve {approval_id}` or `/deny {approval_id}`")


async def send_task_complete(task_id: int, target: str, summary: str) -> bool:
    return await send_notification(f"*Task Complete*\n\nID: `{task_id}`\nTarget: `{target}`\n{summary[:500]}")
