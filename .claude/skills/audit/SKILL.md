---
name: audit
description: Generate weekly financial and operational audit reports. Use this skill when user asks for "audit report", "weekly report", "financial report", "audit", "/audit", or "run audit". Scans AI_Employee_Vault for invoices, bills, completed tasks, and more.
---

# Audit Report Skill

Generates comprehensive weekly financial and operational audit reports by analyzing the AI_Employee_Vault.

## Usage

```
/audit                     # Generate report for previous week
/audit 2026-04-01         # Generate report for specific week (YYYY-MM-DD)
```

## What This Skill Does

### 1. Revenue Check (Previous Week)
- Scans `AI_Employee_Vault/Account/Odoo_Invoices/Done/`
- Parses filenames containing dates (YYYY-MM-DD format)
- Extracts amounts from **TOTAL:** fields in markdown files
- Sums all invoices paid in the week

### 2. Expenses Check (Previous Week)
- Scans `AI_Employee_Vault/Account/Odoo_Bills/Done/`
- Extracts amounts from bills paid in the previous week
- Calculates total expenses

### 3. Pending Unpaid Invoices
- Checks `AI_Employee_Vault/Account/Odoo_Invoices/Pending_Payment/`
- Identifies invoices overdue (pending > 7 days)
- Sums total unpaid amount

### 4. Monthly Total Earnings
- Calculates revenue minus expenses for current month
- Falls back to file modification time if no date in filename
- Pulls from `AI_Employee_Vault/Account/Odoo_Invoices/Done/` and `AI_Employee_Vault/Account/Odoo_Bills/Done/`

### 5. Target Progress
- Reads `AI_Employee_Vault/Business_Goals.md`
- Extracts "Monthly Goal" from the Revenue Target table
- Calculates: (Current Revenue / Target) × 100 = % achieved

### 6. Completed Tasks
- Scans `AI_Employee_Vault/Done/` for files dated within the week
- Uses file modification time if no date in filename
- Lists all completed tasks with timestamps

### 7. Bottlenecks Detection
- `Needs_Action/` > 5 items = "High pending queue"
- `Pending_Approval/` > 3 items = "Pending approvals"
- `Odoo_Bills/Draft/` > 0 = "Unpaid bills"

### 8. Suggestions (Auto-Analysis)
- High queue → "Prioritize or delegate"
- Pending approvals → "Review to keep workflow moving"
- Invoice drafts → "Process to accelerate cash flow"
- Otherwise → "System running smoothly"

### 9. Upcoming Deadlines
- Scans `AI_Employee_Vault/Scheduled/` folder
- Finds all dated items within 7 days
- Also reads `AI_Employee_Vault/Business_Goals.md` for project deadlines in Active Projects table
- Lists with due dates

### 10. Pending Bills
- Scans `AI_Employee_Vault/Account/Odoo_Bills/Draft/` (unapproved bills)
- Lists each bill with amount
- Shows total pending

## Executing the Skill

When this skill is invoked, execute:

```bash
python audit_report.py --skill
```

Or with specific date:

```bash
python audit_report.py --skill 2026-04-01
```

The report will be saved to `AI_Employee_Vault/Audit/audit_YYYY-MM-DD.md`

## Output Format

The skill generates a markdown report with sections:
- Financial Summary (last week + this month)
- Target Progress (% achieved)
- Completed Tasks
- Bottlenecks
- Suggestions
- Upcoming Deadlines
- Pending Bills