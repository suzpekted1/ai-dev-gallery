"""Telegram bot command handlers."""

from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from configs.settings import settings

logger = structlog.get_logger(__name__)

# Internal API base URL
_API_BASE = f"http://localhost:{settings.fastapi_port}"


def _is_admin(update: Update) -> bool:
    """Check whether the message sender is the configured admin."""
    if not settings.telegram_admin_chat_id:
        return False
    return str(update.effective_chat.id) == settings.telegram_admin_chat_id


async def _get_auth_token() -> str:
    """Obtain a JWT token from the internal API."""
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_API_BASE}/api/auth/login",
            json={"username": "admin", "password": "changeme"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    if not _is_admin(update):
        return
    help_text = (
        "*Kali OSINT Agent*\n\n"
        "Commands:\n"
        "/scan <target> - Start OSINT scan\n"
        "/status [task\\_id] - Show task status\n"
        "/approve <id> - Approve pending action\n"
        "/deny <id> - Deny pending action\n"
        "/cctv <lat> <lng> [radius] - Discover cameras\n"
        "/wayback <url> - Search Wayback Machine\n"
        "/scope - List scope targets\n"
        "/opsec - Show OPSEC status\n"
        "/identity - Request new Tor identity"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /scan
# ---------------------------------------------------------------------------


async def scan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new OSINT task via the internal API."""
    if not _is_admin(update) or not context.args:
        await update.message.reply_text("Usage: /scan <target>")
        return

    import httpx

    target = context.args[0]
    task_type = context.args[1] if len(context.args) > 1 else "osint"

    try:
        token = await _get_auth_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_API_BASE}/api/tasks",
                json={"task_type": task_type, "target": target},
                headers=_auth_headers(token),
            )
            resp.raise_for_status()
            data = resp.json()
            await update.message.reply_text(
                f"Task `{data['id']}` created for `{target}`",
                parse_mode="Markdown",
            )
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show task status -- specific task or recent list."""
    if not _is_admin(update):
        return

    import httpx

    try:
        token = await _get_auth_token()
        async with httpx.AsyncClient() as client:
            if context.args:
                resp = await client.get(
                    f"{_API_BASE}/api/tasks/{context.args[0]}",
                    headers=_auth_headers(token),
                )
                resp.raise_for_status()
                d = resp.json()
                await update.message.reply_text(
                    f"`{d['id']}` | `{d['target']}` | *{d['status']}*",
                    parse_mode="Markdown",
                )
            else:
                resp = await client.get(
                    f"{_API_BASE}/api/tasks?limit=5",
                    headers=_auth_headers(token),
                )
                resp.raise_for_status()
                tasks = resp.json()
                lines = [f"`{t['id']}` | `{t['target']}` | *{t['status']}*" for t in tasks]
                await update.message.reply_text(
                    "\n".join(lines) or "No tasks found",
                    parse_mode="Markdown",
                )
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


# ---------------------------------------------------------------------------
# /approve & /deny
# ---------------------------------------------------------------------------


async def approve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a pending action via the internal API."""
    if not _is_admin(update) or not context.args:
        await update.message.reply_text("Usage: /approve <approval\\_id>")
        return

    import httpx

    try:
        token = await _get_auth_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_API_BASE}/api/approvals/{context.args[0]}",
                json={"approved": True},
                headers=_auth_headers(token),
            )
            resp.raise_for_status()
            await update.message.reply_text(
                f"Approved `{context.args[0]}`", parse_mode="Markdown",
            )
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def deny_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deny a pending action via the internal API."""
    if not _is_admin(update) or not context.args:
        await update.message.reply_text("Usage: /deny <approval\\_id>")
        return

    import httpx

    try:
        token = await _get_auth_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_API_BASE}/api/approvals/{context.args[0]}",
                json={"approved": False},
                headers=_auth_headers(token),
            )
            resp.raise_for_status()
            await update.message.reply_text(
                f"Denied `{context.args[0]}`", parse_mode="Markdown",
            )
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


# ---------------------------------------------------------------------------
# /cctv
# ---------------------------------------------------------------------------


async def cctv_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Discover CCTV cameras near given coordinates."""
    if not _is_admin(update) or len(context.args) < 2:
        await update.message.reply_text("Usage: /cctv <lat> <lng> [radius\\_km]")
        return

    from src.tools.cctv_tool import cctv_tool

    try:
        lat = float(context.args[0])
        lng = float(context.args[1])
        radius = float(context.args[2]) if len(context.args) > 2 else 10.0

        result = await cctv_tool(lat=lat, lng=lng, radius_km=radius)
        total = result.get("total_found", 0)
        cameras = result.get("cameras", [])[:10]
        lines = [
            f"`{c['ip']}:{c.get('port', '?')}` - {c.get('distance_km', '?')} km"
            for c in cameras
        ]
        text = f"*{total} cameras found:*\n" + "\n".join(lines) if lines else "No cameras found"
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


# ---------------------------------------------------------------------------
# /wayback
# ---------------------------------------------------------------------------


async def wayback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search the Wayback Machine for a URL."""
    if not _is_admin(update) or not context.args:
        await update.message.reply_text("Usage: /wayback <url>")
        return

    from src.tools.wayback_tool import wayback_tool

    try:
        result = await wayback_tool(url=context.args[0])
        total = result.get("total", 0)
        oldest = result.get("oldest", "N/A")
        newest = result.get("newest", "N/A")
        await update.message.reply_text(
            f"*{total} snapshots* for `{context.args[0]}`\n"
            f"Oldest: `{oldest}`\nNewest: `{newest}`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


# ---------------------------------------------------------------------------
# /scope
# ---------------------------------------------------------------------------


async def scope_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List active scope targets."""
    if not _is_admin(update):
        return

    from src.tools.scope import scope_manager

    try:
        targets = await scope_manager.list_targets()
        if not targets:
            await update.message.reply_text("Scope is empty")
            return
        lines = [f"`{t['target_type']}`: `{t['value']}`" for t in targets]
        await update.message.reply_text(
            "*Scope Targets:*\n" + "\n".join(lines),
            parse_mode="Markdown",
        )
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


# ---------------------------------------------------------------------------
# /opsec
# ---------------------------------------------------------------------------


async def opsec_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current OPSEC status."""
    if not _is_admin(update):
        return

    from src.opsec.proxy_manager import proxy_manager
    from src.opsec.tor_controller import tor_controller

    tor_connected = tor_controller.is_connected()
    exit_ip = "N/A"
    if tor_connected:
        try:
            exit_ip = await tor_controller.get_exit_ip()
        except Exception:
            exit_ip = "error"

    await update.message.reply_text(
        f"*OPSEC Status*\n"
        f"Mode: `{proxy_manager._mode.value}`\n"
        f"Tor: {'Connected' if tor_connected else 'Disconnected'}\n"
        f"Exit IP: `{exit_ip}`",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# /identity
# ---------------------------------------------------------------------------


async def identity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Request a new Tor identity."""
    if not _is_admin(update):
        return

    from src.opsec.tor_controller import tor_controller

    try:
        tor_controller.new_identity()
        new_ip = await tor_controller.get_exit_ip()
        await update.message.reply_text(
            f"New identity acquired\nExit IP: `{new_ip}`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        await update.message.reply_text(f"Failed to rotate identity: {exc}")
