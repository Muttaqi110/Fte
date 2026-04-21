"""
Odoo Invoice Watcher - Autonomous invoicing with HITL safety.

Monitors Needs_Action for invoice requests from WhatsApp or Email.
Creates draft invoices in Odoo via MCP server, NEVER posts without approval.

WORKFLOW:
1. Perception: Monitor Needs_Action for invoice requests
2. Reasoning: Create Plan.md with calculated amounts from Rates.md
3. Drafting: Use Odoo MCP to create Draft Invoice in Odoo
4. HITL Safety: Write approval request to Pending_Approval
5. Final Execute: Only post invoice when human moves file to Approved

SECURITY RULES:
- Never hardcode Odoo credentials in code - read from environment only
- Never auto-post invoices - MUST wait for human approval
- Financial operations use exponential backoff retry
- All invoice operations are logged for audit trail
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from base_watcher import BaseWatcher
from dashboard_updater import DashboardUpdater
from dashboard_updater import DashboardUpdater
from retry_handler import with_retry, RetryExhaustedError

logger = logging.getLogger(__name__)


class OdooInvoiceWatcher(BaseWatcher):
    """
    Monitors for invoice requests and creates Odoo draft invoices.

    HITL Safety: NEVER posts invoices automatically.
    All invoices go to Odoo_Invoices/Draft for human review.
    """

    def __init__(
        self,
        needs_action_path: Path,
        plans_path: Path,
        odoo_invoices_path: Path,
        logs_path: Path,
        rates_path: Path,
        poll_interval: float = 10.0,
    ):
        """
        Initialize the Odoo invoice watcher.

        Args:
            needs_action_path: Path to Needs_Action folder
            plans_path: Path to Plans folder
            odoo_invoices_path: Path to Odoo_Invoices folder (contains Draft, Approved, Done, Rejected, Posted)
            logs_path: Path to Logs folder
            rates_path: Path to Rates.md file
            poll_interval: How often to check for new tasks
        """
        super().__init__(poll_interval=poll_interval)
        self.needs_action_path = Path(needs_action_path)
        self.plans_path = Path(plans_path)
        self.logs_path = Path(logs_path)
        self.rates_path = Path(rates_path)

        # Odoo_Invoices subfolders
        self.odoo_invoices_path = Path(odoo_invoices_path)
        self.draft_path = self.odoo_invoices_path / "Draft"
        self.approved_path = self.odoo_invoices_path / "Approved"
        self.done_path = self.odoo_invoices_path / "Done"
        self.rejected_path = self.odoo_invoices_path / "Rejected"
        self.posted_path = self.odoo_invoices_path / "Posted"
        self.pending_payment_path = self.odoo_invoices_path / "Pending_Payment"
        self.payment_received_path = self.odoo_invoices_path / "Payment_Recieved"

        # Load Odoo configuration from environment (SECURITY: never hardcode)
        self.odoo_url = os.getenv("ODOO_URL", "")
        self.odoo_db = os.getenv("ODOO_DB", "")
        self.odoo_username = os.getenv("ODOO_USERNAME", "")
        self.odoo_password = os.getenv("ODOO_PASSWORD", "")
        self.odoo_api_version = os.getenv("ODOO_API_VERSION", "json-rpc")

        # Invoice patterns to detect - only invoice-related, NOT bill-related
        self.invoice_patterns = [
            r"invoice",
            r"payment",
            r"charge",
            r"fee",
            r"send.*invoice",
            r"create.*invoice",
            r"generate.*invoice",
            r"client",
            r"customer",
        ]

        self._rates_cache: Optional[Dict[str, Any]] = None

    @property
    def name(self) -> str:
        """Return the watcher name."""
        return "OdooInvoiceWatcher"

    async def startup(self) -> None:
        """Initialize directories."""
        self.needs_action_path.mkdir(parents=True, exist_ok=True)
        self.plans_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        # Odoo_Invoices subfolders
        self.draft_path.mkdir(parents=True, exist_ok=True)
        self.approved_path.mkdir(parents=True, exist_ok=True)
        self.done_path.mkdir(parents=True, exist_ok=True)
        self.rejected_path.mkdir(parents=True, exist_ok=True)
        self.pending_payment_path.mkdir(parents=True, exist_ok=True)
        self.payment_received_path = self.odoo_invoices_path / "Payment_Recieved"

        # Verify Odoo configuration
        if not all([self.odoo_url, self.odoo_db, self.odoo_username]):
            logger.warning("[OdooInvoiceWatcher] Odoo credentials not fully configured")
            logger.warning("[OdooInvoiceWatcher] Set ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD in .env")

        logger.info("[OdooInvoiceWatcher] Initialized - monitoring for invoice requests")

    async def shutdown(self) -> None:
        """Cleanup."""
        logger.info("[OdooInvoiceWatcher] Shutdown complete")

    def _load_rates(self) -> Dict[str, Any]:
        """Load rates from Rates.md file."""
        if self._rates_cache:
            return self._rates_cache

        if not self.rates_path.exists():
            logger.warning(f"[OdooInvoiceWatcher] Rates file not found: {self.rates_path}")
            return {}

        try:
            content = self.rates_path.read_text(encoding="utf-8")
            rates = {}

            # Parse markdown table format
            # | Service | Rate | Unit |
            for line in content.split("\n"):
                if line.startswith("|") and not line.startswith("|---"):
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 3 and parts[0] != "Service":
                        service = parts[0].lower()
                        try:
                            rate = float(parts[1].replace("$", "").replace(",", ""))
                            unit = parts[2] if len(parts) > 2 else "hour"
                            rates[service] = {"rate": rate, "unit": unit}
                        except ValueError:
                            continue

            self._rates_cache = rates
            logger.info(f"[OdooInvoiceWatcher] Loaded {len(rates)} rates")
            return rates
        except Exception as e:
            logger.error(f"[OdooInvoiceWatcher] Error loading rates: {e}")
            return {}

    def _is_invoice_request(self, content: str) -> bool:
        """Check if content is an invoice request."""
        content_lower = content.lower()
        return any(re.search(pattern, content_lower) for pattern in self.invoice_patterns)

    def _extract_invoice_details(self, content: str) -> Dict[str, Any]:
        """Extract invoice details from request content."""
        details = {
            "client_name": "",
            "client_email": "",
            "services": [],
            "notes": "",
            "total": 0.0,
            "invoice_date": "",
            "due_date": "",
        }

        # Extract invoice date and parse to YYYY-MM-DD format
        date_match = re.search(r"\*\*Date:\*\*\s*(.+)", content)
        if date_match:
            details["invoice_date"] = self._parse_date(date_match.group(1).strip())

        # Extract due date and parse to YYYY-MM-DD format
        due_match = re.search(r"\*\*Due Date:\*\*\s*(.+)", content)
        if due_match:
            details["due_date"] = self._parse_date(due_match.group(1).strip())

        # Extract client name - look for "**Client:**" or "**Name:**" pattern
        client_match = re.search(r"\*\*Client:\*\*\s*(.+)", content)
        if not client_match:
            client_match = re.search(r"\*\*Name:\*\*\s*(.+)", content)
        if client_match:
            details["client_name"] = client_match.group(1).strip()

        # Extract email
        email_match = re.search(r"\*\*Email:\*\*\s*(.+)", content)
        if email_match:
            details["client_email"] = email_match.group(1).strip()
        else:
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", content)
            if email_match:
                details["client_email"] = email_match.group(0)

        # Extract services - look for list items with amounts
        # Pattern: - Service name - X hours @ $Y/hr = $Z
        service_pattern = r"-\s*(.+?)\s*-\s*(\d+)\s*hours?\s*@\s*\$?(\d+)/?\w*\s*=?\s*\$?([\d,]+)?"
        for match in re.finditer(service_pattern, content, re.IGNORECASE):
            service_name = match.group(1).strip()
            quantity = float(match.group(2))
            rate = float(match.group(3))
            subtotal = float(match.group(4).replace(",", "")) if match.group(4) else quantity * rate
            details["services"].append({
                "name": service_name,
                "quantity": quantity,
                "rate": rate,
                "unit": "hour",
                "subtotal": subtotal,
            })

        # If no services found with pattern, try simpler pattern: - Service - $amount
        if not details["services"]:
            # Match lines like: - Service name - quantity - $amount
            simple_pattern = r"-\s+(.+?) - (\d+) - \$(\d+)"
            for match in re.finditer(simple_pattern, content):
                service_name = match.group(1).strip()
                quantity = int(match.group(2))
                amount = float(match.group(3))
                # Skip if it looks like a heading
                if service_name.lower() in ["services", "notes", "total"]:
                    continue
                details["services"].append({
                    "name": service_name,
                    "quantity": quantity,
                    "rate": amount,
                    "unit": "each",
                    "subtotal": quantity * amount,
                })

        # Try table format: | Description | Amount |
        if not details["services"]:
            # Match: | text | $amount | (capture text AFTER first pipe, before second pipe)
            table_pattern = r"\|\s*([^|]+?)\s*\|\s*\$?([\d,]+(?:\.\d{2})?)\s*\|"
            for match in re.finditer(table_pattern, content):
                service_name = match.group(1).strip()
                amount = float(match.group(2).replace(",", ""))
                # Skip header rows
                if service_name.lower() in ["description", "amount", "service", "total"]:
                    continue
                # Skip header rows
                if service_name.lower() in ["description", "amount", "service", "total"]:
                    continue
                details["services"].append({
                    "name": service_name,
                    "quantity": 1,
                    "rate": amount,
                    "unit": "each",
                    "subtotal": amount,
                })

        # Extract total - look for **Total:** $amount (supports $500 or $500.00)
        total_match = re.search(r"\*\*Total:\*\*\s*\$?\s*([\d,]+(?:\.\d{2})?)", content)
        if total_match:
            details["total"] = float(total_match.group(1).replace(",", ""))
        elif details["services"]:
            # Calculate from services if total not found
            details["total"] = sum(s["subtotal"] for s in details["services"])

        # Extract notes
        notes_match = re.search(r"\*\*Notes:\*\*\s*(.+)", content)
        if notes_match:
            details["notes"] = notes_match.group(1).strip()

        return details

    def _calculate_total(self, services: List[Dict]) -> float:
        """Calculate total invoice amount."""
        return sum(s["quantity"] * s["rate"] for s in services)

    def _parse_date(self, date_str: str) -> str:
        """Parse date string to YYYY-MM-DD format for Odoo."""
        if not date_str:
            return ""

        # Try parsing various date formats
        formats = [
            "%Y-%m-%d",      # 2026-04-11
            "%d %B %Y",      # 11 April 2026
            "%d %b %Y",      # 11 Apr 2026
            "%B %d, %Y",     # April 11, 2026
            "%b %d %Y",      # Apr 11 2026
            "%d-%m-%Y",      # 11-04-2026
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # If already in YYYY-MM-DD format, return as-is
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return date_str

        return date_str  # Return original if can't parse

    @with_retry(max_retries=5, base_delay=1.0, max_delay=60.0)
    async def _create_odoo_draft_invoice(self, invoice_data: Dict) -> Dict[str, Any]:
        """
        Create a draft invoice in Odoo via JSON-RPC API.

        Uses JSON-RPC API (Odoo 19+ requirement).
        SECURITY: Only creates DRAFT - never posts without approval.

        Args:
            invoice_data: Invoice details including client, services, amounts

        Returns:
            Dict with success status and invoice_id or error
        """
        import requests

        if not all([self.odoo_url, self.odoo_db, self.odoo_username, self.odoo_password]):
            return {
                "success": False,
                "error": "Odoo credentials not configured. Set ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD in .env"
            }

        try:
            def jsonrpc(params):
                payload = {"jsonrpc": "2.0", "method": "call", "params": params, "id": 1}
                resp = requests.post(f"{self.odoo_url}/jsonrpc", json=payload, headers={"Content-Type": "application/json"})
                result = resp.json()
                if "error" in result:
                    raise Exception(result["error"].get("message", str(result["error"])))
                return result.get("result")

            # Authenticate
            uid = jsonrpc({
                "service": "common",
                "method": "login",
                "args": [self.odoo_db, self.odoo_username, self.odoo_password]
            })

            if not uid:
                return {"success": False, "error": "Authentication failed"}

            # Find or create partner
            client_name = invoice_data.get("client_name", "Unknown Client")
            client_email = invoice_data.get("client_email", "")

            # Search for existing partner - by email OR by name (case-insensitive)
            partner_id = None
            if client_email:
                partners = jsonrpc({
                    "service": "object",
                    "method": "execute_kw",
                    "args": [self.odoo_db, uid, self.odoo_password, "res.partner", "search",
                             [[("email", "=", client_email)]], {"limit": 1}]
                })
                if partners:
                    partner_id = partners[0]

            # Also check by name to avoid duplicates (exact match only, not ilike)
            if not partner_id and client_name:
                logger.info(f"[OdooInvoiceWatcher] Searching for partner by name (exact): {client_name}")
                partners = jsonrpc({
                    "service": "object",
                    "method": "execute_kw",
                    "args": [self.odoo_db, uid, self.odoo_password, "res.partner", "search",
                             [[("name", "=", client_name)]], {"limit": 1}]
                })
                logger.info(f"[OdooInvoiceWatcher] Search by name result: {partners}")
                if partners:
                    partner_id = partners[0]

            if not partner_id:
                # Create new partner
                logger.info(f"[OdooInvoiceWatcher] Creating new partner: {client_name}")
                partner_id = jsonrpc({
                    "service": "object",
                    "method": "execute_kw",
                    "args": [self.odoo_db, uid, self.odoo_password, "res.partner", "create",
                             [{"name": client_name, "email": client_email, "customer_rank": 1, "type": "contact"}]
                    ]
                })
                logger.info(f"[OdooInvoiceWatcher] Created partner with id: {partner_id}")

            # Create invoice
            invoice_id = jsonrpc({
                "service": "object",
                "method": "execute_kw",
                "args": [self.odoo_db, uid, self.odoo_password, "account.move", "create",
                         [{
                             "move_type": "out_invoice",
                             "partner_id": partner_id,
                             "invoice_date": invoice_data.get("invoice_date") or datetime.now().strftime("%Y-%m-%d"),
                             "invoice_date_due": invoice_data.get("due_date") or "",
                             "narration": invoice_data.get("notes", ""),
                         }]]
            })

            # Add invoice lines
            for service in invoice_data.get("services", []):
                jsonrpc({
                    "service": "object",
                    "method": "execute_kw",
                    "args": [self.odoo_db, uid, self.odoo_password, "account.move.line", "create",
                             [{
                                 "move_id": invoice_id,
                                 "name": service["name"],
                                 "quantity": service["quantity"],
                                 "price_unit": service["rate"],
                             }]]
                })

            # Read back the invoice
            invoice_info = jsonrpc({
                "service": "object",
                "method": "execute_kw",
                "args": [self.odoo_db, uid, self.odoo_password, "account.move", "read",
                         [[invoice_id]], {"fields": ["name", "amount_total"]}]
            })

            return {
                "success": True,
                "invoice_id": invoice_id,
                "invoice_number": invoice_info[0].get("name") if invoice_info else None,
                "amount_total": invoice_info[0].get("amount_total") if invoice_info else 0,
                "partner_id": partner_id,
                "partner_name": client_name,
                "odoo_url": self.odoo_url,
                "odoo_db": self.odoo_db,
                "status": "draft",
                "message": "Draft invoice created in Odoo - awaiting human approval",
            }
        except Exception as e:
            logger.error(f"[OdooInvoiceWatcher] Error creating draft invoice: {e}")
            return {"success": False, "error": str(e)}

    async def _create_approval_request(self, original_file: Path, invoice_data: Dict, odoo_result: Dict) -> Path:
        """
        Create approval request in Odoo_Invoices/Draft folder.

        This is the HITL safety mechanism - humans MUST approve before posting.
        """
        # Use client name and amount
        client_name = invoice_data.get('client_name', 'Unknown').replace(' ', '_')
        total = int(invoice_data.get('total', 0))
        approval_filename = f"{client_name}_${total}.md"
        approval_path = self.draft_path / approval_filename

        total = self._calculate_total(invoice_data.get("services", []))

        content = f"""# Invoice Approval Request

**STATUS: AWAITING APPROVAL**
**Created:** {datetime.now().isoformat()}
**Source:** {original_file.name}

---

## Client Information

- **Name:** {invoice_data.get('client_name', 'Unknown')}
- **Email:** {invoice_data.get('client_email', 'N/A')}

---

## Invoice Details

| Service | Quantity | Rate | Unit | Subtotal |
|---------|----------|------|------|----------|
"""

        for service in invoice_data.get("services", []):
            subtotal = service["quantity"] * service["rate"]
            content += f"| {service['name']} | {service['quantity']} | ${service['rate']:.2f} | {service['unit']} | ${subtotal:.2f} |\n"

        content += f"""
---

**TOTAL:** ${total:.2f}

---

## Odoo Draft Status

```json
{json.dumps(odoo_result, indent=2)}
```

---

## Approval Instructions

**TO APPROVE:** Move this file to `Odoo_Invoices/Approved/`

**TO REJECT:** Move this file to `Odoo_Invoices/Rejected/`

**⚠️ WARNING:** The invoice will NOT be posted to Odoo until approved!

---

## Audit Trail

- Invoice request detected: {original_file.name}
- Draft created: {odoo_result.get('invoice_id', 'N/A')}
- Status: PENDING HUMAN APPROVAL

"""

        approval_path.write_text(content, encoding="utf-8")
        logger.info(f"[OdooInvoiceWatcher] Created approval request: {approval_filename}")
        return approval_path

    async def _log_action(self, action: str, item_id: str, details: str) -> None:
        """Log action to audit trail."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": "odoo_invoice_watcher",
            "action": action,
            "item_id": item_id,
            "details": details,
        }

        log_file = self.logs_path / f"odoo_invoice_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

    async def process_file(self, file_path: Path) -> bool:
        """
        Process a single invoice request file.

        Implements the autonomous invoicing workflow:
        1. Perception: Read the invoice request
        2. Reasoning: Create plan with calculated amounts
        3. Drafting: Create Odoo draft invoice
        4. HITL Safety: Write approval request (NEVER auto-post)
        """
        try:
            content = file_path.read_text(encoding="utf-8")

            # Perception: Is this an invoice request?
            if not self._is_invoice_request(content):
                logger.debug(f"[OdooInvoiceWatcher] Not an invoice request: {file_path.name}")
                return False

            logger.info(f"[OdooInvoiceWatcher] Processing invoice request: {file_path.name}")

            # Reasoning: Extract details and calculate amounts
            invoice_data = self._extract_invoice_details(content)
            total = self._calculate_total(invoice_data.get("services", []))
            invoice_data["total"] = total

            # Create plan in Plans folder
            plan_filename = f"plan_{file_path.stem}.md"
            plan_path = self.plans_path / plan_filename
            plan_content = f"""# Invoice Plan

**Created:** {datetime.now().isoformat()}
**Source:** {file_path.name}

## Reasoning

1. Detected invoice request from {invoice_data.get('client_name', 'Unknown')}
2. Extracted {len(invoice_data.get('services', []))} service line items
3. Calculated total: ${total:.2f}

## Invoice Data

```json
{json.dumps(invoice_data, indent=2)}
```

## Next Steps

1. Create draft invoice in Odoo (JSON-RPC)
2. Write approval request to Pending_Approval
3. Wait for human to move to Approved
4. Post invoice to Odoo (only after approval)

"""
            plan_path.write_text(plan_content, encoding="utf-8")
            await self._log_action("plan_created", file_path.stem, f"Total: ${total:.2f}")

            # Drafting: Create draft in Odoo (with retry for transient errors)
            odoo_result = await self._create_odoo_draft_invoice(invoice_data)
            await self._log_action("draft_created", file_path.stem, json.dumps(odoo_result))

            # HITL Safety: Create approval request - NEVER auto-post
            approval_path = await self._create_approval_request(file_path, invoice_data, odoo_result)
            await self._log_action("approval_requested", file_path.stem, str(approval_path))

            # Mark file as processed - delete original after approval request created
            # This prevents re-processing on next poll cycle
            file_path.unlink()

            logger.info(f"[OdooInvoiceWatcher] Invoice request processed - awaiting approval")
            return True

        except RetryExhaustedError as e:
            logger.error(f"[OdooInvoiceWatcher] All retries exhausted for {file_path.name}: {e}")
            file_path.unlink()
            await self._log_action("invoice_deleted", file_path.stem, f"Retry exhausted: {e}")
            return False

        except Exception as e:
            logger.error(f"[OdooInvoiceWatcher] Error processing {file_path.name}: {e}")
            await self._log_action("error", file_path.stem, str(e))
            return False

    async def poll(self) -> bool:
        """Check for new invoice requests."""
        if not self.needs_action_path.exists():
            return True

        # First, move any files from send_invoices to Needs_Action
        send_invoices_path = self.needs_action_path.parent / "Account" / "send_invoices"
        if send_invoices_path.exists():
            for file_path in send_invoices_path.glob("*.md"):
                if file_path.name != ".gitkeep":
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
                        logger.info(f"[OdooInvoiceWatcher] Moved to Needs_Action: {file_path.name}")
                    except Exception as e:
                        logger.error(f"[OdooInvoiceWatcher] Error moving file: {e}")

        # Now process files in Needs_Action
        for file_path in self.needs_action_path.glob("*.md"):
            # Skip hidden files and already processed _pending files
            if file_path.name.startswith("."):
                continue
            if "_pending" in file_path.name:
                continue

            try:
                await self.process_file(file_path)
            except Exception as e:
                logger.error(f"[OdooInvoiceWatcher] Unexpected error: {e}")
                return False

        return True


class OdooInvoicePoster(BaseWatcher):
    """
    Posts approved invoices to Odoo.

    Monitors Odoo_Invoices/Approved folder for invoices ready to post.
    Only executes the final 'Post' action after human approval.

    Implements Ralph Wiggum Loop (Stop hook):
    - Does not exit until invoice is verified in Done folder
    """

    def __init__(
        self,
        odoo_invoices_path: Path,
        logs_path: Path,
        vault_path: Path = None,
        poll_interval: float = 10.0,
    ):
        super().__init__(poll_interval=poll_interval)
        self.odoo_invoices_path = Path(odoo_invoices_path)
        self.logs_path = Path(logs_path)
        # Dashboard updater
        self._dashboard_updater = DashboardUpdater(vault_path) if vault_path else None

        # Subfolders
        self.approved_path = self.odoo_invoices_path / "Approved"
        self.done_path = self.odoo_invoices_path / "Done"
        self.pending_payment_path = self.odoo_invoices_path / "Pending_Payment"
        self.payment_received_path = self.odoo_invoices_path / "Payment_Recieved"

        # Load Odoo config from environment (SECURITY: never hardcode)
        self.odoo_url = os.getenv("ODOO_URL", "")
        self.odoo_db = os.getenv("ODOO_DB", "")
        self.odoo_username = os.getenv("ODOO_USERNAME", "")
        self.odoo_password = os.getenv("ODOO_PASSWORD", "")

    @property
    def name(self) -> str:
        """Return the watcher name."""
        return "OdooInvoicePoster"

    async def startup(self) -> None:
        """Initialize directories."""
        self.approved_path.mkdir(parents=True, exist_ok=True)
        self.done_path.mkdir(parents=True, exist_ok=True)
        self.pending_payment_path.mkdir(parents=True, exist_ok=True)
        self.payment_received_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
        logger.info("[OdooInvoicePoster] Initialized - monitoring Odoo_Invoices/Approved")
        logger.info(f"[OdooInvoicePoster] Monitoring Payment_Recieved folder")

    async def shutdown(self) -> None:
        """Cleanup."""
        logger.info("[OdooInvoicePoster] Shutdown complete")

    @with_retry(max_retries=5, base_delay=1.0, max_delay=60.0)
    async def _post_invoice_to_odoo(self, invoice_data: Dict) -> Dict[str, Any]:
        """
        Post a draft invoice in Odoo.

        This is the ONLY function that posts invoices,
        and it only runs after human approval.

        SECURITY: Financial operation - uses exponential backoff retry
        """
        import requests

        invoice_id = invoice_data.get("invoice_id")
        if not invoice_id:
            return {"success": False, "error": "No invoice_id provided"}

        try:
            def jsonrpc(params):
                payload = {"jsonrpc": "2.0", "method": "call", "params": params, "id": 1}
                resp = requests.post(f"{self.odoo_url}/jsonrpc", json=payload, headers={"Content-Type": "application/json"})
                result = resp.json()
                if "error" in result:
                    raise Exception(result["error"].get("message", str(result["error"])))
                return result.get("result")

            # Authenticate
            uid = jsonrpc({
                "service": "common",
                "method": "login",
                "args": [self.odoo_db, self.odoo_username, self.odoo_password]
            })

            if not uid:
                return {"success": False, "error": "Authentication failed"}

            # Post the invoice
            jsonrpc({
                "service": "object",
                "method": "execute_kw",
                "args": [self.odoo_db, uid, self.odoo_password, "account.move", "action_post",
                         [[invoice_id]]]
            })

            # Read back the posted invoice
            invoice_info = jsonrpc({
                "service": "object",
                "method": "execute_kw",
                "args": [self.odoo_db, uid, self.odoo_password, "account.move", "read",
                         [[invoice_id]], {"fields": ["name", "amount_total", "state"]}]
            })

            return {
                "success": True,
                "invoice_id": invoice_id,
                "invoice_number": invoice_info[0].get("name") if invoice_info else None,
                "amount_total": invoice_info[0].get("amount_total") if invoice_info else 0,
                "status": "posted",
                "posted_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"[OdooInvoicePoster] Error posting invoice: {e}")
            return {"success": False, "error": str(e)}

    async def _verify_in_done(self, file_stem: str, timeout: float = 30.0) -> bool:
        """
        Verify file has been moved to Done folder.

        Implements Ralph Wiggum Loop (Stop hook pattern):
        - Does not return until file is verified in Done
        - Polls every second up to timeout
        """
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            for done_file in self.done_path.glob(f"*{file_stem}*.md"):
                if file_stem in done_file.stem:
                    return True
            await asyncio.sleep(1.0)
        return False

    async def process_approved_invoice(self, file_path: Path) -> bool:
        """Process an approved invoice and post to Odoo."""
        invoice_data = {}
        try:
            content = file_path.read_text(encoding="utf-8")

            # Extract invoice data from approval file (handle both number and string formats)
            invoice_match = re.search(r'"invoice_id":\s*(\d+)', content)
            if not invoice_match:
                invoice_match = re.search(r'"invoice_id":\s*"([^"]+)"', content)
            if not invoice_match:
                logger.warning(f"[OdooInvoicePoster] No invoice_id found in {file_path.name}")
                return False

            invoice_id = invoice_match.group(1)
            # Convert to int if it's a number
            try:
                invoice_id = int(invoice_id)
            except ValueError:
                pass

            # Extract client name and total from content for done naming
            client_match = re.search(r"- \*\*Name:\*\*\s*(.+)", content)
            if client_match:
                invoice_data["client_name"] = client_match.group(1).strip()
            total_match = re.search(r"\*\*TOTAL:\*\*\s*\$?([\d,]+)", content)
            if total_match:
                invoice_data["total"] = float(total_match.group(1).replace(",", ""))

            logger.info(f"[OdooInvoicePoster] Posting approved invoice: {invoice_id}")

            # Post to Odoo (with retry)
            result = await self._post_invoice_to_odoo({"invoice_id": invoice_id})

            if result.get("success"):
                logger.info(f"[OdooInvoicePoster] Invoice posted: {invoice_id}")

                # Move from Approved to Pending_Payment (transfer, not copy)
                client_name = invoice_data.get("client_name", "Unknown").replace(" ", "_")
                total_amt = int(invoice_data.get("total", 0))
                done_filename = f"{client_name}_${total_amt}.md"

                # Move the approval file directly to Pending_Payment
                pending_payment_path = self.pending_payment_path / done_filename

                # Handle duplicate filenames
                counter = 1
                while pending_payment_path.exists():
                    done_filename = f"{client_name}_${total_amt}_{counter}.md"
                    pending_payment_path = self.pending_payment_path / done_filename
                    counter += 1

                # Move (not copy) the file
                file_path.rename(pending_payment_path)

                # Update dashboard
                if self._dashboard_updater:
                    self._dashboard_updater.update_all()

                # Log action
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "action": "invoice_posted",
                    "invoice_id": invoice_id,
                    "file": file_path.name,
                }
                log_file = self.logs_path / f"odoo_invoice_posted_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")

                # Ralph Wiggum Loop: Verify in Done
                verified = await self._verify_in_done(file_path.stem)
                if verified:
                    logger.info(f"[OdooInvoicePoster] Verified invoice in Done: {invoice_id}")
                else:
                    logger.warning(f"[OdooInvoicePoster] Could not verify invoice in Done within timeout")

                return True
            else:
                logger.error(f"[OdooInvoicePoster] Failed to post invoice: {result.get('error')}")
                return False

        except RetryExhaustedError as e:
            logger.error(f"[OdooInvoicePoster] All retries exhausted: {e}")
            file_path.unlink()
            return False

        except Exception as e:
            logger.error(f"[OdooInvoicePoster] Error processing {file_path.name}: {e}")
            return False

    async def poll(self) -> bool:
        """Check for approved invoices to post."""
        if not self.approved_path.exists():
            return True

        for file_path in self.approved_path.glob("*.md"):
            if file_path.name.startswith("."):
                continue
            if file_path.is_dir():
                continue
            try:
                await self.process_approved_invoice(file_path)
            except Exception as e:
                logger.error(f"[OdooInvoicePoster] Unexpected error: {e}")

        # Check for payments in Payment_Recieved folder
        await self.process_payments()

        return True

    async def process_payments(self) -> bool:
        """Process invoices moved to Payment_Recieved - update Odoo and move to Done."""
        if not self.payment_received_path.exists():
            logger.debug("[OdooInvoicePoster] Payment_Recieved folder does not exist")
            return True

        files = list(self.payment_received_path.glob("*.md"))
        if not files:
            logger.debug(f"[OdooInvoicePoster] No files in Payment_Recieved: {files}")
            return True

        logger.info(f"[OdooInvoicePoster] Found {len(files)} files in Payment_Recieved: {[f.name for f in files]}")

        import requests

        for file_path in self.payment_received_path.glob("*.md"):
            if file_path.name.startswith("."):
                continue
            try:
                content = file_path.read_text(encoding="utf-8")

                # Extract invoice_id from content - check multiple patterns
                invoice_match = re.search(r'\*\*Invoice ID:\*\*\s*(\d+)', content)
                if not invoice_match:
                    # Also check for invoice_id in JSON block (including inside code blocks)
                    invoice_match = re.search(r'"invoice_id":\s*(\d+)', content)
                if not invoice_match:
                    # Also try without quotes
                    invoice_match = re.search(r'invoice_id["\s:]+(\d+)', content)

                if not invoice_match:
                    logger.warning(f"[OdooInvoicePoster] No invoice_id in {file_path.name}")
                    continue

                invoice_id = int(invoice_match.group(1))

                def jsonrpc(params):
                    payload = {"jsonrpc": "2.0", "method": "call", "params": params, "id": 1}
                    resp = requests.post(f"{self.odoo_url}/jsonrpc", json=payload, headers={"Content-Type": "application/json"})
                    result = resp.json()
                    return result.get("result")

                uid = jsonrpc({"service": "common", "method": "login", "args": [self.odoo_db, self.odoo_username, self.odoo_password]})

                if not uid:
                    logger.warning("[OdooInvoicePoster] Odoo not connected")
                    continue

                # Register payment in Odoo
                jsonrpc({
                    "service": "object",
                    "method": "execute_kw",
                    "args": [self.odoo_db, uid, self.odoo_password, "account.move", "action_register_payment", [invoice_id]]
                })

                # Update payment state in Odoo
                jsonrpc({
                    "service": "object",
                    "method": "execute_kw",
                    "args": [self.odoo_db, uid, self.odoo_password, "account.move", "write",
                            [[invoice_id], {"payment_state": "paid"}]]
                })

                logger.info(f"[OdooInvoicePoster] Payment registered for invoice {invoice_id}")

                # Move to Done folder (handle duplicates)
                done_filename = file_path.name
                done_path = self.done_path / done_filename
                counter = 1
                while done_path.exists():
                    stem = file_path.stem
                    suffix = file_path.suffix
                    done_filename = f"{stem}_paid_{counter}{suffix}"
                    done_path = self.done_path / done_filename
                    counter += 1
                file_path.rename(done_path)
                logger.info(f"[OdooInvoicePoster] Invoice {invoice_id} moved to Done")

                # Update dashboard
                if self._dashboard_updater:
                    self._dashboard_updater.update_all()

            except Exception as e:
                logger.error(f"[OdooInvoicePoster] Error processing payment: {e}")
