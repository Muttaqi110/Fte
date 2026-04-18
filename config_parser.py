"""
Config Parser - Dynamically reads vault config files.

Parses:
- Business_Goals.md: Revenue targets, metrics, projects
- Company_Handbook.md: Rules, thresholds, limits
"""

import re
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class ConfigParser:
    """Dynamic configuration from vault markdown files."""

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)
        self.business_goals_path = self.vault_path / "Business_Goals.md"
        self.company_handbook_path = self.vault_path / "Company_Handbook.md"

        # Cache for configs
        self._cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 60  # Cache for 60 seconds

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl_seconds

    def _invalidate_cache(self) -> None:
        """Invalidate cache to force re-read."""
        self._cache.clear()
        self._cache_time = None

    # ==================== BUSINESS GOALS ====================

    def get_revenue_target(self) -> Dict[str, Any]:
        """Get revenue target from Business_Goals.md."""
        if not self.business_goals_path.exists():
            return {"monthly_goal": 10000, "mtd": 0, "status": "Unknown"}

        content = self.business_goals_path.read_text(encoding="utf-8")

        # Extract monthly goal
        monthly_goal = 10000
        match = re.search(r"Monthly Goal.*?\$\s*([\d,]+)", content, re.IGNORECASE)
        if match:
            monthly_goal = int(match.group(1).replace(",", ""))

        # Extract MTD
        mtd = 0
        match = re.search(r"Month-to-Date.*?\$\s*([\d,]+)", content, re.IGNORECASE)
        if match:
            mtd = int(match.group(1).replace(",", ""))

        # Extract status
        status = "Unknown"
        match = re.search(r"Status.*?\*\*([A-Z\s]+)\*\*", content, re.IGNORECASE)
        if match:
            status = match.group(1).strip()

        return {
            "monthly_goal": monthly_goal,
            "mtd": mtd,
            "status": status,
            "last_updated": self._get_last_updated(content),
        }

    def get_key_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get key metrics table from Business_Goals.md."""
        if not self.business_goals_path.exists():
            return {}

        content = self.business_goals_path.read_text(encoding="utf-8")

        metrics = {}
        # Find the table
        table_match = re.search(
            r"\| Metric \| Target \| Alert Threshold \|.*?\|-+\|-+\|-+\|(.+?)(?=\n##|\n\n|\Z)",
            content,
            re.DOTALL | re.IGNORECASE
        )

        if table_match:
            table_content = table_match.group(1)
            for line in table_content.strip().split("\n"):
                if "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 4 and parts[1]:  # Metric, Target, Alert
                        metric_name = parts[1].lower()
                        target = parts[2].strip()
                        alert = parts[3].strip()

                        # Parse target value
                        target_value = None
                        if "<" in target:
                            target_value = target.replace("<", "").strip()
                        elif ">" in target:
                            target_value = target.replace(">", "").strip()
                        else:
                            target_value = target

                        # Parse alert value
                        alert_value = None
                        if ">" in alert:
                            alert_value = alert.replace(">", "").strip()
                        elif "<" in alert:
                            alert_value = alert.replace("<", "").strip()
                        else:
                            alert_value = alert

                        # Extract number
                        target_num = self._extract_number(target)
                        alert_num = self._extract_number(alert)

                        metrics[metric_name] = {
                            "target": target_value,
                            "alert": alert_value,
                            "target_num": target_num,
                            "alert_num": alert_num,
                        }

        return metrics

    def get_active_projects(self) -> list:
        """Get active projects from Business_Goals.md."""
        if not self.business_goals_path.exists():
            return []

        content = self.business_goals_path.read_text(encoding="utf-8")

        projects = []
        # Find the projects table
        table_match = re.search(
            r"\| Project \| Due Date \| Budget \| Status \|.*?\|-+\|-+\|-+\|-+\|(.+?)(?=\n##|\n\n|\Z)",
            content,
            re.DOTALL | re.IGNORECASE
        )

        if table_match:
            table_content = table_match.group(1)
            for line in table_content.strip().split("\n"):
                if "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 5 and parts[1]:  # Project name exists
                        projects.append({
                            "name": parts[1],
                            "due_date": parts[2],
                            "budget": parts[3],
                            "status": parts[4],
                        })

        return projects

    def get_audit_rules(self) -> Dict[str, str]:
        """Get subscription audit rules from Business_Goals.md."""
        if not self.business_goals_path.exists():
            return {
                "no_activity_days": "30",
                "cost_increase_percent": "20",
            }

        content = self.business_goals_path.read_text(encoding="utf-8")

        rules = {}

        # No activity detection
        match = re.search(r"No.*?activity.*?(\d+)\s*days?", content, re.IGNORECASE)
        if match:
            rules["no_activity_days"] = match.group(1)

        # Cost increase
        match = re.search(r"cost.*?increased.*?more.*?than.*?(\d+)\s*%", content, re.IGNORECASE)
        if match:
            rules["cost_increase_percent"] = match.group(1)

        return rules if rules else {
            "no_activity_days": "30",
            "cost_increase_percent": "20",
        }

    # ==================== COMPANY HANDBOOK ====================

    def get_communication_rules(self) -> Dict[str, Any]:
        """Get communication rules from Company_Handbook.md."""
        if not self.company_handbook_path.exists():
            return {
                "always_professional": True,
                "auto_approve_known": True,
                "manual_new_contacts": True,
            }

        content = self.company_handbook_path.read_text(encoding="utf-8")

        rules = {}

        # Professional tone
        if "professional" in content.lower():
            rules["always_professional"] = True

        # Auto-approve known
        if "auto-approve" in content.lower() or "auto approve" in content.lower():
            rules["auto_approve_known"] = True

        # Manual for new contacts
        if "new contacts" in content.lower() and "manual" in content.lower():
            rules["manual_new_contacts"] = True

        return rules

    def get_financial_thresholds(self) -> Dict[str, Any]:
        """Get financial thresholds from Company_Handbook.md."""
        if not self.company_handbook_path.exists():
            return {
                "payment_flag_amount": 500,
                "new_payee_requires_approval": True,
                "recurring_auto_approve_under": 50,
            }

        content = self.company_handbook_path.read_text(encoding="utf-8")

        thresholds = {}

        # Payment flag amount
        patterns = [
            r"over.*?\$?(\d+)",
            r"\$500.*?approval",
            r"flag.*?payment.*?(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                val = int(match.group(1))
                if val > 0:
                    thresholds["payment_flag_amount"] = val
                    break

        # If not found, use default
        if "payment_flag_amount" not in thresholds:
            thresholds["payment_flag_amount"] = 500

        # New payee requires approval
        if "new payee" in content.lower() and "approval" in content.lower():
            thresholds["new_payee_requires_approval"] = True
        else:
            thresholds["new_payee_requires_approval"] = True

        # Recurring auto-approve under
        match = re.search(r"under.*?\$?(\d+).*?auto.*?approve", content, re.IGNORECASE)
        if match:
            thresholds["recurring_auto_approve_under"] = int(match.group(1))
        else:
            thresholds["recurring_auto_approve_under"] = 50

        return thresholds

    def get_social_media_rules(self) -> Dict[str, Any]:
        """Get social media rules from Company_Handbook.md."""
        if not self.company_handbook_path.exists():
            return {
                "scheduled_auto_approve": True,
                "replies_require_review": True,
            }

        content = self.company_handbook_path.read_text(encoding="utf-8")

        rules = {}

        # Scheduled posts auto-approve
        if "scheduled" in content.lower() and "auto" in content.lower():
            rules["scheduled_auto_approve"] = True
        else:
            rules["scheduled_auto_approve"] = True

        # Replies require review
        if "reply" in content.lower() and "review" in content.lower():
            rules["replies_require_review"] = True
        else:
            rules["replies_require_review"] = True

        return rules

    def get_security_rules(self) -> list:
        """Get security rules from Company_Handbook.md."""
        if not self.company_handbook_path.exists():
            return ["never share api keys", "never share env", "never share credentials"]

        content = self.company_handbook_path.read_text(encoding="utf-8")

        rules = []

        # Privacy rules
        if "api key" in content.lower():
            rules.append("Never share API keys")
        if ".env" in content.lower():
            rules.append("Never share .env details")
        if "bank" in content.lower() or "credential" in content.lower():
            rules.append("Never share bank credentials")

        return rules if rules else ["Never share sensitive data"]

    # ==================== HELPER METHODS ====================

    def _extract_number(self, text: str) -> Optional[float]:
        """Extract number from text."""
        if not text:
            return None
        match = re.search(r"[\d,]+", text)
        if match:
            return float(match.group().replace(",", ""))
        return None

    def _get_last_updated(self, content: str) -> str:
        """Extract last_updated from content."""
        match = re.search(r"last_updated.*?(\d{4}-\d{2}-\d{2})", content, re.IGNORECASE)
        if match:
            return match.group(1)
        return datetime.now().strftime("%Y-%m-%d")

    # ==================== PUBLIC API ====================

    def get_all_config(self) -> Dict[str, Any]:
        """Get all configuration values."""
        if self._is_cache_valid() and self._cache:
            return self._cache

        config = {
            "revenue_target": self.get_revenue_target(),
            "key_metrics": self.get_key_metrics(),
            "active_projects": self.get_active_projects(),
            "audit_rules": self.get_audit_rules(),
            "communication_rules": self.get_communication_rules(),
            "financial_thresholds": self.get_financial_thresholds(),
            "social_media_rules": self.get_social_media_rules(),
            "security_rules": self.get_security_rules(),
        }

        self._cache = config
        self._cache_time = datetime.now()

        return config

    def reload(self) -> None:
        """Force reload of config files."""
        self._invalidate_cache()


# ==================== FACTORY ====================

_config_parser: Optional[ConfigParser] = None


def get_config_parser(vault_path: Path | str | None = None) -> ConfigParser:
    """Get or create ConfigParser singleton."""
    global _config_parser
    if vault_path is None:
        vault_path = Path("AI_Employee_Vault")
    if isinstance(vault_path, str):
        vault_path = Path(vault_path)
    if _config_parser is None:
        _config_parser = ConfigParser(vault_path)
    return _config_parser