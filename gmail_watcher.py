"""
Gmail Watcher - Polls Gmail for unread important messages.

Supports two authentication methods:
1. OAuth2 with refresh token (for personal Gmail)
2. Service Account (for Google Workspace with domain-wide delegation)

Includes retry logic with exponential backoff for transient errors.
"""

import asyncio
import base64
import json
import logging
import os
import re
from datetime import datetime, timedelta, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import aiohttp

from base_watcher import BaseWatcher
from retry_handler import with_retry, RetryExhaustedError, FinancialAPIError

logger = logging.getLogger(__name__)


class GmailWatcher(BaseWatcher):
    """
    Gmail API watcher that polls for unread important emails.

    Supports OAuth2 and Service Account authentication.
    Saves each email as a markdown file in the specified Inbox folder.
    """

    # Gmail API endpoints
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_BASE = "https://gmail.googleapis.com/gmail/v1/users"

    def __init__(
        self,
        inbox_path: Path,
        logs_path: Path,
        needs_action_path: Optional[Path] = None,
        poll_interval: float = 120.0,
        query: str = "is:unread category:primary",
        max_results: int = 10,
        auto_process: bool = True,
        # OAuth2 credentials
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        # Service Account credentials
        service_account_key_file: Optional[str] = None,
        impersonate_email: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the Gmail watcher.

        Args:
            inbox_path: Path to Inbox folder (for raw emails)
            logs_path: Path to Logs folder
            needs_action_path: Path to Needs_Action folder (auto-process destination)
            poll_interval: Seconds between polls
            query: Gmail search query
            max_results: Maximum emails to fetch per poll
            auto_process: If True, automatically move emails to Needs_Action for processing
            client_id: Google OAuth2 client ID (for OAuth2)
            client_secret: Google OAuth2 client secret (for OAuth2)
            refresh_token: OAuth2 refresh token (for OAuth2)
            service_account_key_file: Path to service account JSON (for Service Account)
            impersonate_email: Email to impersonate (for Service Account)
        """
        super().__init__(poll_interval=poll_interval, **kwargs)

        self.inbox_path = Path(inbox_path)
        self.logs_path = Path(logs_path)
        self.needs_action_path = Path(needs_action_path) if needs_action_path else None
        self.auto_process = auto_process
        self.query = query
        self.max_results = max_results

        # Determine auth method
        if service_account_key_file and impersonate_email:
            self._auth_method = "service_account"
            self._service_account_key_file = service_account_key_file
            self._impersonate_email = impersonate_email
            self._user_id = impersonate_email
        elif client_id and client_secret and refresh_token:
            self._auth_method = "oauth"
            self.client_id = client_id
            self.client_secret = client_secret
            self.refresh_token = refresh_token
            self._user_id = "me"
        else:
            raise ValueError(
                "Must provide either:\n"
                "  - OAuth2: client_id, client_secret, refresh_token\n"
                "  - Service Account: service_account_key_file, impersonate_email"
            )

        self._access_token: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._processed_ids: set[str] = set()
        self._service_account_data: Optional[dict] = None
        self._last_poll_time: Optional[str] = None
        self._last_poll_time: Optional[str] = None

    @property
    def name(self) -> str:
        return f"GmailWatcher({self._auth_method})"

    async def startup(self) -> None:
        """Initialize HTTP session and authenticate."""
        self._session = aiohttp.ClientSession()

        # Ensure directories exist
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
        if self.needs_action_path:
            self.needs_action_path.mkdir(parents=True, exist_ok=True)
        if self.needs_action_path:
            self.needs_action_path.mkdir(parents=True, exist_ok=True)

        # Load service account key if using that method
        if self._auth_method == "service_account":
            await self._load_service_account_key()

        # Initial authentication
        await self._authenticate()

        # Load previously processed email IDs
        await self._load_processed_ids()

        logger.info(f"[{self.name}] Initialized with query: '{self.query}'")

    async def shutdown(self) -> None:
        """Cleanup HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

        # Save processed IDs for next run
        await self._save_processed_ids()

        logger.info(f"[{self.name}] Shutdown complete")

    async def _load_service_account_key(self) -> None:
        """Load service account JSON key file."""
        key_path = Path(self._service_account_key_file)
        if not key_path.exists():
            raise FileNotFoundError(f"Service account key not found: {key_path}")

        with open(key_path, "r") as f:
            self._service_account_data = json.load(f)

        logger.debug(f"[{self.name}] Loaded service account key")

    async def _authenticate(self) -> None:
        """Authenticate based on the configured method."""
        if self._auth_method == "oauth":
            await self._refresh_oauth_token()
        else:
            await self._get_service_account_token()

    async def _refresh_oauth_token(self) -> None:
        """Refresh the OAuth2 access token."""
        if not self._session:
            raise RuntimeError("Session not initialized")

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        async with self._session.post(self.OAUTH_TOKEN_URL, data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"OAuth token refresh failed: {response.status} - {error_text}")

            token_data = await response.json()
            self._access_token = token_data["access_token"]
            logger.debug(f"[{self.name}] OAuth token refreshed")

    async def _get_service_account_token(self) -> None:
        """Get access token using service account with JWT."""
        if not self._session:
            raise RuntimeError("Session not initialized")
        if not self._service_account_data:
            raise RuntimeError("Service account key not loaded")

        import time

        # Create JWT
        now = int(time.time())
        jwt_header = {"alg": "RS256", "typ": "JWT"}

        jwt_payload = {
            "iss": self._service_account_data["client_email"],
            "scope": "https://www.googleapis.com/auth/gmail.modify",
            "aud": self.OAUTH_TOKEN_URL,
            "sub": self._impersonate_email,
            "iat": now,
            "exp": now + 3600,
        }

        # Encode header and payload
        def b64encode_json(data: dict) -> str:
            return base64.urlsafe_b64encode(
                json.dumps(data).encode()
            ).decode().rstrip("=")

        header_b64 = b64encode_json(jwt_header)
        payload_b64 = b64encode_json(jwt_payload)

        # Sign with private key
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key = serialization.load_pem_private_key(
            self._service_account_data["private_key"].encode(),
            password=None,
        )

        signature = private_key.sign(
            f"{header_b64}.{payload_b64}".encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        jwt_token = f"{header_b64}.{payload_b64}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"

        # Exchange JWT for access token
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_token,
        }

        async with self._session.post(self.OAUTH_TOKEN_URL, data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Service account auth failed: {response.status} - {error_text}")

            token_data = await response.json()
            self._access_token = token_data["access_token"]
            logger.debug(f"[{self.name}] Service account token obtained")

    async def _load_processed_ids(self) -> None:
        """Load previously processed email IDs from disk."""
        ids_file = self.logs_path / "processed_ids.json"
        if ids_file.exists():
            try:
                with open(ids_file, "r") as f:
                    self._processed_ids = set(json.load(f))
                logger.info(
                    f"[{self.name}] Loaded {len(self._processed_ids)} processed IDs"
                )
            except Exception as e:
                logger.warning(f"[{self.name}] Could not load processed IDs: {e}")
                self._processed_ids = set()

    async def _save_processed_ids(self) -> None:
        """Save processed email IDs to disk."""
        ids_file = self.logs_path / "processed_ids.json"
        try:
            with open(ids_file, "w") as f:
                json.dump(list(self._processed_ids), f, indent=2)
            logger.debug(f"[{self.name}] Saved {len(self._processed_ids)} processed IDs")
        except Exception as e:
            logger.error(f"[{self.name}] Could not save processed IDs: {e}")

    def _get_headers(self) -> dict:
        """Get authorization headers for API requests."""
        if not self._access_token:
            raise RuntimeError("Not authenticated")
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def _get_api_url(self, path: str = "") -> str:
        """Get full API URL for the authenticated user."""
        return f"{self.API_BASE}/{self._user_id}{path}"

    async def poll(self) -> bool:
        """
        Poll Gmail for new unread important messages.

        Returns:
            True if poll succeeded, False otherwise
        """
        if not self._session:
            raise RuntimeError("Session not initialized")

        logger.debug(f"[{self.name}] Polling for emails...")

        try:
            # Build query with "after" filter to avoid fetching old messages
            # Only add after filter if we have a previous poll time
            if self._last_poll_time:
                # Use relative date format for Gmail - fetch last 2 days to catch any delayed emails
                last_date = datetime.now() - timedelta(days=2)
                after_filter = f"after:{last_date.strftime('%Y/%m/%d')}"
                query_parts = [self.query, after_filter]
                full_query = " ".join(query_parts)
                logger.debug(f"[{self.name}] Query with after filter: {full_query}")
            else:
                full_query = self.query
                logger.debug(f"[{self.name}] Query (first run): {full_query}")

            # Search for messages
            search_url = (
                f"{self._get_api_url('/messages')}?"
                f"q={quote(full_query)}&maxResults={self.max_results}"
            )

            async with self._session.get(
                search_url, headers=self._get_headers()
            ) as response:
                if response.status == 401:
                    # Token expired, refresh and retry
                    logger.info(f"[{self.name}] Token expired, refreshing...")
                    await self._authenticate()
                    return await self.poll()

                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Search failed: {response.status} - {error_text}")

                data = await response.json()
                messages = data.get("messages", [])

            if not messages:
                logger.debug(f"[{self.name}] No new messages")
                # Update poll time even if no messages
                self._last_poll_time = datetime.now().strftime("%Y/%m/%d")
                return True

            logger.info(f"[{self.name}] Found {len(messages)} message(s)")

            # Process each message
            for msg_ref in messages:
                msg_id = msg_ref["id"]

                if msg_id in self._processed_ids:
                    logger.debug(f"[{self.name}] Skipping already processed: {msg_id}")
                    continue

                await self._process_message(msg_id)
                self._processed_ids.add(msg_id)

            # Update poll time after processing
            self._last_poll_time = datetime.now().strftime("%Y/%m/%d")

            return True

        except aiohttp.ClientError as e:
            logger.error(f"[{self.name}] Network error: {e}")
            raise
        except Exception as e:
            logger.error(f"[{self.name}] Poll error: {e}")
            raise

    async def _process_message(self, msg_id: str) -> None:
        """
        Fetch and save a single message.

        Args:
            msg_id: Gmail message ID
        """
        if not self._session:
            raise RuntimeError("Session not initialized")

        # Fetch full message
        msg_url = f"{self._get_api_url('/messages')}/{msg_id}?format=full"

        async with self._session.get(
            msg_url, headers=self._get_headers()
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Message fetch failed: {response.status} - {error_text}")

            msg_data = await response.json()

        # Extract headers
        headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}

        from_addr = headers.get("From", "Unknown")
        subject = headers.get("Subject", "(No Subject)")
        date_str = headers.get("Date", "")
        to_addr = headers.get("To", "")
        cc_addr = headers.get("Cc", "")

        # Parse date
        received_date = self._parse_date(date_str)

        # Extract body
        body = self._extract_body(msg_data.get("payload", {}))

        # Create filename
        timestamp = received_date.strftime("%Y-%m-%d_%H-%M-%S") if received_date else datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        slug = self._slugify(subject)[:50]
        filename = f"{timestamp}_{slug}.md"

        # Create markdown content
        md_content = f"""# {subject}

## Email Metadata

| Field | Value |
|-------|-------|
| **From** | {from_addr} |
| **To** | {to_addr} |
| **Cc** | {cc_addr} |
| **Subject** | {subject} |
| **Received Date** | {date_str} |
| **Gmail ID** | {msg_id} |

---

## Body

{body}

---

*Retrieved: {datetime.now().isoformat()}*
"""

        # Save to Inbox
        filepath = self.inbox_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"[{self.name}] Saved email: {filename}")

        # Auto-process: move to Needs_Action for orchestrator
        if self.auto_process and self.needs_action_path:
            import shutil
            dest_path = self.needs_action_path / filename
            shutil.move(str(filepath), str(dest_path))
            logger.info(f"[{self.name}] Moved to Needs_Action: {filename}")
            await self._log_action(msg_id, from_addr, subject, "moved_to_needs_action")
        else:
            await self._log_action(msg_id, from_addr, subject, "saved_to_inbox")

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various email date formats."""
        if not date_str:
            return None

        # Common email date formats
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def _extract_body(self, payload: dict) -> str:
        """Extract the text body from the message payload."""
        body = ""

        # Check for direct body
        if "body" in payload and "data" in payload["body"]:
            try:
                body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
            except Exception:
                pass

        # Check for parts (multipart messages)
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    if "body" in part and "data" in part["body"]:
                        try:
                            body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                            break
                        except Exception:
                            continue
                # Recursively check nested parts
                elif "parts" in part:
                    nested_body = self._extract_body(part)
                    if nested_body:
                        body = nested_body
                        break

        return body or "(No text body found)"

    def _slugify(self, text: str) -> str:
        """Convert text to a filesystem-safe slug."""
        # Replace non-alphanumeric with hyphens
        slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = slug.strip("-")
        return slug.lower() or "email"

    @with_retry(max_retries=5, base_delay=1.0, max_delay=60.0)
    @with_retry(max_retries=5, base_delay=1.0, max_delay=60.0)
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        reply_to_message_id: str = "",
    ) -> dict:
        """
        Send an email via Gmail API.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            cc: CC recipients (optional)
            reply_to_message_id: Original message ID for reply (optional)

        Returns:
            dict with 'success' and 'message_id' or 'error'
        """
        if not self._session:
            raise RuntimeError("Session not initialized")

        # Build email message in RFC 2822 format
        email_lines = [f"Subject: {subject}"]
        email_lines.append(f"To: {to}")
        if cc:
            email_lines.append(f"Cc: {cc}")

        # Add In-Reply-To and References headers for replies
        if reply_to_message_id:
            email_lines.append(f"In-Reply-To: <{reply_to_message_id}>")
            email_lines.append(f"References: <{reply_to_message_id}>")

        email_lines.append("Content-Type: text/plain; charset=utf-8")
        email_lines.append("")  # Empty line before body
        email_lines.append(body)

        raw_email = "\r\n".join(email_lines)

        # Base64url encode
        raw_b64 = base64.urlsafe_b64encode(raw_email.encode("utf-8")).decode()

        # Send via Gmail API
        send_url = self._get_api_url("/messages/send")
        payload = {"raw": raw_b64}

        try:
            async with self._session.post(
                send_url,
                headers=self._get_headers(),
                json=payload,
            ) as response:
                if response.status == 401:
                    # Token expired, refresh and retry
                    logger.info(f"[{self.name}] Token expired, refreshing...")
                    await self._authenticate()
                    return await self.send_email(to, subject, body, cc, reply_to_message_id)

                if response.status not in (200, 202):
                    error_text = await response.text()
                    logger.error(f"[{self.name}] Send failed: {response.status} - {error_text}")
                    return {"success": False, "error": f"{response.status}: {error_text}"}

                result = await response.json()
                message_id = result.get("id", "")

                logger.info(f"[{self.name}] Email sent to {to} (ID: {message_id})")
                return {"success": True, "message_id": message_id}

        except Exception as e:
            logger.error(f"[{self.name}] Send error: {e}")
            return {"success": False, "error": str(e)}

    async def _log_action(
        self,
        msg_id: str,
        from_addr: str,
        subject: str,
        action: str,
    ) -> None:
        """Log an action to the JSON log file."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "email_id": msg_id,
            "from": from_addr,
            "subject": subject,
            "result": "success",
        }

        log_file = self.logs_path / f"watcher_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


def create_watcher_from_env(inbox_path: Path, logs_path: Path, needs_action_path: Optional[Path] = None) -> GmailWatcher:
    """
    Factory function to create a GmailWatcher from environment variables.

    Automatically detects authentication method from .env configuration.
    """
    auth_method = os.getenv("AUTH_METHOD", "oauth").lower()
    auto_process = os.getenv("AUTO_PROCESS_EMAILS", "true").lower() == "true"

    if auth_method == "service_account":
        return GmailWatcher(
            inbox_path=inbox_path,
            logs_path=logs_path,
            needs_action_path=needs_action_path,
            auto_process=auto_process,
            service_account_key_file=os.getenv("SERVICE_ACCOUNT_KEY_FILE"),
            impersonate_email=os.getenv("IMPERSONATE_EMAIL"),
            poll_interval=float(os.getenv("POLL_INTERVAL_SECONDS", "120")),
            query=os.getenv("GMAIL_QUERY", "is:unread category:primary"),
        )
    else:
        # Default to OAuth2
        return GmailWatcher(
            inbox_path=inbox_path,
            logs_path=logs_path,
            needs_action_path=needs_action_path,
            auto_process=auto_process,
            client_id=os.getenv("GMAIL_CLIENT_ID"),
            client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
            refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
            poll_interval=float(os.getenv("POLL_INTERVAL_SECONDS", "120")),
            query=os.getenv("GMAIL_QUERY", "is:unread category:primary"),
        )


async def main():
    """Main entry point for standalone testing."""
    from dotenv import load_dotenv

    load_dotenv()

    # Create watcher from environment
    watcher = create_watcher_from_env(
        inbox_path=Path("AI_Employee_Vault/Inbox"),
        logs_path=Path("AI_Employee_Vault/Logs"),
    )

    # Run until interrupted
    try:
        await watcher.run()
    except KeyboardInterrupt:
        watcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
