"""
Dashboard Updater - Updates Dashboard.md with current system state.

Called after tasks are performed to keep dashboard in sync.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DashboardUpdater:
    """Updates Dashboard.md with stats and folder counts."""

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)
        self.dashboard_path = self.vault_path / "Dashboard.md"

    def update_all(self) -> None:
        """Update all dashboard sections except recent activity."""
        try:
            content = self.dashboard_path.read_text(encoding="utf-8")

            # Update folder counts
            content = self._update_folder_counts(content)

            # Update quick stats
            content = self._update_quick_stats(content)

            # Update last updated timestamp
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Replace {{date}} placeholder or hardcoded "> Last Updated: YYYY-MM-DD HH:MM:SS"
            content = content.replace("{{date}}", now)
            import re
            content = re.sub(
                r"> Last Updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                f"> Last Updated: {now}",
                content
            )

            self.dashboard_path.write_text(content, encoding="utf-8")
            logger.info("[DashboardUpdater] Dashboard updated")
        except Exception as e:
            logger.error(f"[DashboardUpdater] Failed to update dashboard: {e}")

    def _update_folder_counts(self, content: str) -> str:
        """Update folder counts in Folders Overview."""
        folder_mappings = {
            # Gmail
            "/Gmail/Inbox": "Gmail/Inbox",
            "/Gmail/Gmail_Messages/Draft": "Gmail/Gmail_Messages/Draft",
            "/Gmail/Gmail_Messages/Done": "Gmail/Gmail_Messages/Done",
            # LinkedIn
            "/Social_Media/LinkedIn_Posts/Draft": "Social_Media/LinkedIn_Posts/Draft",
            "/Social_Media/LinkedIn_Posts/Done": "Social_Media/LinkedIn_Posts/Done",
            # X
            "/Social_Media/X_Posts/Draft": "Social_Media/X_Posts/Draft",
            "/Social_Media/X_Posts/Done": "Social_Media/X_Posts/Done",
            # Facebook
            "/Social_Media/Facebook_Posts/Draft": "Social_Media/Facebook_Posts/Draft",
            "/Social_Media/Facebook_Posts/Done": "Social_Media/Facebook_Posts/Done",
            # Odoo Invoices
            "/Odoo_Invoices/Draft": "Account/Odoo_Invoices/Draft",
            "/Odoo_Invoices/Done": "Account/Odoo_Invoices/Done",
            # Odoo Bills
            "/Odoo_Bills/Draft": "Account/Odoo_Bills/Draft",
            "/Odoo_Bills/Done": "Account/Odoo_Bills/Done",
            # Queues
            "/Needs_Action": "Needs_Action",
            "/Outbox_Queue": "Outbox_Queue",
            "/Human_Review_Queue": "Human_Review_Queue",
            "/Logs": "Logs",
        }

        # Count files in each folder
        for display_path, folder_path in folder_mappings.items():
            full_path = self.vault_path / folder_path
            count = 0
            if full_path.exists() and full_path.is_dir():
                count = len(list(full_path.glob("*.md")))

            # Replace count in table - use regex to match any number
            import re
            pattern = rf"\| `\{re.escape(display_path)}` \| \d+ \|"
            replacement = f"| `{display_path}` | {count} |"
            content = re.sub(pattern, replacement, content)

        return content

    def _update_quick_stats(self, content: str) -> str:
        """Update quick stats section."""
        # Count emails processed today
        inbox_path = self.vault_path / "Inbox"
        done_path = self.vault_path / "Done"
        today = datetime.now().strftime("%Y-%m-%d")

        emails_today = 0
        if done_path.exists():
            for f in done_path.glob("*.md"):
                if today in f.name:
                    emails_today += 1

        # Count drafts awaiting approval
        drafts_count = 0
        for draft_folder in [
            "Social_Media/LinkedIn_Posts/Draft",
            "Social_Media/X_Posts/Draft",
            "Social_Media/Facebook_Posts/Draft",
            "Account/Odoo_Invoices/Draft",
            "Account/Odoo_Bills/Draft",
        ]:
            path = self.vault_path / draft_folder
            if path.exists():
                drafts_count += len(list(path.glob("*.md")))

        # Count failed operations (from Outbox_Queue non-empty means failures)
        failed_count = 0
        outbox_path = self.vault_path / "Outbox_Queue"
        if outbox_path.exists():
            failed_count = len(list(outbox_path.glob("*.md")))

        # Update the stats in content
        content = content.replace(
            "**Emails Processed Today**: 0",
            f"**Emails Processed Today**: {emails_today}"
        )
        content = content.replace(
            "**Drafts Awaiting Approval**: 0",
            f"**Drafts Awaiting Approval**: {drafts_count}"
        )
        content = content.replace(
            "**Failed Operations**: 0",
            f"**Failed Operations**: {failed_count}"
        )

        return content

    def update_folder(self, folder_name: str) -> None:
        """Update a specific folder's count after file changes."""
        try:
            content = self.dashboard_path.read_text(encoding="utf-8")

            # Find the folder entry and update count
            folder_path_map = {
                # Gmail
                "gmail_inbox": ("/Gmail/Inbox", "Gmail/Inbox"),
                "gmail_draft": ("/Gmail/Gmail_Messages/Draft", "Gmail/Gmail_Messages/Draft"),
                "gmail_done": ("/Gmail/Gmail_Messages/Done", "Gmail/Gmail_Messages/Done"),
                # LinkedIn
                "linkedin_draft": ("/Social_Media/LinkedIn_Posts/Draft", "Social_Media/LinkedIn_Posts/Draft"),
                "linkedin_done": ("/Social_Media/LinkedIn_Posts/Done", "Social_Media/LinkedIn_Posts/Done"),
                # X
                "x_draft": ("/Social_Media/X_Posts/Draft", "Social_Media/X_Posts/Draft"),
                "x_done": ("/Social_Media/X_Posts/Done", "Social_Media/X_Posts/Done"),
                # Facebook
                "facebook_draft": ("/Social_Media/Facebook_Posts/Draft", "Social_Media/Facebook_Posts/Draft"),
                "facebook_done": ("/Social_Media/Facebook_Posts/Done", "Social_Media/Facebook_Posts/Done"),
                # Odoo Invoices
                "odoo_invoices_draft": ("/Odoo_Invoices/Draft", "Account/Odoo_Invoices/Draft"),
                "odoo_invoices_done": ("/Odoo_Invoices/Done", "Account/Odoo_Invoices/Done"),
                # Odoo Bills
                "odoo_bills_draft": ("/Odoo_Bills/Draft", "Account/Odoo_Bills/Draft"),
                "odoo_bills_done": ("/Odoo_Bills/Done", "Account/Odoo_Bills/Done"),
                # Queues
                "needs_action": ("/Needs_Action", "Needs_Action"),
                "outbox_queue": ("/Outbox_Queue", "Outbox_Queue"),
                "human_review_queue": ("/Human_Review_Queue", "Human_Review_Queue"),
                "logs": ("/Logs", "Logs"),
            }

            if folder_name in folder_path_map:
                display_path, actual_path = folder_path_map[folder_name]
                full_path = self.vault_path / actual_path
                count = 0
                if full_path.exists() and full_path.is_dir():
                    count = len(list(full_path.glob("*.md")))

                # Replace count - use regex to match any number
                import re
                pattern = rf"\| `\{re.escape(display_path)}` \| \d+ \|"
                replacement = f"| `{display_path}` | {count} |"
                content = re.sub(pattern, replacement, content)

            # Also refresh date
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            content = content.replace("{{date}}", now)
            import re
            content = re.sub(
                r"> Last Updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                f"> Last Updated: {now}",
                content
            )

            self.dashboard_path.write_text(content, encoding="utf-8")
            logger.info(f"[DashboardUpdater] Updated folder: {folder_name}")
        except Exception as e:
            logger.error(f"[DashboardUpdater] Failed to update folder {folder_name}: {e}")


async def update_dashboard_on_action(vault_path: Path, action: str, folder: str = None) -> None:
    """
    Convenience function to update dashboard after an action.

    Args:
        vault_path: Path to AI_Employee_Vault
        action: The action performed (e.g., "draft_created", "approved", "posted", "failed")
        folder: Specific folder that changed (optional)
    """
    updater = DashboardUpdater(vault_path)

    if folder:
        # Update specific folder
        updater.update_folder(folder)
    else:
        # Full update
        updater.update_all()