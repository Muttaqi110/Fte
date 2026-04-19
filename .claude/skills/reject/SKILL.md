---
name: reject
description: Reject draft files and move them to Rejected folder. Use when user asks to "reject", "discard", "delete", or "not approve" a draft. Moves draft files from Draft/ to Rejected/ folder.
---

# Reject Skill

## Usage- IMPORTANT: Follow These Steps IN ORDER

**CRITICAL: Always start with Step 1. Never skip steps.**

```
reject the linkedin draft
discard the facebook post
not approve the email
delete the x post
reject invoice INV-2026-04-12-001
```

## How It Works

When invoked:
1. List available drafts in Draft folders
2. Show user the options
3. Move selected draft to Rejected folder
4. Confirm action to user

## Draft & Rejected Folders

| Platform | Draft Folder | Rejected Folder |
|----------|------------|---------------|
| LinkedIn | Social_Media/LinkedIn_Posts/Draft/ | Social_Media/LinkedIn_Posts/Rejected/ |
| X | Social_Media/X_Posts/Draft/ | Social_Media/X_Posts/Rejected/ |
| Facebook | Social_Media/Facebook_Posts/Draft/ | Social_Media/Facebook_Posts/Rejected/ |
| Email | Gmail/Gmail_Messages/Draft/ | Gmail/Gmail_Messages/Rejected/ |
| WhatsApp | WhatsApp/WhatsApp_Messages/Draft/ | WhatsApp/WhatsApp_Messages/Rejected/ |
| Invoice | Account/Odoo_Invoices/Draft/ | Account/Odoo_Invoices/Rejected/ |

## Executing the Skill

1. Scan Draft folders for available files
2. Ask user which one to reject (or auto-detect from context)
3. Move file to respective Rejected folder
4. Confirm action to user

## Auto-Detection

If user says "reject the invoice" - look in Odoo_Invoices/Draft/
If user says "discard the linkedin post" - look in LinkedIn_Posts/Draft/
If user says "not approve the x post" - look in X_Posts/Draft/

Note: Make sure you first list drafts before moving