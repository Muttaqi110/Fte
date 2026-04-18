---
name: payment-received
description: Transfer invoices from Pending_Payment to Payment_Recieved folder when client pays. Use when user says "payment received", "mark as paid", "invoice paid", or "client paid".
---

# Payment Received Skill

## Usage

```
payment received for Ali invoice
mark the invoice as paid
invoice paid by Anum
client paid the invoice
```

## How It Works

When invoked:
1. List available invoices in `Pending_Payment/` folder
2. Show user the options
3. Move selected invoice to `Payment_Recieved/` folder
4. System will then register payment in Odoo and move to Done/

## Folders

| Folder | Path |
|--------|------|
| Pending Payment | `Account/Odoo_Invoices/Pending_Payment/` |
| Payment Received | `Account/Odoo_Invoices/Payment_Recieved/` |
| Done | `Account/Odoo_Invoices/Done/` |

## Executing the Skill

1. Scan `Pending_Payment/` folder for unpaid invoices
2. Ask user which invoice was paid (or auto-detect from context)
3. Move file to `Payment_Recieved/` folder
4. System will automatically:
   - Register payment in Odoo via JSON-RPC
   - Update payment state to "paid"
   - Move invoice to `Done/` folder

## Auto-Detection

If user mentions a client name (e.g., "Ali paid"), look for that client's invoice in Pending_Payment/
If user says "all paid" or "everything paid", show all options

## Important

- This skill only works for invoices in `Pending_Payment/` folder
- Once moved to `Payment_Recieved/`, the system handles the Odoo payment registration automatically
- The invoice will then appear in `Done/` folder after payment is registered