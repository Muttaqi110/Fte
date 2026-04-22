"""
Orchestrator - Unified workflow engine.

Single file handles all processing:
- Processes tasks from Needs_Action
- Generates drafts on request (via skills)
- Executes approved drafts from Approved folder
"""

import asyncio
import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from config_parser import get_config_parser

import aiofiles

from dashboard_updater import update_dashboard_on_action

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Unified Orchestrator for all processing.

    Auto-detects mode:
    - If Pending_Approval exists: Full HITL workflow
    - If Business_Goals.md exists: Daily LinkedIn posts
    - Always: Process Needs_Action, execute Approved
    """

    def __init__(
        self,
        vault_path: Path,
        poll_interval: float = 5.0,
        daily_post_time: str = "09:00",
        gmail_watcher=None,
        whatsapp_watcher=None,
        linkedin_poster=None,
        x_poster=None,
        facebook_poster=None,
        send_mail_watcher=None,
    ):
        """
        Initialize the orchestrator.

        Args:
            vault_path: Path to AI_Employee_Vault
            poll_interval: Seconds between checks
            daily_post_time: Time for daily LinkedIn post (HH:MM)
            gmail_watcher: GmailWatcher instance for sending emails
            whatsapp_watcher: WhatsAppWatcher instance for sending WhatsApp messages
            linkedin_poster: LinkedInPoster instance for publishing posts
            x_poster: XPoster instance for publishing X (Twitter) posts
            facebook_poster: FacebookPoster instance for publishing Facebook posts
            send_mail_watcher: SendMailWatcher instance for monitoring send_mails
        """
        self.vault_path = Path(vault_path)
        self.poll_interval = poll_interval
        self.daily_post_time = daily_post_time
        self.gmail_watcher = gmail_watcher
        self.whatsapp_watcher = whatsapp_watcher
        self.linkedin_poster = linkedin_poster
        self.x_poster = x_poster
        self.facebook_poster = facebook_poster
        self.send_mail_watcher = send_mail_watcher

        # Dynamic config from vault files
        self.config = get_config_parser(vault_path)

        # Paths
        self.needs_action_path = self.vault_path / "Needs_Action"
        self.done_path = self.vault_path / "Done"
        self.logs_path = self.vault_path / "Logs"
        self.handbook_path = self.vault_path / "Company_Handbook.md"

        # Silver paths (may not exist)
        self.plans_path = self.vault_path / "Plans"
        self.rejected_path = self.vault_path / "Rejected"
        self.business_goals_path = self.vault_path / "Business_Goals.md"

        # LinkedIn posts paths
        self.linkedin_posts_path = self.vault_path / "Social_Media" / "LinkedIn_Posts"
        self.linkedin_drafts_path = self.linkedin_posts_path / "Draft"
        self.linkedin_approved_path = self.linkedin_posts_path / "Approved"
        self.linkedin_done_path = self.linkedin_posts_path / "Done"

        # Gmail messages paths
        self.gmail_messages_path = self.vault_path / "Gmail" / "Gmail_Messages"
        self.gmail_drafts_path = self.gmail_messages_path / "Draft"
        self.gmail_approved_path = self.gmail_messages_path / "Approved"
        self.gmail_done_path = self.gmail_messages_path / "Done"

        # WhatsApp messages paths
        self.whatsapp_messages_path = self.vault_path / "WhatsApp" / "WhatsApp_Messages"
        self.whatsapp_drafts_path = self.whatsapp_messages_path / "Draft"
        self.whatsapp_approved_path = self.whatsapp_messages_path / "Approved"
        self.whatsapp_done_path = self.whatsapp_messages_path / "Done"

        # X (Twitter) posts paths
        self.x_posts_path = self.vault_path / "Social_Media" / "X_Posts"
        self.x_drafts_path = self.x_posts_path / "Draft"
        self.x_approved_path = self.x_posts_path / "Approved"
        self.x_done_path = self.x_posts_path / "Done"

        # Facebook posts paths
        self.facebook_posts_path = self.vault_path / "Social_Media" / "Facebook_Posts"
        self.facebook_drafts_path = self.facebook_posts_path / "Draft"
        self.facebook_approved_path = self.facebook_posts_path / "Approved"
        self.facebook_done_path = self.facebook_posts_path / "Done"

        self._running = False
        self._processed_files: set[str] = set()
        self._last_daily_post: Optional[datetime] = None

        # Disabled daily auto-posts - only on request
        self.daily_posts = False

        features = []
        if self.daily_posts:
            features.append("DailyPosts")

        logger.info(f"[Orchestrator] Initialized {'(' + ', '.join(features) + ')' if features else ''}")

    async def run(self) -> None:
        """Main orchestrator loop."""
        self._running = True

        # Ensure directories
        for path in [self.needs_action_path, self.done_path, self.logs_path, self.plans_path]:
            path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[Orchestrator] Started")

        try:
            while self._running:
                # Always: Process new tasks
                await self._check_needs_action()

                # Always: Execute approved drafts
                await self._check_approved()

                await asyncio.sleep(self.poll_interval)

        except asyncio.CancelledError:
            logger.info("[Orchestrator] Cancelled")
        finally:
            logger.info("[Orchestrator] Stopped")

    def stop(self) -> None:
        """Stop the orchestrator."""
        self._running = False
        logger.info("[Orchestrator] Stop signal received")

    async def _check_needs_action(self) -> None:
        """Process tasks in Needs_Action folder."""
        task_files = [
            f for f in self.needs_action_path.glob("*.md")
            if f.name != ".gitkeep" and f.name not in self._processed_files
        ]

        for task_file in task_files:
            try:
                await self._process_task(task_file)
                self._processed_files.add(task_file.name)
            except Exception as e:
                logger.error(f"[Orchestrator] Failed: {task_file.name}: {e}")
                await self._log_action("process_failed", task_file.name, {"error": str(e)})

    async def _process_task(self, task_path: Path) -> None:
        """Process a single task - auto-execute plans, save drafts for send approval."""
        logger.info(f"[Orchestrator] Processing: {task_path.name}")

        # Read task
        async with aiofiles.open(task_path, "r", encoding="utf-8") as f:
            content = await f.read()

        metadata = self._parse_metadata(content)
        flags = self._check_flags(content)
        source = metadata.get("source", "email")

        # Check if this is a mail request from send_mails folder
        if task_path.name.startswith("mail_") or source == "send_mails":
            await self._process_mail_request(task_path, content, metadata)
            return

        # Check if this is a social media post request (look for platform in content or filename)
        content_lower = content.lower()
        filename_lower = task_path.name.lower()

        # Check for platform in content (YAML metadata or title)
        if re.search(r"platform:\s*linkedin", content, re.IGNORECASE) or \
           "linkedin" in filename_lower or \
           "linkedin post" in content_lower:
            await self._process_linkedin_post_request(task_path, content, metadata)
            return

        if re.search(r"platform:\s*x", content, re.IGNORECASE) or \
           "platform:\s*twitter" in content_lower or \
           "_x_post" in filename_lower or \
           "_twitter_post" in filename_lower:
            await self._process_x_post_request(task_path, content, metadata)
            return

        if re.search(r"platform:\s*facebook", content, re.IGNORECASE) or \
           "facebook" in filename_lower or \
           "facebook post" in content_lower:
            await self._process_facebook_post_request(task_path, content, metadata)
            return

        # Check if this is an invoice request - skip and let OdooInvoiceWatcher handle it
        # Get thresholds dynamically from config
        thresholds = self.config.get_financial_thresholds()
        payment_flag_amount = thresholds.get("payment_flag_amount", 500)

        invoice_keywords = ["invoice", "bill", "payment request", "create invoice", "send invoice"]
        content_lower = content.lower()

        # Check if this is an invoice request - skip and let OdooInvoiceWatcher handle it
        if any(kw in content_lower for kw in invoice_keywords) or "invoice" in task_path.name.lower():
            logger.info(f"[Orchestrator] Invoice request detected - skipping (handled by OdooInvoiceWatcher): {task_path.name}")
            return

        # Check if payment > threshold - flag for manual approval (dynamic from config)
        if "payment" in content_lower or "pay" in content_lower:
            amount_match = re.search(r"\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)", content)
            if amount_match:
                amount = int(amount_match.group(1).replace(",", ""))
                if amount > payment_flag_amount:
                    logger.info(f"[Orchestrator] Payment over ${payment_flag_amount} detected - requiring manual approval: {task_path.name}")
                    flags["requires_manual_approval"] = True
                    flags["reasons"].append(f"Payment amount ${amount} exceeds ${payment_flag_amount} threshold")

        handbook = await self._read_file(self.handbook_path)

        # Always create plan (auto-executed)
        plan = self._create_plan(content, metadata, task_path.name)
        plan_path = self.plans_path / f"plan_{task_path.name}"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(plan_path, "w", encoding="utf-8") as f:
            await f.write(plan)
        logger.info(f"[Orchestrator] Plan created: {plan_path.name}")

        # Generate draft
        draft = await self._generate_draft(content, handbook, metadata, flags)

        # Save to source-specific Draft folder
        if source == "email":
            draft_folder = self.gmail_drafts_path
            approved_folder = self.gmail_approved_path
            done_folder = self.gmail_done_path
        elif source == "whatsapp":
            draft_folder = self.whatsapp_drafts_path
            approved_folder = self.whatsapp_approved_path
            done_folder = self.whatsapp_done_path
        else:
            # Default to done folder for unknown sources
            draft_folder = self.done_path
            approved_folder = self.done_path
            done_folder = self.done_path

        draft_folder.mkdir(parents=True, exist_ok=True)
        approved_folder.mkdir(parents=True, exist_ok=True)
        done_folder.mkdir(parents=True, exist_ok=True)

        draft_path = draft_folder / f"draft_{task_path.name}"

        async with aiofiles.open(draft_path, "w", encoding="utf-8") as f:
            await f.write(draft)

        logger.info(f"[Orchestrator] Draft saved to {source} folder: {draft_path.name}")
        logger.info(f"[Orchestrator] Move to {approved_folder.name}/ to send")

        # Move original to Done
        shutil.move(str(task_path), str(self.done_path / task_path.name))

        await self._log_action("task_processed", task_path.name, {"draft": str(draft_path), "source": source})

    async def _process_mail_request(self, task_path: Path, content: str, metadata: dict) -> None:
        """Process a mail request - generate draft for Gmail approval flow."""
        logger.info(f"[Orchestrator] Processing mail request: {task_path.name}")

        # Extract recipient from metadata or content
        recipient = metadata.get("recipient", "")
        if not recipient:
            import re
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", content)
            if email_match:
                recipient = email_match.group(0)

        # Ensure Gmail directories exist
        self.gmail_drafts_path.mkdir(parents=True, exist_ok=True)
        self.gmail_approved_path.mkdir(parents=True, exist_ok=True)
        self.gmail_done_path.mkdir(parents=True, exist_ok=True)

        # Create plan
        plan = self._create_mail_plan(content, task_path.name, recipient)
        plan_path = self.plans_path / f"plan_{task_path.name}"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(plan_path, "w", encoding="utf-8") as f:
            await f.write(plan)
        logger.info(f"[Orchestrator] Mail plan created: {plan_path.name}")

        # Extract requirements
        requirements = self._extract_mail_requirements(content, recipient)

        # Generate mail draft
        draft = await self._generate_mail_draft(requirements)

        # Create meaningful filename from subject and recipient
        subject = requirements.get("subject", "mail")
        subject_slug = re.sub(r"[^a-zA-Z0-9\s]", "", subject)
        subject_slug = re.sub(r"[\s]+", "-", subject_slug).lower()[:20]
        if not subject_slug:
            subject_slug = "mail"

        # Include recipient email in filename
        recipient_email = requirements.get("recipient", "")
        if recipient_email:
            # Extract username from email
            at_idx = recipient_email.find("@")
            if at_idx > 0:
                recipient_slug = recipient_email[:at_idx].lower()
            else:
                recipient_slug = recipient_email.lower()
            recipient_slug = re.sub(r"[^a-z0-9]", "", recipient_slug)[:15]
        else:
            recipient_slug = "unknown"

        draft_filename = f"email_{recipient_slug}_{subject_slug}.md"

        # Save draft to Gmail_Messages/Draft
        draft_path = self.gmail_drafts_path / draft_filename

        async with aiofiles.open(draft_path, "w", encoding="utf-8") as f:
            await f.write(draft)

        logger.info(f"[Orchestrator] Mail draft saved: {draft_path.name}")
        logger.info(f"[Orchestrator] Move to Gmail_Messages/Approved/ to send")

        # Move original request to Done
        shutil.move(str(task_path), str(self.done_path / task_path.name))

        await self._log_action("mail_draft_created", task_path.name, {"draft": draft_path.name, "recipient": recipient})

    def _create_mail_plan(self, content: str, task_name: str, recipient: str) -> str:
        """Create a plan for mail."""
        return f"""# Plan: Send Email

| Field | Value |
|-------|-------|
| **Task** | {task_name} |
| **Type** | Email |
| **Recipient** | {recipient} |
| **Created** | {datetime.now().isoformat()} |
| **Status** | AUTO-EXECUTED |

## Original Request

{content}

## Execution Steps

1. [x] Read requirements
2. [x] Generate mail draft
3. [x] Save to Gmail Draft folder
4. [ ] Human moves to Approved to send
5. [ ] Send email via Gmail watcher

## Workflow

- ✅ Plan auto-executed (no approval needed)
- ✅ Draft generated and saved
- ⏳ Awaiting human approval to **send**
- 📁 Move draft from `Gmail_Messages/Draft/` to `Gmail_Messages/Approved/`

*Generated: {datetime.now().isoformat()}*
"""

    def _extract_mail_requirements(self, content: str, recipient: str) -> dict:
        """Extract requirements from mail request."""
        requirements = {
            "recipient": recipient,
            "subject": "",
            "body": content,
            "tone": "professional",
        }

        import re

        # Extract subject
        subject_match = re.search(r"^subject:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
        if subject_match:
            requirements["subject"] = subject_match.group(1).strip()

        # Extract tone
        content_lower = content.lower()
        if "casual" in content_lower:
            requirements["tone"] = "casual"
        elif "formal" in content_lower:
            requirements["tone"] = "formal"
        elif "friendly" in content_lower:
            requirements["tone"] = "friendly"

        return requirements

    async def _generate_mail_draft(self, requirements: dict) -> str:
        """Generate email draft using Claude."""
        recipient = requirements.get("recipient", "")
        original_body = requirements.get("body", "")
        tone = requirements.get("tone", "professional")

        # Strict prompt - Claude must output ONLY the email, zero wrapper text
        prompt = f"""You have full permissions to write this email on behalf of the user.

RULE: Output ONLY the complete email text. NOTHING else.
- NO "Here's the email"
- NO "I've drafted"
- NO explanations
- NO intro/outro commentary
- NO "As an AI"
- NO "Here is the response"

Write a {tone} email response to: {recipient}

Context/Body:
{original_body}

Now write ONLY the email:"""

        draft_body = await self._call_claude(prompt)

        if not draft_body:
            draft_body = f"Thank you for your message. I'll respond with details shortly."

        # Clean meta-commentary
        if any(bad in draft_body.lower() for bad in ["i've drafted", "the draft", "you'll need", "approval", "here's the email"]):
            draft_body = f"Thank you for your message. I'll respond with details shortly."
        else:
            # Strip any wrapper lines
            lines = draft_body.splitlines()
            cleaned = []
            found_content = False
            for line in lines:
                stripped = line.strip().lower()
                if any(marker in stripped for marker in ["here's the", "here is the", "i've drafted", "the email"]):
                    continue
                if stripped and not found_content:
                    found_content = True
                if found_content:
                    cleaned.append(line)
            draft_body = "\n".join(cleaned).strip()

        # Wrap in full draft format (matching send_mails & gmail responses)
        draft = f"""# Email Draft

## To: {recipient}
## Subject: Re: (auto-generated)

---

{draft_body}

---

*Generated: {datetime.now().isoformat()}*"""

        return draft

    async def _process_linkedin_post_request(self, task_path: Path, content: str, metadata: dict) -> None:
        """Process a LinkedIn post request - auto-execute, save draft for publish approval."""
        logger.info(f"[Orchestrator] Processing LinkedIn post request: {task_path.name}")

        # Ensure LinkedIn posts directories exist
        self.linkedin_drafts_path.mkdir(parents=True, exist_ok=True)
        self.linkedin_approved_path.mkdir(parents=True, exist_ok=True)
        self.linkedin_done_path.mkdir(parents=True, exist_ok=True)

        # Create plan (auto-executed, no approval needed)
        plan = self._create_linkedin_plan(content, task_path.name)
        plan_path = self.plans_path / f"plan_{task_path.name}"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(plan_path, "w", encoding="utf-8") as f:
            await f.write(plan)
        logger.info(f"[Orchestrator] Plan created: {plan_path.name}")

        # Extract requirements from content
        requirements = self._extract_linkedin_requirements(content)

        # Generate LinkedIn post draft
        draft = await self._generate_linkedin_draft(requirements)

        # Create meaningful filename from topic
        topic = requirements.get("topic", "post")
        # Clean topic for filename
        topic_slug = re.sub(r"[^a-zA-Z0-9\s]", "", topic)
        topic_slug = re.sub(r"[\s]+", "-", topic_slug).lower()[:30]
        if not topic_slug:
            topic_slug = "post"
        draft_filename = f"linkedin_{topic_slug}.md"

        # Save draft to LinkedIn_Posts/Draft - human must move to Approved to publish
        draft_path = self.linkedin_drafts_path / draft_filename

        async with aiofiles.open(draft_path, "w", encoding="utf-8") as f:
            await f.write(draft)

        logger.info(f"[Orchestrator] LinkedIn draft saved: {draft_path.name}")
        logger.info(f"[Orchestrator] Move to LinkedIn_Posts/Approved/ to publish")

        # Move original request to Done
        shutil.move(str(task_path), str(self.done_path / task_path.name))

        await self._log_action("linkedin_draft_created", task_path.name, {"draft": draft_path.name})
        await update_dashboard_on_action(self.vault_path, "draft_created", "linkedin_draft")

    def _create_linkedin_plan(self, content: str, task_name: str) -> str:
        """Create a plan for LinkedIn post."""
        return f"""# Plan: LinkedIn Post

| Field | Value |
|-------|-------|
| **Task** | {task_name} |
| **Type** | LinkedIn Post |
| **Created** | {datetime.now().isoformat()} |
| **Status** | AUTO-EXECUTED |

## Original Request

{content}

## Execution Steps

1. [x] Read requirements
2. [x] Generate post draft
3. [x] Save to Draft folder
4. [ ] Human moves to Approved to publish
5. [ ] Publish to LinkedIn

## Workflow

- ✅ Plan auto-executed (no approval needed)
- ✅ Draft generated and saved
- ⏳ Awaiting human approval to **publish**
- 📁 Move draft from `LinkedIn_Posts/Draft/` to `LinkedIn_Posts/Approved/`

*Generated: {datetime.now().isoformat()}*
"""

    def _extract_linkedin_requirements(self, content: str) -> dict:
        """Extract all requirements from LinkedIn post request."""
        requirements = {
            "topic": None,
            "tone": "professional",
            "include_cta": True,
            "hashtags": [],
            "target_audience": None,
            "value_proposition": None,
            "key_offerings": [],
            "themes": [],
            "business_goals": None,
            "length": "medium",  # short, medium, long
            "emoji": True,
        }

        # Extract full content sections
        content_lower = content.lower()

        # Store the full original request - this is the most important!
        requirements["business_goals"] = content

        # Topic - look for explicit mentions or infer from content
        topic_patterns = [
            r"(?:topic|subject|about|write about):\s*([^\n]+)",
            r"create a linkedin (?:sales )?post (?:about|on)\s*:?\s*([^\n]+)",
            r"write a post (?:about|on|remarking)\s*:?\s*([^\n]+)",
        ]
        for pattern in topic_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                requirements["topic"] = match.group(1).strip()
                break

        # If no explicit topic, extract from "Original Request" section if present
        if not requirements["topic"]:
            original_match = re.search(r"## Original Request\s*\n+(.*?)(?=\n##|\n---|\Z)", content, re.DOTALL)
            if original_match:
                original_content = original_match.group(1).strip()
                # Use first meaningful line as topic hint
                lines = [l.strip() for l in original_content.split("\n") if l.strip()]
                if lines:
                    requirements["topic"] = lines[0][:100]  # First line as topic

        # Tone
        if "casual" in content_lower:
            requirements["tone"] = "casual"
        elif "professional" in content_lower:
            requirements["tone"] = "professional"
        elif "thought-provoking" in content_lower or "insightful" in content_lower:
            requirements["tone"] = "thought-provoking"
        elif "engaging" in content_lower:
            requirements["tone"] = "engaging"

        # CTA preference
        if "no cta" in content_lower or "no call" in content_lower:
            requirements["include_cta"] = False
        elif "cta" in content_lower or "call.to.action" in content_lower:
            requirements["include_cta"] = True

        # Hashtags - extract from content
        hashtags = re.findall(r"#\w+", content)
        if hashtags:
            requirements["hashtags"] = hashtags

        # Number of hashtags
        hashtag_count = re.search(r"(\d+)[ -]?hashtags?", content_lower)
        if hashtag_count:
            requirements["hashtag_count"] = int(hashtag_count.group(1))

        # Length preference
        if "short" in content_lower:
            requirements["length"] = "short"
        elif "long" in content_lower:
            requirements["length"] = "long"

        # Emoji preference
        if "no emoji" in content_lower:
            requirements["emoji"] = False

        # Extract target audience
        audience_match = re.search(r"(?:target audience|audience):\s*([^\n]+)", content, re.IGNORECASE)
        if audience_match:
            requirements["target_audience"] = audience_match.group(1).strip()

        # Extract value proposition
        value_match = re.search(r"(?:value proposition|unique value):\s*([^\n]+)", content, re.IGNORECASE)
        if value_match:
            requirements["value_proposition"] = value_match.group(1).strip()

        # Extract key offerings
        offerings_match = re.search(r"(?:key offerings|offerings|services):\s*\n?([\s\S]*?)(?=\n\n|\n##|\n-|$)", content, re.IGNORECASE)
        if offerings_match:
            offerings_text = offerings_match.group(1)
            requirements["key_offerings"] = [
                line.strip("- ").strip()
                for line in offerings_text.split("\n")
                if line.strip() and line.strip().startswith("-")
            ]

        return requirements

    async def _generate_linkedin_draft(self, requirements: dict) -> str:
        """Generate LinkedIn post draft."""
        original_request = requirements.get("business_goals", "")
        topic = requirements.get("topic", "")

        prompt = f"""ABSOLUTE RULE: Output ONLY the final post text.
NO intro. NO wrapper. NO explanation. NOTHING except the exact post content.

Write a LinkedIn post about: {original_request if original_request else topic}

Output:"""

        draft_content = await self._call_claude(prompt)

        if not draft_content:
            draft_content = self._create_fallback_linkedin_post(requirements)

        # Emergency filter for known meta-text
        if any(bad in draft_content for bad in ["I need permission", "system will automatically", "Once created", "Waiting for file write permission", "Here's the", "Here is the", "I'll generate", "I'll create", "generate the post", "completed post", "final post", "post draft", "draft and save", "ready for publishing"]):
            draft_content = self._create_fallback_linkedin_post(requirements)
        else:
            # Line-by-line cleaning
            lines = draft_content.splitlines()
            cleaned = []
            in_wrapper = True

            for line in lines:
                stripped = line.strip().lower()
                is_wrapper = any(p in stripped for p in [
                    "here's the", "here is the", "i'll generate", "i'll create",
                    "generate the post", "completed post", "final post",
                    "post draft", "draft and save", "ready for publishing",
                ])
                if is_wrapper:
                    continue
                if in_wrapper and stripped == "":
                    continue
                if stripped.startswith("```"):
                    continue
                line = line.lstrip("> ").lstrip()
                in_wrapper = False
                cleaned.append(line)

            draft_content = "\n".join(cleaned).strip()

        # Wrap in full draft template
        draft = f"""# LinkedIn Post Draft

## Status: DRAFT - AWAITING APPROVAL

---

## Post Content

{draft_content}

---

*Generated: {datetime.now().isoformat()}*

---

## Approval Instructions

**To approve this post:**
1. Review the content above
2. Edit if needed
3. Move this file to the `Approved` folder

**To reject:**
- Delete this file
"""
        return draft

    def _create_fallback_linkedin_post(self, requirements: dict) -> str:
        """Create a fallback LinkedIn post (content only)."""
        topic = requirements.get("topic", "business insights")
        tone = requirements.get("tone", "professional")
        include_cta = requirements.get("include_cta", True)
        emoji = requirements.get("emoji", True)
        hashtags = requirements.get("hashtags", ["#Business", "#Growth", "#Leadership"])

        emoji_bullet = "→ "
        fire_emoji = " 🔥" if emoji else ""

        content = f"""The biggest opportunity in {topic}?

{"It's not what most people think." if tone == "thought-provoking" else "Here's what I've learned."}

{emoji_bullet} Focus on value, not volume
{emoji_bullet} Build relationships, not just connections
{emoji_bullet} Share insights, not just announcements

{"The best results come from consistency." if tone == "professional" else "Success leaves clues."}
"""
        if include_cta:
            content += f"""

What's your take on {topic}?

Drop a comment below{fire_emoji}
"""

        content += "\n" + "\n".join(hashtags[:5])
        return content.strip()

    # ==================== X (TWITTER) POST PROCESSING ====================

    async def _process_x_post_request(self, task_path: Path, content: str, metadata: dict) -> None:
        """Process an X (Twitter) post request - short, punchy updates."""
        logger.info(f"[Orchestrator] Processing X (Twitter) post request: {task_path.name}")

        # Ensure X posts directories exist
        self.x_drafts_path.mkdir(parents=True, exist_ok=True)
        self.x_approved_path.mkdir(parents=True, exist_ok=True)
        self.x_done_path.mkdir(parents=True, exist_ok=True)

        # Create plan
        plan = self._create_social_plan(content, task_path.name, "X (Twitter)")
        plan_path = self.plans_path / f"plan_{task_path.name}"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(plan_path, "w", encoding="utf-8") as f:
            await f.write(plan)
        logger.info(f"[Orchestrator] Plan created: {plan_path.name}")

        # Extract requirements
        requirements = self._extract_social_requirements(content, platform="x")

        # Generate X post draft
        draft = await self._generate_x_draft(requirements)

        # Create meaningful filename from topic
        topic = requirements.get("topic", "post")
        topic_slug = re.sub(r"[^a-zA-Z0-9\s]", "", topic)
        topic_slug = re.sub(r"[\s]+", "-", topic_slug).lower()[:30]
        if not topic_slug:
            topic_slug = "post"
        draft_filename = f"x_{topic_slug}.md"

        # Save draft
        draft_path = self.x_drafts_path / draft_filename

        async with aiofiles.open(draft_path, "w", encoding="utf-8") as f:
            await f.write(draft)

        logger.info(f"[Orchestrator] X draft saved: {draft_path.name}")
        logger.info(f"[Orchestrator] Move to X_Posts/Approved/ to publish")

        # Move original request to Done
        shutil.move(str(task_path), str(self.done_path / task_path.name))

        await self._log_action("x_draft_created", task_path.name, {"draft": draft_path.name})
        await update_dashboard_on_action(self.vault_path, "draft_created", "x_draft")

    async def _generate_x_draft(self, requirements: dict) -> str:
        """Generate X (Twitter) post draft."""
        topic = requirements.get("topic", "")

        prompt = f"""ABSOLUTE RULE: Output ONLY the final post text. Max 280 characters.
NO intro. NO wrapper. NO explanation. NO "here's the post". NO "I'll create". NO "completed".
NOTHING except the exact text that should appear in the post.

Write a Twitter/X post about: {topic}

Output:"""

        draft_content = await self._call_claude(prompt)

        if not draft_content:
            draft_content = self._create_fallback_x_post(requirements)

        # Emergency filter
        if any(bad in draft_content for bad in ["I need permission", "system will automatically", "Once created", "Waiting for file write permission"]):
            draft_content = self._create_fallback_x_post(requirements)
        else:
            # Line-by-line cleaning
            lines = draft_content.splitlines()
            cleaned = []
            in_wrapper = True

            for line in lines:
                stripped = line.strip().lower()
                is_wrapper = any(p in stripped for p in [
                    "here's the", "here is the", "i'll generate", "i'll create",
                    "generate the post", "completed post", "final post",
                    "post draft", "draft and save", "ready for publishing",
                    "x post", "twitter post"
                ])
                if is_wrapper:
                    continue
                if in_wrapper and stripped == "":
                    continue
                if stripped.startswith("```"):
                    continue
                line = line.lstrip("> ").lstrip()
                in_wrapper = False
                cleaned.append(line)

            draft_content = "\n".join(cleaned).strip()

        draft = f"""# X (Twitter) Post Draft

## Status: DRAFT - AWAITING APPROVAL

---

## Post Content

{draft_content}

---

**Platform:** X (Twitter)
**Generated:** {datetime.now().isoformat()}*

---

## Approval Instructions

**To approve this post:**
1. Review the content above
2. Edit if needed
3. Move this file to the `Approved` folder

**To reject:**
- Delete this file
"""
        return draft

    def _create_fallback_x_post(self, requirements: dict) -> str:
        """Create a fallback X post."""
        topic = requirements.get("topic", "business")
        hashtags = requirements.get("hashtags", ["#Business", "#Growth"])

        content = f"🚀 {topic} is changing everything. Are you ready? {' '.join(hashtags[:2])}"
        return content

    # ==================== FACEBOOK POST PROCESSING ====================

    async def _process_facebook_post_request(self, task_path: Path, content: str, metadata: dict) -> None:
        """Process a Facebook post request - community-focused engagement posts."""
        logger.info(f"[Orchestrator] Processing Facebook post request: {task_path.name}")

        # Ensure Facebook posts directories exist
        self.facebook_drafts_path.mkdir(parents=True, exist_ok=True)
        self.facebook_approved_path.mkdir(parents=True, exist_ok=True)
        self.facebook_done_path.mkdir(parents=True, exist_ok=True)

        # Create plan
        plan = self._create_social_plan(content, task_path.name, "Facebook")
        plan_path = self.plans_path / f"plan_{task_path.name}"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(plan_path, "w", encoding="utf-8") as f:
            await f.write(plan)
        logger.info(f"[Orchestrator] Plan created: {plan_path.name}")

        # Extract requirements
        requirements = self._extract_social_requirements(content, platform="facebook")

        # Generate Facebook post draft
        draft = await self._generate_facebook_draft(requirements)

        # Create meaningful filename from topic
        topic = requirements.get("topic", "post")
        topic_slug = re.sub(r"[^a-zA-Z0-9\s]", "", topic)
        topic_slug = re.sub(r"[\s]+", "-", topic_slug).lower()[:30]
        if not topic_slug:
            topic_slug = "post"
        draft_filename = f"facebook_{topic_slug}.md"

        # Save draft
        draft_path = self.facebook_drafts_path / draft_filename

        async with aiofiles.open(draft_path, "w", encoding="utf-8") as f:
            await f.write(draft)

        logger.info(f"[Orchestrator] Facebook draft saved: {draft_path.name}")
        logger.info(f"[Orchestrator] Move to Facebook_Posts/Approved/ to publish")

        # Move original request to Done
        shutil.move(str(task_path), str(self.done_path / task_path.name))

        await self._log_action("facebook_draft_created", task_path.name, {"draft": draft_path.name})

    async def _generate_facebook_draft(self, requirements: dict) -> str:
        """Generate Facebook post draft."""
        original_request = requirements.get("business_goals", "")
        topic = requirements.get("topic", "")

        prompt = f"""ABSOLUTE RULE: Output ONLY the final post text.
NO intro. NO wrapper. NO explanation. NOTHING except the exact post content.

Write a Facebook post about: {original_request if original_request else topic}

Output:"""

        draft_content = await self._call_claude(prompt)

        if not draft_content:
            draft_content = self._create_fallback_facebook_post(requirements)

        # Emergency filter
        if any(bad in draft_content for bad in ["I need permission", "system will automatically", "Once created", "Waiting for file write permission", "Here's the", "Here is the", "I'll generate", "I'll create", "generate the post", "completed post", "final post", "post draft", "draft and save", "ready for publishing"]):
            draft_content = self._create_fallback_facebook_post(requirements)
        else:
            # Line-by-line cleaning
            lines = draft_content.splitlines()
            cleaned = []
            in_wrapper = True

            for line in lines:
                stripped = line.strip().lower()
                is_wrapper = any(p in stripped for p in [
                    "here's the", "here is the", "i'll generate", "i'll create",
                    "generate the post", "completed post", "final post",
                    "post draft", "draft and save", "ready for publishing",
                ])
                if is_wrapper:
                    continue
                if in_wrapper and stripped == "":
                    continue
                if stripped.startswith("```"):
                    continue
                line = line.lstrip("> ").lstrip()
                in_wrapper = False
                cleaned.append(line)

            draft_content = "\n".join(cleaned).strip()

        draft = f"""# Facebook Post Draft

## Status: DRAFT - AWAITING APPROVAL

---

## Post Content

{draft_content}

---

**Platform:** Facebook
**Generated:** {datetime.now().isoformat()}*

---

## Approval Instructions

**To approve this post:**
1. Review the content above
2. Edit if needed
3. Move this file to the `Approved` folder

**To reject:**
- Delete this file
"""
        return draft

    def _create_fallback_facebook_post(self, requirements: dict) -> str:
        """Create a fallback Facebook post."""
        topic = requirements.get("topic", "business")

        return f"""📢 Let's talk about {topic}!

I've been thinking about this a lot lately, and I wanted to share some thoughts with our community.

What I've learned:
→ It's not about being perfect, it's about showing up
→ Every challenge is an opportunity in disguise
→ Community matters more than we realize

I'd love to hear from you - what's one thing you've learned recently that surprised you?

Drop a comment below and let's learn from each other! 💬

Don't forget to like and share if this resonates with you! 👍"""

    # ==================== SHARED SOCIAL METHODS ====================

    def _create_social_plan(self, content: str, task_name: str, platform: str) -> str:
        """Create a plan for social media post."""
        platform_folder = f"{platform}_Posts"
        if platform == "X (Twitter)":
            platform_folder = "X_Posts"

        return f"""# Plan: {platform} Post

| Field | Value |
|-------|-------|
| **Task** | {task_name} |
| **Type** | {platform} Post |
| **Created** | {datetime.now().isoformat()} |
| **Status** | AUTO-EXECUTED |

## Original Request

{content}

## Execution Steps

1. [x] Read requirements
2. [x] Generate platform-specific post draft
3. [x] Save to Draft folder
4. [ ] Human moves to Approved to publish
5. [ ] Publish to {platform}

## Workflow

- ✅ Plan auto-executed (no approval needed)
- ✅ Draft generated and saved
- ⏳ Awaiting human approval to **publish**
- 📁 Move draft from `{platform_folder}/Draft/` to `{platform_folder}/Approved/`

*Generated: {datetime.now().isoformat()}*
"""

    def _extract_social_requirements(self, content: str, platform: str = "social") -> dict:
        """Extract requirements from social post request."""
        requirements = {
            "topic": None,
            "tone": "engaging",
            "hashtags": [],
            "target_audience": None,
            "business_goals": content,  # Full original request
            "length": "medium",
            "emoji": True,
            "include_cta": True,
        }

        content_lower = content.lower()

        # Extract topic
        topic_patterns = [
            r"(?:topic|subject|about|write about):\s*([^\n]+)",
            r"create a (?:social |twitter |facebook )?post (?:about|on)\s*:?\s*([^\n]+)",
            r"write a post (?:about|on)\s*:?\s*([^\n]+)",
        ]
        for pattern in topic_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                requirements["topic"] = match.group(1).strip()
                break

        # Extract hashtags
        hashtags = re.findall(r"#\w+", content)
        if hashtags:
            requirements["hashtags"] = hashtags

        # Platform-specific adjustments
        if platform == "x":
            requirements["length"] = "engaging"
        elif platform == "facebook":
            requirements["length"] = "medium"

        return requirements

    def _create_plan(self, content: str, metadata: dict, task_name: str) -> str:
        """Create a plan.md."""
        source = metadata.get("source", "email")
        contact = metadata.get("contact", metadata.get("from", "Unknown"))

        return f"""# Plan: {task_name}

| Field | Value |
|-------|-------|
| **Source** | {source.upper()} |
| **Contact** | {contact} |
| **Created** | {datetime.now().isoformat()} |
| **Status** | AUTO-EXECUTED |

## Execution Steps

1. [x] Analyze message
2. [x] Check Company_Handbook.md
3. [x] Draft response
4. [x] Save to Draft folder
5. [ ] Human moves to Approved to send

## Workflow

- ✅ Plan auto-executed (no approval needed)
- ✅ Response drafted and saved
- ⏳ Awaiting human approval to **send**
- 📁 Move draft from `Draft/` to `Approved/`

*Generated: {datetime.now().isoformat()}*
"""

    async def _check_approved(self) -> None:
        """Execute approved drafts - file presence in Approved folder = approval."""
        # Check Gmail specific Approved folder
        if self.gmail_approved_path.exists():
            for approved_file in list(self.gmail_approved_path.glob("*.md")):
                try:
                    await self._execute_approved(approved_file, source="email")
                except Exception as e:
                    logger.error(f"[Orchestrator] Execute failed: {approved_file.name}: {e}")

        # Check WhatsApp specific Approved folder
        if self.whatsapp_approved_path.exists():
            for approved_file in list(self.whatsapp_approved_path.glob("*.md")):
                try:
                    await self._execute_approved(approved_file, source="whatsapp")
                except Exception as e:
                    logger.error(f"[Orchestrator] Execute failed: {approved_file.name}: {e}")

        # Check LinkedIn specific Approved folder for LinkedIn posts
        if self.linkedin_approved_path.exists() and self.linkedin_poster:
            for approved_file in list(self.linkedin_approved_path.glob("*.md")):
                try:
                    logger.info(f"[Orchestrator] Publishing LinkedIn post: {approved_file.name}")
                    success = await self.linkedin_poster.publish_post(approved_file)
                    if success:
                        await self._log_action("linkedin_post_published", approved_file.name, {})
                    else:
                        await self._log_action("linkedin_post_failed", approved_file.name, {})
                except Exception as e:
                    logger.error(f"[Orchestrator] LinkedIn publish failed: {approved_file.name}: {e}")
                    await self._log_action("linkedin_post_error", approved_file.name, {"error": str(e)})

        # Check X (Twitter) Approved folder
        if self.x_approved_path.exists() and self.x_poster:
            for approved_file in list(self.x_approved_path.glob("*.md")):
                try:
                    logger.info(f"[Orchestrator] Publishing X (Twitter) post: {approved_file.name}")
                    success = await self.x_poster.publish_post(approved_file)
                    if success:
                        await self._log_action("x_post_published", approved_file.name, {})
                    else:
                        await self._log_action("x_post_failed", approved_file.name, {})
                except Exception as e:
                    logger.error(f"[Orchestrator] X publish failed: {approved_file.name}: {e}")
                    await self._log_action("x_post_error", approved_file.name, {"error": str(e)})

        # Check Facebook Approved folder
        if self.facebook_approved_path.exists() and self.facebook_poster:
            for approved_file in list(self.facebook_approved_path.glob("*.md")):
                try:
                    logger.info(f"[Orchestrator] Publishing Facebook post: {approved_file.name}")
                    success = await self.facebook_poster.publish_post(approved_file)
                    if success:
                        await self._log_action("facebook_post_published", approved_file.name, {})
                    else:
                        await self._log_action("facebook_post_failed", approved_file.name, {})
                except Exception as e:
                    logger.error(f"[Orchestrator] Facebook publish failed: {approved_file.name}: {e}")
                    await self._log_action("facebook_post_error", approved_file.name, {"error": str(e)})

    async def _execute_approved(self, draft_path: Path, source: str = None) -> None:
        """Execute an approved draft - folder presence = approval."""
        logger.info(f"[Orchestrator] Executing approved draft: {draft_path.name}")

        # Read draft
        async with aiofiles.open(draft_path, "r", encoding="utf-8") as f:
            content = await f.read()

        # Extract metadata
        metadata = self._parse_metadata(content)

        # Use provided source or detect from metadata
        if source is None:
            source = metadata.get("source", "email")

        # Determine done folder based on source
        if source == "email":
            done_folder = self.gmail_done_path
        elif source == "whatsapp":
            done_folder = self.whatsapp_done_path
        else:
            done_folder = self.done_path

        done_folder.mkdir(parents=True, exist_ok=True)

        # Extract email body (everything after the draft marker or full content)
        body = self._extract_email_body(content)

        # Get recipient - check multiple fields
        to_addr = metadata.get("to") or metadata.get("contact") or metadata.get("from", "")
        subject = metadata.get("subject", "No Subject")

        # If subject starts with "Re: ", keep it; otherwise add it
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        gmail_id = metadata.get("gmail_id", "")

        # Execute based on source
        if source == "email" and self.gmail_watcher and to_addr:
            # Send email via Gmail
            result = await self.gmail_watcher.send_email(
                to=to_addr,
                subject=subject,
                body=body,
                reply_to_message_id=gmail_id,
            )

            if result.get("success"):
                logger.info(f"[Orchestrator] Email sent to {to_addr}")
                shutil.move(str(draft_path), str(done_folder / draft_path.name))
                await self._log_action("email_sent", draft_path.name, {
                    "to": to_addr,
                    "subject": subject,
                    "message_id": result.get("message_id"),
                })
            else:
                logger.error(f"[Orchestrator] Email failed: {result.get('error')}")
                await self._log_action("email_failed", draft_path.name, {
                    "to": to_addr,
                    "error": result.get("error"),
                })

        elif source == "whatsapp" and self.whatsapp_watcher and to_addr:
            # Send WhatsApp message - body already extracted by _extract_email_body
            actual_message = body.strip()

            if not actual_message:
                logger.error(f"[Orchestrator] WhatsApp body empty for {draft_path.name}")
                await self._log_action("whatsapp_failed", draft_path.name, {"error": "Empty message body"})
                return

            result = await self.whatsapp_watcher.send_message(
                contact_name=to_addr,
                message=actual_message,
            )

            if result.get("success"):
                logger.info(f"[Orchestrator] WhatsApp message sent to {to_addr}")
                shutil.move(str(draft_path), str(done_folder / draft_path.name))
                await self._log_action("whatsapp_sent", draft_path.name, {
                    "contact": to_addr,
                })
            else:
                logger.error(f"[Orchestrator] WhatsApp failed: {result.get('error')}")
                await self._log_action("whatsapp_failed", draft_path.name, {
                    "contact": to_addr,
                    "error": result.get("error"),
                })

        elif source == "linkedin":
            # TODO: Implement LinkedIn sending
            logger.info(f"[Orchestrator] LinkedIn sending not yet implemented")
            logger.info(f"[Orchestrator] Draft content:\n{body[:500]}...")
            shutil.move(str(draft_path), str(done_folder / draft_path.name))
            await self._log_action("linkedin_skipped", draft_path.name, {"reason": "not_implemented"})

        else:
            logger.warning(f"[Orchestrator] Cannot execute: missing gmail_watcher or recipient")
            await self._log_action("execute_failed", draft_path.name, {
                "reason": "no_sender_or_recipient",
            })

    def _extract_email_body(self, content: str) -> str:
        """Extract the message body from draft content using separator positions."""
        lines = content.split("\n")
        body_lines = []

        # Find positions of all separator lines
        separator_positions = []
        for i, line in enumerate(lines):
            if line.strip() == "---":
                separator_positions.append(i)

        # Determine body boundaries based on separator count and metadata presence
        start_line = 0
        end_line = len(lines)

        if len(separator_positions) >= 2:
            # Check for metadata section (lines like **To:** or **Source:** before first separator)
            has_metadata = any(
                l.strip().startswith("**") and ":" in l and not l.strip().startswith("**Generated")
                for l in lines[:separator_positions[0]]
            )

            if has_metadata:
                # With metadata: body is after metadata section
                if len(separator_positions) >= 3:
                    # 3-sep format: header | metadata | body | footer
                    start_line = separator_positions[1] + 1
                    end_line = separator_positions[2]
                else:
                    # 2-sep with metadata: body between sep0 and sep1
                    start_line = separator_positions[0] + 1
                    end_line = separator_positions[1]
            else:
                # No metadata: body between first two separators
                start_line = separator_positions[0] + 1
                end_line = separator_positions[1]

        # Check if this is a WhatsApp message format
        is_whatsapp = "**Source:** whatsapp" in content

        # Special handling for WhatsApp format (has **Message:** section)
        if is_whatsapp:
            # Find **Message:** and extract everything after it until *Generated:
            in_message_section = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("**Message:**"):
                    in_message_section = True
                    continue
                if stripped.startswith("*Generated:") or stripped.startswith("*Retrieved:"):
                    break
                if in_message_section:
                    body_lines.append(line)
            return "\n".join(body_lines).strip()

        # Collect body lines for regular format
        for i in range(start_line, end_line):
            line = lines[i]
            stripped = line.strip()

            # Skip section headers
            if stripped.startswith("## "):
                if "Send Instructions" in stripped or "Metadata" in stripped:
                    break
                continue
            # Skip table rows
            if stripped.startswith("| **") or stripped.startswith("|---"):
                continue
            # Skip metadata inline fields
            if stripped.startswith("**Source:**") or stripped.startswith("**To:**"):
                continue
            # Skip checkbox lines
            if "[ ]" in stripped or "[x]" in stripped:
                continue
            # Skip generated/retrieved timestamps
            if stripped.startswith("*Generated:") or stripped.startswith("*Retrieved:"):
                continue

            body_lines.append(line)

        body = "\n".join(body_lines).strip()
        return body

    async def _check_daily_post(self) -> None:
        """Generate daily LinkedIn post if due."""
        now = datetime.now()

        if self._last_daily_post and self._last_daily_post.date() == now.date():
            return

        if now.strftime("%H:%M") >= self.daily_post_time:
            await self._generate_daily_post()
            self._last_daily_post = now

    async def _generate_daily_post(self) -> None:
        """Generate LinkedIn post."""
        logger.info("[Orchestrator] Generating daily LinkedIn post")

        business_goals = await self._read_file(self.business_goals_path)
        if not business_goals:
            return

        prompt = f"""Create a LinkedIn sales post.

Business Goals:
{business_goals}

Requirements:
- Engaging and professional
- Clear call-to-action
- 3-5 hashtags
- Value-focused

Generate now."""

        draft = await self._call_claude(prompt)
        if draft:
            draft += f"\n\n---\n\n- [ ] Approve and post to LinkedIn\n\n*Generated: {datetime.now().isoformat()}*"

            filename = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_linkedin_daily_post.md"
            post_path = self.linkedin_drafts_path / filename
            post_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(post_path, "w", encoding="utf-8") as f:
                await f.write(draft)

            logger.info(f"[Orchestrator] Daily post: {filename}")
            await self._log_action("daily_post", filename, {})

    # ==================== HELPERS ====================

    def _parse_metadata(self, content: str) -> dict:
        """Extract metadata from content."""
        metadata = {
            "source": "email",
            "contact": "",
            "from": "",
            "to": "",
            "subject": "No Subject",
            "gmail_id": "",
        }

        # Table format patterns (from email files)
        table_patterns = {
            "source": r"\*\*Source\*\*\s*\|\s*([^|\n]+)",
            "contact": r"\*\*Contact\*\*\s*\|\s*([^|\n]+)",
            "from": r"\*\*From\*\*\s*\|\s*([^|\n]+)",
            "subject": r"\*\*Subject\*\*\s*\|\s*([^|\n]+)",
            "gmail_id": r"\*\*Gmail ID\*\*\s*\|\s*([^|\n]+)",
        }

        for key, pattern in table_patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                metadata[key] = match.group(1).strip()

        # Draft format patterns (from draft files)
        draft_patterns = {
            "source": r"\*\*Source:\*\*\s*([^\n]+)",
            "to": r"\*\*To:\*\*\s*([^\n]+)",
            "subject": r"\*\*Subject:\*\*\s*([^\n]+)",
            "from": r"\*\*From:\*\*\s*([^\n]+)",
        }

        for key, pattern in draft_patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                metadata[key] = match.group(1).strip()

        # Simple line patterns (To: email@example.com)
        if not metadata.get("to"):
            to_match = re.search(r"^## To:\s*(.+)$", content, re.MULTILINE)
            if to_match:
                metadata["to"] = to_match.group(1).strip()

        # Extract subject from ## Subject: line
        if metadata.get("subject") == "No Subject":
            subj_match = re.search(r"^## Subject:\s*(.+)$", content, re.MULTILINE)
            if subj_match:
                metadata["subject"] = subj_match.group(1).strip()

        # Use 'to' as contact if contact is empty
        if not metadata.get("contact") and metadata.get("to"):
            metadata["contact"] = metadata["to"]

        # Use 'from' as contact if still empty
        if not metadata.get("contact") and metadata.get("from"):
            metadata["contact"] = metadata["from"]

        # Detect source from content if not already set
        content_lower = content.lower()
        if metadata.get("source"):
            # Normalize source to lowercase
            metadata["source"] = metadata["source"].lower()
        elif "whatsapp" in content_lower:
            metadata["source"] = "whatsapp"
        elif "linkedin" in content_lower:
            metadata["source"] = "linkedin"
        else:
            metadata["source"] = "email"

        return metadata

    def _check_flags(self, content: str) -> dict:
        """Check for security flags."""
        flags = {"reasons": []}
        content_lower = content.lower()

        if re.search(r"\$\d+", content) or "payment" in content_lower:
            flags["reasons"].append("Payment-related")

        for s in ["password", "credential", "credit card"]:
            if s in content_lower:
                flags["reasons"].append(f"Sensitive: {s}")

        return flags

    async def _generate_draft(
        self, content: str, handbook: str, metadata: dict, flags: dict
    ) -> str:
        """Generate draft using Claude CLI."""
        source = metadata.get("source", "email")
        contact = metadata.get("contact", metadata.get("from", "Unknown"))

        flags_section = ""
        if flags.get("reasons"):
            flags_section = f"\n## ⚠️ Flags\n{chr(10).join(f'- {r}' for r in flags['reasons'])}\n"

        # WhatsApp responses should be shorter
        is_whatsapp = source.lower() == "whatsapp"

        if is_whatsapp:
            prompt = f"""You have full permissions to respond as the user.

RULE: Output ONLY the response text. NOTHING else.
- NO introductions
- NO "Here's my response"
- NO explanations
- NO commentary

Write a SHORT WhatsApp response (1-2 sentences max) to:
{content}

Now write ONLY the response:"""
        else:
            prompt = f"""You have full permissions to write this email on behalf of the user.

RULE: Output ONLY the complete email content. NOTHING else.
- NO "Here's the email"
- NO "I've drafted"
- NO intro/outro commentary
- NO "As an AI"
- NO "Best regards from AI"
- NOTHING except the actual email body text

## Company Rules
{handbook}
{flags_section}
---

## Original Message
{content}

---

Write a professional email response. Output ONLY the email body:"""

        draft = await self._call_claude(prompt)

        if not draft:
            draft = f"""Thank you for your message. I'll respond with details shortly."""

        # For WhatsApp, preserve the exact format you showed
        if is_whatsapp:
            return f"""---

**Source:** whatsapp
**To:** {contact}

---

**Message:**
{draft.strip()}

*Generated: {datetime.now().isoformat()}*"""
        else:
            # Email/other: wrap in Email Draft format with subject
            subject_from_meta = metadata.get("subject", "No Subject")
            # If subject is generic auto-generated, convert to something useful
            if subject_from_meta in ("No Subject", "", "(No Subject)"):
                # Try to extract meaningful subject from original content
                import re
                subj_match = re.search(r"^## Subject:\s*(.+)$", content, re.MULTILINE)
                if subj_match:
                    subject_from_meta = subj_match.group(1).strip()
                else:
                    subject_from_meta = "Response"

            # Return clean email draft format
            return f"""# Email Draft

## To: {contact}
## Subject: Re: {subject_from_meta}

---

{draft.strip()}

---

*Generated: {datetime.now().isoformat()}*"""

    async def _call_claude(self, prompt: str) -> Optional[str]:
        """Call Claude CLI."""
        try:
            import shutil
            claude_path = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude.exe")
            if not os.path.exists(claude_path):
                claude_path = os.path.expanduser("~/.local/bin/claude")

            result = await asyncio.create_subprocess_exec(
                claude_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await result.communicate(input=prompt.encode("utf-8"))

            if result.returncode == 0 and stdout:
                response = stdout.decode("utf-8").strip()
                if response:
                    logger.info(f"[Orchestrator] Claude: {len(response)} chars")
                    return response

        except Exception as e:
            logger.error(f"[Orchestrator] Claude error: {e}")

        return None

    async def _read_file(self, path: Path) -> str:
        """Read file safely."""
        if path.exists():
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                return await f.read()
        return ""

    async def _log_action(self, action: str, filename: str, details: dict) -> None:
        """Log to JSON file."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "filename": filename,
            "details": details,
        }

        log_file = self.logs_path / f"orchestrator_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

        async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
            await f.write(json.dumps(log_entry) + "\n")

        # Update summary files when posts are published
        if action in ["linkedin_post_published", "x_post_published", "facebook_post_published"]:
            await self._update_social_summary()

        # Also update when drafts are created
        if action in ["linkedin_draft_created", "x_draft_created", "facebook_draft_created"]:
            await self._update_social_summary()

    async def _update_social_summary(self) -> None:
        """Update SUMMARY.md files in each social media folder."""
        platforms = [
            ("LinkedIn", self.linkedin_posts_path, self.linkedin_drafts_path, self.linkedin_done_path),
            ("X", self.x_posts_path, self.x_drafts_path, self.x_done_path),
            ("Facebook", self.facebook_posts_path, self.facebook_drafts_path, self.facebook_done_path),
        ]

        for platform_name, base_path, drafts_path, done_path in platforms:
            summary_path = base_path / "SUMMARY.md"

            # Count files
            draft_files = list(drafts_path.glob("*.md")) if drafts_path.exists() else []
            done_files = list(done_path.glob("*.md")) if done_path.exists() else []

            # Build summary content
            summary = f"# {platform_name} Posts Summary\n\n"
            summary += f"**Drafts:** {len(draft_files)} | **Published:** {len(done_files)}\n\n"
            summary += "---\n\n"

            if done_files:
                summary += f"## Published Posts ({len(done_files)})\n\n"
                for i, done_file in enumerate(done_files, 1):
                    # Read content and extract post content
                    try:
                        content = done_file.read_text(encoding="utf-8")
                        # Find the post content section
                        lines = content.split("\n")
                        post_content = ""
                        in_post_content = False
                        first_dash_found = False
                        for line in lines:
                            if "## Post Content" in line:
                                in_post_content = True
                                continue
                            if in_post_content:
                                # First --- after post content marks end
                                if line.strip() == "---":
                                    if first_dash_found:
                                        break
                                    first_dash_found = True
                                    continue
                                if line.strip():
                                    post_content += line + " "
                        # Get first 60 chars of actual content
                        title = post_content.strip()[:60] if post_content.strip() else done_file.stem
                        if len(title) > 60:
                            title = title[:57] + "..."
                    except:
                        title = done_file.stem
                    summary += f"{i}. {title}\n"
            else:
                summary += "## Published Posts\n\n_No posts published yet_\n"

            summary += f"\n---\n\n*Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"

            # Write summary
            summary_path.write_text(summary, encoding="utf-8")
            logger.info(f"[Orchestrator] Updated {platform_name} summary: {summary_path.name}")


async def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    orchestrator = Orchestrator(vault_path=Path("AI_Employee_Vault"))

    try:
        await orchestrator.run()
    except KeyboardInterrupt:
        orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())
