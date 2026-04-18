# Invoice Approval Request

**STATUS: AWAITING APPROVAL**
**Created:** 2026-04-13T18:08:58.789187
**Source:** NewClient_$100.md

---

## Client Information

- **Name:** NewClient
- **Email:** **Date:** 2026-04-13

---

## Invoice Details

| Service | Quantity | Rate | Unit | Subtotal |
|---------|----------|------|------|----------|
| Testing | 1 | $100.00 | each | $100.00 |

---

**TOTAL:** $100.00

---

## Odoo Draft Status

```json
{
  "success": true,
  "invoice_id": 244,
  "invoice_number": false,
  "amount_total": 100.0,
  "partner_id": 96,
  "partner_name": "NewClient",
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

- Invoice request detected: NewClient_$100.md
- Draft created: 244
- Status: PENDING HUMAN APPROVAL

