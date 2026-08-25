"""Dedicated process for scheduled dispatch and analytics jobs.

Run with: ``python worker.py`` from the backend directory.
Only one worker instance should run per deployment unless the job runners are
replaced with a distributed queue and lock.
"""

import asyncio
import logging

from services.background_jobs import start_background_jobs, stop_background_jobs


async def run_worker() -> None:
    start_background_jobs()
    try:
        await asyncio.Event().wait()
    finally:
        await stop_background_jobs()


if __name__ == "__main__":
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_worker())
