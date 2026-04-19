---
name: linkedin-post
description: Create a LinkedIn post request. Use this skill when user asks to "create linkedin post", "post to linkedin", "make linkedin post", or "linkedin post about [topic]". Creates a post request which is automatically processed by the LinkedInPostWatcher.
---

# LinkedIn Post Skill

## Usage

```
create linkedin post about launching new ai product that helps small businesses
```

or

```
linkedin post about we are hiring a new developer join our team
```

## Post Format

```markdown
---
platform: linkedin
type: business_update
created: 2026-04-12
---

# LinkedIn Post Request

Post about: launching new ai product that helps small businesses

## Details

- **Topic:** New AI product launch
- **Target audience:** Small business owners
- **Tone:** Professional, value-driven
- **Include:** Brief value proposition, call to action
```


## Executing the Skill - IMPORTANT: Follow These Steps IN ORDER

**CRITICAL: Always start with Step 1. Never skip steps.**

### Step 1: Create the Request File
1. Create post request file in `AI_Employee_Vault/Social_Media/linkedin_post_request/`
2. The file must include:
   - platform: linkedin
   - type: (opinion_thought_leadership, business_update, etc.)
   - created: today's date
   - Post about: [the topic]
   - Details section with Target audience, Tone, what to Include

### Step 2: Wait for Draft
The LinkedInPostWatcher will generate a draft in the Draft folder. Poll the Draft folder every 15 seconds (max 12 attempts = 3 minutes).

### Step 3: Show Draft to User
Once the draft appears in `Social_Media/LinkedIn_Posts/Draft/`, read and show it to the user for approval.

### Step 4: Instructions
Instruct the user to move the file to `Approved/` folder to publish.

## Draft Detection

Check for new draft files by:
- Looking for files in `Social_Media/LinkedIn_Posts/Draft/`
- Polling every 15 seconds
- Stop polling after 12 attempts (3 minutes max)

## Polling Logic

```python
import time
from pathlib import Path

draft_path = Path("AI_Employee_Vault/Social_Media/LinkedIn_Posts/Draft")
max_attempts = 12  # 3 minutes max (12 * 15s = 180s)
attempt = 0

while attempt < max_attempts:
    draft_files = list(draft_path.glob("*.md"))
    if draft_files:
        # Show the newest draft
        latest = max(draft_files, key=lambda f: f.stat().st_mtime)
        print(latest.read_text())
        break
    time.sleep(15)
    attempt += 1
```

Note: Make sure you generate .md file