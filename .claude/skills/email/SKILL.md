---
name: email
description: Create and send emails. Use this skill when user asks to "send email", "email to", "compose email", or "mail to [recipient] about [subject]". Creates email request which is automatically processed by the SendMailWatcher and Orchestrator.
---

# Email Skill

## Usage

```
send email to john@example.com about project update saying please review the documents by friday
email to client@company.com about invoice attached please confirm receipt
mail to team about meeting rescheduled to 3pm tomorrow
```

## Email Format

The skill will create a file in `AI_Employee_Vault/Gmail/send_mails/` with the following format:

```markdown
to: john@example.com
subject: Project Update
body: Please review the documents by Friday.
```

## Executing the Skill

When invoked:
1. Parse the user request to extract recipient, subject, and body
2. Create email file in `AI_Employee_Vault/Gmail/send_mails/`
3. Poll `AI_Employee_Vault/Gmail/Gmail_Messages/Draft/` every 15 seconds
4. Once a draft file appears (max 3 minutes), show it to the user
5. Instruct user to move to `Approved/` to send

## Draft Detection

Check for new draft files by:
- Looking for files matching pattern `*mail_draft*.md` or `*_mail_draft*.md`
- Comparing current files against previous scan
- Stop polling after 12 attempts (3 minutes max)

## Response Format

After creating the email, respond to user with:

```
📧 Email Request Created

To: [recipient]
Subject: [subject]

Waiting for draft to be generated...
```

Then start polling every 15s. Once draft appears:

```
✅ Draft Ready!

File: [draft_filename]

---

[Draft content here]

---

To send: Move this file to Gmail/Gmail_Messages/Approved/
```

## Polling Logic

```python
import time
from pathlib import Path

draft_path = Path("AI_Employee_Vault/Gmail/Gmail_Messages/Draft")
max_attempts = 12  # 3 minutes max (12 * 15s = 180s)
attempt = 0

while attempt < max_attempts:
    draft_files = list(draft_path.glob("*email*.md"))
    if draft_files:
        # Show the newest draft
        latest = max(draft_files, key=lambda f: f.stat().st_mtime)
        print(latest.read_text())
        break
    time.sleep(15)
    attempt += 1
```
If draft does not appear in 3 minutes, inform user to wait or to check any issue but never try to solve it yourself.

## Parsing Tips

- Extract email address from "to X" or "email to X"
- Extract subject from "about X" or "subject: X"
- Everything else is the body
- If no subject provided, create a reasonable one based on body content
- File name format: `to_[recipient_name]_[timestamp].md`