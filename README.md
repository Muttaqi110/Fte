# Digital FTE System

AI-powered automation with human-in-the-loop approval for emails, WhatsApp, and LinkedIn posts.

## Run

```bash
python main.py
```

Single command runs all watchers and the orchestrator.

## Features

- **Gmail**: Polls unread important emails every 2 minutes
- **WhatsApp**: Monitors for business messages (requires Playwright)
- **LinkedIn Posts**: Creates and publishes LinkedIn posts with approval workflow
- **Scheduler**: Executes scheduled tasks
- **Claude CLI**: Generates contextual responses and content
- **HITL**: All drafts require human approval

## Setup

```bash
# Install dependencies
pip install aiohttp python-dotenv aiofiles cryptography requests playwright
playwright install chromium

# Configure
cp .env.example .env
python get_refresh_token.py  # For Gmail OAuth

# Run
python main.py
```

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

### LinkedIn Posts
```
Create requirement in linkedin_post/
        ↓
Watcher moves to Needs_Action/
        ↓
Claude creates plan → Plans/
        ↓
Claude creates draft → LinkedIn_Posts/Draft/
        ↓
Human moves to Approved/
        ↓
Poster publishes to LinkedIn → LinkedIn_Posts/Done/
```

## Folders

```
AI_Employee_Vault/
├── Inbox/              # Gmail emails (raw)
├── whatsapp_inbox/     # WhatsApp messages (raw)
├── linkedin_post/      # LinkedIn post requirements
├── Needs_Action/       # Processing queue
├── Plans/              # Execution plans
├── Rejected/           # Discarded drafts
├── Done/               # Completed tasks
├── Gmail_Messages/
│   ├── Draft/          # Email drafts
│   ├── Approved/       # Ready to send
│   └── Done/           # Sent emails
├── WhatsApp_Messages/
│   ├── Draft/          # WhatsApp drafts
│   ├── Approved/       # Ready to send
│   └── Done/           # Sent messages
├── LinkedIn_Posts/
│   ├── Draft/          # Post drafts
│   ├── Approved/       # Ready to publish
│   └── Done/           # Published posts
├── Logs/               # Audit trail
├── Scheduled/          # Future tasks
├── Templates/          # Response templates
├── Company_Handbook.md # Business rules
└── Business_Goals.md   # For daily posts
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
| `scheduler_watcher.py` | Delayed task execution |

## UI

```bash
cd fte-ui && npm run dev
# Open http://localhost:3000
```

## Environment Variables

See `.env.example` for required configuration:

- **Gmail**: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`
- **WhatsApp**: `WHATSAPP_HEADLESS` (true/false)
- **LinkedIn**: `LINKEDIN_HEADLESS` (true/false)
- **Scheduler**: `DAILY_POST_TIME` (default: 09:00)

## License

MIT
