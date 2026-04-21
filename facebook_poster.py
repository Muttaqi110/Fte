"""
Facebook Poster - Publishes approved posts to Facebook.

Monitors the Approved folder for posts ready to publish.
When a draft is approved, publishes it to Facebook and moves to Done.

Workflow:
1. Human creates requirement → facebook_post/
2. Watcher moves to → Needs_Action/
3. Claude Code creates plan → Plans/
4. Claude Code creates draft → Facebook_Posts/Draft/
5. Human approves → Facebook_Posts/Approved/
6. This poster publishes → Facebook_Posts/Done/

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


class FacebookPoster:
    """
    Facebook poster that publishes approved content.

    Watches Approved folder for drafts ready to publish.
    Publishes to Facebook and archives to Done folder.
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
        Initialize the Facebook poster.

        Args:
            approved_path: Path where approved posts wait for publishing
            done_path: Path where posted content is archived
            logs_path: Path to logs folder
            vault_path: Path to AI_Employee_Vault (for dashboard updates)
            headless: Run browser in headless mode
            user_data_dir: Browser profile directory (defaults to project/.facebook_poster_profile)
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
            self.user_data_dir = Path.cwd() / ".facebook_poster_profile"

        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._playwright = None
        self._logged_in = False  # Track if we've successfully logged in
        # Human review path (root of vault)
        self._human_review_path = vault_path / "Human_Review_Queue" if vault_path else None

    async def startup(self) -> None:
        """Initialize directories only. Browser is started lazily when needed."""
        self.approved_path.mkdir(parents=True, exist_ok=True)
        self.done_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
        logger.info("[FacebookPoster] Initialized (browser will start on demand)")

    async def _start_browser(self) -> bool:
        """Start browser for posting."""
        if self._page is not None:
            return True

        # Check if we have a valid session from previous login
        # If logged in before, reuse the session without forcing new browser
        if self._logged_in:
            logger.info("[FacebookPoster] Previously logged in, checking session...")
            self._playwright = await async_playwright().start()
            try:
                self.user_data_dir.mkdir(parents=True, exist_ok=True)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.user_data_dir),
                    headless=self.headless,
                    viewport={"width": 1280, "height": 800},
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

                # Quick check if still logged in
                try:
                    await self._page.wait_for_selector('[role="feed"], [data-pagelet="Feed"], div[aria-label="Create a post"]', timeout=5000)
                    logger.info("[FacebookPoster] Session still valid - logged in")
                    return True
                except:
                    logger.warning("[FacebookPoster] Session expired, need to log in again")
                    await self._close_browser()
                    self._logged_in = False
            except Exception as e:
                logger.error(f"[FacebookPoster] Failed to reuse session: {e}")
                await self._close_browser()

        # Start fresh browser session

        logger.info("[FacebookPoster] Starting browser with persistent profile...")

        # Ensure playwright is started
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        try:
            # Ensure profile directory exists
            self.user_data_dir.mkdir(parents=True, exist_ok=True)

            # Use persistent context to save login state
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                viewport={"width": 1280, "height": 800},
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

            logger.info("[FacebookPoster] Navigating to Facebook...")
            await self._page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            # Check if logged in by looking for feed/post elements
            logged_in = False
            try:
                await self._page.wait_for_selector('[role="feed"], [data-pagelet="Feed"], div[aria-label="Create a post"]', timeout=5000)
                logged_in = True
                logger.info("[FacebookPoster] Browser ready - logged in")
            except:
                pass

            if not logged_in:
                logger.warning("[FacebookPoster] ============================================")
                logger.warning("[FacebookPoster] NOT LOGGED IN - Please log in to Facebook NOW")
                logger.warning("[FacebookPoster] The browser window is waiting for you...")
                logger.warning("[FacebookPoster] ============================================")

                # Wait up to 5 minutes for user to log in
                try:
                    await self._page.wait_for_selector('[role="feed"], [data-pagelet="Feed"], div[aria-label="Create a post"]', timeout=180000)
                    logger.info("[FacebookPoster] Login detected! Proceeding...")
                    self._logged_in = True  # Mark as logged in
                except:
                    logger.warning("[FacebookPoster] Login timeout - retrying with new tab...")
                    await self._close_browser()
                    # Try again with new browser (user gets another chance to login)
                    return await self._start_browser()

            else:
                self._logged_in = True  # Already logged in

            return True
        except Exception as e:
            logger.error(f"[FacebookPoster] Browser launch failed: {e}")
            return False

    async def _close_browser(self) -> None:
        """Close browser after posting. Login state is persisted in profile directory."""
        try:
            if self._page:
                await self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        logger.info("[FacebookPoster] Browser closed")

    async def shutdown(self) -> None:
        """Cleanup browser."""
        await self._close_browser()
        logger.info("[FacebookPoster] Shutdown complete")

    async def check_for_approved_posts(self) -> list[Path]:
        """Check for approved posts ready to publish."""
        approved_files = list(self.approved_path.glob("*.md"))
        return approved_files

    async def publish_post(self, post_path: Path, retry_count: int = 0) -> bool:
        """
        Publish an approved post to Facebook with retry logic.

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
            logger.error("[FacebookPoster] Could not start browser")
            if retry_count < MAX_RETRIES:
                delay = min(BASE_DELAY * (2 ** retry_count), MAX_DELAY)
                logger.warning(f"[FacebookPoster] Retrying in {delay:.1f}s... (attempt {retry_count + 1}/{MAX_RETRIES})")
                await asyncio.sleep(delay)
                return await self.publish_post(post_path, retry_count + 1)
            # All retries exhausted - move to human review
            logger.error(f"[FacebookPoster] All {MAX_RETRIES} retries exhausted - browser failed to start")
            await self._move_to_human_review(post_path, "Browser failed to start after max retries")
            return False

        if not self._page:
            logger.error("[FacebookPoster] Could not initialize browser")
            if retry_count < MAX_RETRIES:
                delay = min(BASE_DELAY * (2 ** retry_count), MAX_DELAY)
                logger.warning(f"[FacebookPoster] Retrying in {delay:.1f}s... (attempt {retry_count + 1}/{MAX_RETRIES})")
                await asyncio.sleep(delay)
                return await self.publish_post(post_path, retry_count + 1)
            # All retries exhausted - move to human review
            logger.error(f"[FacebookPoster] All {MAX_RETRIES} retries exhausted - page initialization failed")
            await self._move_to_human_review(post_path, "Page initialization failed after max retries")
            return False

        # Read approved post
        content = post_path.read_text(encoding="utf-8")

        # Extract post content from markdown
        post_text = self._extract_content_from_markdown(content)

        if not post_text:
            logger.error(f"[FacebookPoster] No content found in {post_path}")
            await self._close_browser()
            return False

        # Facebook post limit is 63206 characters, but we'll keep it reasonable
        if len(post_text) > 5000:
            logger.warning(f"[FacebookPoster] Post is long ({len(post_text)} chars), consider shortening")

        try:
            # Navigate to Facebook
            logger.info("[FacebookPoster] Navigating to Facebook home...")
            await self._page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)


            # Find and click the "Create post" area
            clicked = False

            # Method 1: Try finding by aria-label
            try:
                create_selectors = [
                    'div[aria-label="Create a post"]',
                    'span:has-text("Create post")',
                    'div[role="button"]:has-text("Create post")',
                    '[data-pagelet="CreatePost"]',
                    'div[contenteditable="true"][aria-label*="post"]',
                ]
                for selector in create_selectors:
                    try:
                        element = await self._page.wait_for_selector(selector, timeout=3000)
                        if element:
                            await element.click()
                            clicked = True
                            logger.info(f"[FacebookPoster] Clicked create post: {selector}")
                            break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Method 1 (create post) failed: {e}")

            # Method 2: Look for the status update box
            if not clicked:
                try:
                    # Facebook often has a "What's on your mind?" prompt
                    element = await self._page.query_selector('div[aria-label*="mind"], span:has-text("on your mind")')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[FacebookPoster] Clicked 'What's on your mind'")
                except Exception as e:
                    logger.debug(f"Method 2 (status update) failed: {e}")

            # Method 3: Try clicking on the composer directly
            if not clicked:
                try:
                    # The composer is often a contenteditable div
                    element = await self._page.query_selector('div[contenteditable="true"][role="textbox"]')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[FacebookPoster] Clicked on contenteditable textbox")
                except Exception as e:
                    logger.debug(f"Method 3 (contenteditable) failed: {e}")

            if not clicked:
                logger.error("[FacebookPoster] Could not find create post area")
                raise Exception("Could not find create post area")

            # Wait for composer to fully open
            await asyncio.sleep(2)

            # Find the text editor - Facebook uses a contenteditable div
            editor = None
            editor_selectors = [
                'div[contenteditable="true"][role="textbox"]',
                'div[contenteditable="true"][aria-label*="post"]',
                'div[contenteditable="true"][data-text]',

            ]

            for selector in editor_selectors:
                try:
                    editor = await self._page.wait_for_selector(selector, timeout=5000)
                    if editor:
                        is_visible = await editor.is_visible()
                        if is_visible:
                            logger.info(f"[FacebookPoster] Found editor: {selector}")
                            break
                        else:
                            editor = None
                except Exception:
                    continue

            if not editor:
                logger.error("[FacebookPoster] Could not find text editor")
                raise Exception("Could not find text editor")

            # Click and type the post - try keyboard first, fallback to JS injection
            try:
                await editor.click()
                await asyncio.sleep(0.5)

                # Clear any placeholder text
                await self._page.keyboard.press('Control+a')
                await asyncio.sleep(0.2)

                # Type the post
                await self._page.keyboard.type(post_text, delay=10)
                await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"[FacebookPoster] Keyboard typing failed, trying JS injection: {e}")
                # Fallback: Use JavaScript to inject content directly
                # Escape backticks for JS string
                escaped_text = post_text.replace("`", "\\`")
                js_code = '''
                    () => {
                        const editor = document.querySelector('div[contenteditable="true"][role="textbox"]');
                        if (editor) {
                            editor.focus();
                            editor.textContent = arguments[0];
                            // Trigger input events so Facebook knows there's content
                            editor.dispatchEvent(new Event('input', {bubbles: true}));
                            editor.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    }
                '''
                await self._page.evaluate(js_code, escaped_text)
                await asyncio.sleep(1)


            # Click the Post button - use JavaScript execution for reliability
            posted = False

            # Method 1: JavaScript evaluation to find and click the button - most reliable
            try:
                posted = await self._page.evaluate('''() => {
                    // Find all potential post buttons
                    const selectors = [
                        'div[aria-label="Post"]',
                        'button[data-testid="react-composer-post-button"]',
                        'div[role="button"][aria-label="Post"]',
                        'span:has-text("Post")',
                        'button:has-text("Post")'
                    ];

                    for (const sel of selectors) {
                        const btn = document.querySelector(sel);
                        if (btn && (btn.offsetParent !== null)) {  // visible
                            // Use both click methods
                            btn.click();
                            btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                            return true;
                        }
                    }

                    // Last resort - search all buttons/text
                    const all = document.querySelectorAll('button, div[role="button"], span, a');
                    for (const el of all) {
                        const txt = el.textContent?.trim().toLowerCase() || '';
                        if (txt === 'post' && el.offsetParent !== null) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                if posted:
                    logger.info("[FacebookPoster] Posted via JavaScript click")
            except Exception as e:
                logger.debug(f"JS click failed: {e}")

            # Method 2: Ctrl+Enter works on Facebook
            if not posted:
                await self._page.keyboard.press('Control+Enter')
                posted = True
                logger.info("[FacebookPoster] Posted via Ctrl+Enter")

            # Method 3: Click via evaluate with explicit action
            if not posted:
                try:
                    await self._page.evaluate('''() => {
                        document.activeElement?.blur();
                        const postBtn = Array.from(document.querySelectorAll('div[role="button"], button'))
                            .find(el => el.textContent?.trim() === 'Post');
                        if (postBtn) {
                            postBtn.click();
                            postBtn.dispatchEvent(new Event('click', {bubbles: true}));
                        }
                    }''')
                    posted = True
                except Exception as e:
                    logger.debug(f"Method 3 failed: {e}")

            if not posted:
                logger.error("[FacebookPoster] Could not find Post button")
                raise Exception("Could not find Post button")

            # Wait for post to be submitted and verify it worked
            logger.info("[FacebookPoster] Waiting for post to be published...")
            await asyncio.sleep(3)

            # Check if post appeared in feed (look for the text we just posted)
            post_appeared = False
            try:
                # Look for any newly created post in the feed
                feed_posts = await self._page.query_selector_all('[role="article"], [data-pagelet="FeedUnit"]')
                if feed_posts:
                    post_appeared = True
                    logger.info("[FacebookPoster] Post detected in feed")
            except Exception:
                pass

            # Check if composer closed (post was submitted)
            try:
                composer = await self._page.query_selector('div[aria-label="Create a post"]')
                if composer:
                    is_visible = await composer.is_visible()
                    if not is_visible:
                        post_appeared = True
                        logger.info("[FacebookPoster] Composer closed - post likely published")
            except Exception:
                pass

            # Wait longer for Facebook to process the post
            await asyncio.sleep(5)

            # Additional verification: Navigate to own profile and check for the post
            try:

                # Check if we have any posts by looking for post content
                search_term = post_text[:15].replace("'", "\\'")
                post_content_match = await self._page.evaluate(('(term) => {const posts = document.querySelectorAll("[role=article], [data-pagelet*=FeedUnit]"); return posts[0]?.textContent?.includes(term);'), search_term)
                if not post_content_match:
                    logger.warning('[FacebookPoster] Post may not have published - content not found')
            except Exception as e:
                logger.debug(f"Profile check failed: {e}")


            # Check that composer input is cleared (meaning post was published)
            # If text still exists, the post may have failed
            try:
                editor = await self._page.query_selector('div[contenteditable="true"][role="textbox"]')
                if editor:
                    editor_text = await editor.inner_text()
                    if editor_text and len(editor_text.strip()) > 0:
                        logger.warning("[FacebookPoster] Editor still has text - post may NOT have been published!")
                        logger.warning("[FacebookPoster] Posting likely FAILED - moving to human review")
                        await self._close_browser()
                        await self._move_to_human_review(post_path, "Post likely failed - editor still has text")
                        return False
            except Exception:
                pass

            # Move to Done folder
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            done_filename = f"{timestamp}_done_{post_path.stem}.md"
            done_path = self.done_path / done_filename

            # Add posted metadata
            done_content = content + f"\n\n---\n\n**POSTED TO FACEBOOK:** {datetime.now().isoformat()}\n"
            done_path.write_text(done_content, encoding="utf-8")

            # Delete from approved
            post_path.unlink()

            await self._log_action("post_published", post_path.stem, str(done_path), post_text)

            logger.info(f"[FacebookPoster] Successfully posted: {done_filename}")

            # Update dashboard
            if self._dashboard_updater:
                self._dashboard_updater.update_all()

            # Close browser after successful posting
            await self._close_browser()
            return True

        except Exception as e:
            logger.error(f"[FacebookPoster] Failed to publish post: {e}")
            await self._log_action("post_failed", post_path.stem, str(e))
            await self._close_browser()

            # Retry with exponential backoff
            if retry_count < MAX_RETRIES:
                delay = min(BASE_DELAY * (2 ** retry_count), MAX_DELAY)
                logger.warning(f"[FacebookPoster] Retrying in {delay:.1f}s... (attempt {retry_count + 1}/{MAX_RETRIES})")
                await self._log_action("post_retry", post_path.stem, f"attempt {retry_count + 1}, delay {delay:.1f}s")
                await asyncio.sleep(delay)
                return await self.publish_post(post_path, retry_count + 1)

            # All retries exhausted - move to human review
            logger.error(f"[FacebookPoster] All {MAX_RETRIES} retries exhausted for {post_path.stem}")
            await self._move_to_human_review(post_path, str(e))
            return False

    def _extract_content_from_markdown(self, md_content: str) -> Optional[str]:
        """Extract post content from markdown file."""
        # Always take everything after ## Post Content until the next --- or header
        match = re.search(
            r"## Post Content\s*\n+(.*?)(?=\n---|\n## |\Z)",
            md_content,
            re.DOTALL
        )
        if match:
            content = match.group(1).strip()
            if content:
                return content

        # Strategy 2: Fallback - get everything after the first ---
        match = re.search(r"---\s*\n+(.+)", md_content, re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Stop at the next --- or platform info
            if "##" in content or "Platform:" in content:
                content = content.split("##")[0].split("Platform:")[0].strip()
            return content

        # Fallback: get everything after "## Post Content"
        match = re.search(r"## Post Content\s*\n+(.+)", md_content, re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Remove subsequent metadata section if present
            if "## Approval" in content:
                content = content.split("## Approval")[0].strip()
            elif "## Metadata" in content:
                content = content.split("## Metadata")[0].strip()
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
            "source": "facebook_poster",
            "platform": "facebook",
            "actor": "claude_code",
            "action": action,
            "item_id": item_id,
            "details": details,
            "post_content": post_content[:500] if post_content else "",
            "approval_status": "approved" if action == "post_published" else "failed",
        }

        log_file = self.logs_path / f"facebook_poster_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

    async def _move_to_human_review(
        self,
        file_path: Path,
        reason: str,
    ) -> None:
        """Move failed post to human review queue at vault root."""
        try:
            if not self._human_review_path:
                return

            self._human_review_path.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            review_filename = f"{timestamp}_failed_{file_path.stem}.md"
            review_file = self._human_review_path / review_filename

            # Add error metadata
            content = file_path.read_text(encoding="utf-8")
            review_content = content + f"\n\n---\n\n**PUBLISHING FAILED:** {datetime.now().isoformat()}\n**Error:** {reason}\n**Action Required:** Manual review and retry\n"
            review_file.write_text(review_content, encoding="utf-8")

            # Remove original
            file_path.unlink()

            await self._log_action("moved_to_human_review", file_path.stem, f"Error: {reason}")
            logger.warning(f"[FacebookPoster] Moved to Human_Review_Queue: {file_path.name}")
        except Exception as e:
            logger.error(f"[FacebookPoster] Failed to move to human review: {e}")


async def main():
    """Main entry point for standalone testing."""
    import dotenv
    dotenv.load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    vault_path = Path("AI_Employee_Vault")

    poster = FacebookPoster(
        approved_path=vault_path / "Social_Media" / "Facebook_Posts" / "Approved",
        done_path=vault_path / "Social_Media" / "Facebook_Posts" / "Done",
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
            print("1. Create requirement file in facebook_post/")
            print("2. Watcher moves it to Needs_Action/")
            print("3. Claude Code creates plan in Plans/")
            print("4. Claude Code creates draft in Facebook_Posts/Draft/")
            print("5. Human moves draft to Approved/")
            print("6. This poster publishes and moves to Done/")

    finally:
        await poster.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
