"""
SendMailWatcher - Monitors send_mails folder for outgoing email requests.

Watches send_mails/ directory for mail request files.
Copies them to Needs_Action/ so the orchestrator can process them.

Folder structure:
AI_Employee_Vault/
  send_mails/           <- User writes email requests here
    - to_john_doe.md   <- "Send email to john@example.com about project update"
    - to_client.md     <- "Send email to client@company.com about invoice"
"""

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path

from base_watcher import BaseWatcher
import aiofiles

logger = logging.getLogger("SendMailWatcher")


class SendMailWatcher(BaseWatcher):
    """
    Watches send_mails folder for email requests.

    Reads mail request files in format:
    - to: recipient@example.com
    - subject: Email Subject Line
    - body: Description/context for the email

    Copies to Needs_Action/ for orchestrator processing.
    """

    def __init__(
        self,
        send_mails_path: Path,
        needs_action_path: Path,
        logs_path: Path,
        poll_interval: float = 10.0,
    ):
        """Initialize the watcher."""
        super().__init__(
            poll_interval=poll_interval,
            max_retries=5,
            initial_backoff=1.0,
            max_backoff=30.0,
        )
        self.send_mails_path = Path(send_mails_path)
        self.needs_action_path = Path(needs_action_path)
        self.logs_path = Path(logs_path)
        self._processed_files: set[str] = set()

    @property
    def name(self) -> str:
        return "SendMailWatcher"

    async def startup(self) -> None:
        """Initialize paths."""
        self.send_mails_path.mkdir(parents=True, exist_ok=True)
        self.needs_action_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[SendMailWatcher] Started - watching: {self.send_mails_path}")

    async def shutdown(self) -> None:
        """Cleanup."""
        logger.info(f"[SendMailWatcher] Stopped")

    async def poll(self) -> bool:
        """Check for new mail request files."""
        mail_files = [
            f for f in self.send_mails_path.glob("*.md")
            if f.name != ".gitkeep" and f.name not in self._processed_files
        ]

        if not mail_files:
            return True

        for mail_file in mail_files:
            try:
                await self._process_mail_request(mail_file)
                self._processed_files.add(mail_file.name)
            except Exception as e:
                logger.error(f"[SendMailWatcher] Failed to process {mail_file.name}: {e}")
                return False

        return True

    async def _process_mail_request(self, mail_path: Path) -> None:
        """Process a mail request file."""
        logger.info(f"[SendMailWatcher] Processing: {mail_path.name}")

        # Read the request
        async with aiofiles.open(mail_path, "r", encoding="utf-8") as f:
            content = await f.read()

        # Parse recipient from content
        recipient = self._extract_recipient(content)
        if not recipient:
            logger.warning(f"[SendMailWatcher] No recipient found in {mail_path.name}, using filename")
            recipient = mail_path.stem.replace("_", " ").replace("-", " ")

        # Create Email Draft format matching user's exact pattern
        enriched_content = f"""# Email Draft

## To: {recipient}
## Subject: {self._extract_subject(content) or '(No Subject)'}

---

{content.strip()}

---

*Generated: {datetime.now().isoformat()}*"""

        # Move to Needs_Action using email_<recipient>_<subject> naming pattern (same as orchestrator generates)
        # Extract subject from content if available
        subject = self._extract_subject(content) or "no-subject"
        slug_subject = self._slugify(subject)[:50]
        slug_recipient = self._slugify(recipient)[:30]
        new_filename = f"email_{slug_recipient}_{slug_subject}.md"
        new_path = self.needs_action_path / new_filename

        # Write enriched content to Needs_Action
        async with aiofiles.open(new_path, "w", encoding="utf-8") as f:
            await f.write(enriched_content)

        # Delete the original file from send_mails
        mail_path.unlink()

        logger.info(f"[SendMailWatcher] Moved to Needs_Action: {new_filename}")

        # Log the action
        await self._log_action("mail_request_moved", mail_path.name, {"recipient": recipient})

    def _extract_recipient(self, content: str) -> str:
        """Extract recipient email from content."""
        import re

        # Look for "to: email@example.com" or "recipient: email@example.com"
        patterns = [
            r"^to:\s*(.+)$",
            r"^recipient:\s*(.+)$",
            r"email.*to:\s*(.+)$",
            r"@(?:gmail|hotmail|outlook|yahoo)\.com",
        ]

        content_lower = content.lower()
        for pattern in patterns:
            match = re.search(pattern, content_lower, re.MULTILINE)
            if match:
                return match.group(1).strip()

        # Try to find any email address
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", content)
        if email_match:
            return email_match.group(0)

        return ""

    def _extract_subject(self, content: str) -> str:
        """Extract subject from content."""
        import re

        patterns = [
            r"^subject:\s*(.+)$",
            r"^Subject:\s*(.+)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                return match.group(1).strip()

        return ""

    def _slugify(self, text: str) -> str:
        """Convert text to a filesystem-safe slug."""
        import re

        slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = slug.strip("-")
        return slug.lower() or "untitled"

    async def _log_action(self, action: str, filename: str, details: dict) -> None:
        """Log to JSON file."""
        import json

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "filename": filename,
            "details": details,
        }

        log_file = self.logs_path / f"send_mail_watcher_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

        async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
            await f.write(json.dumps(log_entry) + "\n")


def create_watcher_from_env(
    send_mails_path: Path,
    needs_action_path: Path,
    logs_path: Path,
) -> SendMailWatcher:
    """Create SendMailWatcher from vault paths."""
    return SendMailWatcher(
        send_mails_path=send_mails_path,
        needs_action_path=needs_action_path,
        logs_path=logs_path,
        poll_interval=10.0,
    )