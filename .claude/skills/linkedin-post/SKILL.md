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


## Executing the Skill

When invoked:
1. Create post request file in `AI_Employee_Vault/Social_Media/linkedin_post/`
2. Poll Draft folder every 15 seconds (max 12 attempts = 3 minutes)
3. Once draft appears, show it to user for approval
4. Instruct user to move to Approved/ to publish

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