from __future__ import annotations

import asyncio
import logging
import sys

import structlog
import uvicorn

from configs.settings import settings


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    )


async def start_services() -> None:
    from src.api.main import app

    config = uvicorn.Config(app, host=settings.api_host, port=settings.api_port, log_level=settings.log_level.lower())
    server = uvicorn.Server(config)

    from src.bot.bot import create_telegram_app
    telegram_app = create_telegram_app()

    if telegram_app:
        async with telegram_app:
            await telegram_app.start()
            await server.serve()
            await telegram_app.stop()
    else:
        await server.serve()


def main() -> None:
    configure_logging()
    logger = structlog.get_logger()
    logger.info("starting_kali_osint_agent", api_port=settings.api_port, proxy_mode=settings.proxy_mode.value)

    try:
        asyncio.run(start_services())
    except KeyboardInterrupt:
        logger.info("shutting_down")
        sys.exit(0)


if __name__ == "__main__":
    main()
