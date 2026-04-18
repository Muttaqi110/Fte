# Company Handbook

## Rules of Engagement

These rules govern how the Digital FTE system processes and responds to all communications, invoices, and social media. All automated actions must comply with these guidelines.

---

### 1. General Communication Rules

| Rule ID | Rule | Implementation |
|---------|------|--------------|
| COM-001 | Always be professional and polite | Tone must be professional and polite, especially on WhatsApp and Email |
| COM-002 | Auto-Approve known contacts | Replies to known contacts can be drafted and sent automatically |
| COM-003 | Manual-Approval required | New contacts, bulk sends, or sensitive negotiations must be placed in `/Pending_Approval` |

**Implementation:**
- Known contacts: Anyone previously communicated with (stored in contact history)
- Unknown senders: Always require human review before drafting

---

### 2. Financial & Accounting Thresholds (Gold Tier Requirement)

| Rule ID | Rule | Implementation |
|---------|------|--------------|
| FIN-001 | General Limit | Flag any payment or transaction over **$500** for manual approval |
| FIN-002 | Odoo - Draft Only | All invoices and payments in Odoo must be created as **'Draft'** only |
| FIN-003 | Never auto-post | Never 'Post' or 'Confirm' a transaction unless file is moved to `/Approved` folder |
| FIN-004 | New Payees | Always require human approval for any new payee, regardless of amount |
| FIN-005 | Recurring Costs | Auto-approve recurring payments under **$50**; anything above requires check |

**Implementation:**
- Odoo workflow: Request → Draft → Human moves to Approved → System posts → Done
- Payments > $500: Move to `/Pending_Approval` folder until approved

---

### 3. Social Media & Content Rules

| Rule ID | Rule | Implementation |
|---------|------|--------------|
| SOC-001 | Scheduling | Scheduled posts can be auto-approved |
| SOC-002 | Engagement Review | Direct replies to comments or DMs on Facebook or X (Twitter) must be reviewed by human first |

**Implementation:**
- Scheduled posts: Files in `/Scheduled` folder are auto-approved
- Replies: Move engagement drafts to `/Pending_Approval` before responding

---

### 4. Safety & Security Protocol

| Rule ID | Rule | Implementation |
|---------|------|--------------|
| SEC-001 | Data Integrity | No files should be deleted or moved outside the vault without explicit permission |
| SEC-002 | Privacy | **Never share** API keys, `.env` details, or bank credentials in any communication |
| SEC-003 | No Passwords | Never share account passwords |
| SEC-004 | Verify Identity | Verify sender identity before acting on requests |
| SEC-005 | No Unknown Downloads | Never execute file downloads from unknown senders |

---

### 5. The 'Aha!' Logic

| Rule ID | Rule | Implementation |
|---------|------|--------------|
| AHA-001 | Monday Morning CEO Briefing | During the Monday Morning CEO Briefing, detect software subscriptions with no activity for 30 days and suggest cancellation |
| AHA-002 | Suggestion Folder | Move cancellation suggestions to `/Pending_Approval` folder for human approval |

**Implementation:**
- Analyze: Check software/SaaS subscriptions for activity in the past 30 days
- Detection: No login, no usage, no payments in 30 days = candidate for cancellation
- Action: Create cancellation request in `/Pending_Approval` with reasoning

---

### 6. Escalation Rules

| Condition | Action |
|-----------|--------|
| Payment over $500 | Flag for manual approval |
| New payee | Require human approval |
| Sensitive negotiation | Move to `/Pending_Approval` |
| Unknown sender | Extra scrutiny, verify identity |
| Suspected phishing | Move to quarantine, alert admin |
| Subscription inactive 30+ days | Suggest cancellation in `/Pending_Approval` |

---

### 7. Approval Workflow

#### Email/WhatsApp
```
Request Received → Classify → Draft Generated → Human Review → Move to Approved → Send → Done
```

#### Odoo Invoice
```
Request → OdooInvoiceWatcher detects → Draft created in Odoo → File in Draft folder → Human moves to Approved → OdooInvoicePoster posts → Done
```

#### Social Media
```
Post Request → Draft Generated → Scheduled (auto-approved) OR Pending_Approval (for replies) → Human reviews → Post → Done
```

---

### 8. Audit & Logging

All actions are logged to `/Logs` in JSON format:
- Timestamp
- Action type
- File ID / Reference
- Result
- Any flags raised

---

### 9. Folder Structure Reference

| Folder | Purpose |
|--------|---------|
| `Needs_Action` | Incoming requests to process |
| `Plans` | Generated execution plans |
| `Pending_Approval` | Items requiring human approval (not auto-processed) |
| `Gmail_Messages/Draft` | Email drafts awaiting approval |
| `Gmail_Messages/Approved` | Approved emails ready to send |
| `Odoo_Invoices/Draft` | Draft invoices in Odoo |
| `Odoo_Invoices/Approved` | Approved invoices to post |
| `LinkedIn_Posts/Draft` | LinkedIn post drafts |
| `X_Posts/Draft` | X/Twitter post drafts |
| `Facebook_Posts/Draft` | Facebook post drafts |
| `Done` | Completed items |

---

*Version: 2.0.0 | Last Updated: 2026-04-09*