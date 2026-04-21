"""
Digital FTE - Main Entry Point

Single command runs all watchers and orchestrator.
python main.py

Includes error recovery and graceful degradation for 24/7 reliability.
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure local imports work
sys.path.insert(0, str(Path(__file__).parent))

from base_watcher import WatcherManager
from gmail_watcher import create_watcher_from_env
from orchestrator import Orchestrator
from graceful_degradation import GracefulDegradation
from watchdog import write_heartbeat, clear_heartbeat
from config_parser import get_config_parser
from subscription_auditor import create_auditor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("AI_Employee_Vault/Logs/system.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


async def run_system():
    """Initialize and run all FTE components."""
    load_dotenv()

    # Paths
    vault_path = Path("AI_Employee_Vault")
    logs_path = vault_path / "Logs"

    # Ensure ALL directories exist
    all_folders = [
        "Needs_Action", "Plans",
        "Rejected", "Done", "Logs", "Templates", "Scheduled",
        "Pending_Approval",
        # Error recovery folders
        "Outbox_Queue", "Human_Review_Queue", "Quarantine",
        # Social Media
        "Social_Media/linkedin_post_request", "Social_Media/x_post_request", "Social_Media/facebook_post_request",
        "Social_Media/LinkedIn_Posts/Draft", "Social_Media/LinkedIn_Posts/Approved", "Social_Media/LinkedIn_Posts/Done",
        "Social_Media/X_Posts/Draft", "Social_Media/X_Posts/Approved", "Social_Media/X_Posts/Done",
        "Social_Media/Facebook_Posts/Draft", "Social_Media/Facebook_Posts/Approved", "Social_Media/Facebook_Posts/Done",
        # Gmail
        "Gmail/Inbox", "Gmail/send_mails",
        "Gmail/Gmail_Messages/Draft", "Gmail/Gmail_Messages/Approved", "Gmail/Gmail_Messages/Done",
        # WhatsApp
        "WhatsApp/whatsapp_inbox",
        "WhatsApp/WhatsApp_Messages/Draft", "WhatsApp/WhatsApp_Messages/Approved", "WhatsApp/WhatsApp_Messages/Done",
        # Account (Odoo)
        "Account/Odoo_Invoices", "Account/Odoo_Bills", "Account/send_bills",
        "Account/Odoo_Invoices/Draft", "Account/Odoo_Invoices/Approved", "Account/Odoo_Invoices/Done",
        "Account/Odoo_Bills/Draft", "Account/Odoo_Bills/Approved", "Account/Odoo_Bills/Done",
    ]

    for folder in all_folders:
        (vault_path / folder).mkdir(parents=True, exist_ok=True)

    # ==================== GRACEFUL DEGRADATION ====================
    graceful_degradation = GracefulDegradation(
        vault_path=vault_path,
        logs_path=logs_path,
    )
    await graceful_degradation.initialize()
    logger.info("Graceful degradation system initialized")

    # Create watcher manager
    manager = WatcherManager()

    # Gmail watcher reference for orchestrator
    gmail_watcher = None
    whatsapp_watcher = None

    # ==================== GMAIL WATCHER ====================
    auth_method = os.getenv("AUTH_METHOD", "oauth").lower()
    has_gmail = False

    if auth_method == "service_account":
        has_gmail = bool(
            os.getenv("SERVICE_ACCOUNT_KEY_FILE") and os.getenv("IMPERSONATE_EMAIL")
        )
    else:
        has_gmail = bool(
            os.getenv("GMAIL_CLIENT_ID")
            and os.getenv("GMAIL_CLIENT_SECRET")
            and os.getenv("GMAIL_REFRESH_TOKEN")
        )

    if has_gmail:
        try:
            gmail_watcher = create_watcher_from_env(
                inbox_path=vault_path / "Gmail" / "Inbox",
                logs_path=logs_path,
                needs_action_path=vault_path / "Needs_Action",
            )
            manager.add_watcher(gmail_watcher)
            logger.info("Gmail watcher initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Gmail watcher: {e}")
            logger.error("Run 'python get_refresh_token.py' to generate a new refresh token")
    else:
        logger.warning("Gmail credentials not found. Gmail watcher disabled.")

    # ==================== WHATSAPP WATCHER ====================
    try:
        from whatsapp_watcher import WhatsAppWatcher
        whatsapp_watcher = WhatsAppWatcher(
            inbox_path=vault_path / "WhatsApp" / "whatsapp_inbox",
            needs_action_path=vault_path / "Needs_Action",
            logs_path=logs_path,
            business_goals_path=vault_path / "Business_Goals.md",
            poll_interval=15.0,
            headless=os.getenv("WHATSAPP_HEADLESS", "false").lower() == "true",
        )
        manager.add_watcher(whatsapp_watcher)
        logger.info("WhatsApp watcher initialized")
    except ImportError:
        logger.warning("WhatsApp watcher not available (playwright not installed)")
    except Exception as e:
        logger.warning(f"WhatsApp watcher failed: {e}")


    # ==================== LINKEDIN POST WATCHER ====================
    try:
        from linkedin_post_watcher import LinkedInPostWatcher
        linkedin_post_request_watcher = LinkedInPostWatcher(
            linkedin_post_request_path=vault_path / "Social_Media" / "linkedin_post_request",
            needs_action_path=vault_path / "Needs_Action",
            logs_path=logs_path,
            poll_interval=10.0,
        )
        manager.add_watcher(linkedin_post_request_watcher)
        logger.info("LinkedIn post watcher initialized")
    except ImportError:
        logger.warning("LinkedIn post watcher not available")
    except Exception as e:
        logger.warning(f"LinkedIn post watcher failed: {e}")

    # ==================== SOCIAL POST WATCHER (X, Facebook) ====================
    try:
        from social_post_watcher import SocialPostWatcher
        social_post_watcher = SocialPostWatcher(
            vault_path=vault_path,
            needs_action_path=vault_path / "Needs_Action",
            logs_path=logs_path,
            poll_interval=10.0,
            platforms=["x", "facebook"],
        )
        manager.add_watcher(social_post_watcher)
        logger.info("Social post watcher initialized (X, Facebook)")
    except ImportError:
        logger.warning("Social post watcher not available")
    except Exception as e:
        logger.warning(f"Social post watcher failed: {e}")

    # ==================== SCHEDULER WATCHER ====================
    try:
        from scheduler_watcher import SchedulerWatcher
        scheduler_watcher = SchedulerWatcher(
            scheduled_path=vault_path / "Scheduled",
            needs_action_path=vault_path / "Needs_Action",
            logs_path=logs_path,
            poll_interval=60.0,
        )
        manager.add_watcher(scheduler_watcher)
        logger.info("Scheduler watcher initialized")
    except ImportError:
        logger.warning("Scheduler watcher not available")

    # ==================== SEND MAIL WATCHER ====================
    try:
        from send_mail_watcher import SendMailWatcher
        send_mail_watcher = SendMailWatcher(
            send_mails_path=vault_path / "Gmail" / "send_mails",
            needs_action_path=vault_path / "Needs_Action",
            logs_path=logs_path,
            poll_interval=10.0,
        )
        manager.add_watcher(send_mail_watcher)
        logger.info("SendMail watcher initialized")
    except ImportError:
        logger.warning("SendMail watcher not available")
    except Exception as e:
        logger.warning(f"SendMail watcher failed: {e}")

    # ==================== LINKEDIN POSTER ====================
    linkedin_post_requester = None
    try:
        from linkedin_poster import LinkedInPoster
        linkedin_post_requester = LinkedInPoster(
            approved_path=vault_path / "Social_Media" / "LinkedIn_Posts" / "Approved",
            done_path=vault_path / "Social_Media" / "LinkedIn_Posts" / "Done",
            logs_path=logs_path,
            vault_path=vault_path,
            headless=os.getenv("LINKEDIN_HEADLESS", "false").lower() == "true",
        )
        await linkedin_post_requester.startup()
        logger.info("LinkedIn poster initialized")
    except ImportError:
        logger.warning("LinkedIn poster not available (playwright not installed)")
    except Exception as e:
        logger.warning(f"LinkedIn poster failed: {e}")

    # ==================== X (TWITTER) POSTER ====================
    x_poster = None
    try:
        from x_poster import XPoster
        x_poster = XPoster(
            approved_path=vault_path / "Social_Media" / "X_Posts" / "Approved",
            done_path=vault_path / "Social_Media" / "X_Posts" / "Done",
            logs_path=logs_path,
            vault_path=vault_path,
            headless=os.getenv("X_HEADLESS", "false").lower() == "true",
        )
        await x_poster.startup()
        logger.info("X (Twitter) poster initialized")
    except ImportError:
        logger.warning("X poster not available (playwright not installed)")
    except Exception as e:
        logger.warning(f"X poster failed: {e}")

    # ==================== FACEBOOK POSTER ====================
    facebook_poster = None
    try:
        from facebook_poster import FacebookPoster
        facebook_poster = FacebookPoster(
            approved_path=vault_path / "Social_Media" / "Facebook_Posts" / "Approved",
            done_path=vault_path / "Social_Media" / "Facebook_Posts" / "Done",
            logs_path=logs_path,
            vault_path=vault_path,
            headless=os.getenv("FACEBOOK_HEADLESS", "false").lower() == "true",
        )
        await facebook_poster.startup()
        logger.info("Facebook poster initialized")
    except ImportError:
        logger.warning("Facebook poster not available (playwright not installed)")
    except Exception as e:
        logger.warning(f"Facebook poster failed: {e}")

    # ==================== ODOO INVOICE WATCHER (Gold Tier) ====================
    odoo_invoice_watcher = None
    odoo_invoice_poster = None
    if os.getenv("ENABLE_ODOO_INVOICING", "false").lower() == "true":
        try:
            from odoo_invoice_watcher import OdooInvoiceWatcher, OdooInvoicePoster

            # Invoice watcher - monitors send_invoices for invoice requests
            odoo_invoice_watcher = OdooInvoiceWatcher(
                needs_action_path=vault_path / "Needs_Action",
                plans_path=vault_path / "Plans",
                odoo_invoices_path=vault_path / "Account" / "Odoo_Invoices",
                logs_path=logs_path,
                rates_path=vault_path / "Rates.md",
                poll_interval=10.0,
            )
            manager.add_watcher(odoo_invoice_watcher)
            logger.info("Odoo invoice watcher initialized")

            # Invoice poster - posts approved invoices to Odoo
            odoo_invoice_poster = OdooInvoicePoster(
                odoo_invoices_path=vault_path / "Account" / "Odoo_Invoices",
                logs_path=logs_path,
                vault_path=vault_path,
                poll_interval=10.0,
            )
            manager.add_watcher(odoo_invoice_poster)
            await odoo_invoice_poster.startup()
            logger.info("Odoo invoice poster initialized")
        except ImportError:
            logger.warning("Odoo invoice watcher not available")
        except Exception as e:
            logger.warning(f"Odoo invoice watcher failed: {e}")
    else:
        logger.info("Odoo invoicing disabled (set ENABLE_ODOO_INVOICING=true to enable)")

    # ==================== ODOO BILL MAKER ====================
    odoo_bill_watcher = None
    odoo_bill_poster = None
    if os.getenv("ENABLE_ODOO_BILLS", "false").lower() == "true":
        try:
            from odoo_bill_watcher import OdooBillWatcher, OdooBillPoster

            # Bill watcher - monitors send_bills for vendor bills
            odoo_bill_watcher = OdooBillWatcher(
                send_bills_path=vault_path / "Account" / "send_bills",
                needs_action_path=vault_path / "Needs_Action",
                odoo_bills_path=vault_path / "Account" / "Odoo_Bills",
                logs_path=logs_path,
                rates_path=vault_path / "Rates.md",
                poll_interval=10.0,
            )
            manager.add_watcher(odoo_bill_watcher)
            logger.info("Odoo bill watcher initialized")

            # Bill poster - posts approved bills to Odoo
            odoo_bill_poster = OdooBillPoster(
                odoo_bills_path=vault_path / "Account" / "Odoo_Bills",
                logs_path=logs_path,
                vault_path=vault_path,
                poll_interval=10.0,
            )
            manager.add_watcher(odoo_bill_poster)
            logger.info("Odoo bill poster initialized")
        except ImportError:
            logger.warning("Odoo bill watcher not available")
        except Exception as e:
            logger.warning(f"Odoo bill watcher failed: {e}")
    else:
        logger.info("Odoo bills disabled (set ENABLE_ODOO_BILLS=true to enable)")

    # ==================== SUBSCRIPTION AUDITOR (Aha! Logic) ====================
    # Run Sunday night audit
    from datetime import datetime
    auditor = create_auditor(vault_path=vault_path)

    async def sunday_audit():
        """Run subscription audit on Sundays."""
        # Check if it's Sunday
        if datetime.now().weekday() == 6:  # Sunday = 6
            logger.info("[Main] Running Sunday subscription audit...")
            try:
                findings = await auditor.run_audit()
                logger.info(f"[Main] Audit complete: {len(findings['recommendations'])} recommendations")
            except Exception as e:
                logger.error(f"[Main] Audit failed: {e}")

    # ==================== ORCHESTRATOR ====================
    orchestrator = Orchestrator(
        vault_path=vault_path,
        poll_interval=5.0,
        gmail_watcher=gmail_watcher,
        whatsapp_watcher=whatsapp_watcher,
        linkedin_poster=linkedin_post_requester,
        x_poster=x_poster,
        facebook_poster=facebook_poster,
        send_mail_watcher=send_mail_watcher,
    )

    # ==================== SIGNAL HANDLING ====================
    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        manager.stop_all()
        orchestrator.stop()
        if linkedin_post_requester:
            asyncio.create_task(linkedin_post_requester.shutdown())
        if x_poster:
            asyncio.create_task(x_poster.shutdown())
        if facebook_poster:
            asyncio.create_task(facebook_poster.shutdown())
        # Clear heartbeats on shutdown
        clear_heartbeat("orchestrator")
        clear_heartbeat("gmail_watcher")
        clear_heartbeat("whatsapp_watcher")
        clear_heartbeat("linkedin_watcher")
        clear_heartbeat("social_watcher")
        clear_heartbeat("send_mail_watcher")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # ==================== HEARTBEAT TASK ====================
    async def heartbeat_loop():
        """Write heartbeats for watchdog monitoring."""
        while True:
            write_heartbeat("orchestrator")
            if gmail_watcher:
                write_heartbeat("gmail_watcher")
            if whatsapp_watcher:
                write_heartbeat("whatsapp_watcher")
            write_heartbeat("linkedin_watcher")
            write_heartbeat("social_watcher")
            if send_mail_watcher:
                write_heartbeat("send_mail_watcher")
            await asyncio.sleep(30)  # Heartbeat every 30 seconds

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    # ==================== RUN ====================
    logger.info("=" * 60)
    logger.info("Digital FTE Starting")
    logger.info("=" * 60)

    # Start Gmail watcher first to authenticate before orchestrator runs
    if gmail_watcher:
        await gmail_watcher.startup()

    # Start Odoo bill watcher/poster if enabled
    if odoo_bill_watcher:
        await odoo_bill_watcher.startup()
    if odoo_bill_poster:
        await odoo_bill_poster.startup()

    try:
        await asyncio.gather(
            manager.start_all(),
            orchestrator.run(),
        )
    except asyncio.CancelledError:
        logger.info("System shutdown requested")
    finally:
        heartbeat_task.cancel()
        logger.info("Digital FTE stopped")


def main():
    """Main entry point."""
    asyncio.run(run_system())


if __name__ == "__main__":
    main()
