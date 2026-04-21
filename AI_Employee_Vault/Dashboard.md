# Digital FTE Dashboard

> Last Updated: 2026-04-21 10:43:37

---

## System Status

| Component | Status | Last Heartbeat |
|-----------|--------|----------------|
| Orchestrator | 🔴 Offline | - |
| Gmail Watcher | 🔴 Offline | - |
| WhatsApp Watcher | 🔴 Offline | - |
| LinkedIn Watcher | 🔴 Offline | - |
| Social Watcher | 🔴 Offline | - |
| Watchdog | 🔴 Offline | - |
| Claude API | 🟡 Unconfigured | - |

### Social Media Posters

| Platform | Status | Profile |
|----------|--------|---------|
| LinkedIn | 🔴 Offline | .linkedin_poster_profile/ |
| X (Twitter) | 🔴 Offline | .x_poster_profile/ |
| Facebook | 🔴 Offline | .facebook_poster_profile/ |

### Odoo ERP

| Component | Status |
|-----------|--------|
| Invoice Posting | 🟢 Enabled |
| Bill Management | 🟢 Enabled |

---

## Folders Overview

### Gmail

| Folder | Count | Purpose |
|--------|-------|---------|
| `/Gmail/Inbox` | 0 | Raw incoming emails |
| `/Gmail/Gmail_Messages/Draft` | 0 | Generated email drafts |
| `/Gmail/Gmail_Messages/Done` | 0 | Sent emails |

### LinkedIn Posts

| Folder | Count | Purpose |
|--------|-------|---------|
| `/Social_Media/LinkedIn_Posts/Draft` | 0 | Post drafts |
| `/Social_Media/LinkedIn_Posts/Done` | 0 | Published posts |

### X (Twitter) Posts

| Folder | Count | Purpose |
|--------|-------|---------|
| `/Social_Media/X_Posts/Draft` | 0 | Post drafts (280 char max) |
| `/Social_Media/X_Posts/Done` | 0 | Published posts |

### Facebook Posts

| Folder | Count | Purpose |
|--------|-------|---------|
| `/Social_Media/Facebook_Posts/Draft` | 0 | Post drafts |
| `/Social_Media/Facebook_Posts/Done` | 0 | Published posts |

### Odoo Invoices

| Folder | Count | Purpose |
|--------|-------|---------|
| `/Account/Odoo_Invoices/Draft` | 0 | Draft invoices |
| `/Account/Odoo_Invoices/Pending_Payment` | 0 | Awaiting payment |
| `/Account/Odoo_Invoices/Done` | 0 | Posted invoices |

### Odoo Bills

| Folder | Count | Purpose |
|--------|-------|---------|
| `/Account/Odoo_Bills/Draft` | 0 | Draft bills |
| `/Account/Odoo_Bills/Done` | 0 | Posted bills |

---

## Workflow

### Social Media Posting Flow

```
Create requirement → [platform]_post/
        ↓
Watcher moves to → Needs_Action/
        ↓
Claude Code creates plan → Plans/
        ↓
Claude Code creates draft → [Platform]_Posts/Draft/
        ↓
Human moves to → [Platform]_Posts/Approved/
        ↓
Poster publishes → [Platform]_Posts/Done/
```

### Safety Rules

- **HITL Required**: All posts require human approval (move to Approved folder)
- **Character Limits**: X (Twitter) posts are capped at 280 characters
- **Logging**: All actions are logged with timestamp, platform, actor, and approval status

---

*Refresh this page to see updated status. Logs available in `/Logs` folder.*
