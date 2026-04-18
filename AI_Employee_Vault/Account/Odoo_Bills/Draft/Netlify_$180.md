# Vendor Bill Approval Request

**STATUS: AWAITING APPROVAL**
**Created:** 2026-04-10T18:07:44.530322
**Source:** netlify_test.md

---

## Vendor Information

- **Name:** Netlify
- **Email:** billing@netlify.com

---

## Bill Details

| Item | Quantity | Rate | Subtotal |
|------|----------|------|---------|
| Pro Plan | 1 | $180.00 | $180.00 |

---

**TOTAL:** $180.00

---

## Odoo Vendor Bill Status

```json
{
  "success": true,
  "bill_id": 98,
  "vendor_id": 63,
  "amount_total": 180.0,
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

