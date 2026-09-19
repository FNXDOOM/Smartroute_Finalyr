"""Run scheduled jobs; single instance only."""

import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from database import run_startup_migrations
from services.background_jobs import start_background_jobs, stop_background_jobs


async def run_worker() -> None:
    """Run background jobs until the worker is stopped."""
    try:
        run_startup_migrations()
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).error("Startup schema backfill failed: %s", exc)
    start_background_jobs()
    try:
        await asyncio.Event().wait()
    finally:
        await stop_background_jobs()


if __name__ == "__main__":
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_worker())
