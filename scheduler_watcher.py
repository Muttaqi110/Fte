"""
Scheduler Watcher - Monitors /Scheduled folder for delayed task execution.

Reads files with `execute_at: YYYY-MM-DD HH:MM` header and moves them
to /Needs_Action when the scheduled time arrives.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiofiles

from base_watcher import BaseWatcher

logger = logging.getLogger(__name__)


class SchedulerWatcher(BaseWatcher):
    """
    Scheduler watcher that monitors /Scheduled folder.

    Reads scheduled tasks and moves them to /Needs_Action when
    their execute_at time arrives.
    """

    def __init__(
        self,
        scheduled_path: Path,
        needs_action_path: Path,
        logs_path: Path,
        poll_interval: float = 60.0,
        **kwargs,
    ):
        """
        Initialize the scheduler watcher.

        Args:
            scheduled_path: Path to Scheduled folder
            needs_action_path: Path to Needs_Action folder
            logs_path: Path to Logs folder
            poll_interval: Seconds between checks (default 1 minute)
        """
        super().__init__(poll_interval=poll_interval, **kwargs)

        self.scheduled_path = Path(scheduled_path)
        self.needs_action_path = Path(needs_action_path)
        self.logs_path = Path(logs_path)

    @property
    def name(self) -> str:
        return "SchedulerWatcher"

    async def startup(self) -> None:
        """Initialize directories."""
        self.scheduled_path.mkdir(parents=True, exist_ok=True)
        self.needs_action_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{self.name}] Monitoring scheduled tasks")

    async def shutdown(self) -> None:
        """Cleanup."""
        logger.info(f"[{self.name}] Shutdown complete")

    async def poll(self) -> bool:
        """
        Check for scheduled tasks ready to execute.

        Returns:
            True if poll succeeded
        """
        logger.debug(f"[{self.name}] Checking scheduled tasks...")

        try:
            # Get all .md files in Scheduled folder
            scheduled_files = [
                f for f in self.scheduled_path.glob("*.md")
                if f.name != ".gitkeep"
            ]

            if not scheduled_files:
                return True

            now = datetime.now()

            for file_path in scheduled_files:
                await self._check_scheduled_file(file_path, now)

            return True

        except Exception as e:
            logger.error(f"[{self.name}] Poll error: {e}")
            raise

    async def _check_scheduled_file(self, file_path: Path, now: datetime) -> None:
        """
        Check if a scheduled file is ready to execute.

        Args:
            file_path: Path to the scheduled file
            now: Current datetime
        """
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()

            # Parse execute_at from content
            execute_at = self._parse_execute_at(content)

            if not execute_at:
                logger.warning(f"[{self.name}] No execute_at found in {file_path.name}")
                return

            # Check if time has arrived
            if now >= execute_at:
                logger.info(f"[{self.name}] Executing scheduled task: {file_path.name}")

                # Move to Needs_Action
                dest_path = self.needs_action_path / file_path.name

                # Add execution metadata
                execution_note = f"""

---

## Execution

| Field | Value |
|-------|-------|
| **Scheduled For** | {execute_at.isoformat()} |
| **Executed At** | {now.isoformat()} |
| **Status** | Moved to Needs_Action |

---

*This task was automatically moved from /Scheduled to /Needs_Action*
"""

                async with aiofiles.open(file_path, "a", encoding="utf-8") as f:
                    await f.write(execution_note)

                # Move file
                file_path.rename(dest_path)

                # Log
                await self._log_action(file_path.name, execute_at, now)

        except Exception as e:
            logger.error(f"[{self.name}] Error processing {file_path.name}: {e}")

    def _parse_execute_at(self, content: str) -> Optional[datetime]:
        """
        Parse execute_at datetime from file content.

        Supports formats:
        - execute_at: 2026-04-01 08:00
        - execute_at: 2026-04-01T08:00:00
        - scheduled: tomorrow 9am
        - scheduled: in 2 hours
        """
        # Try ISO format first
        iso_match = re.search(
            r"execute_at:\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)",
            content,
            re.IGNORECASE
        )

        if iso_match:
            date_str = iso_match.group(1).replace(" ", "T")
            try:
                return datetime.fromisoformat(date_str)
            except ValueError:
                pass

        # Try relative time formats
        relative_match = re.search(
            r"(?:execute_at|scheduled):\s*(.+)",
            content,
            re.IGNORECASE
        )

        if relative_match:
            relative_str = relative_match.group(1).strip().lower()
            now = datetime.now()

            # Parse relative times
            if "tomorrow" in relative_str:
                tomorrow = now + timedelta(days=1)
                # Try to extract time
                time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", relative_str)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2) or 0)
                    if time_match.group(3) == "pm" and hour < 12:
                        hour += 12
                    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

            if "in" in relative_str:
                # "in 2 hours", "in 30 minutes"
                hours_match = re.search(r"in\s+(\d+)\s+hours?", relative_str)
                mins_match = re.search(r"in\s+(\d+)\s+minutes?", relative_str)

                hours = int(hours_match.group(1)) if hours_match else 0
                mins = int(mins_match.group(1)) if mins_match else 0

                return now + timedelta(hours=hours, minutes=mins)

        return None

    async def _log_action(
        self,
        filename: str,
        scheduled_time: datetime,
        executed_time: datetime,
    ) -> None:
        """Log action to JSON file."""
        log_entry = {
            "timestamp": executed_time.isoformat(),
            "source": "scheduler",
            "action": "task_executed",
            "filename": filename,
            "scheduled_for": scheduled_time.isoformat(),
            "executed_at": executed_time.isoformat(),
        }

        log_file = self.logs_path / f"scheduler_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

        async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
            await f.write(json.dumps(log_entry) + "\n")


def create_scheduled_task(
    task_content: str,
    execute_at: datetime,
    scheduled_path: Path,
    task_name: Optional[str] = None,
) -> Path:
    """
    Helper function to create a scheduled task file.

    Args:
        task_content: The task content/markdown
        execute_at: When to execute the task
        scheduled_path: Path to Scheduled folder
        task_name: Optional task name (default: auto-generated)

    Returns:
        Path to created file
    """
    scheduled_path = Path(scheduled_path)
    scheduled_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", task_name or "task")[:30]
    slug = re.sub(r"[\s_]+", "-", slug).lower().strip("-")

    filename = f"{timestamp}_scheduled_{slug}.md"

    # Add execute_at header if not present
    if "execute_at:" not in task_content:
        task_content = f"""---
execute_at: {execute_at.strftime("%Y-%m-%d %H:%M")}
---

{task_content}
"""

    file_path = scheduled_path / filename
    file_path.write_text(task_content, encoding="utf-8")

    return file_path


async def main():
    """Main entry point for standalone testing."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    vault_path = Path("AI_Employee_Vault")

    watcher = SchedulerWatcher(
        scheduled_path=vault_path / "Scheduled",
        needs_action_path=vault_path / "Needs_Action",
        logs_path=vault_path / "Logs",
        poll_interval=60.0,
    )

    try:
        await watcher.run()
    except KeyboardInterrupt:
        watcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
