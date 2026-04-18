# Invoice Approval Request

**STATUS: AWAITING APPROVAL**
**Created:** 2026-04-13T18:17:46.715057
**Source:** TestNewPartnerXYZ_$500.md

---

## Client Information

- **Name:** TestNewPartnerXYZ
- **Email:** **Date:** 2026-04-13

---

## Invoice Details

| Service | Quantity | Rate | Unit | Subtotal |
|---------|----------|------|------|----------|
| Test Service | 1 | $500.00 | each | $500.00 |

---

**TOTAL:** $500.00

---

## Odoo Draft Status

```json
{
  "success": true,
  "invoice_id": 246,
  "invoice_number": false,
  "amount_total": 500.0,
  "partner_id": 96,
  "partner_name": "TestNewPartnerXYZ",
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

- Invoice request detected: TestNewPartnerXYZ_$500.md
- Draft created: 246
- Status: PENDING HUMAN APPROVAL

