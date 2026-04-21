"""
X (Twitter) Poster - Publishes approved posts to X (Twitter).

Monitors the Approved folder for posts ready to publish.
When a draft is approved, publishes it to X (Twitter) and moves to Done.

Workflow:
1. Human creates requirement → x_post/
2. Watcher moves to → Needs_Action/
3. Claude Code creates plan → Plans/
4. Claude Code creates draft → X_Posts/Draft/
5. Human approves → X_Posts/Approved/
6. This poster publishes → X_Posts/Done/

Includes retry logic with exponential backoff for transient errors.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from dashboard_updater import DashboardUpdater

logger = logging.getLogger(__name__)


class XPoster:
    """
    X (Twitter) poster that publishes approved content.

    Watches Approved folder for drafts ready to publish.
    Publishes to X (Twitter) and archives to Done folder.
    """

    def __init__(
        self,
        approved_path: Path,
        done_path: Path,
        logs_path: Path,
        vault_path: Path = None,
        headless: bool = False,
        user_data_dir: Optional[str] = None,
    ):
        """
        Initialize the X (Twitter) poster.

        Args:
            approved_path: Path where approved posts wait for publishing
            done_path: Path where posted content is archived
            logs_path: Path to logs folder
            vault_path: Path to AI_Employee_Vault (for dashboard updates)
            headless: Run browser in headless mode
            user_data_dir: Browser profile directory (defaults to project/.x_poster_profile)
        """
        self.approved_path = Path(approved_path)
        self.done_path = Path(done_path)
        self.logs_path = Path(logs_path)
        # Dashboard updater
        self._dashboard_updater = DashboardUpdater(vault_path) if vault_path else None
        self.headless = headless
        # Use project-local profile directory to avoid conflicts
        if user_data_dir:
            self.user_data_dir = Path(user_data_dir)
        else:
            self.user_data_dir = Path.cwd() / ".x_poster_profile"

        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._playwright = None
        # Human review path (root of vault)
        self._human_review_path = vault_path / "Human_Review_Queue" if vault_path else None

    async def startup(self) -> None:
        """Initialize directories only. Browser is started lazily when needed."""
        self.approved_path.mkdir(parents=True, exist_ok=True)
        self.done_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
        logger.info("[XPoster] Initialized (browser will start on demand)")

    async def _start_browser(self) -> bool:
        """Start browser for posting. Reuses existing browser if available."""
        # Check if we have an existing, working browser/page
        if self._page is not None:
            try:
                # Verify page is still working
                if not self._page.is_closed():
                    return True
            except Exception:
                # Page is closed or invalid, need to restart
                pass

        # Clean up any existing broken browser state first
        await self._close_browser()

        self._playwright = await async_playwright().start()

        logger.info("[XPoster] Starting browser with persistent profile...")
        try:
            # Ensure profile directory exists
            self.user_data_dir.mkdir(parents=True, exist_ok=True)

            # Use persistent context to save login state
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-extensions",
                    "--disable-session-crashed-bubble",
                    "--disable-infobars",
                ],
                ignore_default_args=["--enable-automation"],
                ignore_https_errors=True,
            )

            if len(self._context.pages) > 0:
                self._page = self._context.pages[0]
            else:
                self._page = await self._context.new_page()

            logger.info("[XPoster] Navigating to X (Twitter)...")
            await self._page.goto("https://x.com", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            # Check if logged in by looking for home/tweet elements
            logged_in = False
            try:
                await self._page.wait_for_selector('[data-testid="tweetTextarea_0"], [data-testid="SideNav_NewTweet_Button"], a[href="/home"]', timeout=5000)
                logged_in = True
                logger.info("[XPoster] Browser ready - logged in")
            except:
                pass

            if not logged_in:
                logger.warning("[XPoster] ============================================")
                logger.warning("[XPoster] NOT LOGGED IN - Please log in to X (Twitter) NOW")
                logger.warning("[XPoster] The browser window is waiting for you...")
                logger.warning("[XPoster] ============================================")

                # Wait up to 5 minutes for user to log in
                try:
                    await self._page.wait_for_selector('[data-testid="tweetTextarea_0"], [data-testid="SideNav_NewTweet_Button"], a[href="/home"]', timeout=300000)
                    logger.info("[XPoster] Login detected! Proceeding...")
                except:
                    logger.error("[XPoster] Login timeout - took too long to log in")
                    return False

            return True
        except Exception as e:
            logger.error(f"[XPoster] Browser launch failed: {e}")
            return False

    async def _close_browser(self) -> None:
        """Close browser after posting. Login state is persisted in profile directory."""
        try:
            if self._page:
                await self._page.close()
        except Exception as e:
            logger.debug(f"[XPoster] Error closing page: {e}")
        try:
            if self._context:
                await self._context.close()
        except Exception as e:
            logger.debug(f"[XPoster] Error closing context: {e}")
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"[XPoster] Error stopping playwright: {e}")
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        logger.info("[XPoster] Browser closed")

    async def shutdown(self) -> None:
        """Cleanup browser."""
        await self._close_browser()
        logger.info("[XPoster] Shutdown complete")

    async def check_for_approved_posts(self) -> list[Path]:
        """Check for approved posts ready to publish."""
        approved_files = list(self.approved_path.glob("*.md"))
        return approved_files

    async def publish_post(self, post_path: Path, retry_count: int = 0) -> bool:
        """
        Publish an approved post to X (Twitter) with retry logic.

        Args:
            post_path: Path to approved post markdown file
            retry_count: Current retry attempt (internal use)

        Returns:
            True if published successfully
        """
        MAX_RETRIES = 5
        BASE_DELAY = 1.0
        MAX_DELAY = 60.0

        # Start browser for posting
        if not await self._start_browser():
            logger.error("[XPoster] Could not start browser")
            if retry_count < MAX_RETRIES:
                delay = min(BASE_DELAY * (2 ** retry_count), MAX_DELAY)
                logger.warning(f"[XPoster] Retrying in {delay:.1f}s... (attempt {retry_count + 1}/{MAX_RETRIES})")
                await asyncio.sleep(delay)
                return await self.publish_post(post_path, retry_count + 1)
            return False

        if not self._page:
            logger.error("[XPoster] Could not initialize browser")
            if retry_count < MAX_RETRIES:
                delay = min(BASE_DELAY * (2 ** retry_count), MAX_DELAY)
                logger.warning(f"[XPoster] Retrying in {delay:.1f}s... (attempt {retry_count + 1}/{MAX_RETRIES})")
                await asyncio.sleep(delay)
                return await self.publish_post(post_path, retry_count + 1)
            return False

        # Read approved post
        content = post_path.read_text(encoding="utf-8")

        # Extract post content from markdown
        post_text = self._extract_content_from_markdown(content)

        if not post_text:
            logger.error(f"[XPoster] No content found in {post_path}")
            await self._close_browser()
            return False

        try:
            # Navigate to X (Twitter) home/feed
            logger.info("[XPoster] Navigating to X (Twitter) home...")
            await self._page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            # Take a screenshot for debugging
            screenshot_path = self.logs_path / f"x_debug_feed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await self._page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(f"[XPoster] Saved debug screenshot: {screenshot_path}")

            # Try multiple ways to find the post composer
            clicked = False

            # Method 1: Try finding by data-testid
            try:
                compose_selectors = [
                    '[data-testid="SideNav_NewTweet_Button"]',
                    'a[data-testid="AppTabBar_Compose_Link"]',
                    'div[data-testid="tweetButtonInline"]',
                    'button[data-testid="tweetButton"]',
                ]
                for selector in compose_selectors:
                    try:
                        element = await self._page.wait_for_selector(selector, timeout=3000)
                        if element:
                            await element.click()
                            clicked = True
                            logger.info(f"[XPoster] Clicked compose button: {selector}")
                            break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Method 1 (data-testid) failed: {e}")

            # Method 2: Try finding by aria-label
            if not clicked:
                try:
                    element = await self._page.query_selector('[aria-label="Post"]')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[XPoster] Clicked Post via aria-label")
                except Exception as e:
                    logger.debug(f"Method 2 (aria-label) failed: {e}")

            # Method 3: Try finding by text
            if not clicked:
                try:
                    element = await self._page.query_selector('button:has-text("Post")')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[XPoster] Clicked button with 'Post' text")
                except Exception as e:
                    logger.debug(f"Method 3 (text) failed: {e}")

            # Method 4: Click on the text area directly (often visible on home page)
            if not clicked:
                try:
                    # The composer textarea is often already visible on the home page
                    textarea = await self._page.query_selector(
                        'div[data-testid="tweetTextarea_0"], div[contenteditable="true"][data-testid="tweetTextarea_0"]'
                    )
                    if textarea:
                        await textarea.click()
                        clicked = True
                        logger.info("[XPoster] Clicked on tweet textarea directly")
                except Exception as e:
                    logger.debug(f"Method 4 (textarea) failed: {e}")

            # Method 5: Use JavaScript to find composer
            if not clicked:
                try:
                    found = await self._page.evaluate('''() => {
                        const buttons = document.querySelectorAll('button, a');
                        for (const btn of buttons) {
                            const text = btn.textContent?.trim().toLowerCase() || '';
                            const ariaLabel = btn.getAttribute('aria-label')?.toLowerCase() || '';
                            if (text === 'post' || ariaLabel === 'post' || text.includes('tweet')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    if found:
                        clicked = True
                        logger.info("[XPoster] Clicked via JavaScript search")
                except Exception as e:
                    logger.debug(f"Method 5 (JS search) failed: {e}")

            if not clicked:
                logger.error("[XPoster] Could not find post/compose button")
                raise Exception("Could not find post/compose button on page")

            # Wait for composer to appear
            await asyncio.sleep(2)

            # Find the text editor - X uses a contenteditable div (new UI)
            editor = None
            editor_selectors = [
                'div[data-testid="tweetTextarea_0"]',
                'div[data-testid="tweetTextarea"]',
                'div[contenteditable="true"][data-testid="tweetTextarea_0"]',
                'div[contenteditable="true"]',
                '[role="textbox"][contenteditable="true"]',
                'div[aria-label="Post text"]',
                'div[aria-label="What is happening?!"',
                'div[aria-label*="Tweet"]',
                'span[data-text="true"]',
            ]

            for selector in editor_selectors:
                try:
                    editor = await self._page.query_selector(selector)
                    if editor:
                        is_visible = await editor.is_visible()
                        if is_visible:
                            logger.info(f"[XPoster] Found editor: {selector}")
                            break
                        else:
                            editor = None
                except Exception:
                    continue

            # If still not found, take screenshot for debugging
            if not editor:
                debug_path = self.logs_path / f"x_debug_editor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await self._page.screenshot(path=str(debug_path), full_page=True)
                logger.warning(f"[XPoster] Editor not found, saved screenshot: {debug_path}")
                # Try clicking the compose area directly via JS
                try:
                    clicked_via_js = await self._page.evaluate('''() => {
                        // Try to find and click the first contenteditable element
                        const editors = document.querySelectorAll('[contenteditable="true"]');
                        for (const ed of editors) {
                            if (ed.offsetParent !== null) { // visible
                                ed.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    if clicked_via_js:
                        logger.info("[XPoster] Clicked editor via JS")
                        await asyncio.sleep(1)
                        editor = await self._page.query_selector('[contenteditable="true"]')
                except Exception as e:
                    logger.debug(f"JS click fallback failed: {e}")

            if not editor:
                logger.error("[XPoster] Could not find text editor")
                raise Exception("Could not find text editor")

            # Click and type the post
            await editor.click()
            await asyncio.sleep(0.5)

            # Clear any existing content
            await self._page.keyboard.press('Control+a')
            await asyncio.sleep(0.2)

            # Type the post
            await self._page.keyboard.type(post_text, delay=10)
            await asyncio.sleep(1)

            # Take screenshot before posting
            pre_post_screenshot = self.logs_path / f"x_pre_post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await self._page.screenshot(path=str(pre_post_screenshot), full_page=True)
            logger.info(f"[XPoster] Saved pre-post screenshot: {pre_post_screenshot}")

            # Click the Post button
            posted = False
            post_button_selectors = [
                'button[data-testid="tweetButton"]',
                'button[data-testid="tweetButtonInline"]',
                'button[type="button"]:has-text("Post")',
                'div[data-testid="tweetButtonInline"]',
                'button[aria-label="Post"]',
            ]

            for selector in post_button_selectors:
                try:
                    button = await self._page.wait_for_selector(selector, timeout=3000)
                    if button:
                        is_visible = await button.is_visible()
                        is_enabled = await button.is_enabled()
                        if is_visible and is_enabled:
                            await button.click()
                            posted = True
                            logger.info(f"[XPoster] Clicked post button: {selector}")
                            break
                except Exception:
                    continue

            if not posted:
                # Fallback: JavaScript
                try:
                    found = await self._page.evaluate('''() => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = btn.textContent?.trim().toLowerCase() || '';
                            const dataTestId = btn.getAttribute('data-testid') || '';
                            if (text === 'post' || dataTestId.includes('tweetButton')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    if found:
                        posted = True
                        logger.info("[XPoster] Clicked post button via JavaScript")
                except Exception as e:
                    logger.debug(f"JS post button search failed: {e}")

            if not posted:
                logger.error("[XPoster] Could not find 'Post' button")
                raise Exception("Could not find 'Post' button")

            # Wait for post to be submitted
            await asyncio.sleep(3)

            logger.info("[XPoster] Post submitted successfully")

            # Move to Done folder
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            done_filename = f"{timestamp}_done_{post_path.stem}.md"
            done_path = self.done_path / done_filename

            # Add posted metadata
            done_content = content + f"\n\n---\n\n**POSTED TO X (TWITTER):** {datetime.now().isoformat()}\n"
            done_path.write_text(done_content, encoding="utf-8")

            # Delete from approved
            post_path.unlink()

            await self._log_action("post_published", post_path.stem, str(done_path), post_text)

            logger.info(f"[XPoster] Successfully posted: {done_filename}")

            # Update dashboard
            if self._dashboard_updater:
                self._dashboard_updater.update_all()

            # Close browser after successful posting
            await self._close_browser()
            return True

        except Exception as e:
            logger.error(f"[XPoster] Failed to publish post: {e}")
            await self._log_action("post_failed", post_path.stem, str(e))
            await self._close_browser()

            # Retry with exponential backoff
            if retry_count < MAX_RETRIES:
                delay = min(BASE_DELAY * (2 ** retry_count), MAX_DELAY)
                logger.warning(f"[XPoster] Retrying in {delay:.1f}s... (attempt {retry_count + 1}/{MAX_RETRIES})")
                await self._log_action("post_retry", post_path.stem, f"attempt {retry_count + 1}, delay {delay:.1f}s")
                await asyncio.sleep(delay)
                return await self.publish_post(post_path, retry_count + 1)

            # All retries exhausted - move to Human_Review_Queue
            logger.error(f"[XPoster] All {MAX_RETRIES} retries exhausted for {post_path.stem}")
            await self._move_to_human_review(post_path, str(e))
            return False

    async def _move_to_human_review(self, post_path: Path, error: str) -> None:
        """Move failed post to human review queue at vault root."""
        try:
            if not self._human_review_path:
                return

            self._human_review_path.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            review_filename = f"{timestamp}_failed_{post_path.stem}.md"
            review_file = self._human_review_path / review_filename

            # Add error metadata
            content = post_path.read_text(encoding="utf-8")
            review_content = content + f"\n\n---\n\n**PUBLISHING FAILED:** {datetime.now().isoformat()}\n**Error:** {error}\n**Action Required:** Manual review and retry\n"
            review_file.write_text(review_content, encoding="utf-8")

            # Remove from approved
            post_path.unlink()

            await self._log_action("moved_to_human_review", post_path.stem, f"Error: {error}")
            logger.warning(f"[XPoster] Moved to Human_Review_Queue: {post_path.name}")
        except Exception as e:
            logger.error(f"[XPoster] Failed to move to human review: {e}")

    def _extract_content_from_markdown(self, md_content: str) -> Optional[str]:
        """Extract post content from markdown file."""
        # Strategy 1: Find content between "## Post Content" and "---"
        # This captures everything including multiple bold sections
        match = re.search(
            r"## Post Content\s*\n+(.*?)\n*---",
            md_content,
            re.DOTALL
        )
        if match:
            content = match.group(1).strip()
            # Skip if it starts with the wrapper text
            if not content.startswith("Based on the request details"):
                return content

        # Strategy 2: Get ALL bold text using greedy match between ** and **
        # This captures the full post even if it has multiple ** sections
        match = re.search(r"\*\*(.+)\*\*", md_content, re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Make sure it's not just "Based on the request details..."
            if "Based on the request details" not in content:
                return content

        # Strategy 3: Find content between "## Post Content" and "##" (next header)
        match = re.search(
            r"## Post Content\s*\n+(.*?)(?=\n## |\Z)",
            md_content,
            re.DOTALL
        )
        if match:
            content = match.group(1).strip()
            if not content.startswith("Based on the request details"):
                return content

        return None

    async def _log_action(
        self,
        action: str,
        item_id: str,
        details: str,
        post_content: str = "",
    ) -> None:
        """Log action to JSON file."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": "x_poster",
            "platform": "x_twitter",
            "actor": "claude_code",
            "action": action,
            "item_id": item_id,
            "details": details,
            "post_content": post_content if post_content else "",
            "approval_status": "approved" if action == "post_published" else "failed",
        }

        log_file = self.logs_path / f"x_poster_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
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

    poster = XPoster(
        approved_path=vault_path / "X_Posts" / "Approved",
        done_path=vault_path / "X_Posts" / "Done",
        logs_path=vault_path / "Logs",
        headless=False,
    )

    await poster.startup()

    try:
        # Check for approved posts ready to publish
        print("Checking for approved posts...")
        approved = await poster.check_for_approved_posts()

        if approved:
            print(f"Found {len(approved)} approved posts to publish")
            for post_path in approved:
                print(f"Publishing: {post_path}")
                success = await poster.publish_post(post_path)
                if success:
                    print("[OK] Published successfully")
                else:
                    print("[FAIL] Failed to publish")
        else:
            print("No approved posts found.")
            print("\nWorkflow:")
            print("1. Create requirement file in x_post/")
            print("2. Watcher moves it to Needs_Action/")
            print("3. Claude Code creates plan in Plans/")
            print("4. Claude Code creates draft in X_Posts/Draft/")
            print("5. Human moves draft to Approved/")
            print("6. This poster publishes and moves to Done/")

    finally:
        await poster.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
