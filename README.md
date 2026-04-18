# Digital FTE System

AI-powered automation with human-in-the-loop approval for emails, WhatsApp, and social media posts.

**Gold Tier** - Built for 24/7 reliability with automatic error recovery and graceful degradation.

## Run

```bash
python main.py
```

Single command runs all watchers and the orchestrator.

### Production (PM2)

```bash
# Install PM2 globally
npm install -g pm2

# Start all processes
pm2 start ecosystem.config.js

# Save process list
pm2 save

# Configure auto-start on boot (run the command it outputs)
pm2 startup

# Monitoring
pm2 status          # View process status
pm2 logs            # View all logs
pm2 monit           # Real-time dashboard
pm2 restart all     # Restart all processes
pm2 stop all        # Stop all processes
```

## Features

- **Gmail**: Polls unread important emails every 2 minutes
- **WhatsApp**: Monitors for business messages (requires Playwright)
- **LinkedIn Posts**: Creates and publishes LinkedIn posts with approval workflow
- **X (Twitter)**: Creates and publishes posts (no character limit)
- **Facebook**: Creates and publishes community-focused engagement posts
- **Scheduler**: Executes scheduled tasks with repeat support:
  - `once` - Single execution
  - `daily` - Execute every day at the same time
  - `weekly` - Execute on the same day each week
  - `custom` - Execute every X days (configurable)
  - Supports end dates for finite repeat schedules
- **Skills**: Claude Code skills for quick actions (see below)
- **HITL**: All drafts require human approval
- **Audit**: Weekly financial and operational reports

### Error Recovery (Gold Tier)

- **Exponential Backoff Retry**: Automatic retry with 1s base delay, 60s max delay, 5 max retries
- **Comms Failure**: Outgoing tasks queued in `Outbox_Queue/` for auto-retry
- **Financial Safety**: Banking/payment APIs never auto-retry, require human approval
- **Social Media Retry**: Post publishing failures retry 5 times, then move to `Human_Review_Queue/`
- **Watchdog**: Monitors process health, auto-restarts crashed processes
- **PM2**: Daemonized processes survive system reboots

### Odoo Invoice Automation (Gold Tier)

Autonomous invoicing with human-in-the-loop safety:

- **Perception**: Monitors `Needs_Action/` for invoice requests (created via skills or manual addition)
- **Drafting**: Creates draft invoice in Odoo via JSON-RPC API
- **HITL Safety**: Writes approval request to `Odoo_Invoices/Draft/` - NEVER auto-posts
- **Execution**: Posts invoice after human moves file to `Odoo_Invoices/Approved/`
- **Payment Tracking**: Moves to `Pending_Payment/` until client pays
- **Payment Registration**: When human moves to `Payment_Recieved/`, registers payment in Odoo and moves to `Done/`

**Workflow:**
```
Needs_Action → Odoo_Invoices/Draft → Approved → Pending_Payment → Payment_Recieved → Done
```

**File Naming:** Invoices are saved as `ClientName_$Amount.md` (e.g., `Demo_Client_$850.md`)

### Odoo Bill Automation (Gold Tier)

Vendor bill management with human approval:

- **Perception**: Monitors `Needs_Action/` for bill requests (created via skills or manual addition)
- **Drafting**: Creates vendor bill in Odoo via JSON-RPC API
- **HITL Safety**: Writes approval request to `Odoo_Bills/Draft/` - NEVER auto-posts
- **Execution**: Posts and pays bill after human moves file to `Odoo_Bills/Approved/`

**Workflow:**
```
Needs_Action → Odoo_Bills/Draft → Approved → Done (posted & paid)
```

**File Naming:** Bills are saved as `VendorName_$Amount.md` (e.g., `Stripe_$100.md`)

**Security Rules:**
- Odoo credentials are read from `.env` only - never hardcoded in code
- Invoices are NEVER posted without human approval
- Financial operations use exponential backoff retry

## Setup

```bash
# Install dependencies
pip install aiohttp python-dotenv aiofiles cryptography requests playwright
playwright install chromium

# Configure
cp .env.example .env
python get_refresh_token.py  # For Gmail OAuth

# For Odoo invoicing (optional)
# Set these in .env:
# ODOO_URL=http://localhost:8069
# ODOO_DB=odoo
# ODOO_USERNAME=admin
# ODOO_PASSWORD=your_password
# ENABLE_ODOO_INVOICING=true
# ENABLE_ODOO_BILLS=true

# Run
python main.py
```

### First-Time Login for Social Media

When you first run the system with social media posters enabled:

1. A browser window will open for each platform
2. If not logged in, you'll see a warning in the console
3. **You have 5 minutes to log in manually** in the browser window
4. Login state is saved in profile directories (`.linkedin_poster_profile/`, `.x_poster_profile/`, etc.)
5. Subsequent runs will use saved login state

## Workflows

### Gmail Messages
```
Email arrives → Inbox/ → Needs_Action/
        ↓
Claude generates plan → Plans/
        ↓
Claude generates draft → Gmail_Messages/Draft/
        ↓
Human moves to Approved/
        ↓
Auto-send email → Gmail_Messages/Done/
```

### WhatsApp Messages
```
Message arrives → whatsapp_inbox/ → Needs_Action/
        ↓
Claude generates plan → Plans/
        ↓
Claude generates draft → WhatsApp_Messages/Draft/
        ↓
Human moves to Approved/
        ↓
Auto-send message → WhatsApp_Messages/Done/
```

### Social Media Posts (LinkedIn, X, Facebook)
```
Create requirement in Social_Media/[platform]_post/
        ↓
Watcher moves to Needs_Action/
        ↓
Claude creates plan → Plans/
        ↓
Claude creates platform-specific draft → Social_Media/[Platform]_Posts/Draft/
        ↓
Human moves to Approved/
        ↓
Poster publishes to platform → Social_Media/[Platform]_Posts/Done/
```

**Platform-specific notes:**
- **X (Twitter)**: 280 characters max
- **LinkedIn**: Professional, business-oriented content
- **Facebook**: Community-focused, conversational tone

### Odoo Invoice Workflow (Gold Tier)
```
Invoice request → Needs_Action/ → Odoo_Invoices/Draft/
        ↓
Human reviews and moves to Odoo_Invoices/Approved/
        ↓
Odoo Invoice Poster posts to Odoo → Odoo_Invoices/Pending_Payment/
        ↓
Human moves to Odoo_Invoices/Payment_Recieved/ when payment received
        ↓
Payment registered in Odoo → Odoo_Invoices/Done/
```

**Workflow:**
1. Add invoice request to `Needs_Action/` (or use `invoice` skill)
2. System creates draft in Odoo and writes approval to `Odoo_Invoices/Draft/`
3. Move to `Odoo_Invoices/Approved/` to post
4. Invoice moves to `Odoo_Invoices/Pending_Payment/` (waiting for client payment)
5. Move to `Odoo_Invoices/Payment_Recieved/` when client pays (or use `payment-received` skill)
6. System registers payment in Odoo and moves to `Odoo_Invoices/Done/`

**HITL Safety**: Invoices are NEVER auto-posted. Human must approve.

## Folders

```
AI_Employee_Vault/
├── Inbox/              # Gmail emails (raw)
├── whatsapp_inbox/     # WhatsApp messages (raw)
├── Needs_Action/       # Processing queue (invoice & bill requests go here)
├── Plans/              # Execution plans
├── Rejected/           # Discarded drafts
├── Done/               # Completed tasks
├── Account/            # Accounting
│   ├── send_invoices/  # (deprecated, use Needs_Action/)
│   ├── send_bills/     # (deprecated, use Needs_Action/)
│   ├── Odoo_Invoices/  # Invoice workflow
│   └── Odoo_Bills/     # Bill workflow
├── Social_Media/
│   ├── linkedin_post/      # LinkedIn post requirements
│   ├── x_post/             # X (Twitter) post requirements
│   ├── facebook_post/     # Facebook post requirements
│   ├── LinkedIn_Posts/
│   │   ├── Draft/
│   │   ├── Approved/
│   │   ├── Done/
│   │   └── SUMMARY.md     # Post summary
│   ├── X_Posts/
│   │   ├── Draft/
│   │   ├── Approved/
│   │   ├── Done/
│   │   └── SUMMARY.md     # Post summary
│   └── Facebook_Posts/
│       ├── Draft/
│       ├── Approved/
│       ├── Done/
│       └── SUMMARY.md     # Post summary
├── Gmail/
│   ├── Inbox/
│   ├── send_mails/
│   └── Gmail_Messages/
│       ├── Draft/
│       ├── Approved/
│       └── Done/
├── WhatsApp/
│   ├── whatsapp_inbox/
│   └── WhatsApp_Messages/
│       ├── Draft/
│       ├── Approved/
│       └── Done/
├── Odoo_Invoices/
│   ├── Draft/
│   ├── Approved/
│   ├── Pending_Payment/
│   ├── Payment_Recieved/
│   ├── Done/
│   └── Rejected/
├── Odoo_Bills/
│   ├── Draft/
│   ├── Approved/
│   └── Done/
├── Outbox_Queue/       # Failed outgoing tasks (auto-retry)
├── Human_Review_Queue/ # Uninterpretable messages
├── Quarantine/         # Corrupted/invalid files
├── Logs/               # Audit trail
├── Scheduled/          # Future tasks (supports repeat schedules)
├── Rates.md            # Service rates for invoice calculation
├── Templates/          # Response templates
├── Dashboard.md        # System status dashboard
├── Company_Handbook.md # Business rules
└── Business_Goals.md   # For daily posts

/tmp/
├── AI_Employee_Buffer/    # Storage fallback when vault locked
└── AI_Employee_Heartbeat/ # Process health monitoring
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point - runs all watchers |
| `orchestrator.py` | Process tasks, generate drafts |
| `gmail_watcher.py` | Gmail API integration |
| `whatsapp_watcher.py` | WhatsApp Web automation |
| `linkedin_post_watcher.py` | Monitors linkedin_post folder |
| `linkedin_poster.py` | Publishes approved posts to LinkedIn |
| `social_post_watcher.py` | Monitors x_post, facebook_post folders |
| `x_poster.py` | Publishes approved posts to X (Twitter) |
| `facebook_poster.py` | Publishes approved posts to Facebook |
| `scheduler_watcher.py` | Delayed task execution with repeat schedules (daily, weekly, custom) |
| `odoo_invoice_watcher.py` | Monitors Needs_Action for invoice requests, creates drafts |
| `odoo_invoice_poster.py` | Posts approved invoices to Odoo |
| `odoo_bill_watcher.py` | Monitors send_bills for bill requests, creates drafts |
| `odoo_bill_poster.py` | Posts approved bills to Odoo |
| `audit_report.py` | Generates weekly financial and operational audit reports |
| `retry_handler.py` | Exponential backoff retry logic |
| `graceful_degradation.py` | Error recovery protocols |
| `watchdog.py` | Process monitoring and auto-restart |
| `watchdog_runner.py` | Standalone watchdog process |
| `ecosystem.config.js` | PM2 process configuration |

## UI

```bash
cd fte-ui && npm run dev
# Open http://localhost:3000
```

The UI provides:
- Tabbed interface for Gmail, WhatsApp, LinkedIn, X, Facebook, Odoo
- File viewer with edit capability
- One-click approval workflow
- Real-time file sync
- **Odoo Invoice Management**: Create, review, approve, and post invoices directly from UI
- **Scheduled Task Creation** with repeat options:
  - **Once** - Single execution at specified time
  - **Daily** - Execute every day
  - **Weekly** - Execute on the same day each week
  - **Custom** - Execute every X days
  - Optional end date for repeat schedules

### Creating Scheduled Posts

1. Click "New Post" on any social platform tab (LinkedIn, X, Facebook)
2. Write your post requirements
3. Click "📅 Schedule" button
4. Set execution date and time
5. Choose repeat type (once, daily, weekly, custom)
6. Optionally set an end date for repeating tasks
7. Click "Schedule Task"

Tasks are saved to the `Scheduled/` folder and automatically moved to `Needs_Action/` when the scheduled time arrives.

## Skills

Claude Code skills for quick actions:

| Skill | Usage | Description |
|-------|-------|-------------|
| `email` | `send email to john@example.com about project update` | Create email request |
| `linkedin-post` | `create linkedin post about new product launch` | Create LinkedIn post |
| `x-post` | `create x post about big announcement` | Create X/Twitter post |
| `facebook-post` | `create facebook post about event` | Create Facebook post |
| `invoice` | `create invoice of $500 against ClientName` | Create invoice |
| `bill` | `create bill of $100 against AWS` | Create vendor bill |
| `payment-received` | `mark invoice as paid` | Move to Payment_Recieved |
| `approve` | `approve the linkedin draft` | Move draft to Approved |
| `reject` | `reject the facebook post` | Move draft to Rejected |
| `schedule` | `schedule linkedin post at tomorrow 9am` | Schedule task |
| `audit` | `generate audit report` or `audit of 13 april` | Generate audit report |

### Using Skills

1. Just tell Claude what you want (e.g., "create linkedin post about AI")
2. System creates the request file automatically
3. Draft appears in Draft folder within 3 minutes
4. Use `approve` skill to publish

### Audit Reports

Generate weekly financial and operational reports:

```bash
python audit_report.py --skill              # Last week
python audit_report.py --skill 2026-04-13    # Specific week
```

Reports include:
- **Financial Summary**: Revenue, expenses, net earnings (weekly & monthly)
- **Target Progress**: Monthly revenue vs target percentage
- **Completed Tasks**: Tasks completed during the week
- **Bottlenecks**: High pending queue, pending approvals, etc.
- **Upcoming Deadlines**: From Scheduled/ folder and Business_Goals.md projects
- **Pending Bills**: Bills awaiting approval in Odoo_Bills/Draft/

## Environment Variables

See `.env.example` for required configuration:

- **Gmail**: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`
- **WhatsApp**: `WHATSAPP_HEADLESS` (true/false)
- **LinkedIn**: `LINKEDIN_HEADLESS` (true/false)
- **X (Twitter)**: `X_HEADLESS` (true/false)
- **Facebook**: `FACEBOOK_HEADLESS` (true/false)
- **Scheduler**: `DAILY_POST_TIME` (default: 09:00)
- **Odoo**: `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD`, `ENABLE_ODOO_INVOICING`

## Scheduled Task Format

Tasks in the `Scheduled/` folder use YAML frontmatter:

```markdown
---
execute_at: 2026-04-10 09:00
repeat_type: daily
repeat_days: 3          # Only for 'custom' type
repeat_end: 2026-05-01  # Optional end date
---

# Your Task Content

Task description goes here...
```

**Supported `repeat_type` values:**
- `once` - Single execution (default)
- `daily` - Execute every day
- `weekly` - Execute every week on the same day
- `custom` - Execute every `repeat_days` days

## Browser Profiles

Login states are persisted in these directories:

| Platform | Profile Directory |
|----------|------------------|
| LinkedIn | `.linkedin_poster_profile/` |
| X (Twitter) | `.x_poster_profile/` |
| Facebook | `.facebook_poster_profile/` |
| WhatsApp | `.whatsapp_fte_profile/` |

To reset login: delete the profile directory and restart the system.

## Logging

All actions are logged with structured JSON in `AI_Employee_Vault/Logs/`:

```json
{
  "timestamp": "2026-04-06T12:00:00",
  "platform": "facebook",
  "actor": "claude_code",
  "action": "post_published",
  "approval_status": "approved"
}
```

## Error Recovery System

### Retry Logic

All API-calling functions use exponential backoff retry:
- **Base delay**: 1 second
- **Max delay**: 60 seconds
- **Max retries**: 5 attempts
- **Transient errors**: Network timeouts, rate limits (429), server errors (5xx)

### Graceful Degradation

| Failure Type | Behavior |
|--------------|----------|
| **Comms Down** | Tasks queued in `Outbox_Queue/`, auto-retry on restore |
| **Storage Locked** | Fallback to `/tmp/AI_Employee_Buffer/`, sync on restore |
| **Financial API** | Never auto-retry → `Needs_Action/` with human approval flag |
| **Uninterpretable** | Move to `Human_Review_Queue/` |
| **Corrupted Data** | Move to `Quarantine/`, alert on Dashboard |

### Financial Safety

Functions with these keywords are **never** auto-retried:
- `payment`, `bank`, `financial`, `stripe`, `paypal`, `plaid`
- `transfer`, `wallet`, `transaction`, `checkout`, `billing`

Instead, they're moved to `Needs_Action/` with `requires_human_approval: true`.

### Watchdog

The watchdog monitors process health via heartbeat files:
- **Check interval**: 60 seconds
- **Auto-restart**: Max 3 restarts in 5 minutes
- **Processes monitored**: Orchestrator, Gmail Watcher, WhatsApp Watcher, LinkedIn Watcher, Social Watcher

### Audit Trail

Recovery events are logged to `recovery_audit_*.jsonl`:

```json
{
  "timestamp": "2026-04-06T12:00:00",
  "action_type": "retry_attempt",
  "function": "send_email",
  "attempt": 2,
  "error_observed": "TimeoutError: Connection timed out",
  "delay_seconds": 2.5,
  "result": "retrying"
}
```

## License

MIT

## File Naming

Draft files are named meaningfully based on content:
- LinkedIn: `linkedin_topic-summary.md`
- X: `x_topic-summary.md`
- Facebook: `facebook_topic-summary.md`
- Email: `email_recipient_topic.md`

Each social media folder has a `SUMMARY.md` showing draft count and published posts.
