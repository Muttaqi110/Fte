"""
LinkedIn Poster - Publishes approved LinkedIn posts.

Monitors the Approved folder for posts ready to publish.
When a draft is approved, publishes it to LinkedIn and moves to Done.

Workflow:
1. Human creates requirement → linkedin_post/
2. Watcher moves to → Needs_Action/
3. Claude Code creates plan → Plans/
4. Claude Code creates draft → Draft/
5. Human approves → Approved/
6. This poster publishes → Done/

Includes retry logic with exponential backoff for transient errors.
"""

import asyncio
import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from dashboard_updater import DashboardUpdater

logger = logging.getLogger(__name__)


class LinkedInPoster:
    """
    LinkedIn poster that publishes approved content.

    Watches Approved folder for drafts ready to publish.
    Publishes to LinkedIn and archives to Done folder.
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
        Initialize the LinkedIn poster.

        Args:
            approved_path: Path where approved posts wait for publishing
            done_path: Path where posted content is archived
            logs_path: Path to logs folder
            vault_path: Path to AI_Employee_Vault (for dashboard updates)
            headless: Run browser in headless mode
            user_data_dir: Browser profile directory (defaults to project/.linkedin_profile)
        """
        self.approved_path = Path(approved_path)
        self.done_path = Path(done_path)
        self.logs_path = Path(logs_path)
        self.headless = headless
        # Dashboard updater
        self._dashboard_updater = DashboardUpdater(vault_path) if vault_path else None
        # Use project-local profile directory to avoid conflicts
        if user_data_dir:
            self.user_data_dir = Path(user_data_dir)
        else:
            self.user_data_dir = Path.cwd() / ".linkedin_poster_profile"

        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._playwright = None

    async def startup(self) -> None:
        """Initialize directories only. Browser is started lazily when needed."""
        self.approved_path.mkdir(parents=True, exist_ok=True)
        self.done_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
        logger.info("[LinkedInPoster] Initialized (browser will start on demand)")

    async def _start_browser(self) -> bool:
        """Start browser for posting."""
        if self._page is not None:
            return True

        self._playwright = await async_playwright().start()

        logger.info("[LinkedInPoster] Starting browser with persistent profile...")
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

            logger.info("[LinkedInPoster] Navigating to LinkedIn...")
            await self._page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(5)  # Give more time for page to load

            # Check if logged in by looking for various LinkedIn feed elements
            logged_in = False
            login_selectors = [
                'button[aria-label="Start a post"]',
                '[data-control-name="actor.sharebox"]',
                'div.share-box',
                'button[data-control-name="sharebox"]',
                '.share-box-feed-entry',
                'div[role="button"][aria-label*="post"]',
                'span:has-text("Start a post")',
                '.share-promoted-detour',
                'div[class*="share-box"]',
            ]

            for selector in login_selectors:
                try:
                    element = await self._page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            logged_in = True
                            logger.info(f"[LinkedInPoster] Found login indicator: {selector}")
                            break
                except:
                    continue

            # Also check URL - if we're on feed, we're logged in
            current_url = self._page.url
            if 'linkedin.com/feed' in current_url or 'linkedin.com/in/' in current_url:
                logged_in = True
                logger.info("[LinkedInPoster] Detected logged in from URL")

            if not logged_in:
                logger.warning("[LinkedInPoster] ============================================")
                logger.warning("[LinkedInPoster] NOT LOGGED IN - Please log in to LinkedIn NOW")
                logger.warning("[LinkedInPoster] The browser window is waiting for you...")
                logger.warning("[LinkedInPoster] ============================================")

                # Wait up to 5 minutes for user to log in
                try:
                    await self._page.wait_for_selector('button[aria-label="Start a post"], [data-control-name="actor.sharebox"], div.share-box, .share-box-feed-entry', timeout=300000)
                    logger.info("[LinkedInPoster] Login detected! Proceeding...")
                    logged_in = True
                except:
                    # Check URL again as fallback
                    await asyncio.sleep(2)
                    current_url = self._page.url
                    if 'linkedin.com/feed' in current_url or 'login' not in current_url:
                        logged_in = True
                        logger.info("[LinkedInPoster] Login detected from URL change!")
                    else:
                        logger.error("[LinkedInPoster] Login timeout - took too long to log in")
                        return False

            return True
        except Exception as e:
            logger.error(f"[LinkedInPoster] Browser launch failed: {e}")
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
        logger.info("[LinkedInPoster] Browser closed")

    async def shutdown(self) -> None:
        """Cleanup browser."""
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
        logger.info("[LinkedInPoster] Shutdown complete")

    async def check_for_approved_posts(self) -> List[Path]:
        """Check for approved posts ready to publish."""
        approved_files = list(self.approved_path.glob("*.md"))
        return approved_files

    async def publish_post(self, post_path: Path, retry_count: int = 0) -> bool:
        """
        Publish an approved post to LinkedIn with retry logic.

        Args:
            post_path: Path to approved post markdown file
            retry_count: Current retry attempt (internal use)

        Returns:
            True if published successfully
        """
        MAX_RETRIES = 5
        BASE_DELAY = 1.0
        MAX_DELAY = 60.0

        # Start browser for posting (if not already running)
        if self._page is None:
            if not await self._start_browser():
                logger.error("[LinkedInPoster] Could not start browser")
                # Don't retry here - _start_browser already waited for login
                # Move to human review instead
                await self._move_to_human_review(post_path, "Browser startup failed - manual login required")
                return False

        if not self._page:
            logger.error("[LinkedInPoster] Could not initialize browser")
            await self._move_to_human_review(post_path, "Browser initialization failed")
            return False

        # Read approved post
        content = post_path.read_text(encoding="utf-8")

        # Extract post content from markdown
        post_text = self._extract_content_from_markdown(content)

        if not post_text:
            logger.error(f"[LinkedInPoster] No content found in {post_path}")
            await self._close_browser()
            return False

        try:
            # Navigate to LinkedIn feed
            logger.info("[LinkedInPoster] Navigating to feed...")
            await self._page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(5)  # Wait for page to fully load

            # Take a screenshot for debugging
            screenshot_path = self.logs_path / f"debug_feed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await self._page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(f"[LinkedInPoster] Saved debug screenshot: {screenshot_path}")

            # Try multiple ways to find "Start a post" button
            clicked = False

            # Wait for page to fully load
            await asyncio.sleep(3)

            # Method 1: Try finding by aria-label (most specific)
            try:
                element = await self._page.wait_for_selector('button[aria-label="Start a post"]', timeout=3000)
                if element:
                    await element.click()
                    clicked = True
                    logger.info("[LinkedInPoster] Clicked 'Start a post' via aria-label")
            except Exception as e:
                logger.debug(f"Method 1 (aria-label) failed: {e}")

            # Method 2: Try finding by text content with button
            if not clicked:
                try:
                    element = await self._page.query_selector('button:has-text("Start a post")')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[LinkedInPoster] Clicked 'Start a post' via button text")
                except Exception as e:
                    logger.debug(f"Method 2 (button text) failed: {e}")

            # Method 3: Try finding the share box trigger div
            if not clicked:
                try:
                    # LinkedIn often uses a div that looks like a button
                    element = await self._page.query_selector('[data-control-name="actor.sharebox"]')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[LinkedInPoster] Clicked sharebox trigger")
                except Exception as e:
                    logger.debug(f"Method 3 (sharebox trigger) failed: {e}")

            # Method 4: Try share-box-feed-entry class
            if not clicked:
                try:
                    element = await self._page.query_selector('.share-box-feed-entry__trigger')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[LinkedInPoster] Clicked share-box-feed-entry__trigger")
                except Exception as e:
                    logger.debug(f"Method 4 (share-box class) failed: {e}")

            # Method 5: Try finding by partial class match on button
            if not clicked:
                try:
                    element = await self._page.query_selector('button[class*="share-box"]')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[LinkedInPoster] Clicked button with share-box class")
                except Exception as e:
                    logger.debug(f"Method 5 (share-box class match) failed: {e}")

            # Method 6: Try artdeco-button with text
            if not clicked:
                try:
                    element = await self._page.query_selector('.artdeco-button:has-text("Start")')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[LinkedInPoster] Clicked artdeco-button with 'Start'")
                except Exception as e:
                    logger.debug(f"Method 6 (artdeco-button) failed: {e}")

            # Method 7: Try finding the pencil icon container
            if not clicked:
                try:
                    # LinkedIn often has a pencil icon for creating posts
                    element = await self._page.query_selector('button:has(svg[class*="pencil"])')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[LinkedInPoster] Clicked button with pencil icon")
                except Exception as e:
                    logger.debug(f"Method 7 (pencil icon) failed: {e}")

            # Method 8: Try any element containing "Start a post" text
            if not clicked:
                try:
                    # Use evaluate to find and click any element with the text
                    found = await self._page.evaluate('''() => {
                        const buttons = document.querySelectorAll('button, [role="button"], div[class*="share"]');
                        for (const btn of buttons) {
                            if (btn.textContent && btn.textContent.toLowerCase().includes('start a post')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    if found:
                        clicked = True
                        logger.info("[LinkedInPoster] Clicked via JavaScript text search")
                except Exception as e:
                    logger.debug(f"Method 8 (JS text search) failed: {e}")

            # Method 9: Try clicking on the share box area directly
            if not clicked:
                try:
                    element = await self._page.query_selector('.share-box-feed-entry, [class*="share-box"]')
                    if element:
                        await element.click()
                        clicked = True
                        logger.info("[LinkedInPoster] Found share box area")
                except Exception as e:
                    logger.debug(f"Method 9 (share box area) failed: {e}")

            if not clicked:
                # Log page content for debugging
                html_content = await self._page.content()
                debug_html = self.logs_path / f"debug_html_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                debug_html.write_text(html_content, encoding="utf-8")
                logger.error(f"[LinkedInPoster] Could not find 'Start a post' button. Saved HTML to {debug_html}")
                # Raise exception to trigger retry
                raise Exception("Could not find 'Start a post' button on page")

            # Wait for the post modal to appear
            logger.info("[LinkedInPoster] Waiting for post modal...")
            await asyncio.sleep(3)

            # Take screenshot of modal
            modal_screenshot = self.logs_path / f"debug_modal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await self._page.screenshot(path=str(modal_screenshot), full_page=True)
            logger.info(f"[LinkedInPoster] Saved modal screenshot: {modal_screenshot}")

            # Find the text editor - LinkedIn uses a contenteditable div
            # Try multiple times with increasing wait
            editor = None
            for attempt in range(5):
                editor_selectors = [
                    'div[contenteditable="true"][role="textbox"]',
                    'div[contenteditable="true"][aria-label*="post"]',
                    'div[contenteditable="true"][aria-label*="What"]',
                    '.ql-editor[contenteditable="true"]',
                    '[data-test="share-post-box"] div[contenteditable="true"]',
                    'div[contenteditable="true"][data-placeholder*="What do you want"]',
                    '.share-box-feed-entry__text-editor div[contenteditable="true"]',
                    '.artdeco-text-input--input div[contenteditable="true"]',
                    'div[contenteditable="true"][data-placeholder]',
                    'div[contenteditable="true"]',
                ]

                for selector in editor_selectors:
                    try:
                        editor = await self._page.wait_for_selector(selector, timeout=3000)
                        if editor:
                            # Verify it's visible and editable
                            is_visible = await editor.is_visible()
                            if is_visible:
                                logger.info(f"[LinkedInPoster] Found editor: {selector}")
                                break
                            else:
                                editor = None
                    except Exception:
                        continue

                if editor:
                    break

                await asyncio.sleep(2)
                logger.info(f"[LinkedInPoster] Retrying editor search (attempt {attempt + 2})")

            if not editor:
                # Try clicking on the modal first to focus it
                try:
                    # Click on the modal dialog
                    await self._page.click('[role="dialog"], .artdeco-modal, [class*="modal"]', timeout=2000)
                    await asyncio.sleep(1)
                    # Now try finding editor again
                    editor = await self._page.query_selector('div[contenteditable="true"]')
                    if editor:
                        logger.info("[LinkedInPoster] Found editor after clicking modal")
                except Exception:
                    pass

            if not editor:
                # Try JavaScript to find and focus editor
                try:
                    found = await self._page.evaluate('''() => {
                        const editors = document.querySelectorAll('div[contenteditable="true"]');
                        if (editors.length > 0) {
                            // Find the most likely editor (usually has placeholder text)
                            for (const ed of editors) {
                                const placeholder = ed.getAttribute('data-placeholder') || ed.getAttribute('aria-label') || '';
                                if (placeholder.toLowerCase().includes('want to talk') ||
                                    placeholder.toLowerCase().includes('post') ||
                                    placeholder.toLowerCase().includes('share')) {
                                    ed.focus();
                                    return true;
                                }
                            }
                            // Fallback to first visible editor
                            for (const ed of editors) {
                                if (ed.offsetParent !== null) {
                                    ed.focus();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }''')
                    if found:
                        editor = await self._page.query_selector('div[contenteditable="true"]')
                        if editor:
                            logger.info("[LinkedInPoster] Found editor via JavaScript")
                except Exception as e:
                    logger.debug(f"JS editor search failed: {e}")

            if not editor:
                logger.error("[LinkedInPoster] Could not find text editor")
                # Save debug HTML
                html_content = await self._page.content()
                debug_html = self.logs_path / f"debug_editor_html_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                debug_html.write_text(html_content, encoding="utf-8")
                logger.error(f"[LinkedInPoster] Saved HTML to {debug_html}")
                # Raise exception to trigger retry
                raise Exception("Could not find text editor in post modal")

            await editor.click()
            await asyncio.sleep(0.5)

            # Clear any existing content and type the new post
            await self._page.keyboard.press('Control+a')
            await asyncio.sleep(0.2)
            await self._page.keyboard.type(post_text, delay=10)
            await asyncio.sleep(1)

            # Click "Post" button
            posted = False
            post_button_selectors = [
                'button[aria-label="Post"]',
                'button[aria-label="post"]',
                'button:has-text("Post")',
                '[data-control-name="share"]',
                'button.share-actions__primary-action',
                'button.artdeco-button--primary:has-text("Post")',
                'button.artdeco-button--primary',
                'button[type="submit"]',
            ]

            for selector in post_button_selectors:
                try:
                    button = await self._page.wait_for_selector(selector, timeout=3000)
                    if button:
                        # Verify it's visible
                        is_visible = await button.is_visible()
                        if is_visible:
                            await button.click()
                            posted = True
                            logger.info(f"[LinkedInPoster] Clicked post button: {selector}")
                            break
                except Exception:
                    continue

            # Fallback: Try JavaScript to find and click post button
            if not posted:
                try:
                    found = await self._page.evaluate('''() => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = btn.textContent?.trim().toLowerCase() || '';
                            const ariaLabel = btn.getAttribute('aria-label')?.toLowerCase() || '';
                            if (text === 'post' || ariaLabel === 'post') {
                                btn.click();
                                return true;
                            }
                        }
                        // Also try submit buttons in dialogs
                        const submitBtns = document.querySelectorAll('[role="dialog"] button[type="submit"], .artdeco-modal button.artdeco-button--primary');
                        for (const btn of submitBtns) {
                            if (btn.offsetParent !== null) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    if found:
                        posted = True
                        logger.info("[LinkedInPoster] Clicked post button via JavaScript")
                except Exception as e:
                    logger.debug(f"JS post button search failed: {e}")

            if not posted:
                logger.error("[LinkedInPoster] Could not find 'Post' button")
                # Save screenshot
                post_btn_screenshot = self.logs_path / f"debug_post_btn_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await self._page.screenshot(path=str(post_btn_screenshot), full_page=True)
                # Raise exception to trigger retry
                raise Exception("Could not find 'Post' button in modal")

            await asyncio.sleep(3)

            # Verify post was published - check if dialog closed
            logger.info("[LinkedInPoster] Post submitted successfully")

            # Move to Done folder
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            done_filename = f"{timestamp}_done_{post_path.stem}.md"
            done_path = self.done_path / done_filename

            # Add posted metadata
            done_content = content + f"\n\n---\n\n**POSTED:** {datetime.now().isoformat()}\n"
            done_path.write_text(done_content, encoding="utf-8")

            # Delete from approved
            post_path.unlink()

            await self._log_action("post_published", post_path.stem, str(done_path))

            logger.info(f"[LinkedInPoster] Successfully posted: {done_filename}")

            # Update dashboard
            if self._dashboard_updater:
                self._dashboard_updater.update_folder("linkedin_done")

            # Close browser after successful posting
            await self._close_browser()
            return True

        except Exception as e:
            logger.error(f"[LinkedInPoster] Failed to publish post: {e}")
            await self._log_action("post_failed", post_path.stem, str(e))

            # Retry with exponential backoff (keep browser open for retry)
            if retry_count < MAX_RETRIES:
                delay = min(BASE_DELAY * (2 ** retry_count), MAX_DELAY)
                logger.warning(f"[LinkedInPoster] Retrying in {delay:.1f}s... (attempt {retry_count + 1}/{MAX_RETRIES})")
                await self._log_action("post_retry", post_path.stem, f"attempt {retry_count + 1}, delay {delay:.1f}s")

                # Try to refresh the page before retry
                try:
                    if self._page:
                        await self._page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
                except:
                    pass

                await asyncio.sleep(delay)
                return await self.publish_post(post_path, retry_count + 1)

            # All retries exhausted - close browser and move to Human_Review_Queue
            await self._close_browser()
            logger.error(f"[LinkedInPoster] All {MAX_RETRIES} retries exhausted for {post_path.stem}")
            await self._move_to_human_review(post_path, str(e))
            return False

    async def _move_to_human_review(self, post_path: Path, error: str) -> None:
        """Move failed post to human review queue."""
        try:
            review_path = self.approved_path.parent.parent / "Human_Review_Queue"
            review_path.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            review_filename = f"{timestamp}_failed_{post_path.stem}.md"
            review_file = review_path / review_filename

            # Add error metadata
            content = post_path.read_text(encoding="utf-8")
            review_content = content + f"\n\n---\n\n**PUBLISHING FAILED:** {datetime.now().isoformat()}\n**Error:** {error}\n**Action Required:** Manual review and retry\n"
            review_file.write_text(review_content, encoding="utf-8")

            # Remove from approved
            post_path.unlink()

            await self._log_action("moved_to_human_review", post_path.stem, f"Error: {error}")
            logger.info(f"[LinkedInPoster] Moved to Human_Review_Queue: {review_filename}")
        except Exception as e:
            logger.error(f"[LinkedInPoster] Failed to move to human review: {e}")

    def _extract_content_from_markdown(self, md_content: str) -> Optional[str]:
        """Extract post content from markdown file."""
        # Find content between "## Post Content" and "---"
        match = re.search(
            r"## Post Content\s*\n+(.*?)\n*---",
            md_content,
            re.DOTALL
        )
        if match:
            return match.group(1).strip()

        # Fallback: get everything after "## Post Content"
        match = re.search(r"## Post Content\s*\n+(.*)", md_content, re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Remove metadata section if present
            if "## Metadata" in content:
                content = content.split("## Metadata")[0].strip()
            return content

        return None

    def _slugify(self, text: str) -> str:
        """Convert text to filesystem-safe slug."""
        slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text)
        slug = re.sub(r"[\s_]+", "-", slug)
        return slug.strip("-").lower() or "post"

    async def _log_action(
        self,
        action: str,
        item_id: str,
        details: str,
    ) -> None:
        """Log action to JSON file."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": "linkedin_poster",
            "action": action,
            "item_id": item_id,
            "details": details,
        }

        log_file = self.logs_path / f"linkedin_poster_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
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

    poster = LinkedInPoster(
        approved_path=vault_path / "LinkedIn_Posts" / "Approved",
        done_path=vault_path / "LinkedIn_Posts" / "Done",
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
            print("1. Create requirement file in linkedin_post/")
            print("2. Watcher moves it to Needs_Action/")
            print("3. Claude Code creates plan in Plans/")
            print("4. Claude Code creates draft in Draft/")
            print("5. Human moves draft to Approved/")
            print("6. This poster publishes and moves to Done/")

    finally:
        await poster.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
