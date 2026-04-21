"""
Dashboard Updater - Updates Dashboard.md with current system state.

Called after tasks are performed to keep dashboard in sync.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DashboardUpdater:
    """Updates Dashboard.md with stats and folder counts."""

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)
        self.dashboard_path = self.vault_path / "Dashboard.md"

    def set_system_online(self) -> None:
        """Set all system components to Online status."""
        try:
            content = self.dashboard_path.read_text(encoding="utf-8")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Update System Status table rows (replace entire row to end of line)
            content = re.sub(r"\| Orchestrator \|.*$", "| Orchestrator | 🟢 Online | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| Gmail Watcher \|.*$", "| Gmail Watcher | 🟢 Online | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| WhatsApp Watcher \|.*$", "| WhatsApp Watcher | 🟢 Online | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| LinkedIn Watcher \|.*$", "| LinkedIn Watcher | 🟢 Online | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| Social Watcher \|.*$", "| Social Watcher | 🟢 Online | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| Watchdog \|.*$", "| Watchdog | 🟢 Online | - |", content, flags=re.MULTILINE)

            # Update Social Media Posters table rows
            content = re.sub(r"\| LinkedIn \|.*$", "| LinkedIn | 🟢 Online | .linkedin_poster_profile/ |", content, flags=re.MULTILINE)
            content = re.sub(r"\| X \(Twitter\) \|.*$", "| X (Twitter) | 🟢 Online | .x_poster_profile/ |", content, flags=re.MULTILINE)
            content = re.sub(r"\| Facebook \|.*$", "| Facebook | 🟢 Online | .facebook_poster_profile/ |", content, flags=re.MULTILINE)

            # Update last updated
            content = re.sub(
                r"> Last Updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                f"> Last Updated: {now}",
                content
            )

            self.dashboard_path.write_text(content, encoding="utf-8")
            logger.info("[DashboardUpdater] System set to Online")
        except Exception as e:
            logger.error(f"[DashboardUpdater] Failed to set system online: {e}")

    def set_system_offline(self) -> None:
        """Set all system components to Offline status."""
        try:
            content = self.dashboard_path.read_text(encoding="utf-8")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Update System Status table rows (replace entire row to end of line)
            content = re.sub(r"\| Orchestrator \|.*$", "| Orchestrator | 🔴 Offline | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| Gmail Watcher \|.*$", "| Gmail Watcher | 🔴 Offline | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| WhatsApp Watcher \|.*$", "| WhatsApp Watcher | 🔴 Offline | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| LinkedIn Watcher \|.*$", "| LinkedIn Watcher | 🔴 Offline | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| Social Watcher \|.*$", "| Social Watcher | 🔴 Offline | - |", content, flags=re.MULTILINE)
            content = re.sub(r"\| Watchdog \|.*$", "| Watchdog | 🔴 Offline | - |", content, flags=re.MULTILINE)

            # Update Social Media Posters table rows
            content = re.sub(r"\| LinkedIn \|.*$", "| LinkedIn | 🔴 Offline | .linkedin_poster_profile/ |", content, flags=re.MULTILINE)
            content = re.sub(r"\| X \(Twitter\) \|.*$", "| X (Twitter) | 🔴 Offline | .x_poster_profile/ |", content, flags=re.MULTILINE)
            content = re.sub(r"\| Facebook \|.*$", "| Facebook | 🔴 Offline | .facebook_poster_profile/ |", content, flags=re.MULTILINE)

            # Update last updated
            content = re.sub(
                r"> Last Updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                f"> Last Updated: {now}",
                content
            )

            self.dashboard_path.write_text(content, encoding="utf-8")
            logger.info("[DashboardUpdater] System set to Offline")
        except Exception as e:
            logger.error(f"[DashboardUpdater] Failed to set system offline: {e}")

    def update_all(self) -> None:
        """Update all dashboard sections except recent activity."""
        try:
            content = self.dashboard_path.read_text(encoding="utf-8")

            # Update folder counts
            content = self._update_folder_counts(content)

            # Update last updated timestamp
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            "/Account/Odoo_Invoices/Draft": "Account/Odoo_Invoices/Draft",
            "/Account/Odoo_Invoices/Pending_Payment": "Account/Odoo_Invoices/Pending_Payment",
            "/Account/Odoo_Invoices/Done": "Account/Odoo_Invoices/Done",
            # Odoo Bills
            "/Account/Odoo_Bills/Draft": "Account/Odoo_Bills/Draft",
            "/Account/Odoo_Bills/Done": "Account/Odoo_Bills/Done",
        }

        # Count files in each folder
        for display_path, folder_path in folder_mappings.items():
            full_path = self.vault_path / folder_path
            count = 0
            if full_path.exists() and full_path.is_dir():
                count = len(list(full_path.glob("*.md")))

            # Replace count in table - match literal display_path followed by any number
            pattern = rf"\| `{display_path}` \| \d+ \|"
            replacement = f"| `{display_path}` | {count} |"
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

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
                "odoo_invoices_draft": ("/Account/Odoo_Invoices/Draft", "Account/Odoo_Invoices/Draft"),
                "odoo_invoices_pending_payment": ("/Account/Odoo_Invoices/Pending_Payment", "Account/Odoo_Invoices/Pending_Payment"),
                "odoo_invoices_done": ("/Account/Odoo_Invoices/Done", "Account/Odoo_Invoices/Done"),
                # Odoo Bills
                "odoo_bills_draft": ("/Account/Odoo_Bills/Draft", "Account/Odoo_Bills/Draft"),
                "odoo_bills_done": ("/Account/Odoo_Bills/Done", "Account/Odoo_Bills/Done"),
            }

            if folder_name in folder_path_map:
                display_path, actual_path = folder_path_map[folder_name]
                full_path = self.vault_path / actual_path
                count = 0
                if full_path.exists() and full_path.is_dir():
                    count = len(list(full_path.glob("*.md")))

                # Replace count - use regex to match any number
                pattern = rf"\| `\{re.escape(display_path)}` \| \d+ \|"
                replacement = f"| `{display_path}` | {count} |"
                content = re.sub(pattern, replacement, content)

            # Also refresh date
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        folder: Specific folder that changed (ignored - always full update)
    """
    updater = DashboardUpdater(vault_path)
    updater.update_all()
