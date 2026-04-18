# Invoice Approval Request

**STATUS: AWAITING APPROVAL**
**Created:** 2026-04-18T23:05:13.538582
**Source:** Invoice_Flateies_$500.md

---

## Client Information

- **Name:** Flateies
- **Email:** flaties@event.com

---

## Invoice Details

| Service | Quantity | Rate | Unit | Subtotal |
|---------|----------|------|------|----------|
| Event Booking | 1 | $500.00 | each | $500.00 |

---

**TOTAL:** $500.00

---

## Odoo Draft Status

```json
{
  "success": true,
  "invoice_id": 252,
  "invoice_number": false,
  "amount_total": 500.0,
  "partner_id": 99,
  "partner_name": "Flateies",
  "odoo_url": "http://localhost:8069",
  "odoo_db": "qamar",
  "status": "draft",
  "message": "Draft invoice created in Odoo - awaiting human approval"
}
```

---

## Approval Instructions

**TO APPROVE:** Move this file to `Odoo_Invoices/Approved/`

**TO REJECT:** Move this file to `Odoo_Invoices/Rejected/`

**⚠️ WARNING:** The invoice will NOT be posted to Odoo until approved!

---

## Audit Trail

- Invoice request detected: Invoice_Flateies_$500.md
- Draft created: 252
- Status: PENDING HUMAN APPROVAL

