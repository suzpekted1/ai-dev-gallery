from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from configs.settings import settings

logger = structlog.get_logger()


def _is_admin(update: Update) -> bool:
    return str(update.effective_chat.id) == settings.telegram_admin_chat_id


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    await update.message.reply_text("*Kali OSINT Agent*\n\n/scan /status /approve /deny /cctv /wayback /scope /opsec /identity", parse_mode="Markdown")


async def scan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update) or not context.args:
        return
    import httpx
    async with httpx.AsyncClient() as c:
        tok = (await c.post(f"http://localhost:{settings.api_port}/api/auth/login", json={"username": "admin", "password": "changeme"})).json()["access_token"]
        data = (await c.post(f"http://localhost:{settings.api_port}/api/tasks", json={"task_type": "osint", "target": context.args[0]}, headers={"Authorization": f"Bearer {tok}"})).json()
        await update.message.reply_text(f"Task `{data['id']}` created", parse_mode="Markdown")


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    import httpx
    async with httpx.AsyncClient() as c:
        tok = (await c.post(f"http://localhost:{settings.api_port}/api/auth/login", json={"username": "admin", "password": "changeme"})).json()["access_token"]
        if context.args:
            d = (await c.get(f"http://localhost:{settings.api_port}/api/tasks/{context.args[0]}", headers={"Authorization": f"Bearer {tok}"})).json()
            await update.message.reply_text(f"`{d['id']}` {d['target']} *{d['status']}*", parse_mode="Markdown")
        else:
            tasks = (await c.get(f"http://localhost:{settings.api_port}/api/tasks?limit=5", headers={"Authorization": f"Bearer {tok}"})).json()
            lines = [f"`{t['id']}` {t['target']} *{t['status']}*" for t in tasks]
            await update.message.reply_text("\n".join(lines) or "No tasks", parse_mode="Markdown")


async def approve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update) or not context.args:
        return
    import httpx
    async with httpx.AsyncClient() as c:
        tok = (await c.post(f"http://localhost:{settings.api_port}/api/auth/login", json={"username": "admin", "password": "changeme"})).json()["access_token"]
        await c.post(f"http://localhost:{settings.api_port}/api/approvals/{context.args[0]}", json={"approved": True}, headers={"Authorization": f"Bearer {tok}"})
        await update.message.reply_text(f"Approved `{context.args[0]}`", parse_mode="Markdown")


async def deny_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update) or not context.args:
        return
    import httpx
    async with httpx.AsyncClient() as c:
        tok = (await c.post(f"http://localhost:{settings.api_port}/api/auth/login", json={"username": "admin", "password": "changeme"})).json()["access_token"]
        await c.post(f"http://localhost:{settings.api_port}/api/approvals/{context.args[0]}", json={"approved": False}, headers={"Authorization": f"Bearer {tok}"})
        await update.message.reply_text(f"Denied `{context.args[0]}`", parse_mode="Markdown")


async def cctv_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update) or len(context.args) < 2:
        return
    from src.tools.cctv_discovery import cctv_tool
    result = await cctv_tool.run("", lat=float(context.args[0]), lng=float(context.args[1]), radius_km=int(context.args[2]) if len(context.args) > 2 else 5)
    cams = result.get("cameras", [])[:10]
    lines = [f"`{c['ip']}` {c.get('distance_m', '?')}m" for c in cams]
    await update.message.reply_text(f"*{result.get('cameras_found', 0)} cameras:*\n" + "\n".join(lines) if lines else "None found", parse_mode="Markdown")


async def wayback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update) or not context.args:
        return
    from src.tools.wayback_tool import wayback_tool
    result = await wayback_tool.run(context.args[0])
    total = result.get("total", 0)
    await update.message.reply_text(f"*{total} snapshots* for `{context.args[0]}`", parse_mode="Markdown")


async def scope_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    from src.tools.scope import scope_manager
    targets = await scope_manager.list_targets()
    lines = [f"`{t.target_type}`: {t.value}" for t in targets]
    await update.message.reply_text("*Scope:*\n" + "\n".join(lines) if lines else "Empty scope", parse_mode="Markdown")


async def opsec_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    from src.opsec.proxy_manager import proxy_manager
    from src.opsec.tor_controller import tor_controller
    await update.message.reply_text(f"*OPSEC*\nMode: `{proxy_manager.mode.value}`\nTor: {'Yes' if tor_controller.is_connected() else 'No'}\nExit: `{tor_controller.get_exit_ip() or '?'}`", parse_mode="Markdown")


async def identity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    from src.opsec.tor_controller import tor_controller
    ok = tor_controller.new_identity()
    await update.message.reply_text(f"New identity: `{tor_controller.get_exit_ip()}`" if ok else "Failed", parse_mode="Markdown")
