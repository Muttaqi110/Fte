"""
Subscription Auditor - The 'Aha!' Logic

Runs Sunday night to audit software subscriptions:
- Flags 30+ days inactive → Suggest cancellation
- Flags cost increase > 20% → Budget review
- Flags duplicate functionality → Consolidation

Uses config from Business_Goals.md
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

import aiofiles

from config_parser import get_config_parser

logger = logging.getLogger("SubscriptionAuditor")


class SubscriptionAuditor:
    """
    Audits software subscriptions for waste/cancellation opportunities.
    """

    def __init__(
        self,
        vault_path: Path,
        pending_approval_path: Path,
        logs_path: Path,
    ):
        self.vault_path = Path(vault_path)
        self.pending_approval_path = Path(pending_approval_path)
        self.logs_path = Path(logs_path)
        self.config = get_config_parser(vault_path)

    async def run_audit(self) -> Dict[str, Any]:
        """Run the subscription audit."""
        logger.info("[SubscriptionAuditor] Starting audit...")

        # Get audit rules from config
        audit_rules = self.config.get_audit_rules()
        no_activity_days = int(audit_rules.get("no_activity_days", "30"))
        cost_increase_threshold = int(audit_rules.get("cost_increase_percent", "20"))

        findings = {
            "inactive_subscriptions": [],
            "cost_increases": [],
            "duplicates": [],
            "recommendations": [],
        }

        # Read subscription tracking file if exists
        subscriptions = await self._load_subscriptions()

        for sub in subscriptions:
            # Check inactivity
            if sub.get("last_login"):
                daysSinceLogin = self._days_since(sub["last_login"])
                if daysSinceLogin > no_activity_days:
                    findings["inactive_subscriptions"].append({
                        "name": sub["name"],
                        "days_inactive": daysSinceLogin,
                        "monthly_cost": sub.get("cost", 0),
                        "reason": f"No activity for {daysSinceLogin} days",
                    })
                    findings["recommendations"].append({
                        "item": sub["name"],
                        "action": "CANCEL",
                        "reason": f"No login for {daysSinceLogin} days (> {no_activity_days} threshold)",
                        "savings": sub.get("cost", 0),
                    })

            # Check cost increase
            if sub.get("previous_cost") and sub.get("cost"):
                increase = ((sub["cost"] - sub["previous_cost"]) / sub["previous_cost"]) * 100
                if increase > cost_increase_threshold:
                    findings["cost_increases"].append({
                        "name": sub["name"],
                        "previous_cost": sub["previous_cost"],
                        "current_cost": sub["cost"],
                        "increase_percent": round(increase, 1),
                        "reason": f"Cost increased by {round(increase, 1)}%",
                    })
                    findings["recommendations"].append({
                        "item": sub["name"],
                        "action": "REVIEW",
                        "reason": f"Cost increased by {round(increase, 1)}% (> {cost_increase_threshold}% threshold)",
                        "savings": 0,
                    })

        # Check for duplicates (simple keyword matching)
        tool_keywords = {}
        for sub in subscriptions:
            name = sub.get("name", "").lower()
            for keyword in ["email", "crm", "calendar", "hosting", "storage", "chat"]:
                if keyword in name:
                    tool_keywords.setdefault(keyword, []).append(sub["name"])

        for keyword, tools in tool_keywords.items():
            if len(tools) > 1:
                findings["duplicates"].append({
                    "keyword": keyword,
                    "tools": tools,
                    "reason": f"Multiple tools for: {keyword}",
                })
                # Get cheapest to recommend
                cheapest = min(subscriptions, key=lambda x: x.get("cost", 999))
                findings["recommendations"].append({
                    "item": cheapest["name"],
                    "action": "CONSOLIDATE",
                    "reason": f"Duplicate {keyword} functionality - consider consolidating",
                    "savings": sum(s.get("cost", 0) for s in subscriptions if keyword in s.get("name", "").lower()) - cheapest.get("cost", 0),
                })

        # Create pending approval file if there are recommendations
        if findings["recommendations"]:
            await self._create_pending_approval(findings)

        total_savings = sum(r.get("savings", 0) for r in findings["recommendations"])
        logger.info(
            f"[SubscriptionAuditor] Audit complete: {len(findings['recommendations'])} recommendations, "
            f"${total_savings}/month potential savings"
        )

        return findings

    async def _load_subscriptions(self) -> list:
        """Load subscriptions from tracking file."""
        sub_file = self.vault_path / "Subscriptions.md"

        if not sub_file.exists():
            return []

        content = sub_file.read_text(encoding="utf-8")

        subscriptions = []
        # Parse table
        table_match = re.search(
            r"\|.*?Name.*?\|.*?Cost.*?\|.*?(?=\n##|\n\n|\Z)",
            content,
            re.DOTALL | re.IGNORECASE
        )

        if table_match:
            table_content = table_match.group(0)
            for line in table_content.split("\n"):
                if "|" in line and "---" not in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 3 and parts[1] and parts[1] != "Name":
                        cost_match = re.search(r"\$?([\d,]+)", parts[2])
                        subscriptions.append({
                            "name": parts[1],
                            "cost": int(cost_match.group(1).replace(",", "")) if cost_match else 0,
                            "last_login": None,
                            "previous_cost": None,
                        })

        return subscriptions

    def _days_since(self, date_str: str) -> int:
        """Calculate days since date."""
        try:
            last_login = datetime.strptime(date_str, "%Y-%m-%d")
            return (datetime.now() - last_login).days
        except:
            return 0

    async def _create_pending_approval(self, findings: Dict[str, Any]) -> None:
        """Create pending approval file with recommendations."""
        self.pending_approval_path.mkdir(parents=True, exist_ok=True)

        content = "# Subscription Audit - Pending Approval\n\n"
        content += f"**Audit Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
        content += "---\n\n"

        for rec in findings["recommendations"]:
            content += f"## {rec['item']}\n\n"
            content += f"- **Action:** {rec['action']}\n"
            content += f"- **Reason:** {rec['reason']}\n"
            if rec.get("savings"):
                content += f"- **Potential Savings:** ${rec['savings']}/month\n"
            content += "\n"

        # Calculate total savings
        total = sum(r.get("savings", 0) for r in findings["recommendations"])
        content += f"---\n\n**Total Potential Savings:** ${total}/month\n"

        filename = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_subscription_audit.md"
        filepath = self.pending_approval_path / filename

        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.info(f"[SubscriptionAuditor] Created pending approval: {filename}")


# ==================== FACTORY ====================

def create_auditor(
    vault_path: Path | str = "AI_Employee_Vault",
) -> SubscriptionAuditor:
    """Create SubscriptionAuditor instance."""
    if isinstance(vault_path, str):
        vault_path = Path(vault_path)

    return SubscriptionAuditor(
        vault_path=vault_path,
        pending_approval_path=vault_path / "Pending_Approval",
        logs_path=vault_path / "Logs",
    )