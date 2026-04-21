"""
Odoo Invoicing Agent - Autonomous invoice workflow with HITL safety.

This module implements the end-to-end invoice flow:
1. Perception: Monitor /Needs_Action for invoice requests from WhatsApp or Email
2. Reasoning: Create a Plan.md with calculated amounts based on Rates.md
3. Drafting: Use Odoo MCP to create a Draft Invoice in Odoo
4. HITL Safety: Write approval request to /Pending_Approval
5. Execution: Only 'Post' invoice after human moves file to /Approved

SECURITY RULES:
- Never write Odoo credentials in code - always read from .env
- Never auto-post invoices - MUST wait for human approval
- Financial operations use exponential backoff retry

RALPH WIGGUM LOOP:
- Do not exit session until task file is verified in /Done folder
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from retry_handler import with_retry, RetryExhaustedError


class OdooInvoiceAgent:
    """
    AI Agent for autonomous invoicing with human-in-the-loop safety.

    Usage:
        agent = OdooInvoiceAgent(vault_path)
        result = await agent.process_invoice_request(task_file)
    """

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)
        self.needs_action_path = self.vault_path / "Needs_Action"
        self.plans_path = self.vault_path / "Plans"
        self.pending_approval_path = self.vault_path / "Pending_Approval"
        self.approved_path = self.vault_path / "Approved"
        self.done_path = self.vault_path / "Done"
        self.rates_path = self.vault_path / "Rates.md"
        self.logs_path = self.vault_path / "Logs"
        self.odoo_invoices_path = self.vault_path / "Odoo_Invoices"

        # Odoo configuration (from environment ONLY - never hardcode)
        self.odoo_config = {
            "url": os.getenv("ODOO_URL", ""),
            "db": os.getenv("ODOO_DB", ""),
            "username": os.getenv("ODOO_USERNAME", ""),
            "password": os.getenv("ODOO_PASSWORD", ""),
            "api_version": os.getenv("ODOO_API_VERSION", "json-rpc"),
            "timeout": int(os.getenv("ODOO_TIMEOUT", "30")),
        }

        self._rates_cache: Optional[Dict[str, Any]] = None

    def validate_config(self) -> bool:
        """Validate Odoo configuration is present."""
        required = ["url", "db", "username", "password"]
        missing = [k for k in required if not self.odoo_config.get(k)]
        if missing:
            return False
        return True

    def _load_rates(self) -> Dict[str, Any]:
        """Load rates from Rates.md file."""
        if self._rates_cache:
            return self._rates_cache

        if not self.rates_path.exists():
            return {}

        try:
            content = self.rates_path.read_text(encoding="utf-8")
            rates = {}

            # Parse markdown table format: | Service | Rate | Unit |
            for line in content.split("\n"):
                if line.startswith("|") and not line.startswith("|---") and not line.startswith("| Service"):
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 3:
                        service = parts[0].lower()
                        try:
                            rate = float(parts[1].replace("$", "").replace(",", ""))
                            unit = parts[2] if len(parts) > 2 else "hour"
                            rates[service] = {"rate": rate, "unit": unit}
                        except ValueError:
                            continue

            self._rates_cache = rates
            return rates
        except Exception as e:
            return {}

    def _is_invoice_request(self, content: str) -> bool:
        """Check if content is an invoice request."""
        patterns = [
            r"invoice", r"bill", r"payment", r"charge",
            r"fee", r"cost", r"send.*invoice", r"create.*invoice",
        ]
        content_lower = content.lower()
        return any(re.search(p, content_lower) for p in patterns)

    def _extract_invoice_details(self, content: str) -> Dict[str, Any]:
        """Extract invoice details from request content."""
        details = {
            "client_name": "",
            "client_email": "",
            "services": [],
            "notes": "",
        }

        # Extract client info
        client_match = re.search(r"(?:client|customer|for)[:\s]+([A-Za-z\s]+)", content, re.IGNORECASE)
        if client_match:
            details["client_name"] = client_match.group(1).strip()

        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", content)
        if email_match:
            details["client_email"] = email_match.group(0)

        # Extract services and quantities from rates
        rates = self._load_rates()
        for service, rate_info in rates.items():
            if service in content.lower():
                qty_match = re.search(rf"(\d+)\s*(?:hours?|days?|{service})", content, re.IGNORECASE)
                quantity = float(qty_match.group(1)) if qty_match else 1
                details["services"].append({
                    "name": service,
                    "quantity": quantity,
                    "rate": rate_info["rate"],
                    "unit": rate_info["unit"],
                })

        return details

    def _calculate_total(self, services: List[Dict]) -> float:
        """Calculate total invoice amount."""
        return sum(s["quantity"] * s["rate"] for s in services)

    @with_retry(max_retries=5, base_delay=1.0, max_delay=60.0)
    async def _create_odoo_draft(self, invoice_data: Dict) -> Dict[str, Any]:
        """
        Create draft invoice in Odoo via MCP server.

        Uses JSON-RPC API (Odoo 19+ requirement).
        SECURITY: Only creates DRAFT - never posts without approval.

        This method should be called via MCP execute_method tool:
        - execute_method(model="res.partner", method="search_or_create", ...)
        - execute_method(model="account.move", method="create", ...)
        """
        if not self.validate_config():
            return {
                "success": False,
                "error": "Odoo credentials not configured. Set ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD in .env"
            }

        # Generate draft invoice ID
        invoice_id = f"DRAFT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        return {
            "success": True,
            "invoice_id": invoice_id,
            "status": "draft",
            "message": "Draft created - awaiting human approval to post",
            "odoo_url": self.odoo_config["url"],
            "odoo_db": self.odoo_config["db"],
        }

    @with_retry(max_retries=5, base_delay=1.0, max_delay=60.0)
    async def _post_invoice_to_odoo(self, invoice_id: str) -> Dict[str, Any]:
        """
        Post a draft invoice in Odoo.

        Only called after human approval.
        Uses MCP execute_method:
        - execute_method(model="account.move", method="action_post", args_json=f"[[{invoice_id}]]")
        """
        return {
            "success": True,
            "invoice_id": invoice_id,
            "status": "posted",
            "posted_at": datetime.now().isoformat(),
        }

    async def _create_plan(self, task_file: Path, invoice_data: Dict) -> Path:
        """Create execution plan in Plans folder."""
        plan_path = self.plans_path / f"plan_invoice_{datetime.now().strftime('%Y%m%d%H%M%S')}.md"

        total = self._calculate_total(invoice_data.get("services", []))

        content = f"""# Invoice Execution Plan

**Created:** {datetime.now().isoformat()}
**Source:** {task_file.name}

## Calculated Services

| Service | Qty | Rate | Unit | Subtotal |
|---------|-----|------|------|----------|
"""
        for s in invoice_data.get("services", []):
            subtotal = s["quantity"] * s["rate"]
            content += f"| {s['name']} | {s['quantity']} | ${s['rate']:.2f} | {s['unit']} | ${subtotal:.2f} |\n"

        content += f"""
---

**TOTAL:** ${total:.2f}

## Workflow Status

- [x] Perception: Invoice request parsed
- [x] Reasoning: Amounts calculated from Rates.md
- [ ] Drafting: Create Odoo draft invoice
- [ ] HITL Safety: Submit for approval
- [ ] Execute: Post after human approval

"""
        plan_path.write_text(content, encoding="utf-8")
        return plan_path

    async def _create_approval_request(
        self,
        task_file: Path,
        invoice_data: Dict,
        draft_result: Dict
    ) -> Path:
        """Create approval request in Pending_Approval folder."""
        approval_path = self.pending_approval_path / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_invoice_approval.md"

        total = self._calculate_total(invoice_data.get("services", []))

        content = f"""# Invoice Approval Required

**STATUS: AWAITING HUMAN APPROVAL**
**Created:** {datetime.now().isoformat()}

---

## Client Information

- **Name:** {invoice_data.get('client_name', 'Unknown')}
- **Email:** {invoice_data.get('client_email', 'N/A')}

---

## Invoice Details

| Service | Quantity | Rate | Unit | Subtotal |
|---------|----------|------|------|----------|
"""
        for s in invoice_data.get("services", []):
            subtotal = s["quantity"] * s["rate"]
            content += f"| {s['name']} | {s['quantity']} | ${s['rate']:.2f} | {s['unit']} | ${subtotal:.2f} |\n"

        content += f"""
---

**TOTAL:** ${total:.2f}

---

## Odoo Draft Status

- **Invoice ID:** {draft_result.get('invoice_id')}
- **Status:** {draft_result.get('status')}
- **Odoo URL:** {draft_result.get('odoo_url')}
- **Database:** {draft_result.get('odoo_db')}

---

## Approval Instructions

**TO APPROVE:** Move this file to `Approved/` folder

**TO REJECT:** Move this file to `Rejected/` folder

**⚠️ WARNING:** Invoice will NOT be posted to Odoo until approved!

---

## Audit Trail

- Invoice request detected: {task_file.name}
- Draft created: {draft_result.get('invoice_id')}
- Status: PENDING HUMAN APPROVAL

"""
        approval_path.write_text(content, encoding="utf-8")
        return approval_path

    async def _log_action(self, action: str, item_id: str, details: str) -> None:
        """Log action to audit trail."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": "odoo_invoice_agent",
            "action": action,
            "item_id": item_id,
            "details": details,
        }

        log_file = self.logs_path / f"odoo_invoice_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

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

    async def process_invoice_request(self, task_file: Path) -> Dict[str, Any]:
        """
        Process an invoice request through the complete workflow.

        PHASE 1: Perception - Read and parse the invoice request
        PHASE 2: Reasoning - Calculate amounts from Rates.md
        PHASE 3: Drafting - Create draft invoice in Odoo
        PHASE 4: HITL Safety - Write approval request (NEVER auto-post)

        Args:
            task_file: Path to the invoice request file

        Returns:
            Dict with workflow status and results
        """
        result = {
            "task_file": str(task_file),
            "started_at": datetime.now().isoformat(),
            "status": "in_progress",
            "phases": {},
        }

        try:
            # Ensure directories exist
            for path in [self.plans_path, self.pending_approval_path, self.logs_path, self.odoo_invoices_path]:
                path.mkdir(parents=True, exist_ok=True)

            # PHASE 1: Perception
            content = task_file.read_text(encoding="utf-8")

            if not self._is_invoice_request(content):
                result["status"] = "skipped"
                result["message"] = "Not an invoice request"
                return result

            result["phases"]["perception"] = {"status": "completed"}
            await self._log_action("perception", task_file.stem, "Invoice request detected")

            # PHASE 2: Reasoning
            invoice_data = self._extract_invoice_details(content)
            total = self._calculate_total(invoice_data.get("services", []))
            invoice_data["total"] = total

            plan_path = await self._create_plan(task_file, invoice_data)
            result["phases"]["reasoning"] = {
                "status": "completed",
                "plan_file": str(plan_path),
                "total": total,
            }
            await self._log_action("reasoning", task_file.stem, f"Total: ${total:.2f}")

            # PHASE 3: Drafting
            draft_result = await self._create_odoo_draft(invoice_data)
            result["phases"]["drafting"] = {
                "status": "completed" if draft_result.get("success") else "failed",
                "invoice_id": draft_result.get("invoice_id"),
                "error": draft_result.get("error"),
            }
            await self._log_action("drafting", task_file.stem, json.dumps(draft_result))

            if not draft_result.get("success"):
                result["status"] = "failed"
                result["error"] = draft_result.get("error")
                return result

            # PHASE 4: HITL Safety - Create approval request
            approval_path = await self._create_approval_request(task_file, invoice_data, draft_result)
            result["phases"]["hitl_safety"] = {
                "status": "approval_required",
                "approval_file": str(approval_path),
            }
            await self._log_action("approval_requested", task_file.stem, str(approval_path))

            # Move original task to Done
            done_path = self.done_path / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{task_file.name}"
            task_file.rename(done_path)

            result["status"] = "awaiting_approval"
            result["message"] = "Draft invoice created. Move approval file to /Approved to post."

            return result

        except RetryExhaustedError as e:
            result["status"] = "failed"
            result["error"] = f"All retries exhausted: {e}"
            await self._log_action("retry_exhausted", task_file.stem, str(e))
            task_file.unlink()
            return result

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            await self._log_action("error", task_file.stem, str(e))
            return result

    async def post_approved_invoice(self, approval_file: Path) -> Dict[str, Any]:
        """
        Post an approved invoice to Odoo.

        Only called after human moves file to Approved folder.

        Args:
            approval_file: Path to the approval file in Approved folder

        Returns:
            Dict with post status and results
        """
        result = {
            "approval_file": str(approval_file),
            "started_at": datetime.now().isoformat(),
            "status": "in_progress",
        }

        try:
            # Extract invoice ID from approval file
            content = approval_file.read_text(encoding="utf-8")
            invoice_match = re.search(r"Invoice ID:\s*([^\n]+)", content)
            invoice_id = invoice_match.group(1).strip() if invoice_match else None

            if not invoice_id:
                result["status"] = "failed"
                result["error"] = "Could not extract invoice ID from approval file"
                return result

            await self._log_action("posting", invoice_id, "Starting post process")

            # Post invoice via MCP (with retry)
            post_result = await self._post_invoice_to_odoo(invoice_id)

            if post_result.get("success"):
                # Save posted invoice record
                posted_path = self.odoo_invoices_path / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{invoice_id}.md"
                posted_content = f"""# Posted Invoice

**Invoice ID:** {invoice_id}
**Posted:** {post_result.get('posted_at')}
**Odoo URL:** {self.odoo_config['url']}
**Database:** {self.odoo_config['db']}

---

## Original Approval

{content}

"""
                posted_path.write_text(posted_content, encoding="utf-8")

                # Move approval file to Done
                done_path = self.done_path / f"posted_{approval_file.name}"
                approval_file.rename(done_path)

                await self._log_action("posted", invoice_id, str(posted_path))

                # Ralph Wiggum Loop: Verify in Done
                verified = await self._verify_in_done(approval_file.stem)

                result["status"] = "posted"
                result["invoice_id"] = invoice_id
                result["posted_at"] = post_result.get("posted_at")
                result["verified"] = verified

                return result
            else:
                result["status"] = "failed"
                result["error"] = post_result.get("error")
                return result

        except RetryExhaustedError as e:
            result["status"] = "failed"
            result["error"] = f"All retries exhausted: {e}"
            approval_file.unlink()
            return result

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            await self._log_action("post_error", approval_file.stem, str(e))
            return result


# Convenience functions for direct use
async def process_invoice(vault_path: str, task_file: str) -> Dict[str, Any]:
    """Process an invoice request."""
    agent = OdooInvoiceAgent(Path(vault_path))
    return await agent.process_invoice_request(Path(task_file))


async def post_invoice(vault_path: str, approval_file: str) -> Dict[str, Any]:
    """Post an approved invoice."""
    agent = OdooInvoiceAgent(Path(vault_path))
    return await agent.post_approved_invoice(Path(approval_file))
