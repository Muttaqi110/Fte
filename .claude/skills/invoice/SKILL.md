---
name: invoice
description: Create invoices for clients. Use this skill when user asks to "create invoice", "generate invoice", "make invoice", or "invoice [amount] against [name]". Creates invoice request which is automatically processed by the OdooInvoiceWatcher.
---

# Invoice Skill

## Usage

```
create invoice of $500 against Anum emails is anam.zehra.zaidi@gmail.com due date is 12 april 2026 as she booked a tv
```

## Invoice Format

```markdown
# Invoice INV-2026-04-11-026

**Date:** 2026-04-11
**Due Date:** 2026-04-15

---

## Client Information

- **Name:** SampleTest
- **Email:** sampletest@test.com

---

## Details

| Description | Amount |
|-------------|--------|
| Sample Service | $250.00 |

---

**TOTAL:** $250.00
```


## Executing the Skill

When invoked:
1. Create invoice file in `AI_Employee_Vault/Needs_Action/`
2. OdooInvoiceWatcher will detect it, create draft in Odoo, and move to Odoo_Invoices/Draft
3. Poll Draft folder every 15 seconds (max 12 attempts = 3 minutes)
4. Once draft appears, show user the Odoo status (invoice_id, partner_id, partner_name)
5. Instruct user to move to Approved/ to post

## Draft Detection

Check for new draft files by:
- Looking for files in `Account/Odoo_Invoices/Draft/`
- Polling every 15 seconds
- Stop polling after 12 attempts (3 minutes max)

## Polling Logic

```python
import time
from pathlib import Path

draft_path = Path("AI_Employee_Vault/Account/Odoo_Invoices/Draft")
max_attempts = 12  # 3 minutes max (12 * 15s = 180s)
attempt = 0

while attempt < max_attempts:
    draft_files = list(draft_path.glob("*.md"))
    if draft_files:
        # Show the newest draft
        latest = max(draft_files, key=lambda f: f.stat().st_mtime)
        print(latest.read_text())
        break
    time.sleep(15)
    attempt += 1
```

Note: Make sure you generate .md file