"""
Perception Daemon
Standalone entry point for the sensing Docker container.
Connects to core via HTTP/WebSocket and publishes CSI events.
"""

import asyncio
import logging
import os

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    from doppelganger.core.config import get_settings
    from doppelganger.core.event_bus import bus
    from doppelganger.perception.pipeline import PerceptionPipeline

    settings = get_settings()
    await bus.start()

    pipeline = PerceptionPipeline(bus, settings)
    await pipeline.start()

    logger.info("Perception daemon running. CTRL+C to stop.")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await pipeline.stop()
        await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
