"""
Base Watcher - Abstract base class for polling-based watchers.

Provides core polling logic with exponential backoff, error recovery,
and lifecycle management.
"""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class BaseWatcher(ABC):
    """
    Abstract base class for all watchers in the Digital FTE system.

    Implements the polling loop with configurable intervals, exponential
    backoff for error recovery, and graceful shutdown handling.
    """

    def __init__(
        self,
        poll_interval: float = 120.0,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        jitter: bool = True,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        """
        Initialize the watcher.

        Args:
            poll_interval: Seconds between polls (default 2 minutes)
            max_retries: Maximum consecutive failures before stopping
            initial_backoff: Initial backoff duration in seconds
            max_backoff: Maximum backoff duration in seconds
            jitter: Add random jitter to backoff to avoid thundering herd
            on_error: Optional callback for error handling
        """
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.jitter = jitter
        self.on_error = on_error

        self._running = False
        self._consecutive_failures = 0
        self._current_backoff = initial_backoff
        self._last_poll_time: Optional[datetime] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the watcher name for logging."""
        pass

    @abstractmethod
    async def poll(self) -> bool:
        """
        Perform a single poll operation.

        Returns:
            True if poll succeeded, False if it failed

        Raises:
            Exception: Any exception during polling
        """
        pass

    @abstractmethod
    async def startup(self) -> None:
        """
        Initialize resources before polling begins.

        Called once when the watcher starts.
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Cleanup resources after polling ends.

        Called once when the watcher stops.
        """
        pass

    def calculate_backoff(self) -> float:
        """
        Calculate the current backoff duration with optional jitter.

        Uses exponential backoff: backoff = min(initial * 2^failures, max)
        """
        base_backoff = min(
            self.initial_backoff * (2 ** self._consecutive_failures),
            self.max_backoff
        )

        if self.jitter:
            # Add up to 25% jitter
            jitter_amount = base_backoff * random.uniform(0, 0.25)
            return base_backoff + jitter_amount

        return base_backoff

    def reset_backoff(self) -> None:
        """Reset backoff after a successful poll."""
        self._consecutive_failures = 0
        self._current_backoff = self.initial_backoff
        logger.info(f"[{self.name}] Backoff reset after successful poll")

    async def run(self) -> None:
        """
        Main polling loop with error recovery.

        Runs until stop() is called or max retries exceeded.
        """
        self._running = True
        logger.info(f"[{self.name}] Starting watcher (poll interval: {self.poll_interval}s)")

        try:
            await self.startup()
            logger.info(f"[{self.name}] Startup complete, beginning poll loop")

            while self._running:
                try:
                    self._last_poll_time = datetime.now()
                    success = await self.poll()

                    if success:
                        self.reset_backoff()
                    else:
                        self._handle_poll_failure(Exception("Poll returned False"))

                except Exception as e:
                    self._handle_poll_failure(e)

                    if self._consecutive_failures >= self.max_retries:
                        logger.error(
                            f"[{self.name}] Max retries ({self.max_retries}) exceeded. "
                            f"Stopping watcher."
                        )
                        break

                    # Wait for backoff period
                    backoff_duration = self.calculate_backoff()
                    logger.warning(
                        f"[{self.name}] Poll failed. Retrying in {backoff_duration:.1f}s "
                        f"(attempt {self._consecutive_failures}/{self.max_retries})"
                    )
                    await asyncio.sleep(backoff_duration)
                    continue

                # Normal poll interval wait
                await asyncio.sleep(self.poll_interval)

        except asyncio.CancelledError:
            logger.info(f"[{self.name}] Watcher cancelled")

        finally:
            await self.shutdown()
            logger.info(f"[{self.name}] Watcher stopped")

    def stop(self) -> None:
        """Signal the watcher to stop gracefully."""
        logger.info(f"[{self.name}] Stop signal received")
        self._running = False

    def _handle_poll_failure(self, error: Exception) -> None:
        """Handle a poll failure with logging and error callback."""
        self._consecutive_failures += 1

        logger.error(
            f"[{self.name}] Poll failed: {type(error).__name__}: {error}"
        )

        if self.on_error:
            try:
                self.on_error(error)
            except Exception as callback_error:
                logger.error(
                    f"[{self.name}] Error callback failed: {callback_error}"
                )

    @property
    def status(self) -> dict:
        """Return current watcher status."""
        return {
            "name": self.name,
            "running": self._running,
            "poll_interval": self.poll_interval,
            "consecutive_failures": self._consecutive_failures,
            "current_backoff": self._current_backoff,
            "last_poll_time": (
                self._last_poll_time.isoformat() if self._last_poll_time else None
            ),
        }


class WatcherManager:
    """
    Manages multiple watchers with coordinated start/stop.
    """

    def __init__(self):
        self._watchers: list[BaseWatcher] = []
        self._tasks: list[asyncio.Task] = []

    def add_watcher(self, watcher: BaseWatcher) -> None:
        """Add a watcher to be managed."""
        self._watchers.append(watcher)

    async def start_all(self) -> None:
        """Start all watchers concurrently."""
        logger.info(f"Starting {len(self._watchers)} watcher(s)")
        self._tasks = [
            asyncio.create_task(w.run())
            for w in self._watchers
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def stop_all(self) -> None:
        """Stop all watchers."""
        logger.info("Stopping all watchers")
        for watcher in self._watchers:
            watcher.stop()

    async def wait_all(self) -> None:
        """Wait for all watchers to complete."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
