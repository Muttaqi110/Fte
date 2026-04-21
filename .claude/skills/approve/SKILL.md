---
name: approve
description: Transfer/move draft files to their respective Approved folder for publishing. Use when user asks to "approve", "move to approved","/aprove", "publish", or "send [platform]". Moves draft files from Draft/ to Approved/ folder.
---

# Approve Skill

## Usage

```
approve the linkedin draft
move to approved facebook post
publish the x post
approve invoice INV-2026-04-12-001
send the email
```

## How It Works

When invoked:
1. List available drafts in Draft folders
2. Show user the options
3. Move selected draft to Approved folder
4. System will then publish/send the content

## Draft Folders

| Platform | Draft Folder | Approved Folder |
|----------|------------|---------------|
| LinkedIn | Social_Media/LinkedIn_Posts/Draft/ | Social_Media/LinkedIn_Posts/Approved/ |
| X | Social_Media/X_Posts/Draft/ | Social_Media/X_Posts/Approved/ |
| Facebook | Social_Media/Facebook_Posts/Draft/ | Social_Media/Facebook_Posts/Approved/ |
| Email | Gmail/Gmail_Messages/Draft/ | Gmail/Gmail_Messages/Approved/ |
| WhatsApp | WhatsApp/WhatsApp_Messages/Draft/ | WhatsApp/WhatsApp_Messages/Approved/ |
| Invoice | Account/Odoo_Invoices/Draft/ | Account/Odoo_Invoices/Approved/ |
| Other | Other/Draft/ | Other/Approved/ |

## Executing the Skill

1. Scan Draft folders for available files
2. Ask user which one to approve (or auto-detect from context)
3. Move file to respective Approved folder
4. Confirm action to user

## Auto-Detection

If user says "approve the invoice" - look in Odoo_Invoices/Draft/
If user says "approve the linkedin post" - look in LinkedIn_Posts/Draft/
If user says "publish the x post" - look in X_Posts/Draft/

## Polling After Approval

After moving to Approved:
- For social posts: system publishes automatically
- For emails: system sends automatically
- For invoices: waits in Approved until moved to Payment_Recieved/

Note: Make sure you first list drafts before moving