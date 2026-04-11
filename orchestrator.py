"""
Orchestrator - Unified workflow engine.

Single file handles all processing:
- Processes tasks from Needs_Action
- Uses HITL workflow if Pending_Approval folder exists
- Generates daily LinkedIn posts if Business_Goals.md exists
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

import aiofiles

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
        """
        self.vault_path = Path(vault_path)
        self.poll_interval = poll_interval
        self.daily_post_time = daily_post_time
        self.gmail_watcher = gmail_watcher
        self.whatsapp_watcher = whatsapp_watcher
        self.linkedin_poster = linkedin_poster

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
        self.linkedin_posts_path = self.vault_path / "LinkedIn_Posts"
        self.linkedin_drafts_path = self.linkedin_posts_path / "Draft"
        self.linkedin_approved_path = self.linkedin_posts_path / "Approved"
        self.linkedin_done_path = self.linkedin_posts_path / "Done"

        # Gmail messages paths
        self.gmail_messages_path = self.vault_path / "Gmail_Messages"
        self.gmail_drafts_path = self.gmail_messages_path / "Draft"
        self.gmail_approved_path = self.gmail_messages_path / "Approved"
        self.gmail_done_path = self.gmail_messages_path / "Done"

        # WhatsApp messages paths
        self.whatsapp_messages_path = self.vault_path / "WhatsApp_Messages"
        self.whatsapp_drafts_path = self.whatsapp_messages_path / "Draft"
        self.whatsapp_approved_path = self.whatsapp_messages_path / "Approved"
        self.whatsapp_done_path = self.whatsapp_messages_path / "Done"

        # Gmail messages paths
        self.gmail_messages_path = self.vault_path / "Gmail_Messages"
        self.gmail_drafts_path = self.gmail_messages_path / "Draft"
        self.gmail_approved_path = self.gmail_messages_path / "Approved"
        self.gmail_done_path = self.gmail_messages_path / "Done"

        # WhatsApp messages paths
        self.whatsapp_messages_path = self.vault_path / "WhatsApp_Messages"
        self.whatsapp_drafts_path = self.whatsapp_messages_path / "Draft"
        self.whatsapp_approved_path = self.whatsapp_messages_path / "Approved"
        self.whatsapp_done_path = self.whatsapp_messages_path / "Done"

        self._running = False
        self._processed_files: set[str] = set()
        self._last_daily_post: Optional[datetime] = None

        # Detect features
        self.daily_posts = self.business_goals_path.exists()

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

                # If enabled: Daily LinkedIn post
                if self.daily_posts:
                    await self._check_daily_post()

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

        # Check if this is a LinkedIn post request
        if "linkedin_post" in task_path.name.lower() or "linkedin post request" in content.lower():
            await self._process_linkedin_post_request(task_path, content, metadata)
            return

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

        # Save draft to LinkedIn_Posts/Draft - human must move to Approved to publish
        draft_filename = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_linkedin_draft.md"
        draft_path = self.linkedin_drafts_path / draft_filename

        async with aiofiles.open(draft_path, "w", encoding="utf-8") as f:
            await f.write(draft)

        logger.info(f"[Orchestrator] LinkedIn draft saved: {draft_path.name}")
        logger.info(f"[Orchestrator] Move to LinkedIn_Posts/Approved/ to publish")

        # Move original request to Done
        shutil.move(str(task_path), str(self.done_path / task_path.name))

        await self._log_action("linkedin_draft_created", task_path.name, {"draft": draft_path.name})

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
        """Generate LinkedIn post draft using all requirements."""
        # Get business goals for additional context (optional)
        business_goals = await self._read_file(self.business_goals_path)

        # Build requirements section for prompt
        req_lines = []

        # Use the original request content as the primary source
        original_request = requirements.get("business_goals", "")

        topic = requirements.get("topic")
        if topic:
            req_lines.append(f"- Topic/Subject: {topic}")

        tone = requirements.get("tone", "professional")
        req_lines.append(f"- Tone: {tone}")

        target_audience = requirements.get("target_audience")
        if target_audience:
            req_lines.append(f"- Target Audience: {target_audience}")

        value_prop = requirements.get("value_proposition")
        if value_prop:
            req_lines.append(f"- Value Proposition: {value_prop}")

        include_cta = requirements.get("include_cta", True)
        req_lines.append(f"- Call-to-Action: {'Yes - include clear CTA' if include_cta else 'No CTA needed'}")

        hashtags = requirements.get("hashtags", [])
        hashtag_count = requirements.get("hashtag_count", 5)
        if hashtags:
            req_lines.append(f"- Use these hashtags: {' '.join(hashtags)}")
        else:
            req_lines.append(f"- Include {hashtag_count} relevant hashtags")

        length = requirements.get("length", "medium")
        length_guide = {"short": "100-150 words", "medium": "150-250 words", "long": "250-400 words"}
        req_lines.append(f"- Length: {length_guide.get(length, '150-250 words')}")

        emoji = requirements.get("emoji", True)
        req_lines.append(f"- Use emojis: {'Yes, sparingly' if emoji else 'No emojis'}")

        key_offerings = requirements.get("key_offerings", [])
        if key_offerings:
            req_lines.append(f"- Key Offerings to mention: {', '.join(key_offerings)}")

        requirements_text = "\n".join(req_lines)

        # Build prompt with user's specific request as primary, business goals as secondary context
        context_section = ""
        if business_goals:
            context_section = f"\n\nBusiness Context (for reference):\n{business_goals}"

        prompt = f"""Create a LinkedIn post based on the user's specific request.

## User's Request:
{original_request}

## Extracted Requirements:
{requirements_text}
{context_section}

Generate the LinkedIn post now. Output ONLY the post content, ready to publish."""

        draft_content = await self._call_claude(prompt)

        if not draft_content:
            # Fallback template using requirements
            draft_content = self._create_fallback_linkedin_post(requirements)

        # Ensure proper draft format
        if "# LinkedIn Post Draft" not in draft_content:
            draft_content = f"""# LinkedIn Post Draft

## Status: DRAFT - AWAITING APPROVAL

---

## Post Content

{draft_content}

---

*Generated: {datetime.now().isoformat()}*
"""

        # Add approval instructions
        draft_content += """

---

## Approval Instructions

**To approve this post:**
1. Review the content above
2. Edit if needed
3. Move this file to the `Approved` folder

**To reject:**
- Delete this file
"""

        return draft_content

    def _create_fallback_linkedin_post(self, requirements: dict) -> str:
        """Create a fallback LinkedIn post from requirements."""
        topic = requirements.get("topic", "business insights")
        tone = requirements.get("tone", "professional")
        include_cta = requirements.get("include_cta", True)
        emoji = requirements.get("emoji", True)
        hashtags = requirements.get("hashtags", ["#Business", "#Growth", "#Leadership"])

        emoji_bullet = "→ " if not emoji else "→ "
        emoji_fire = "" if not emoji else " 🔥"

        content = f"""# LinkedIn Post Draft

## Status: DRAFT - AWAITING APPROVAL

---

## Post Content

The biggest opportunity in {topic}?

{"It's not what most people think." if tone == "thought-provoking" else "Here's what I've learned."}

{emoji_bullet} Focus on value, not volume
{emoji_bullet} Build relationships, not just connections
{emoji_bullet} Share insights, not just announcements

{"The best results come from consistency." if tone == "professional" else "Success leaves clues."}

"""
        if include_cta:
            content += f"""What's your take on {topic}?

Drop a comment below{emoji_fire}

"""

        content += "\n".join(hashtags[:5])
        content += f"\n\n---\n\n*Generated: {datetime.now().isoformat()}*"

        return content

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
            # Send WhatsApp message
            result = await self.whatsapp_watcher.send_message(
                contact_name=to_addr,
                message=body,
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
        """Extract the message body from draft content."""
        lines = content.split("\n")
        body_lines = []
        separator_count = 0
        in_body = False

        for line in lines:
            # Count separators to skip metadata section
            if line.strip() == "---":
                separator_count += 1
                # After 2 separators, we're past the metadata header
                if separator_count == 2:
                    in_body = True
                    continue
                # After 3+ separators, we're past the body
                if separator_count >= 3:
                    in_body = False
                continue

            # Skip metadata section
            if line.startswith("## ") and "Metadata" in line:
                continue
            if line.startswith("| **") or line.startswith("|---"):
                continue
            # Skip Source/To metadata lines
            if line.startswith("**Source:**") or line.startswith("**To:**"):
                continue
            # Skip Send Instructions section
            if line.startswith("## Send Instructions"):
                in_body = False
                continue
            # Skip checkbox lines
            if "[ ]" in line or "[x]" in line:
                continue
            # Skip generated timestamp
            if line.startswith("*Generated:"):
                continue
            if line.startswith("*Retrieved:"):
                continue

            if in_body:
                body_lines.append(line)

        # Clean up
        body = "\n".join(body_lines).strip()
        # Remove leading/trailing separators
        body = re.sub(r"^-{3,}\n?", "", body)
        body = re.sub(r"\n-{3,}$", "", body)
        return body.strip()

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

        prompt = f"""You are an AI assistant. Generate a professional response.

## Company Rules
{handbook}
{flags_section}
---

## Message ({source.upper()})
{content}

---

Generate a professional response. Do NOT include any checkboxes or approval markers."""

        draft = await self._call_claude(prompt)

        if not draft:
            draft = f"""Thank you for your message. I'll respond with details shortly.

*Generated: {datetime.now().isoformat()}*"""

        # Add metadata header to preserve source and contact
        draft_with_metadata = f"""---

**Source:** {source}
**To:** {contact}

---

{draft}

---

## Send Instructions

**To send this response:**
1. Review the content above
2. Edit if needed
3. Move this file to the `Approved` folder

**To reject:**
- Delete this file

*Generated: {datetime.now().isoformat()}*"""

        return draft_with_metadata

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
