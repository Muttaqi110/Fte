# Vendor Bill Approval Request

**STATUS: AWAITING APPROVAL**
**Created:** 2026-04-10T18:14:49.017407
**Source:** stripe_test.md

---

## Vendor Information

- **Name:** Stripe
- **Email:** billing@stripe.com

---

## Bill Details

| Item | Quantity | Rate | Subtotal |
|------|----------|------|---------|
| Processing Fees | 1 | $100.00 | $100.00 |

---

**TOTAL:** $100.00

---

## Odoo Vendor Bill Status

```json
{
  "success": true,
  "bill_id": 100,
  "vendor_id": 65,
  "amount_total": 100.0,
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

