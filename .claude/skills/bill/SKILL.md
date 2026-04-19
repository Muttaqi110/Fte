---
name: bill
description: Create a vendor bill request. Use when user says "create bill", "new bill", "add vendor bill", "bill for [vendor]", or "bill of $X against [vendor]". Creates bill request file in Needs_Action/ which is processed by OdooBillWatcher.
---

# Bill Skill

## Usage

```
create bill of $500 against Stripe
new vendor bill for AWS $300
add bill for Google Cloud $150
bill for digital ocean $50
```

## Bill Format

```markdown
# Bill Request

**Vendor:** VendorName
**Email:** vendor@email.com (optional)

---

## Line Items

- Service Name - Quantity - $Rate

---

**Total:** $Amount

---

## Notes

Optional notes about the bill
```

## Executing the Skill- IMPORTANT: Follow These Steps IN ORDER

**CRITICAL: Always start with Step 1. Never skip steps.**

When invoked:
1. Parse user input to extract vendor name and amount
2. Create bill request file in `AI_Employee_Vault/Account/send_bills`
3. OdooBillWatcher will detect it, create draft in Odoo, and move to Odoo_Bills/Draft
4. Poll Draft folder every 15 seconds (max 12 attempts = 3 minutes)
5. Once draft appears, show user the Odoo status (bill_id, vendor_id)
6. Instruct user to move to Approved/ to post and pay
If draft does not appear in 3 minutes, inform user to wait or to check any issue

## Draft Detection

Check for new draft files by:
- Looking for files in `Account/Odoo_Bills/Draft/`
- Polling every 15 seconds
- Stop polling after 12 attempts (3 minutes max)

## Polling Logic

```python
import time
from pathlib import Path

draft_path = Path("AI_Employee_Vault/Account/Odoo_Bills/Draft")
max_attempts = 12  # 3 minutes max (12 * 15s = 180s)
attempt = 0

while attempt < max_attempts:
    draft_files = list(draft_path.glob("*.md"))
    # Filter out .gitkeep
    draft_files = [f for f in draft_files if f.name != ".gitkeep"]
    if draft_files:
        # Show the newest draft
        latest = max(draft_files, key=lambda f: f.stat().st_mtime)
        print(latest.read_text())
        break
    time.sleep(15)
    attempt += 1
```

Note: Make sure you generate .md file