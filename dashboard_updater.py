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
            content = content.replace(
                "{{date}}",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

            self.dashboard_path.write_text(content, encoding="utf-8")
            logger.info("[DashboardUpdater] Dashboard updated")
        except Exception as e:
            logger.error(f"[DashboardUpdater] Failed to update dashboard: {e}")

    def _update_folder_counts(self, content: str) -> str:
        """Update folder counts in Folders Overview."""
        folder_mappings = {
            "/Inbox": "Inbox",
            "/Needs_Action": "Needs_Action",
            "/Draft": "Gmail/Gmail_Messages/Draft",
            "/Done": "Done",
            "/Logs": "Logs",
            "/linkedin_post": "Social_Media/linkedin_post",
            "/Social_Media/LinkedIn_Posts/Draft": "Social_Media/LinkedIn_Posts/Draft",
            "/Social_Media/LinkedIn_Posts/Approved": "Social_Media/LinkedIn_Posts/Approved",
            "/Social_Media/LinkedIn_Posts/Done": "Social_Media/LinkedIn_Posts/Done",
            "/x_post": "Social_Media/x_post",
            "/Social_Media/X_Posts/Draft": "Social_Media/X_Posts/Draft",
            "/Social_Media/X_Posts/Approved": "Social_Media/X_Posts/Approved",
            "/Social_Media/X_Posts/Done": "Social_Media/X_Posts/Done",
            "/facebook_post": "Social_Media/facebook_post",
            "/Social_Media/Facebook_Posts/Draft": "Social_Media/Facebook_Posts/Draft",
            "/Social_Media/Facebook_Posts/Approved": "Social_Media/Facebook_Posts/Approved",
            "/Social_Media/Facebook_Posts/Done": "Social_Media/Facebook_Posts/Done",
            "/send_invoices": "Account/send_invoices",
            "/Odoo_Invoices/Draft": "Account/Odoo_Invoices/Draft",
            "/Odoo_Invoices/Approved": "Account/Odoo_Invoices/Approved",
            "/Odoo_Invoices/Done": "Account/Odoo_Invoices/Done",
            "/send_bills": "Account/send_bills",
            "/Odoo_Bills/Draft": "Account/Odoo_Bills/Draft",
            "/Odoo_Bills/Approved": "Account/Odoo_Bills/Approved",
            "/Odoo_Bills/Done": "Account/Odoo_Bills/Done",
        }

        # Count files in each folder
        for display_path, folder_path in folder_mappings.items():
            full_path = self.vault_path / folder_path
            count = 0
            if full_path.exists() and full_path.is_dir():
                count = len(list(full_path.glob("*.md")))

            # Replace count in table
            # Pattern: | `/folder` | 0 |
            search = f"| `{display_path}` | 0 |"
            replace = f"| `{display_path}` | {count} |"
            content = content.replace(search, replace)

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
                "linkedin_post": ("/linkedin_post", "Social_Media/linkedin_post"),
                "linkedin_draft": ("/Social_Media/LinkedIn_Posts/Draft", "Social_Media/LinkedIn_Posts/Draft"),
                "linkedin_approved": ("/Social_Media/LinkedIn_Posts/Approved", "Social_Media/LinkedIn_Posts/Approved"),
                "linkedin_done": ("/Social_Media/LinkedIn_Posts/Done", "Social_Media/LinkedIn_Posts/Done"),
                "x_post": ("/x_post", "Social_Media/x_post"),
                "x_draft": ("/Social_Media/X_Posts/Draft", "Social_Media/X_Posts/Draft"),
                "x_approved": ("/Social_Media/X_Posts/Approved", "Social_Media/X_Posts/Approved"),
                "x_done": ("/Social_Media/X_Posts/Done", "Social_Media/X_Posts/Done"),
                "facebook_post": ("/facebook_post", "Social_Media/facebook_post"),
                "facebook_draft": ("/Social_Media/Facebook_Posts/Draft", "Social_Media/Facebook_Posts/Draft"),
                "facebook_approved": ("/Social_Media/Facebook_Posts/Approved", "Social_Media/Facebook_Posts/Approved"),
                "facebook_done": ("/Social_Media/Facebook_Posts/Done", "Social_Media/Facebook_Posts/Done"),
                "send_invoices": ("/send_invoices", "Account/send_invoices"),
                "odoo_invoices_draft": ("/Odoo_Invoices/Draft", "Account/Odoo_Invoices/Draft"),
                "odoo_invoices_approved": ("/Odoo_Invoices/Approved", "Account/Odoo_Invoices/Approved"),
                "odoo_invoices_done": ("/Odoo_Invoices/Done", "Account/Odoo_Invoices/Done"),
                "send_bills": ("/send_bills", "Account/send_bills"),
                "odoo_bills_draft": ("/Odoo_Bills/Draft", "Account/Odoo_Bills/Draft"),
                "odoo_bills_approved": ("/Odoo_Bills/Approved", "Account/Odoo_Bills/Approved"),
                "odoo_bills_done": ("/Odoo_Bills/Done", "Account/Odoo_Bills/Done"),
            }

            if folder_name in folder_path_map:
                display_path, actual_path = folder_path_map[folder_name]
                full_path = self.vault_path / actual_path
                count = 0
                if full_path.exists() and full_path.is_dir():
                    count = len(list(full_path.glob("*.md")))

                search = f"| `{display_path}` | 0 |"
                replace = f"| `{display_path}` | {count} |"
                content = content.replace(search, replace)

            # Also refresh date
            content = content.replace(
                "{{date}}",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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