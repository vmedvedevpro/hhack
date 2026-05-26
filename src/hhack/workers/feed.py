import asyncio

from loguru import logger

from hhack.config import settings
from hhack.logging import setup_logging


async def _run() -> None:
    setup_logging(settings.log_level)
    logger.bind(worker="feed").info("started (Phase 0 stub)")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
