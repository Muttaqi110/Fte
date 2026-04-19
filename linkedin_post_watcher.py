"""
LinkedIn Post Request Watcher - Monitors for new post requirements.

Watches linkedin_post_request/ folder for new requirement files.
When detected, moves them to Needs_Action/ for Claude Code to process.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Set

from base_watcher import BaseWatcher

logger = logging.getLogger(__name__)


class LinkedInPostWatcher(BaseWatcher):
    """
    Watches for LinkedIn post requirements.

    Flow:
    1. Human creates requirement file in linkedin_post_request/
    2. This watcher detects it
    3. Moves file to Needs_Action/
    4. Claude Code reads it and creates plan/draft
    """

    def __init__(
        self,
        linkedin_post_request_path: Path,
        needs_action_path: Path,
        logs_path: Path,
        poll_interval: float = 10.0,
        **kwargs,
    ):
        """
        Initialize the LinkedIn post watcher.

        Args:
            linkedin_post_request_path: Path to linkedin_post_request folder (human input)
            needs_action_path: Path to Needs_Action folder
            logs_path: Path to Logs folder
            poll_interval: Seconds between checks
        """
        super().__init__(poll_interval=poll_interval, **kwargs)

        self.linkedin_post_request_path = Path(linkedin_post_request_path)
        self.needs_action_path = Path(needs_action_path)
        self.logs_path = Path(logs_path)

        self._processed_files: Set[str] = set()

    @property
    def name(self) -> str:
        return "LinkedInPostWatcher"

    async def startup(self) -> None:
        """Initialize directories."""
        self.linkedin_post_request_path.mkdir(parents=True, exist_ok=True)
        self.needs_action_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        # Don't skip existing files - process them on startup
        # Only skip files that have already been moved (tracked in logs)
        logger.info(f"[{self.name}] Watching {self.linkedin_post_request_path}")

    async def shutdown(self) -> None:
        """Cleanup."""
        logger.info(f"[{self.name}] Shutdown complete")

    async def poll(self) -> bool:
        """
        Check for new post requirement files.

        Returns:
            True if poll succeeded
        """
        current_files = set(f.name for f in self.linkedin_post_request_path.glob("*") if f.is_file())

        # Log current state for debugging
        logger.debug(f"[{self.name}] Current files: {current_files}")
        logger.debug(f"[{self.name}] Already processed: {self._processed_files}")

        # Find new files
        new_files = current_files - self._processed_files

        if new_files:
            logger.info(f"[{self.name}] Found {len(new_files)} new file(s) to process")

        for filename in new_files:
            file_path = self.linkedin_post_request_path / filename

            if not file_path.is_file():
                continue

            logger.info(f"[{self.name}] New requirement detected: {filename}")

            # Move to Needs_Action
            await self._move_to_needs_action(file_path)

            # Mark as processed
            self._processed_files.add(filename)

        return True

    async def _move_to_needs_action(self, file_path: Path) -> None:
        """Move file to Needs_Action folder with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        new_filename = f"{timestamp}_linkedin_post_request_{file_path.name}"
        dest_path = self.needs_action_path / new_filename

        # Read content
        content = file_path.read_text(encoding="utf-8")

        # Add metadata header
        enhanced_content = f"""# LinkedIn Post Request

## Status: PENDING - AWAITING CLAUDE CODE PROCESSING

---

## Original Request

{content}

---

## Processing Instructions

1. Claude Code should read this request
2. Create a plan in Plans/ folder
3. Generate LinkedIn post draft
4. Save draft to Draft/ folder

---

**Source:** {file_path.name}
**Detected:** {datetime.now().isoformat()}
**Moved to Needs_Action:** {datetime.now().isoformat()}
"""

        # Write to Needs_Action
        dest_path.write_text(enhanced_content, encoding="utf-8")

        # Delete original
        file_path.unlink()

        logger.info(f"[{self.name}] Moved to Needs_Action: {new_filename}")

        # Log
        await self._log_action("moved_to_needs_action", str(dest_path))

    async def _log_action(self, action: str, details: str) -> None:
        """Log action to JSON file."""
        import json

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": "linkedin_post_request_watcher",
            "action": action,
            "details": details,
        }

        log_file = self.logs_path / f"linkedin_post_request_watcher_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


async def main():
    """Main entry point for standalone testing."""
    import dotenv
    dotenv.load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    vault_path = Path("AI_Employee_Vault")

    watcher = LinkedInPostWatcher(
        linkedin_post_request_path=vault_path / "Social_Media" / "linkedin_post_request",
        needs_action_path=vault_path / "Needs_Action",
        logs_path=vault_path / "Logs",
        poll_interval=10.0,
    )

    try:
        await watcher.run()
    except KeyboardInterrupt:
        watcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
