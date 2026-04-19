# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Digital FTE (Full-Time Employee) is an AI-powered automation system that acts as a virtual employee handling email, WhatsApp, social media (LinkedIn, X, Facebook), and Odoo invoicing. It runs as a single process managing multiple watchers and agents.

## Running the System

```bash
python main.py
```

The system starts all watchers and the orchestrator. It includes graceful degradation for 24/7 reliability.

## Architecture

### Watchers (Input)
- `gmail_watcher.py` - Monitors Gmail inbox for new emails
- `whatsapp_watcher.py` - Monitors WhatsApp messages
- `linkedin_post_watcher.py` - Monitors LinkedIn post requests
- `social_post_watcher.py` - Monitors X and Facebook post requests
- `scheduler_watcher.py` - Monitors scheduled tasks
- `send_mail_watcher.py` - Monitors outgoing email queue
- `odoo_invoice_watcher.py` - Monitors invoice requests (Gold Tier)
- `odoo_bill_watcher.py` - Monitors vendor bill requests (Gold Tier)

### Posters (Output)
- `linkedin_poster.py` - Posts to LinkedIn
- `x_poster.py` - Posts to X (Twitter)
- `facebook_poster.py` - Posts to Facebook
- `odoo_invoice_watcher.py` - Posts approved invoices to Odoo
- `odoo_bill_watcher.py` - Posts approved bills to Odoo

### Core
- `main.py` - Entry point, initializes all watchers and posters
- `orchestrator.py` - Coordinates workflow between components
- `base_watcher.py` - Base watcher interface
- `graceful_degradation.py` - Error recovery and system health

### UI
- `fte-ui/` - Next.js dashboard running on localhost:3000

## Key Files

- `main.py` - All watchers and posters are initialized here
- `orchestrator.py` - Contains the core workflow logic
- `Company_Handbook.md` - Rules governing all automated actions
- `Rates.md` - Pricing/contact rates
- `Business_Goals.md` - Business objectives

## Configuration

Copy `.env.example` to `.env` and configure. Key options:
- `ENABLE_WHATSAPP=true/false` - Enable WhatsApp
- `ENABLE_LINKEDIN=true/false` - Enable LinkedIn posting
- `ENABLE_X=true/false` - Enable X posting
- `ENABLE_FACEBOOK=true/false` - Enable Facebook posting
- `ENABLE_ODOO_INVOICING=true/false` - Enable Odoo invoice automation
- `ENABLE_ODOO_BILLS=true/false` - Enable Odoo bill automation

## Skills Available

When user requests match these actions, invoke the corresponding skill:
- "create linkedin post" → linkedin-post skill
- "create facebook post" → facebook-post skill
- "create x post" → x-post skill
- "send email" → email skill
- "create invoice" → invoice skill
- "create bill" → bill skill
- "payment received" → payment-received skill
- "schedule" → schedule-task skill
- "audit report" → audit skill