# Digital FTE Dashboard

> Last Updated: 2026-04-11 13:31:32

---

## System Status

| Component | Status | Last Heartbeat |
|-----------|--------|----------------|
| Orchestrator | 🟡 Idle | - |
| Gmail Watcher | 🟡 Idle | - |
| WhatsApp Watcher | 🟡 Idle | - |
| LinkedIn Watcher | 🟡 Idle | - |
| Social Watcher | 🟡 Idle | - |
| Watchdog | 🟡 Idle | - |
| Claude API | 🟡 Unconfigured | - |

### Social Media Posters

| Platform | Status | Profile |
|----------|--------|---------|
| LinkedIn | 🟡 Idle | .linkedin_poster_profile/ |
| X (Twitter) | 🟡 Idle | .x_poster_profile/ |
| Facebook | 🟡 Idle | .facebook_poster_profile/ |

### Odoo ERP

| Component | Status |
|-----------|--------|
| Invoice Posting | 🟢 Enabled |
| Bill Management | 🟢 Enabled |

---

## Recent Activity

| Time | Action | Details |
|------|--------|---------|
| - | System initialized | Dashboard created |

---

## Pending Tasks

| Priority | Task | Source | Age |
|----------|------|--------|-----|
| - | No pending tasks | - | - |

---

## Quick Stats

- **Emails Processed Today**: 3
- **Drafts Awaiting Approval**: 15
- **Failed Operations**: 0

---

## Error Recovery Status

### Queue Status

| Queue | Count | Status |
|-------|-------|--------|
| Needs_Action | 0 | 🟢 Normal |
| Outbox_Queue | 0 | 🟢 Normal |
| Human_Review_Queue | 0 | 🟢 Normal |
| Quarantine | 0 | 🟢 Normal |

### Graceful Degradation

| System | Status |
|--------|--------|
| Obsidian Vault | 🟢 Available |
| Gmail API | 🟢 Available |
| WhatsApp | 🟢 Available |
| LinkedIn | 🟢 Available |
| X (Twitter) | 🟢 Available |
| Facebook | 🟢 Available |

### Recovery Audit Log (Last 10)

| Timestamp | Action | Error | Result |
|-----------|--------|-------|--------|
| *No entries* | | | |

---

## ⚠️ Active Alerts

*No active alerts.*

---

## Folders Overview

### Communication Channels

| Folder | Count | Purpose |
|--------|-------|---------|
| `/Inbox` | 0 | Raw incoming emails |
| `/Needs_Action` | 1 | Items requiring processing |
| `/Draft` | 33 | Generated responses |
| `/Done` | 17 | Completed tasks |
| `/Logs` | 0 | Audit logs |

### LinkedIn Posts

| Folder | Count | Purpose |
|--------|-------|---------|
| `/linkedin_post` | 0 | New post requirements |
| `/Social_Media/LinkedIn_Posts/Draft` | 10 | Post drafts |
| `/Social_Media/LinkedIn_Posts/Approved` | 0 | Ready to publish |
| `/Social_Media/LinkedIn_Posts/Done` | 0 | Published posts |

### X (Twitter) Posts

| Folder | Count | Purpose |
|--------|-------|---------|
| `/x_post` | 0 | New post requirements |
| `/Social_Media/X_Posts/Draft` | 1 | Post drafts (280 char max) |
| `/Social_Media/X_Posts/Approved` | 0 | Ready to publish |
| `/Social_Media/X_Posts/Done` | 0 | Published posts |



### Facebook Posts

| Folder | Count | Purpose |
|--------|-------|---------|
| `/facebook_post` | 1 | New post requirements |
| `/Social_Media/Facebook_Posts/Draft` | 1 | Post drafts |
| `/Social_Media/Facebook_Posts/Approved` | 0 | Ready to publish |
| `/Social_Media/Facebook_Posts/Done` | 1 | Published posts |

### Odoo Invoices

| Folder | Count | Purpose |
|--------|-------|---------|
| `/send_invoices` | 0 | Invoice requests |
| `/Odoo_Invoices/Draft` | 0 | Draft invoices |
| `/Odoo_Invoices/Approved` | 0 | Approved for posting |
| `/Odoo_Invoices/Done` | 7 | Posted invoices |

### Odoo Bills

| Folder | Count | Purpose |
|--------|-------|---------|
| `/send_bills` | 0 | Vendor bill requests |
| `/Odoo_Bills/Draft` | 4 | Draft bills |
| `/Odoo_Bills/Approved` | 0 | Approved for posting |
| `/Odoo_Bills/Done` | 2 | Posted bills |

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
