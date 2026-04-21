"""
Audit Report Skill - Generates weekly financial and operational audit reports.

Usage:
    python audit_report.py              # Current week's audit
    python audit_report.py --week-of 2026-04-01  # Specific week

Skill invocation:
    /audit - Generate weekly audit report
    /audit 2026-04-01 - Audit for specific week

Features:
- Revenue check (Odoo_Invoices/Done - previous week)
- Expenses check (Odoo_Bills/Done - previous week)
- Pending unpaid invoices (Odoo_Bills/Pending_Payment)
- Monthly total earnings
- Target from Business_Goals.md
- Target percentage achieved
- Completed tasks
- Bottlenecks
- Suggestions
- Upcoming Deadlines
- Pending bills
"""

import argparse
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditReport:
    """Generates weekly audit reports."""

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)

    def generate_report(self, week_start: Optional[datetime] = None) -> str:
        """Generate full audit report for given week."""
        if week_start is None:
            # Default to previous week
            today = datetime.now()
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday + 7)

        week_end = week_start + timedelta(days=6)

        report = f"""# Weekly Audit Report

**Period:** {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

---
"""

        # Financial Summary
        report += self._generate_financial_summary(week_start, week_end)

        # Target Progress
        report += self._generate_target_progress()

        # Completed Tasks
        report += self._generate_completed_tasks(week_start, week_end)

        # Bottlenecks
        report += self._generate_bottlenecks()

        # Suggestions
        report += self._generate_suggestions()

        # Upcoming Deadlines
        report += self._generate_upcoming_deadlines()

        # Pending Bills
        report += self._generate_pending_bills()

        return report

    def _get_files_in_date_range(
        self, folder: Path, start: datetime, end: datetime
    ) -> List[Path]:
        """Get files modified within date range."""
        if not folder.exists():
            return []

        files = []
        for f in folder.glob("*.md"):
            file_date = None

            # Try to parse date from filename (format: YYYY-MM-DD_...)
            match = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
            if match:
                try:
                    file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
                except ValueError:
                    pass

            # Fallback: use file modification time if no date in filename
            if not file_date:
                timestamp = f.stat().st_mtime
                file_date = datetime.fromtimestamp(timestamp)

            if start <= file_date <= end:
                files.append(f)

        return files

    def _extract_amount(self, content: str) -> float:
        """Extract amount from file content."""
        # Look for **TOTAL:** $XX,XXX or similar patterns
        patterns = [
            r"\*\*TOTAL:\*\*\s*\$([\d,]+)",
            r"total[:\s]*\$([\d,]+)",
            r"amount[:\s]*\$([\d,]+)",
            r"\$([\d,]+)",
        ]
        for pattern in patterns:
            try:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    val = match.group(1).replace(",", "")
                    try:
                        return float(val)
                    except ValueError:
                        pass
            except re.error:
                pass
        return 0.0

    def _generate_financial_summary(
        self, week_start: datetime, week_end: datetime
    ) -> str:
        """Generate financial summary section."""
        invoices_done = self.vault_path / "Account" / "Odoo_Invoices" / "Done"
        bills_done = self.vault_path / "Account" / "Odoo_Bills" / "Done"
        pending_payment = self.vault_path / "Account" / "Odoo_Bills" / "Pending_Payment"

        # Revenue (invoices paid last week)
        revenue = 0
        for f in self._get_files_in_date_range(invoices_done, week_start, week_end):
            content = f.read_text(encoding="utf-8")
            revenue += self._extract_amount(content)

        # Expenses (bills paid last week)
        expenses = 0
        for f in self._get_files_in_date_range(bills_done, week_start, week_end):
            content = f.read_text(encoding="utf-8")
            expenses += self._extract_amount(content)

        # Pending unpaid invoices from last week
        pending_unpaid = 0
        if pending_payment.exists():
            last_week = week_end - timedelta(days=7)
            for f in pending_payment.glob("*.md"):
                # Consider files pending for more than a week as overdue
                pending_unpaid += self._extract_amount(f.read_text(encoding="utf-8"))

        # Monthly totals
        month_start = week_start.replace(day=1)
        monthly_revenue = 0
        monthly_expenses = 0

        for f in invoices_done.glob("*.md"):
            file_date = None
            match = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
            if match:
                try:
                    file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
                except ValueError:
                    pass
            if not file_date:
                file_date = datetime.fromtimestamp(f.stat().st_mtime)
            if file_date.month == month_start.month and file_date.year == month_start.year:
                monthly_revenue += self._extract_amount(f.read_text(encoding="utf-8"))

        for f in bills_done.glob("*.md"):
            file_date = None
            match = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
            if match:
                try:
                    file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
                except ValueError:
                    pass
            if not file_date:
                file_date = datetime.fromtimestamp(f.stat().st_mtime)
            if file_date.month == month_start.month and file_date.year == month_start.year:
                monthly_expenses += self._extract_amount(f.read_text(encoding="utf-8"))

        net_earnings = monthly_revenue - monthly_expenses
        month_name = month_start.strftime("%B %Y")

        return f"""## Financial Summary

### Last Week ({week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')})

| Metric | Amount |
|--------|--------|
| Revenue (Invoices Paid) | ${revenue:,.2f} |
| Expenses (Bills Paid) | ${expenses:,.2f} |
| Net | ${revenue - expenses:,.2f} |
| Overdue Unpaid | ${pending_unpaid:,.2f} |

### This Month ({month_name})

| Metric | Amount |
|--------|--------|
| Total Revenue | ${monthly_revenue:,.2f} |
| Total Expenses | ${monthly_expenses:,.2f} |
| Net Earnings | ${net_earnings:,.2f} |

---

"""

    def _generate_target_progress(self) -> str:
        """Generate target progress section."""
        business_goals = self.vault_path / "Business_Goals.md"

        target = 0
        if business_goals.exists():
            content = business_goals.read_text(encoding="utf-8")
            # Look for Monthly Goal in table
            match = re.search(r"\| Monthly Goal \|\s*\$([\d,]+)\s*\|", content, re.IGNORECASE)
            if match:
                target = float(match.group(1).replace(",", ""))
            # Fallback: look for any large number labeled as goal/target
            if target == 0:
                match = re.search(r"(?:revenue|target|goal)[:\s]*\$([\d,]+)", content, re.IGNORECASE)
                if match and match.group(1):
                    try:
                        target = float(match.group(1).replace(",", ""))
                    except ValueError:
                        pass

        # Get monthly revenue for percentage
        invoices_done = self.vault_path / "Account" / "Odoo_Invoices" / "Done"
        month_start = datetime.now().replace(day=1)
        monthly_revenue = 0

        for f in invoices_done.glob("*.md"):
            file_date = None
            match = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
            if match:
                try:
                    file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
                except ValueError:
                    pass
            if not file_date:
                file_date = datetime.fromtimestamp(f.stat().st_mtime)
            if file_date.month == month_start.month and file_date.year == month_start.year:
                monthly_revenue += self._extract_amount(f.read_text(encoding="utf-8"))

        percentage = (monthly_revenue / target * 100) if target > 0 else 0

        return f"""## Target Progress

| Metric | Value |
|--------|--------|
| Monthly Target | ${target:,.2f} |
| Current Revenue | ${monthly_revenue:,.2f} |
| Target Achieved | {percentage:.1f}% |

---

"""

    def _generate_completed_tasks(
        self, week_start: datetime, week_end: datetime
    ) -> str:
        """Generate completed tasks section."""
        done_folder = self.vault_path / "Done"

        tasks = []
        for f in self._get_files_in_date_range(done_folder, week_start, week_end):
            task_name = f.stem
            # Extract meaningful part
            if "_done_" in task_name:
                task_name = task_name.split("_done_", 1)[1]
            tasks.append(f"- {task_name[:60]}")

        if not tasks:
            tasks.append("- No tasks completed this week")

        return f"""## Completed Tasks

{chr(10).join(tasks)}

---

"""

    def _generate_bottlenecks(self) -> str:
        """Generate bottlenecks section."""
        bottlenecks = []

        # Check for pending items
        needs_action = self.vault_path / "Needs_Action"
        if needs_action.exists():
            count = len(list(needs_action.glob("*.md")))
            if count > 5:
                bottlenecks.append(f"- High pending queue: {count} items")

        pending_approval = self.vault_path / "Pending_Approval"
        if pending_approval.exists():
            count = len(list(pending_approval.glob("*.md")))
            if count > 3:
                bottlenecks.append(f"- Pending approvals: {count} items")

        human_review = self.vault_path / "Human_Review_Queue"
        if human_review.exists():
            count = len(list(human_review.glob("*.md")))
            if count > 0:
                bottlenecks.append(f"- Human review items: {count} items")

        # Check for overdue invoices
        pending_payment = self.vault_path / "Account" / "Odoo_Bills" / "Pending_Payment"
        if pending_payment.exists():
            count = len(list(pending_payment.glob("*.md")))
            if count > 0:
                bottlenecks.append(f"- Unpaid bills: {count} bills pending payment")

        if not bottlenecks:
            bottlenecks.append("- No major bottlenecks identified")

        return f"""## Bottlenecks

{chr(10).join(bottlenecks)}

---

"""

    def _generate_suggestions(self) -> str:
        """Generate suggestions section."""
        suggestions = []

        # Analyze patterns and add suggestions
        needs_action = self.vault_path / "Needs_Action"
        if needs_action.exists():
            count = len(list(needs_action.glob("*.md")))
            if count > 10:
                suggestions.append(
                    "- High workload detected. Consider prioritizing or delegating."
                )

        pending_approval = self.vault_path / "Pending_Approval"
        if pending_approval.exists() and list(pending_approval.glob("*.md")):
            suggestions.append(
                "- Review pending approvals to keep workflow moving"
            )

        # Check invoice turnaround
        draft = self.vault_path / "Account" / "Odoo_Invoices" / "Draft"
        if draft.exists() and list(draft.glob("*.md")):
            suggestions.append(
                "- Process pending invoice drafts to accelerate cash flow"
            )

        if not suggestions:
            suggestions.append("- System is running smoothly")

        return f"""## Suggestions

{chr(10).join(suggestions)}

---

"""

    def _generate_upcoming_deadlines(self) -> str:
        """Generate upcoming deadlines section."""
        deadlines = []

        # Check scheduled folder
        scheduled = self.vault_path / "Scheduled"
        if scheduled.exists():
            for f in scheduled.glob("*.md"):
                content = f.read_text(encoding="utf-8")
                # Look for dates
                matches = re.findall(
                    r"(\d{4}-\d{2}-\d{2})", content
                )
                for date_str in matches:
                    try:
                        date = datetime.strptime(date_str, "%Y-%m-%d")
                        if date <= datetime.now() + timedelta(days=7):
                            deadlines.append(
                                f"- {f.stem[:40]}: {date.strftime('%b %d')}"
                            )
                    except ValueError:
                        pass

        # Also check Business_Goals.md for project deadlines
        business_goals = self.vault_path / "Business_Goals.md"
        if business_goals.exists():
            content = business_goals.read_text(encoding="utf-8")
            # Look for project deadlines in the Active Projects table only
            # Find the section between "Active Projects" and the next "##" or "---"
            active_section = re.search(r"## Active Projects.*?(?=##|\Z)", content, re.DOTALL)
            if active_section:
                section_text = active_section.group(0)
                # Look for project rows: | Project Name | YYYY-MM-DD | Budget | Status |
                # Capture: name, date, budget, status
                project_matches = re.findall(
                    r"\|\s*([^|]+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]*?)\s*\|\s*([^|]+?)\s*\|",
                    section_text
                )
                for project_name, date_str, budget, status in project_matches:
                    # Skip completed projects
                    status_lower = status.strip().lower()
                    if status_lower in ["done", "completed", "cancelled"]:
                        continue
                    try:
                        date = datetime.strptime(date_str, "%Y-%m-%d")
                        if date <= datetime.now() + timedelta(days=7):
                            deadlines.append(
                                f"- {project_name.strip()}: {date.strftime('%b %d')}"
                            )
                    except ValueError:
                        pass

        if not deadlines:
            deadlines.append("- No upcoming deadlines this week")

        return f"""## Upcoming Deadlines

{chr(10).join(deadlines)}

---

"""

    def _generate_pending_bills(self) -> str:
        """Generate pending bills section - shows bills in Draft folder awaiting approval."""
        draft = self.vault_path / "Account" / "Odoo_Bills" / "Draft"

        bills = []
        total = 0
        if draft.exists():
            for f in draft.glob("*.md"):
                content = f.read_text(encoding="utf-8")
                amount = self._extract_amount(content)
                bills.append(f"- {f.stem[:50]} - ${amount:,.2f}")
                total += amount

        if not bills:
            bills.append("- No pending bills")

        bill_count = len(list(draft.glob("*.md"))) if draft.exists() else 0

        return f"""## Pending Bills

| Status | Count | Total |
|--------|-------|-------|
| Awaiting Payment | {bill_count} | ${total:,.2f} |

{chr(10).join(bills)}

---

"""


def run_audit(week_of: str = None) -> str:
    """Run audit and return report path."""
    vault_path = Path("AI_Employee_Vault")

    # Create Audit folder
    audit_path = vault_path / "Audit"
    audit_path.mkdir(parents=True, exist_ok=True)

    # Determine week
    week_start = None
    if week_of:
        try:
            week_start = datetime.strptime(week_of, "%Y-%m-%d")
        except ValueError:
            print(f"Invalid date format: {week_of}. Use YYYY-MM-DD")
            sys.exit(1)

    # Generate report
    audit = AuditReport(vault_path)
    report = audit.generate_report(week_start)

    # Save report
    today = datetime.now()
    if week_start:
        filename = f"audit_{week_start.strftime('%Y-%m-%d')}"
    else:
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday + 7)
        filename = f"audit_{week_start.strftime('%Y-%m-%d')}"

    report_path = audit_path / f"{filename}.md"
    report_path.write_text(report, encoding="utf-8")

    return str(report_path), report


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate weekly audit report",
        epilog="""
Examples:
  python audit_report.py              # Current week's audit
  python audit_report.py --week-of 2026-04-01  # Audit for week starting Apr 1, 2026
  python audit_report.py --skill     # Called as skill from the system
        """
    )
    parser.add_argument(
        "--week-of",
        type=str,
        help="Week start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--skill",
        action="store_true",
        help="Called as skill (silent mode)",
    )
    parser.add_argument(
        "args",
        nargs="*",
        help="Additional arguments (for skill invocation)",
    )
    args = parser.parse_args()

    # Handle /audit skill invocation
    if args.args:
        # Called with arguments like /audit 2026-04-01
        week_of = None
        if args.args[0] != "audit":
            week_of = args.args[0]
        report_path, report = run_audit(week_of)
    else:
        report_path, report = run_audit(args.week_of)

    print(f"Audit report saved: {report_path}")
    if not args.skill:
        print("\n" + report)


if __name__ == "__main__":
    main()