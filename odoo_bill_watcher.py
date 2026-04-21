"""
Odoo Bill Maker - Creates vendor bills in Odoo.

Watches send_bills/ folder for bill requests.
Creates vendor bills in Odoo as drafts.

Workflow:
1. User creates bill request in send_bills/
2. BillWatcher detects → Creates vendor bill in Odoo (Draft)
3. File saved to Odoo_Bills/Draft/
4. User moves to Odoo_Bills/Approved/ → Posted to Odoo
5. File moves to Odoo_Bills/Done/
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
import json
import requests

from base_watcher import BaseWatcher
from dashboard_updater import DashboardUpdater
from dashboard_updater import DashboardUpdater

logger = logging.getLogger("OdooBillWatcher")

# Simple logging - only key events
def log_event(logs_path: Path, event_type: str, data: dict):
    """Log key events to JSONL file."""
    logs_path.mkdir(parents=True, exist_ok=True)
    log_file = logs_path / f"odoo_bills_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        **data
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")


class OdooBillWatcher(BaseWatcher):
    """
    Monitors send_bills folder for bill requests and creates vendor bills in Odoo.
    """

    def __init__(
        self,
        send_bills_path: Path,
        needs_action_path: Path,
        odoo_bills_path: Path,
        logs_path: Path,
        rates_path: Path = None,
        poll_interval: float = 10.0,
    ):
        super().__init__(
            poll_interval=poll_interval,
            max_retries=5,
            initial_backoff=1.0,
            max_backoff=30.0,
        )
        self.send_bills_path = Path(send_bills_path)
        self.needs_action_path = Path(needs_action_path)
        self.odoo_bills_path = Path(odoo_bills_path)
        self.logs_path = Path(logs_path)
        self.rates_path = rates_path
        self._processed_files = set()

        # Odoo connection
        self._odoo_url = None
        self._odoo_db = None
        self._odoo_user = None
        self._odoo_password = None
        self._session = None

    @property
    def name(self) -> str:
        return "OdooBillWatcher"

    async def startup(self) -> None:
        """Initialize paths and Odoo connection."""
        from dotenv import load_dotenv

        load_dotenv()

        # Setup logging
        log_event(self.logs_path, "started", {"name": self.name})

        # Ensure directories exist
        self.send_bills_path.mkdir(parents=True, exist_ok=True)
        self.needs_action_path.mkdir(parents=True, exist_ok=True)
        self.odoo_bills_path.mkdir(parents=True, exist_ok=True)
        self.odoo_bills_path.joinpath("Draft").mkdir(parents=True, exist_ok=True)
        self.odoo_bills_path.joinpath("Approved").mkdir(parents=True, exist_ok=True)
        self.odoo_bills_path.joinpath("Done").mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        # Load Odoo credentials - use the correct env vars like invoice watcher
        import os
        self._odoo_url = os.getenv("ODOO_URL", "http://localhost:8069")
        self._odoo_db = os.getenv("ODOO_DB", "qamar")
        self._odoo_user = os.getenv("ODOO_USERNAME", "admin")  # Fixed env var name
        self._odoo_password = os.getenv("ODOO_PASSWORD", "")

        # Using sync requests (like invoice watcher)

        logger.info(f"[OdooBillWatcher] Started - watching: {self.send_bills_path}")

    async def shutdown(self) -> None:
        """Cleanup."""
        logger.info(f"[OdooBillWatcher] Stopped")

    async def poll(self) -> bool:
        """Check for new bill request files."""
        # First, move any files from send_bills to Needs_Action
        if self.send_bills_path.exists():
            for file_path in self.send_bills_path.glob("*.md"):
                if file_path.name != ".gitkeep" and file_path.name not in self._processed_files:
                    try:
                        # Move to Needs_Action
                        dest_path = self.needs_action_path / file_path.name
                        # Handle duplicates
                        counter = 1
                        while dest_path.exists():
                            stem = file_path.stem
                            dest_path = self.needs_action_path / f"{stem}_{counter}.md"
                            counter += 1
                        file_path.rename(dest_path)
                        logger.info(f"[OdooBillWatcher] Moved to Needs_Action: {file_path.name}")
                    except Exception as e:
                        logger.error(f"[OdooBillWatcher] Error moving file: {e}")

        # Now process files in Needs_Action
        bill_files = [
            f for f in self.needs_action_path.glob("*.md")
            if f.name != ".gitkeep" and f.name not in self._processed_files
        ]

        if not bill_files:
            return True

        for bill_file in bill_files:
            try:
                await self._process_bill_request(bill_file)
                self._processed_files.add(bill_file.name)
            except Exception as e:
                logger.error(f"[OdooBillWatcher] Error processing {bill_file.name}: {e}")
                return False

        return True

    async def _process_bill_request(self, original_file: Path) -> None:
        """Process a bill request file."""
        logger.info(f"[OdooBillWatcher] Processing: {original_file.name}")

        # Read the request
        async with aiofiles.open(original_file, "r", encoding="utf-8") as f:
            content = await f.read()

        # Check if this is a bill request
        if not self._is_bill_request(content):
            logger.warning(f"[OdooBillWatcher] Not detected as bill request: {original_file.name}")
            logger.warning(f"[OdooBillWatcher] Content: {content[:200]}")
            return

        logger.info(f"[OdooBillWatcher] Detected as bill request: {original_file.name}")

        # Extract bill details
        bill_data = self._extract_bill_details(content, original_file.name)

        # Create vendor bill in Odoo
        odoo_result = await self._create_odoo_vendor_bill(bill_data)

        # Create approval request file
        await self._create_approval_request(original_file, bill_data, odoo_result)

        logger.info(f"[OdooBillWatcher] Created vendor bill: {odoo_result.get('bill_id', 'N/A')}")

        # Log key event
        if odoo_result.get("success"):
            log_event(self.logs_path, "bill_created", {
                "bill_id": odoo_result.get("bill_id"),
                "vendor": bill_data.get("vendor_name"),
                "amount": bill_data.get("total"),
                "filename": original_file.name
            })

    def _is_bill_request(self, content: str) -> bool:
        """Check if content is a bill request."""
        content_lower = content.lower()
        patterns = [
            r"vendor",
            r"supplier",
            r"bill\s*(?:to|for|request)",
            r"create\s*bill",
            r"expense",
            r"pay\s*(?:vendor|supplier)",
            r"\*\*vendor\*\*",
            r"line\s*items",
        ]
        return any(re.search(pattern, content_lower) for pattern in patterns)

    def _extract_bill_details(self, content: str, filename: str) -> Dict[str, Any]:
        """Extract bill details from content."""
        details = {
            "vendor_name": "",
            "vendor_email": "",
            "items": [],
            "notes": "",
            "total": 0.0,
        }

        # Extract vendor name
        vendor_match = re.search(r"\*\*Vendor:\*\*\s*(.+)", content)
        if vendor_match:
            details["vendor_name"] = vendor_match.group(1).strip()
        else:
            # Try to find from filename
            details["vendor_name"] = filename.replace(".md", "").replace("_", " ").title()

        # Extract email
        email_match = re.search(r"\*\*Email:\*\*\s*(.+)", content)
        if email_match:
            details["vendor_email"] = email_match.group(1).strip()
        else:
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", content)
            if email_match:
                details["vendor_email"] = email_match.group(0)

        # Extract line items
        # Pattern: - Description - Quantity - $Rate
        item_pattern = r"-\s*(.+?)\s*-\s*(\d+)\s*-\s*\$?(\d+)"
        for match in re.finditer(item_pattern, content, re.IGNORECASE):
            item_name = match.group(1).strip()
            quantity = int(match.group(2))
            rate = float(match.group(3))
            details["items"].append({
                "name": item_name,
                "quantity": quantity,
                "rate": rate,
                "subtotal": quantity * rate,
            })

        # If no items, try simpler pattern
        if not details["items"]:
            simple_pattern = r"-\s*(.+?)\s*[-=]\s*\$?([\d,]+)"
            for match in re.finditer(simple_pattern, content):
                item_name = match.group(1).strip()
                if item_name.lower() in ["total", "notes", "vendor"]:
                    continue
                amount = float(match.group(2).replace(",", ""))
                details["items"].append({
                    "name": item_name,
                    "quantity": 1,
                    "rate": amount,
                    "subtotal": amount,
                })

        # Calculate total
        details["total"] = sum(item["subtotal"] for item in details["items"])

        # Extract notes
        notes_match = re.search(r"\*\*Notes:\*\*\s*(.+)", content, re.DOTALL)
        if notes_match:
            details["notes"] = notes_match.group(1).strip()

        return details

    async def _create_odoo_vendor_bill(self, bill_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create vendor bill in Odoo using sync requests (like invoice watcher)."""
        # Use credentials from startup
        odoo_url = self._odoo_url
        odoo_db = self._odoo_db
        odoo_username = self._odoo_user
        odoo_password = self._odoo_password

        logger.info(f"[OdooBillWatcher] _create_odoo_vendor_bill called with credentials:")
        logger.info(f"  odoo_url: {odoo_url}")
        logger.info(f"  odoo_db: {odoo_db}")
        logger.info(f"  odoo_username: {odoo_username}")
        logger.info(f"  odoo_password: {'SET' if odoo_password else 'EMPTY'}")
        logger.info(f"  raw pwd from env: {repr(self._odoo_password)}")

        logger.info(f"[OdooBillWatcher] Odoo config: url={odoo_url}, db={odoo_db}, user={odoo_username}")

        if not odoo_password:
            odoo_password = os.getenv("ODOO_PASSWORD", "")
            logger.warning(f"[OdooBillWatcher] ODOO_PASSWORD empty, using: {odoo_password}")

        def jsonrpc(params):
            payload = {"jsonrpc": "2.0", "method": "call", "params": params, "id": 1}
            resp = requests.post(f"{odoo_url}/jsonrpc", json=payload, headers={"Content-Type": "application/json"})
            result = resp.json()
            if "error" in result:
                raise Exception(result["error"].get("message", str(result["error"])))
            return result.get("result")

        # Authenticate
        logger.info(f"[OdooBillWatcher] Auth: url={odoo_url}, db={odoo_db}, user={odoo_username}, pwd={'set' if odoo_password else 'EMPTY'}")
        try:
            uid = jsonrpc({
                "service": "common",
                "method": "login",
                "args": [odoo_db, odoo_username, odoo_password]
            })
            logger.info(f"[OdooBillWatcher] Login successful, uid={uid}")
        except Exception as e:
            logger.error(f"[OdooBillWatcher] Auth error: {e}")
            return {"success": False, "error": f"Auth failed: {e}"}

        if not uid:
            logger.error(f"[OdooBillWatcher] UID is None - login failed")
            return {"success": False, "error": "Authentication failed"}

        # Find or create vendor
        vendor_name = bill_data.get("vendor_name", "Unknown")
        vendor_email = bill_data.get("vendor_email", "")
        logger.info(f"[OdooBillWatcher] Looking for vendor: {vendor_name} ({vendor_email})")

        # Search for vendor - by email OR by name
        partner_id = None
        if vendor_email:
            try:
                partners = jsonrpc({
                    "service": "object",
                    "method": "execute_kw",
                    "args": [odoo_db, uid, odoo_password, "res.partner", "search",
                            [[("email", "=", vendor_email)]], {"limit": 1}]
                })
                logger.info(f"[OdooBillWatcher] Search partners result: {partners}")
                if partners:
                    partner_id = partners[0]
            except Exception as e:
                logger.error(f"[OdooBillWatcher] Search error: {e}")

        # Also check by name to avoid duplicates (only if no partner found yet)
        if not partner_id and vendor_name:
            try:
                partners = jsonrpc({
                    "service": "object",
                    "method": "execute_kw",
                    "args": [odoo_db, uid, odoo_password, "res.partner", "search",
                            [[("name", "ilike", vendor_name)]], {"limit": 1}]
                })
                if partners:
                    partner_id = partners[0]
            except Exception as e:
                logger.error(f"[OdooBillWatcher] Search by name error: {e}")

        if not partner_id:
            try:
                logger.info(f"[OdooBillWatcher] Creating vendor: {vendor_name}")
                partner_id = jsonrpc({
                    "service": "object",
                    "method": "execute_kw",
                    "args": [
                        odoo_db, uid, odoo_password, "res.partner", "create",
                        [{"name": vendor_name, "email": vendor_email}]
                    ]
                })
                logger.info(f"[OdooBillWatcher] Vendor created, id: {partner_id}")
            except Exception as e:
                logger.error(f"[OdooBillWatcher] Create vendor error: {e}")
                return {"success": False, "error": f"Could not create vendor: {e}"}

        # Create vendor bill
        line_vals = []
        for item in bill_data.get("items", []):
            line_vals.append((0, 0, {
                "name": item["name"],
                "quantity": item["quantity"],
                "price_unit": item["rate"],
            }))

        bill_vals = {
            "partner_id": partner_id,
            "move_type": "in_invoice",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "line_ids": line_vals,
        }

        try:
            bill_id = jsonrpc({
                "service": "object",
                "method": "execute_kw",
                "args": [odoo_db, uid, odoo_password, "account.move", "create", [bill_vals]]
            })

            if bill_id:
                # Don't post yet - user will approve and post later
                logger.info(f"[OdooBillWatcher] Created vendor bill (draft): {bill_id}")
                return {
                    "success": True,
                    "bill_id": bill_id,
                    "vendor_id": partner_id,
                    "total": bill_data.get("total", 0),
                }
            else:
                return {"success": False, "error": "Failed to create bill"}
        except Exception as e:
            logger.error(f"[OdooBillWatcher] Odoo API error: {e}")
            return {"success": False, "error": str(e)}

    async def _find_or_create_vendor(self, name: str, email: str) -> Optional[int]:
        """Dummy function - now handled in _create_odoo_vendor_bill"""
        return None

    async def _call_odoo(self, model: str, method: str, args: list, kwargs: dict = None) -> Dict:
        """Dummy function - now handled in _create_odoo_vendor_bill"""
        import json

        if kwargs is None:
            kwargs = {}

        # Get Odoo session
        try:
            url = f"{self._odoo_url}/jsonrpc"
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "object",
                    "method": "execute",
                    "args": [
                        self._odoo_db,
                        1,  # admin user
                        self._odoo_password,
                        model,
                        method,
                        *args,
                    ],
                    "kwargs": kwargs,
                },
            }

            async with self._session.post(url, json=payload) as response:
                result = await response.json()
                return {"result": result.get("result", {})}

        except Exception as e:
            logger.error(f"[OdooBillWatcher] Odoo call error: {e}")
            return {"result": None}

    async def _create_approval_request(
        self,
        original_file: Path,
        bill_data: Dict,
        odoo_result: Dict
    ) -> None:
        """Create approval request file."""
        # Create directory
        draft_path = self.odoo_bills_path / "Draft"
        draft_path.mkdir(parents=True, exist_ok=True)

        # Format content
        content = f"""# Vendor Bill Approval Request

**STATUS: AWAITING APPROVAL**
**Created:** {datetime.now().isoformat()}
**Source:** {original_file.name}

---

## Vendor Information

- **Name:** {bill_data.get('vendor_name', 'Unknown')}
- **Email:** {bill_data.get('vendor_email', '')}

---

## Bill Details

| Item | Quantity | Rate | Subtotal |
|------|----------|------|---------|
"""

        for item in bill_data.get("items", []):
            content += f"| {item['name']} | {item['quantity']} | ${item['rate']:.2f} | ${item['subtotal']:.2f} |\n"

        content += f"""
---

**TOTAL:** ${bill_data.get('total', 0):.2f}

---

## Odoo Vendor Bill Status

```json
{json.dumps({
    "success": odoo_result.get("success"),
    "bill_id": odoo_result.get("bill_id"),
    "vendor_id": odoo_result.get("vendor_id"),
    "amount_total": bill_data.get("total"),
    "odoo_url": self._odoo_url,
    "odoo_db": self._odoo_db,
    "status": "draft" if odoo_result.get("success") else "error",
    "message": "Vendor bill created in Odoo - awaiting approval" if odoo_result.get("success") else odoo_result.get("error"),
}, indent=2)}
```

---

## Approval Instructions

**TO APPROVE:** Move this file to `Odoo_Bills/Approved/` → Bill will be posted and paid in Odoo

**TO REJECT:** Move this file to `Odoo_Bills/Rejected/`

**⚠️ WARNING:** The bill will be POSTED when moved to Approved!

"""

        # Write file - use vendor name and amount with .md extension
        vendor_name = bill_data.get('vendor_name', 'Unknown').replace(' ', '_')
        amount = int(bill_data.get('total', 0))
        draft_filename = f"{vendor_name}_${amount}.md"
        draft_file = draft_path / draft_filename

        async with aiofiles.open(draft_file, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.info(f"[OdooBillWatcher] Created approval request: {draft_filename}")

        # Delete original file from send_bills after creating approval request
        if original_file.exists():
            original_file.unlink()
            logger.info(f"[OdooBillWatcher] Deleted original: {original_file.name}")


# ==================== POSTER ====================

import json


class OdooBillPoster(BaseWatcher):
    """Posts approved vendor bills to Odoo."""

    def __init__(
        self,
        odoo_bills_path: Path,
        logs_path: Path,
        vault_path: Path = None,
        poll_interval: float = 10.0,
    ):
        super().__init__(
            poll_interval=poll_interval,
            max_retries=5,
            initial_backoff=1.0,
            max_backoff=30.0,
        )
        self.odoo_bills_path = Path(odoo_bills_path)
        self.logs_path = Path(logs_path)
        # Dashboard updater
        self._dashboard_updater = DashboardUpdater(vault_path) if vault_path else None

        # Odoo connection
        self._odoo_url = None
        self._odoo_db = None
        self._odoo_user = None
        self._odoo_password = None
        self._session = None

    @property
    def name(self) -> str:
        return "OdooBillPoster"

    async def startup(self) -> None:
        """Initialize."""
        from dotenv import load_dotenv
        import aiohttp

        load_dotenv()

        # Setup logging
        log_event(self.logs_path, "started", {"name": self.name})

        import os
        self._odoo_url = os.getenv("ODOO_URL", "http://localhost:8069")
        self._odoo_db = os.getenv("ODOO_DB", "qamar")
        self._odoo_user = os.getenv("ODOO_USERNAME", "admin")
        self._odoo_password = os.getenv("ODOO_PASSWORD", "admin")

        self._session = aiohttp.ClientSession()

        # Ensure directories
        approved_path = self.odoo_bills_path / "Approved"
        done_path = self.odoo_bills_path / "Done"
        approved_path.mkdir(parents=True, exist_ok=True)
        done_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[OdooBillPoster] Initialized - monitoring {approved_path}")

    async def shutdown(self) -> None:
        """Cleanup."""
        if self._session:
            await self._session.close()
        logger.info(f"[OdooBillPoster] Stopped")

    async def poll(self) -> bool:
        """Check for approved bills."""
        approved_path = self.odoo_bills_path / "Approved"

        if not approved_path.exists():
            return True

        approved_files = list(approved_path.glob("*.md"))

        if not approved_files:
            return True

        for approved_file in approved_files:
            try:
                await self._post_bill(approved_file)
            except Exception as e:
                logger.error(f"[OdooBillPoster] Error posting {approved_file.name}: {e}")
                return False

        return True

    async def _post_bill(self, bill_file: Path) -> None:
        """Post approved bill to Odoo."""
        logger.info(f"[OdooBillPoster] Posting approved bill: {bill_file.name}")

        # Read bill file
        async with aiofiles.open(bill_file, "r", encoding="utf-8") as f:
            content = await f.read()

        # Extract bill ID from content
        bill_id_match = re.search(r'"bill_id":\s*(\d+)', content)

        # Also check if it's a manually entered bill
        if not bill_id_match:
            manual_match = re.search(r'manual_bill_id["\s:]*(\d+)', content, re.IGNORECASE)
            if manual_match:
                bill_id = int(manual_match.group(1))
            else:
                bill_id = 0  # No bill_id - will just move to Done without posting
        else:
            bill_id = int(bill_id_match.group(1))

        # Post and pay the bill in Odoo
        try:
            if bill_id and bill_id > 0:
                # Post the bill first
                await self._call_odoo(
                    "account.move",
                    "action_post",
                    [bill_id]
                )
                logger.info(f"[OdooBillPoster] Bill posted: {bill_id}")

                # Now pay using register wizard
                self._pay_with_wizard(bill_id)

                # Log key event
                log_event(self.logs_path, "bill_paid", {
                    "bill_id": bill_id,
                    "filename": bill_file.name
                })
            else:
                logger.info(f"[OdooBillPoster] No bill_id - marked complete: {bill_file.name}")
        except Exception as e:
            logger.error(f"[OdooBillPoster] Error: {e}")

        # Move to Done
        done_path = self.odoo_bills_path / "Done"
        done_path.mkdir(parents=True, exist_ok=True)

        import shutil
        shutil.move(str(bill_file), str(done_path / bill_file.name))

        logger.info(f"[OdooBillPoster] Bill completed: {bill_file.name}")

        # Update dashboard
        if self._dashboard_updater:
            self._dashboard_updater.update_folder("odoo_bills_done")

        # Update dashboard
        if self._dashboard_updater:
            self._dashboard_updater.update_folder("odoo_bills_done")

    async def _call_odoo(self, model: str, method: str, args: list) -> Dict:
        """Call Odoo API with proper authentication."""
        import requests

        # First login to get UID
        login_payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "common",
                "method": "login",
                "args": [self._odoo_db, self._odoo_user, self._odoo_password]
            },
        }

        async with self._session.post(f"{self._odoo_url}/jsonrpc", json=login_payload) as response:
            result = await response.json()
            uid = result.get("result")

        if not uid:
            logger.error("[OdooBillPoster] Login failed")
            return {"result": None}

        # Now call the method with proper UID
        url = f"{self._odoo_url}/jsonrpc"
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    self._odoo_db,
                    uid,
                    self._odoo_password,
                    model,
                    method,
                    args,
                ],
            },
        }

        async with self._session.post(url, json=payload) as response:
            result = await response.json()
            return {"result": result.get("result", {})}

    async def _pay_bill(self, bill_id: int) -> bool:
        """Pay bill using wizard (via sync call)."""
        return self._pay_with_wizard(bill_id)

    def _create_payment(self, bill_id: int) -> bool:
        """Create payment synchronously for a bill."""
        import requests

        url = self._odoo_url + "/jsonrpc"

        # Login
        payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "service": "common", "method": "login",
            "args": [self._odoo_db, self._odoo_user, self._odoo_password]
        }, "id": 1}

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        uid = resp.json().get("result")

        if not uid:
            logger.error("[OdooBillPoster] Login failed")
            return False

        # Get bill details
        payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "service": "object", "method": "execute_kw",
            "args": [self._odoo_db, uid, self._odoo_password, "account.move", "read", [bill_id], {"fields": ["partner_id", "amount_total"]}]
        }, "id": 1}

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        bill_data = resp.json().get("result", [{}])[0]
        partner_id = bill_data.get("partner_id", [0])[0]
        amount = bill_data.get("amount_total", 0)

        if not partner_id:
            return False

        # Create payment
        payment_vals = {
            "partner_id": partner_id,
            "amount": amount,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "journal_id": 6,
            "payment_type": "outbound",
            "partner_type": "supplier",
            "destination_account_id": 15,
        }

        payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "service": "object", "method": "execute_kw",
            "args": [self._odoo_db, uid, self._odoo_password, "account.payment", "create", [payment_vals]]
        }, "id": 1}

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        payment_id = resp.json().get("result")

        if not payment_id:
            logger.error(f"[OdooBillPoster] Failed to create payment")
            return False

        # Post the payment
        post_payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "service": "object", "method": "execute_kw",
            "args": [self._odoo_db, uid, self._odoo_password, "account.payment", "action_post", [[payment_id]]]
        }, "id": 1}

        requests.post(url, json=post_payload, headers={"Content-Type": "application/json"})

        # Process reconciliations
        reconcile_payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "service": "object", "method": "execute_kw",
            "args": [self._odoo_db, uid, self._odoo_password, "account.payment", "process_reconciliations", [[payment_id]]]
        }, "id": 1}

        requests.post(url, json=reconcile_payload, headers={"Content-Type": "application/json"})

        # Manually reconcile - get the move line and mark as reconciled
        lines_payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "service": "object", "method": "execute_kw",
            "args": [self._odoo_db, uid, self._odoo_password, "account.move.line", "search_read",
                    [["move_id", "=", bill_id]], {"fields": ["id"], "limit": 1}]
        }, "id": 1}

        resp = requests.post(url, json=lines_payload, headers={"Content-Type": "application/json"})
        lines = resp.json().get("result", [])

        if lines:
            line_id = lines[0]["id"]
            # Mark as reconciled
            reconcile_line = {"jsonrpc": "2.0", "method": "call", "params": {
                "service": "object", "method": "execute_kw",
                "args": [self._odoo_db, uid, self._odoo_password, "account.move.line", "write", [[line_id], {"reconciled": True}]]
            }, "id": 1}
            requests.post(url, json=reconcile_line, headers={"Content-Type": "application/json"})

        logger.info(f"[OdooBillPoster] Payment {payment_id} processed")
        return True

    def _pay_with_wizard(self, bill_id: int) -> bool:
        """Pay bill using account.payment.register wizard."""
        import requests

        url = self._odoo_url + "/jsonrpc"

        # Login
        payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "service": "common", "method": "login",
            "args": [self._odoo_db, self._odoo_user, self._odoo_password]
        }, "id": 1}

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        uid = resp.json().get("result")

        if not uid:
            logger.error("[OdooBillPoster] Login failed")
            return False

        # Create payment register wizard with context
        wizard_vals = {
            "journal_id": 6,  # Bank journal
        }

        # The context is passed in kwargs
        payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "service": "object", "method": "execute_kw",
            "args": [self._odoo_db, uid, self._odoo_password, "account.payment.register", "create",
                    [wizard_vals], {"context": {"active_model": "account.move", "active_ids": [bill_id]}}]
        }, "id": 1}

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        wizard_id = resp.json().get("result")

        if not wizard_id:
            logger.error("[OdooBillPoster] Failed to create payment register wizard")
            return False

        logger.info(f"[OdooBillPoster] Created payment wizard: {wizard_id}")

        # Trigger the 'action_create_payments' action
        payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "service": "object", "method": "execute_kw",
            "args": [self._odoo_db, uid, self._odoo_password, "account.payment.register", "action_create_payments", [wizard_id]]
        }, "id": 1}

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        result = resp.json()

        logger.info(f"[OdooBillPoster] Wizard action result: {result}")
        return True

    async def _register_payment(self, bill_id: int) -> None:
        """Register payment for a vendor bill using action_register_payment."""
        # Use Odoo's built-in action to register payment
        # This opens the payment registration wizard
        result = await self._call_odoo(
            "account.move",
            "action_register_payment",
            [bill_id]
        )
        # If it returns a dict with payment_id, process it
        if result and isinstance(result, dict):
            payment_id = result.get("result") or result.get("res_id")
            if payment_id:
                # Get the payment and post it
                await self._call_odoo(
                    "account.payment",
                    "action_post",
                    [payment_id]
                )
                logger.info(f"[OdooBillPoster] Payment registered: {payment_id}")


# ==================== FACTORY ====================

def create_bill_system(
    vault_path: str = "AI_Employee_Vault",
) -> tuple:
    """Create bill watcher and poster."""
    vault = Path(vault_path)

    bill_watcher = OdooBillWatcher(
        send_bills_path=vault / "send_bills",
        needs_action_path=vault / "Needs_Action",
        odoo_bills_path=vault / "Odoo_Bills",
        logs_path=vault / "Logs",
        rates_path=vault / "Rates.md",
        poll_interval=10.0,
    )

    bill_poster = OdooBillPoster(
        odoo_bills_path=vault / "Odoo_Bills",
        logs_path=vault / "Logs",
        poll_interval=10.0,
    )

    return bill_watcher, bill_poster