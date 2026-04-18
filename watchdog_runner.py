"""
Watchdog Runner - Standalone watchdog process for PM2.

This script runs the watchdog as a separate process that monitors
the main FTE processes and restarts them if they crash.

Run with: python watchdog_runner.py
Or with PM2: pm2 start ecosystem.config.js (includes fte-watchdog)
"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure local imports work
sys.path.insert(0, str(Path(__file__).parent))

from watchdog import Watchdog, write_heartbeat

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


async def main():
    """Run the watchdog process."""
    vault_path = Path("AI_Employee_Vault")
    logs_path = vault_path / "Logs"

    # Write initial heartbeat
    write_heartbeat("watchdog")

    # Create and run watchdog
    watchdog = Watchdog(
        vault_path=vault_path,
        logs_path=logs_path,
        check_interval=60.0,  # 60 seconds as specified
        auto_restart=True,
    )

    await watchdog.initialize()

    # Heartbeat loop
    async def heartbeat_loop():
        while True:
            write_heartbeat("watchdog")
            await asyncio.sleep(30)

    # Run watchdog and heartbeat together
    heartbeat_task = asyncio.create_task(heartbeat_loop())

    try:
        await watchdog.run()
    except KeyboardInterrupt:
        logger.info("Watchdog interrupted")
    finally:
        heartbeat_task.cancel()
        logger.info("Watchdog stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
