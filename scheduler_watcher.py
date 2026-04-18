"""
Scheduler Watcher - Monitors /Scheduled folder for delayed task execution.

Reads files with `execute_at: YYYY-MM-DD HH:MM` header and moves them
to /Needs_Action when the scheduled time arrives.

Supports repeat schedules:
- once: Single execution (default)
- daily: Execute every day
- weekly: Execute every week on the same day
- custom: Execute every X days
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum

import aiofiles

from base_watcher import BaseWatcher

logger = logging.getLogger(__name__)


class RepeatType(Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    CUSTOM = "custom"


class SchedulerWatcher(BaseWatcher):
    """
    Scheduler watcher that monitors /Scheduled folder.

    Reads scheduled tasks and moves them to /Needs_Action when
    their execute_at time arrives. Supports repeat schedules.
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

            # Parse schedule metadata
            schedule_info = self._parse_schedule_metadata(content)

            if not schedule_info.get("execute_at"):
                logger.warning(f"[{self.name}] No execute_at found in {file_path.name}")
                return

            execute_at = schedule_info["execute_at"]
            repeat_type = schedule_info.get("repeat_type", RepeatType.ONCE)
            repeat_days = schedule_info.get("repeat_days", 1)
            repeat_end = schedule_info.get("repeat_end")

            # Check if time has arrived
            if now >= execute_at:
                logger.info(f"[{self.name}] Executing scheduled task: {file_path.name}")

                # Create task content for Needs_Action
                task_content = self._strip_schedule_metadata(content)

                # Add execution metadata
                execution_note = f"""

---

## Execution

| Field | Value |
|-------|-------|
| **Scheduled For** | {execute_at.isoformat()} |
| **Executed At** | {now.isoformat()} |
| **Repeat Type** | {repeat_type.value} |
| **Status** | Moved to Needs_Action |

---

*This task was automatically moved from /Scheduled to /Needs_Action*
"""
                task_content_with_meta = task_content + execution_note

                # Save to Needs_Action
                dest_path = self.needs_action_path / file_path.name
                async with aiofiles.open(dest_path, "w", encoding="utf-8") as f:
                    await f.write(task_content_with_meta)

                # Handle repeat schedules
                if repeat_type != RepeatType.ONCE:
                    await self._handle_repeat_schedule(
                        file_path,
                        execute_at,
                        repeat_type,
                        repeat_days,
                        repeat_end,
                        content
                    )
                else:
                    # Remove original file for one-time tasks
                    file_path.unlink()

                # Log
                await self._log_action(file_path.name, execute_at, now, repeat_type.value)

        except Exception as e:
            logger.error(f"[{self.name}] Error processing {file_path.name}: {e}")

    async def _handle_repeat_schedule(
        self,
        file_path: Path,
        last_execute_at: datetime,
        repeat_type: RepeatType,
        repeat_days: int,
        repeat_end: Optional[datetime],
        original_content: str,
    ) -> None:
        """
        Update the scheduled file for the next execution.

        Args:
            file_path: Path to the scheduled file
            last_execute_at: The execution time that just passed
            repeat_type: Type of repeat schedule
            repeat_days: Custom repeat days (for custom type)
            repeat_end: End date for repeat (if set)
            original_content: Original file content
        """
        # Calculate next execution time
        if repeat_type == RepeatType.DAILY:
            next_execute = last_execute_at + timedelta(days=1)
        elif repeat_type == RepeatType.WEEKLY:
            next_execute = last_execute_at + timedelta(weeks=1)
        elif repeat_type == RepeatType.CUSTOM:
            next_execute = last_execute_at + timedelta(days=repeat_days)
        else:
            return

        # Check if past end date
        if repeat_end and next_execute > repeat_end:
            logger.info(f"[{self.name}] Repeat schedule ended for {file_path.name}")
            file_path.unlink()
            return

        # Update the file with new execute_at
        new_content = self._update_execute_at(original_content, next_execute)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(new_content)

        logger.info(
            f"[{self.name}] Updated repeat schedule for {file_path.name}: "
            f"next execution at {next_execute.isoformat()}"
        )

    def _parse_schedule_metadata(self, content: str) -> dict:
        """
        Parse schedule metadata from file content.

        Returns:
            dict with execute_at, repeat_type, repeat_days, repeat_end
        """
        result = {
            "execute_at": None,
            "repeat_type": RepeatType.ONCE,
            "repeat_days": 1,
            "repeat_end": None,
        }

        # Parse execute_at (supports both ISO and space format)
        iso_match = re.search(
            r"execute_at:\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)",
            content,
            re.IGNORECASE
        )

        if iso_match:
            date_str = iso_match.group(1).replace(" ", "T")
            try:
                result["execute_at"] = datetime.fromisoformat(date_str)
            except ValueError:
                pass

        # Parse repeat_type
        repeat_match = re.search(
            r"repeat_type:\s*(once|daily|weekly|custom)",
            content,
            re.IGNORECASE
        )
        if repeat_match:
            result["repeat_type"] = RepeatType(repeat_match.group(1).lower())

        # Parse repeat_days
        repeat_days_match = re.search(
            r"repeat_days:\s*(\d+)",
            content,
            re.IGNORECASE
        )
        if repeat_days_match:
            result["repeat_days"] = int(repeat_days_match.group(1))

        # Parse repeat_end
        repeat_end_match = re.search(
            r"repeat_end:\s*(\d{4}-\d{2}-\d{2})",
            content,
            re.IGNORECASE
        )
        if repeat_end_match:
            try:
                result["repeat_end"] = datetime.fromisoformat(repeat_end_match.group(1))
            except ValueError:
                pass

        # Parse relative time formats if no ISO date
        if not result["execute_at"]:
            result["execute_at"] = self._parse_relative_time(content)

        return result

    def _parse_relative_time(self, content: str) -> Optional[datetime]:
        """
        Parse relative time formats.

        Supports: "tomorrow 9am", "in 2 hours", "in 30 minutes"
        """
        relative_match = re.search(
            r"(?:execute_at|scheduled):\s*(.+)",
            content,
            re.IGNORECASE
        )

        if relative_match:
            relative_str = relative_match.group(1).strip().lower()
            now = datetime.now()

            if "tomorrow" in relative_str:
                tomorrow = now + timedelta(days=1)
                time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", relative_str)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2) or 0)
                    if time_match.group(3) == "pm" and hour < 12:
                        hour += 12
                    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

            if "in" in relative_str:
                hours_match = re.search(r"in\s+(\d+)\s+hours?", relative_str)
                mins_match = re.search(r"in\s+(\d+)\s+minutes?", relative_str)

                hours = int(hours_match.group(1)) if hours_match else 0
                mins = int(mins_match.group(1)) if mins_match else 0

                return now + timedelta(hours=hours, minutes=mins)

        return None

    def _strip_schedule_metadata(self, content: str) -> str:
        """Remove YAML frontmatter from content."""
        # Remove YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content

    def _update_execute_at(self, content: str, new_execute_at: datetime) -> str:
        """Update the execute_at value in content."""
        new_date_str = new_execute_at.strftime("%Y-%m-%d %H:%M")

        # Update existing execute_at
        if "execute_at:" in content:
            return re.sub(
                r"execute_at:\s*[\d\-T: ]+",
                f"execute_at: {new_date_str}",
                content
            )

        # Add frontmatter if not present
        if not content.startswith("---"):
            return f"""---
execute_at: {new_date_str}
---

{content}
"""

        # Add execute_at to existing frontmatter
        return re.sub(
            r"^---\n",
            f"---\nexecute_at: {new_date_str}\n",
            content
        )

    async def _log_action(
        self,
        filename: str,
        scheduled_time: datetime,
        executed_time: datetime,
        repeat_type: str = "once",
    ) -> None:
        """Log action to JSON file."""
        log_entry = {
            "timestamp": executed_time.isoformat(),
            "source": "scheduler",
            "action": "task_executed",
            "filename": filename,
            "scheduled_for": scheduled_time.isoformat(),
            "executed_at": executed_time.isoformat(),
            "repeat_type": repeat_type,
        }

        log_file = self.logs_path / f"scheduler_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

        async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
            await f.write(json.dumps(log_entry) + "\n")


def create_scheduled_task(
    task_content: str,
    execute_at: datetime,
    scheduled_path: Path,
    task_name: Optional[str] = None,
    repeat_type: str = "once",
    repeat_days: int = 1,
    repeat_end: Optional[datetime] = None,
) -> Path:
    """
    Helper function to create a scheduled task file.

    Args:
        task_content: The task content/markdown
        execute_at: When to execute the task
        scheduled_path: Path to Scheduled folder
        task_name: Optional task name (default: auto-generated)
        repeat_type: "once", "daily", "weekly", or "custom"
        repeat_days: Days between executions (for custom)
        repeat_end: End date for repeat schedule

    Returns:
        Path to created file
    """
    scheduled_path = Path(scheduled_path)
    scheduled_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", task_name or "task")[:30]
    slug = re.sub(r"[\s_]+", "-", slug).lower().strip("-")

    filename = f"{timestamp}_scheduled_{slug}.md"

    # Build frontmatter
    frontmatter = f"""---
execute_at: {execute_at.strftime("%Y-%m-%d %H:%M")}
repeat_type: {repeat_type}
"""
    if repeat_type == "custom":
        frontmatter += f"repeat_days: {repeat_days}\n"

    if repeat_end:
        frontmatter += f"repeat_end: {repeat_end.strftime('%Y-%m-%d')}\n"

    frontmatter += "---\n\n"

    # Add frontmatter if not present
    if "execute_at:" not in task_content:
        task_content = frontmatter + task_content

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
