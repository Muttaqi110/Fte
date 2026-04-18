"""
WhatsApp Watcher - Monitors WhatsApp Web for messages.

Uses Playwright to automate WhatsApp Web, saves all unread messages
to whatsapp_inbox and copies to Needs_Action.
Marks messages as read after downloading by opening and closing the chat.

Includes retry logic with exponential backoff for transient errors.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

from playwright.async_api import async_playwright, Page, BrowserContext

from base_watcher import BaseWatcher
from retry_handler import with_retry

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = [
    "pricing", "quote", "proposal", "meeting", "contract",
    "urgent", "deadline", "project", "collaboration", "partnership",
    "order", "purchase", "invoice", "payment", "budget",
    "hello", "hi", "help", "question", "info"
]


class WhatsAppWatcher(BaseWatcher):
    """WhatsApp Web watcher that monitors for messages."""

    def __init__(
        self,
        inbox_path: Path,
        needs_action_path: Path,
        logs_path: Path,
        business_goals_path: Path = None,
        poll_interval: float = 30.0,
        keywords: Optional[list[str]] = None,
        headless: bool = False,
        user_data_dir: Optional[str] = None,
        save_all_messages: bool = True,
        **kwargs,
    ):
        super().__init__(poll_interval=poll_interval, **kwargs)

        self.inbox_path = Path(inbox_path)
        self.needs_action_path = Path(needs_action_path)
        self.logs_path = Path(logs_path)
        self.business_goals_path = Path(business_goals_path) if business_goals_path else None
        self.headless = headless
        self.user_data_dir = user_data_dir or os.path.expanduser("~/.whatsapp_fte_profile")
        self.save_all_messages = save_all_messages
        self.keywords = keywords or DEFAULT_KEYWORDS

        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._processed_in_this_cycle: Set[str] = set()  # Reset each poll cycle
        self._playwright = None

    @property
    def name(self) -> str:
        return "WhatsAppWatcher"

    async def startup(self) -> None:
        """Initialize browser and navigate to WhatsApp Web."""
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.needs_action_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        # Start Playwright
        self._playwright = await async_playwright().start()

        logger.info(f"[{self.name}] Launching browser...")

        # Launch persistent context (keeps login)
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 720},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
            ],
        )

        self._page = await self._context.new_page()

        # Navigate to WhatsApp Web
        logger.info(f"[{self.name}] Navigating to WhatsApp Web...")
        await self._page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=60000)

        # Wait for app to load
        await asyncio.sleep(3)

        # Check if logged in
        try:
            await self._page.wait_for_selector('[data-testid="chat-list"]', timeout=30000)
            logger.info(f"[{self.name}] WhatsApp Web loaded - logged in")
        except:
            logger.warning(f"[{self.name}] Waiting for QR code scan...")
            try:
                await self._page.wait_for_selector('[data-testid="chat-list"]', timeout=120000)
                logger.info(f"[{self.name}] Login detected!")
            except:
                logger.error(f"[{self.name}] Login timeout - please restart and scan QR code")

    async def shutdown(self) -> None:
        """Cleanup browser."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()

        logger.info(f"[{self.name}] Shutdown complete")

    async def poll(self) -> bool:
        """Check for new WhatsApp messages."""
        if not self._page:
            raise RuntimeError("Browser not initialized")

        logger.debug(f"[{self.name}] Polling for messages...")

        # Reset processed set for this poll cycle
        self._processed_in_this_cycle = set()

        try:
            # Get all chats with unread messages
            unread_chats = await self._get_unread_chats()

            if not unread_chats:
                logger.debug(f"[{self.name}] No unread chats")
                return True

            logger.info(f"[{self.name}] Found {len(unread_chats)} unread chat(s)")

            for chat in unread_chats:
                try:
                    await self._process_chat(chat)
                except Exception as e:
                    logger.error(f"[{self.name}] Failed to process {chat.get('name')}: {e}")

            return True

        except Exception as e:
            logger.error(f"[{self.name}] Poll error: {e}")
            return False

    async def _get_unread_chats(self) -> list[dict]:
        """Get unread chats from WhatsApp Web."""
        script = """
        () => {
            const chats = [];

            // Find all chat list items
            const chatItems = document.querySelectorAll(
                '[data-testid="chat-list"] > div > div, ' +
                '#pane-side > div > div > div > div, ' +
                '[role="listitem"]'
            );

            chatItems.forEach((item, index) => {
                try {
                    // Find chat name
                    let nameEl = item.querySelector('[dir="auto"] span[title]') ||
                                 item.querySelector('span[title]') ||
                                 item.querySelector('[data-testid="cell-title"] span');

                    // Find message preview
                    let previewEl = item.querySelector('[data-testid="cell-text"] span') ||
                                    item.querySelector('[dir="ltr"]:last-child') ||
                                    item.querySelector('span[dir="ltr"]');

                    // Find unread badge/count - MUST have this
                    let unreadEl = item.querySelector('[data-testid="icon-unread-count"]') ||
                                   item.querySelector('span[aria-label*="unread"]') ||
                                   item.querySelector('[class*="unread"]') ||
                                   item.querySelector('[data-testid="unread-count"]') ||
                                   item.querySelector('span[class*="_3xMGe"]');

                    // Only include if has actual unread indicator
                    if (unreadEl) {
                        const name = nameEl ? (nameEl.getAttribute('title') || nameEl.textContent) : `Chat ${index}`;
                        const preview = previewEl ? previewEl.textContent : '';
                        const unread = unreadEl.textContent || '1';

                        chats.push({
                            name: name.trim(),
                            id: name.trim().toLowerCase().replace(/\\s+/g, '_') + '_' + index,
                            preview: preview.trim(),
                            unread: unread,
                            element: index
                        });
                    }
                } catch (e) {}
            });

            return chats;
        }
        """

        try:
            chats = await self._page.evaluate(script)
            return chats or []
        except Exception as e:
            logger.error(f"[{self.name}] Failed to get chats: {e}")
            return []

    async def _process_chat(self, chat: dict) -> None:
        """Process a single chat - download messages and mark as read."""
        chat_id = chat.get("id", "")
        chat_name = chat.get("name", "Unknown")
        preview = chat.get("preview", "")

        # Skip if already processed in this cycle
        if chat_id in self._processed_in_this_cycle:
            logger.debug(f"[{self.name}] Already processed in this cycle: {chat_name}")
            return

        logger.info(f"[{self.name}] Processing chat: {chat_name}")

        # Check keywords
        content_lower = (chat_name + " " + preview).lower()
        matched_keywords = [kw for kw in self.keywords if kw.lower() in content_lower]

        # Skip if not saving all and no keywords match
        if not self.save_all_messages and not matched_keywords:
            logger.debug(f"[{self.name}] Skipping {chat_name} - no keyword match")
            # Still mark as read
            await self._mark_chat_as_read(chat_name)
            self._processed_in_this_cycle.add(chat_id)
            return

        try:
            # Open the chat
            await self._open_chat(chat_name)
            await asyncio.sleep(2)

            # Get messages
            messages = await self._get_messages()

            # Create file
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            slug = self._slugify(chat_name)[:30]
            filename = f"{timestamp}_whatsapp_{slug}.md"

            keywords_str = ', '.join(matched_keywords) if matched_keywords else 'None (general chat)'

            content = f"""# WhatsApp Message

## Metadata

| Field | Value |
|-------|-------|
| **Source** | WhatsApp |
| **Contact** | {chat_name} |
| **Chat ID** | {chat_id} |
| **Received** | {datetime.now().isoformat()} |
| **Keywords** | {keywords_str} |

---

## Messages

{messages}

---

*Retrieved: {datetime.now().isoformat()}*
"""

            # Save to inbox
            inbox_file = self.inbox_path / filename
            inbox_file.write_text(content, encoding="utf-8")
            logger.info(f"[{self.name}] Saved: {filename}")

            # Copy to Needs_Action
            needs_action_file = self.needs_action_path / filename
            needs_action_file.write_text(content, encoding="utf-8")
            logger.info(f"[{self.name}] Copied to Needs_Action")

            # Log
            await self._log_action(chat_name, matched_keywords)

            # Mark as processed
            self._processed_in_this_cycle.add(chat_id)

            # Close the chat to mark messages as read
            await self._close_chat()

            # Go back to home/chat list
            await self._go_home()

            # Go back to home/chat list
            await self._go_home()

        except Exception as e:
            logger.error(f"[{self.name}] Failed to process {chat_name}: {e}")

    async def _open_chat(self, chat_name: str) -> bool:
        """Open a chat by name. Returns True if successful."""
        try:
            # Method 1: Use search
            search = await self._page.query_selector('[data-testid="search"] input, [placeholder*="Search"]')
            if search:
                await search.click()
                await asyncio.sleep(0.3)
                # Clear existing search
                await self._page.keyboard.press("Control+A")
                await search.fill(chat_name)
                await asyncio.sleep(1)

                # Press Enter to open first result
                await self._page.keyboard.press("Enter")
                await asyncio.sleep(1)
                logger.debug(f"[{self.name}] Opened chat via search: {chat_name}")
                return True
        except Exception as e:
            logger.debug(f"[{self.name}] Search method failed: {e}")

        # Method 2: Click chat in list
        try:
            chat_el = await self._page.query_selector(f'text="{chat_name}"')
            if chat_el:
                await chat_el.click()
                await asyncio.sleep(1)
                logger.debug(f"[{self.name}] Clicked chat in list: {chat_name}")
                return True
        except Exception as e:
            logger.debug(f"[{self.name}] Click method failed: {e}")

        logger.warning(f"[{self.name}] Could not open chat: {chat_name}")
        return False

    async def _close_chat(self) -> None:
        """Close the current chat to mark messages as read."""
        try:
            # Method 1: Click back button
            back_btn = await self._page.query_selector('[data-testid="conversation-back-button"]')
            if back_btn:
                await back_btn.click()
                await asyncio.sleep(0.5)
                logger.debug(f"[{self.name}] Closed chat via back button")
                return

            # Method 2: Press Escape
            await self._page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            logger.debug(f"[{self.name}] Closed chat via Escape")

        except Exception as e:
            logger.debug(f"[{self.name}] Close chat failed: {e}")

    async def _go_home(self) -> None:
        """Close search list if open and go to home/main chat list."""
        try:
            # Check if search box is active/focused and close it
            search_active = await self._page.query_selector('[data-testid="search"]:focus-within, [data-testid="search"].focus')
            if search_active:
                # Press Escape to close search
                await self._page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                logger.debug(f"[{self.name}] Closed search list via Escape")

            # Also try clicking anywhere in the chat list area to ensure we're in the main view
            # This helps if we're stuck in search results
            chat_list = await self._page.query_selector('[data-testid="chat-list"]')
            if chat_list:
                await chat_list.click()
                await asyncio.sleep(0.3)

            # Press Escape one more time just in case
            await self._page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

            logger.debug(f"[{self.name}] Returned to home/chat list")

        except Exception as e:
            logger.debug(f"[{self.name}] Go home failed: {e}")

    async def _go_home(self) -> None:
        """Close search list if open and go to home/main chat list."""
        try:
            # Check if search box is active/focused and close it
            search_active = await self._page.query_selector('[data-testid="search"]:focus-within, [data-testid="search"].focus')
            if search_active:
                # Press Escape to close search
                await self._page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                logger.debug(f"[{self.name}] Closed search list via Escape")

            # Also try clicking anywhere in the chat list area to ensure we're in the main view
            # This helps if we're stuck in search results
            chat_list = await self._page.query_selector('[data-testid="chat-list"]')
            if chat_list:
                await chat_list.click()
                await asyncio.sleep(0.3)

            # Press Escape one more time just in case
            await self._page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

            logger.debug(f"[{self.name}] Returned to home/chat list")

        except Exception as e:
            logger.debug(f"[{self.name}] Go home failed: {e}")

    async def _mark_chat_as_read(self, chat_name: str) -> None:
        """Open and close a chat to mark it as read."""
        await self._open_chat(chat_name)
        await asyncio.sleep(1)
        await self._close_chat()
        logger.debug(f"[{self.name}] Marked as read: {chat_name}")

    async def _get_messages(self) -> str:
        """Get messages from current chat."""
        script = """
        () => {
            const messages = [];

            // Find all message elements
            const msgSelectors = [
                '[data-testid="msg-container"]',
                '.message-in, .message-out',
                '[class*="message"]'
            ];

            let elements = [];
            for (const sel of msgSelectors) {
                const found = document.querySelectorAll(sel);
                if (found.length > elements.length) {
                    elements = found;
                }
            }

            elements.forEach(el => {
                try {
                    // Try to find text content
                    const textEl = el.querySelector('[data-testid="msg-text"]') ||
                                   el.querySelector('[dir="ltr"]') ||
                                   el.querySelector('span');

                    // Try to find time
                    const timeEl = el.querySelector('[data-testid="msg-meta"]') ||
                                   el.querySelector('time') ||
                                   el.querySelector('[class*="time"]');

                    // Determine sender (in/out)
                    const isOut = el.classList.contains('message-out') ||
                                  el.closest('[class*="out"]') ||
                                  el.querySelector('[data-testid="msg-dblcheck"]');

                    const text = textEl ? textEl.textContent.trim() : '';
                    const time = timeEl ? timeEl.textContent.trim() : '';
                    const sender = isOut ? 'You' : 'Contact';

                    if (text) {
                        messages.push(`[${time}] ${sender}: ${text}`);
                    }
                } catch (e) {}
            });

            // Return last 20 messages
            return messages.slice(-20).join('\\n') || 'No messages found';
        }
        """

        try:
            messages = await self._page.evaluate(script)
            return messages or "Could not read messages"
        except Exception as e:
            logger.error(f"[{self.name}] Get messages failed: {e}")
            return f"Error reading messages: {e}"

    def _slugify(self, text: str) -> str:
        """Convert text to slug."""
        slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text)
        slug = re.sub(r"[\s_]+", "-", slug)
        return slug.strip("-").lower() or "chat"

    @with_retry(max_retries=5, base_delay=1.0, max_delay=60.0)
    @with_retry(max_retries=5, base_delay=1.0, max_delay=60.0)
    async def send_message(self, contact_name: str, message: str) -> dict:
        """
        Send a WhatsApp message to a contact.

        Args:
            contact_name: Name of the contact/chat to send to
            message: Message text to send

        Returns:
            dict with 'success' bool and 'error' if failed
        """
        if not self._page:
            return {"success": False, "error": "Browser not initialized"}

        try:
            logger.info(f"[{self.name}] Sending message to {contact_name}")

            # Open the chat
            if not await self._open_chat(contact_name):
                return {"success": False, "error": "Could not open chat"}

            await asyncio.sleep(2)

            # Find the message input box
            input_selectors = [
                '[data-testid="conversation-compose-box-input"]',
                'div[contenteditable="true"][data-tab="10"]',
                'footer div[contenteditable="true"]',
                '#main div[contenteditable="true"]',
            ]

            input_box = None
            for selector in input_selectors:
                input_box = await self._page.query_selector(selector)
                if input_box:
                    break

            if not input_box:
                logger.error(f"[{self.name}] Could not find message input")
                # Close chat before returning
                await self._close_chat()
                return {"success": False, "error": "Message input not found"}

            # Type the message
            await input_box.click()
            await asyncio.sleep(0.5)
            await input_box.fill(message)
            await asyncio.sleep(0.5)

            # Send by pressing Enter
            await self._page.keyboard.press("Enter")
            await asyncio.sleep(1)

            # Close the chat so new messages show as unread
            await self._close_chat()

            # Go back to home/chat list
            await self._go_home()

            logger.info(f"[{self.name}] Message sent to {contact_name} and chat closed")
            return {"success": True}

        except Exception as e:
            logger.error(f"[{self.name}] Send failed: {e}")
            # Try to close chat on error too
            try:
                await self._close_chat()
            except:
                pass
            return {"success": False, "error": str(e)}

    async def _log_action(self, chat_name: str, keywords: list) -> None:
        """Log action."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": "whatsapp",
            "chat_name": chat_name,
            "keywords": keywords,
        }

        log_file = self.logs_path / f"whatsapp_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


async def main():
    """Test the watcher."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    vault_path = Path("AI_Employee_Vault")

    watcher = WhatsAppWatcher(
        inbox_path=vault_path / "whatsapp_inbox",
        needs_action_path=vault_path / "Needs_Action",
        logs_path=vault_path / "Logs",
        poll_interval=30.0,
        headless=False,
        save_all_messages=True,
    )

    try:
        await watcher.run()
    except KeyboardInterrupt:
        watcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
