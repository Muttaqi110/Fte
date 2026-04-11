"""
Digital FTE - Main Entry Point

Single command runs all watchers and orchestrator.
python main.py
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
        "Inbox", "whatsapp_inbox",
        "Needs_Action", "Plans",
        "Rejected", "Done", "Logs", "Templates", "Scheduled",
        "linkedin_post",
        "LinkedIn_Posts/Draft", "LinkedIn_Posts/Approved", "LinkedIn_Posts/Done",
        "Gmail_Messages/Draft", "Gmail_Messages/Approved", "Gmail_Messages/Done",
        "WhatsApp_Messages/Draft", "WhatsApp_Messages/Approved", "WhatsApp_Messages/Done",
    ]

    for folder in all_folders:
        (vault_path / folder).mkdir(parents=True, exist_ok=True)

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
                inbox_path=vault_path / "Inbox",
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
            inbox_path=vault_path / "whatsapp_inbox",
            needs_action_path=vault_path / "Needs_Action",
            logs_path=logs_path,
            business_goals_path=vault_path / "Business_Goals.md",
            poll_interval=30.0,
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
        linkedin_post_watcher = LinkedInPostWatcher(
            linkedin_post_path=vault_path / "linkedin_post",
            needs_action_path=vault_path / "Needs_Action",
            logs_path=logs_path,
            poll_interval=10.0,
        )
        manager.add_watcher(linkedin_post_watcher)
        logger.info("LinkedIn post watcher initialized")
    except ImportError:
        logger.warning("LinkedIn post watcher not available")
    except Exception as e:
        logger.warning(f"LinkedIn post watcher failed: {e}")

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

    # ==================== LINKEDIN POSTER ====================
    linkedin_poster = None
    try:
        from linkedin_poster import LinkedInPoster
        linkedin_poster = LinkedInPoster(
            approved_path=vault_path / "LinkedIn_Posts" / "Approved",
            done_path=vault_path / "LinkedIn_Posts" / "Done",
            logs_path=logs_path,
            headless=os.getenv("LINKEDIN_HEADLESS", "false").lower() == "true",
        )
        await linkedin_poster.startup()
        logger.info("LinkedIn poster initialized")
    except ImportError:
        logger.warning("LinkedIn poster not available (playwright not installed)")
    except Exception as e:
        logger.warning(f"LinkedIn poster failed: {e}")

    # ==================== ORCHESTRATOR ====================
    orchestrator = Orchestrator(
        vault_path=vault_path,
        poll_interval=5.0,
        daily_post_time=os.getenv("DAILY_POST_TIME", "09:00"),
        gmail_watcher=gmail_watcher,
        whatsapp_watcher=whatsapp_watcher,
        linkedin_poster=linkedin_poster,
    )

    # ==================== SIGNAL HANDLING ====================
    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        manager.stop_all()
        orchestrator.stop()
        if linkedin_poster:
            asyncio.create_task(linkedin_poster.shutdown())

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # ==================== RUN ====================
    logger.info("=" * 60)
    logger.info("Digital FTE Starting")
    logger.info("=" * 60)

    try:
        await asyncio.gather(
            manager.start_all(),
            orchestrator.run(),
        )
    except asyncio.CancelledError:
        logger.info("System shutdown requested")
    finally:
        logger.info("Digital FTE stopped")


def main():
    """Main entry point."""
    asyncio.run(run_system())


if __name__ == "__main__":
    main()
