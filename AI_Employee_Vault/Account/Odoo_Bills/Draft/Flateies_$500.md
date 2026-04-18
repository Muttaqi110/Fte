# Vendor Bill Approval Request

**STATUS: AWAITING APPROVAL**
**Created:** 2026-04-18T23:05:24.205569
**Source:** Bill_Flateies_$500.md

---

## Vendor Information

- **Name:** Flateies
- **Email:** flaties@event.com

---

## Bill Details

| Item | Quantity | Rate | Subtotal |
|------|----------|------|---------|
| Event Booking | 1 | $500.00 | $500.00 |

---

**TOTAL:** $500.00

---

## Odoo Vendor Bill Status

```json
{
  "success": true,
  "bill_id": 253,
  "vendor_id": 99,
  "amount_total": 500.0,
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

