"""
Social Post Watcher - Monitors for new social media post requirements.

Watches x_post_request_request/, facebook_post/ folders for new requirement files.
When detected, moves them to Needs_Action/ for Claude Code to process.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Set

from base_watcher import BaseWatcher

logger = logging.getLogger(__name__)


class SocialPostWatcher(BaseWatcher):
    """
    Watches for social media post requirements.

    Flow:
    1. Human creates requirement file in x_post_request_request/ or facebook_post/
    2. This watcher detects it
    3. Moves file to Needs_Action/
    4. Claude Code reads it and creates plan/draft
    """

    # Platform-specific folders (under Social_Media/)
    PLATFORM_FOLDERS = {
        "x": "Social_Media/x_post_request",
        "twitter": "Social_Media/x_post_request",
        "facebook": "Social_Media/facebook_post_request",
    }

    def __init__(
        self,
        vault_path: Path,
        needs_action_path: Path,
        logs_path: Path,
        poll_interval: float = 10.0,
        platforms: list[str] = None,
        **kwargs,
    ):
        """
        Initialize the social post watcher.

        Args:
            vault_path: Path to AI_Employee_Vault
            needs_action_path: Path to Needs_Action folder
            logs_path: Path to Logs folder
            poll_interval: Seconds between checks
            platforms: List of platforms to watch (default: all)
        """
        super().__init__(poll_interval=poll_interval, **kwargs)

        self.vault_path = Path(vault_path)
        self.needs_action_path = Path(needs_action_path)
        self.logs_path = Path(logs_path)

        # Determine which platforms to watch
        if platforms:
            self.platforms = [p.lower() for p in platforms]
        else:
            self.platforms = ["x", "facebook"]

        # Build list of folders to watch
        self.watch_folders = {}
        for platform in self.platforms:
            folder_name = self.PLATFORM_FOLDERS.get(platform, f"{platform}_post")
            self.watch_folders[platform] = self.vault_path / folder_name

        self._processed_files: Set[str] = set()

    @property
    def name(self) -> str:
        return "SocialPostWatcher"

    async def startup(self) -> None:
        """Initialize directories."""
        for folder in self.watch_folders.values():
            folder.mkdir(parents=True, exist_ok=True)
        self.needs_action_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{self.name}] Watching folders: {list(self.watch_folders.values())}")

    async def shutdown(self) -> None:
        """Cleanup."""
        logger.info(f"[{self.name}] Shutdown complete")

    async def poll(self) -> bool:
        """
        Check for new post requirement files.

        Returns:
            True if poll succeeded
        """
        for platform, folder_path in self.watch_folders.items():
            current_files = set(f.name for f in folder_path.glob("*") if f.is_file())

            # Find new files
            new_files = current_files - self._processed_files

            if new_files:
                logger.info(f"[{self.name}] Found {len(new_files)} new file(s) for {platform}")

            for filename in new_files:
                file_path = folder_path / filename

                if not file_path.is_file():
                    continue

                logger.info(f"[{self.name}] New {platform} requirement detected: {filename}")

                # Move to Needs_Action
                await self._move_to_needs_action(file_path, platform)

                # Mark as processed
                self._processed_files.add(filename)

        return True

    async def _move_to_needs_action(self, file_path: Path, platform: str) -> None:
        """Move file to Needs_Action folder with timestamp and platform metadata."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        platform_name = platform.upper() if platform == "x" else platform.capitalize()
        new_filename = f"{timestamp}_{platform}_post_{file_path.name}"
        dest_path = self.needs_action_path / new_filename

        # Read content
        content = file_path.read_text(encoding="utf-8")

        # Add metadata header
        enhanced_content = f"""# {platform_name} Post Request

## Status: PENDING - AWAITING CLAUDE CODE PROCESSING

---

## Original Request

{content}

---

## Processing Instructions

1. Claude Code should read this request
2. Create a plan in Plans/ folder
3. Generate {platform_name} post draft
4. Save draft to {platform_name}_Posts/Draft/ folder

---

**Platform:** {platform_name}
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
        await self._log_action("moved_to_needs_action", str(dest_path), platform)

    async def _log_action(self, action: str, details: str, platform: str) -> None:
        """Log action to JSON file."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": "social_post_watcher",
            "platform": platform,
            "action": action,
            "details": details,
        }

        log_file = self.logs_path / f"social_post_watcher_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
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

    watcher = SocialPostWatcher(
        vault_path=vault_path,
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
