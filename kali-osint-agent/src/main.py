"""Application entry point -- starts FastAPI and Telegram bot concurrently."""

from __future__ import annotations

import asyncio
import logging
import sys

import structlog
import uvicorn

from configs.settings import settings


def configure_logging() -> None:
    """Set up structlog with ISO timestamps and console rendering."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def start_services() -> None:
    """Start both the FastAPI server and the Telegram bot.

    If the Telegram bot token is not configured, only the FastAPI
    server is started.
    """
    from src.api.main import app

    config = uvicorn.Config(
        app,
        host=settings.fastapi_host,
        port=settings.fastapi_port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)

    from src.bot.bot import create_telegram_app

    telegram_app = create_telegram_app()

    if telegram_app is not None:
        # Run both FastAPI and Telegram bot concurrently
        async with telegram_app:
            await telegram_app.start()
            try:
                await server.serve()
            finally:
                await telegram_app.stop()
    else:
        # Telegram not configured -- run FastAPI only
        await server.serve()


def main() -> None:
    """Configure logging and launch all services."""
    configure_logging()
    logger = structlog.get_logger(__name__)
    logger.info(
        "starting_kali_osint_agent",
        host=settings.fastapi_host,
        port=settings.fastapi_port,
        proxy_mode=settings.proxy_mode.value,
        environment=settings.environment.value,
    )

    try:
        asyncio.run(start_services())
    except KeyboardInterrupt:
        logger.info("shutting_down")
        sys.exit(0)


if __name__ == "__main__":
    main()
