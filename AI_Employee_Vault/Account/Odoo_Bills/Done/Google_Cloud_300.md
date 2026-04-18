# Vendor Bill Approval Request

**STATUS: AWAITING APPROVAL**
**Created:** 2026-04-10T17:41:11.589604
**Source:** google_test.md

---

## Vendor Information

- **Name:** Google Cloud
- **Email:** billing@cloud.google.com

---

## Bill Details

| Item | Quantity | Rate | Subtotal |
|------|----------|------|---------|
| Storage | 1 | $300.00 | $300.00 |

---

**TOTAL:** $300.00

---

## Odoo Vendor Bill Status

```json
{
  "success": true,
  "bill_id": 93,
  "vendor_id": 55,
  "amount_total": 300.0,
  "odoo_url": "http://localhost:8069",
  "odoo_db": "qamar",
  "status": "draft",
  "message": "Vendor bill created in Odoo - awaiting approval"
}
```

---

## Approval Instructions

**TO APPROVE:** Move this file to `Odoo_Bills/Approved/` → Bill will be posted and paid in Odoo

**TO REJECT:** Move this file to `Odoo_Bills/Rejected/`

**⚠️ WARNING:** The bill will be POSTED when moved to Approved!

