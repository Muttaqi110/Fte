---
name: schedule-task
description: Create a scheduled task that executes at a specific time. Use when user asks to "schedule", "schedule post", "schedule email", "post at", or "remind me to". Creates a task in Scheduled/ folder that moves to Needs_Action at the specified time.
---

# Schedule Skill

## Usage

```
schedule linkedin post about new product launch at tomorrow 9am
schedule x post about big announcement at 2026-04-15 14:00
schedule email to john at in 2 hours
schedule facebook post about event at next monday 10am
schedule daily post at 09:00
schedule weekly post every monday at 8am
schedule custom post every 3 days until 2026-05-01
```

## Schedule Format

```markdown
---
execute_at: 2026-04-14 09:00
repeat_type: once
---

# Task

Post about: new product launch
```

## Supported Time Formats

| Format | Example |
|--------|---------|
| Specific date/time | `2026-04-15 14:00` |
| Relative | `tomorrow 9am`, `next monday 10am` |
| From now | `in 2 hours`, `in 30 minutes` |

## Repeat Types

| Type | Description | Example |
|------|-------------|---------|
| `once` | Single execution (default) | `repeat_type: once` |
| `daily` | Every day | `repeat_type: daily` |
| `weekly` | Every week same day | `repeat_type: weekly` |
| `custom` | Every X days | `repeat_type: custom`, `repeat_days: 3` |

## Executing the Skill

When invoked:
1. Parse user request to extract:
   - Platform (linkedin, x, facebook, email)
   - Content/topic
   - Execute time (parse "at [time]", "in [duration]")
   - Repeat type (daily, weekly, custom)
2. Create scheduled task file in `AI_Employee_Vault/Scheduled/`
3. Confirm schedule to user

## Parsing Tips

- Extract platform from "linkedin post", "x post", "facebook post", "email to"
- Extract time from "at [time]", "tomorrow [time]", "in [duration]"
- Extract repeat from "daily", "weekly", "every X days"
- Everything else is the content/topic

## Scheduled Folder

Tasks go to: `AI_Employee_Vault/Scheduled/`

When scheduled time arrives:
- Moves to `AI_Employee_Vault/Needs_Action/`
- Orchestrator processes it
- Draft created in respective Draft folder

## Polling

- SchedulerWatcher checks every 60 seconds
- When time arrives, automatically moves to Needs_Action

Note: Make sure you generate .md file