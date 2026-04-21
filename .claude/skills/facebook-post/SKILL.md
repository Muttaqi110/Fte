---
name: facebook-post
description: Create a Facebook post request. Use this skill when user asks to "create facebook post", "post to facebook", "make fb post", or "facebook post about [topic]". Creates a post request which is automatically processed by the SocialPostWatcher.
---

# Facebook Post Skill

## Usage

```
create facebook post about launching new ai product
```

or

```
facebook post about we are hiring a new developer
```

or

```
fb post about come visit our store
```

## Post Format

```markdown
---
platform: facebook
type: business_update
created: 2026-04-12
---

# Facebook Post Request

Post about: launching new ai product

## Details

- **Topic:** New AI product launch
- **Tone:** Community-focused, conversational
- **Include:** Engaging question or call to action
```

## Executing the Skill- IMPORTANT: Follow These Steps IN ORDER

**CRITICAL: Always start with Step 1. Never skip steps.**

When invoked:
1. Create post request file in `AI_Employee_Vault/Social_Media/facebook_post_request/`
2. Poll Draft folder every 15 seconds (max 12 attempts = 3 minutes)
3. Once draft appears, show it to user for approval
4. Instruct user to move to Approved/ to publish
If draft does not appear in 3 minutes, inform user to wait or to check any issue but never try to solve it yourself.

## Draft Detection

Check for new draft files by:
- Looking for files in `Social_Media/Facebook_Posts/Draft/`
- Polling every 15 seconds
- Stop polling after 12 attempts (3 minutes max)

## Polling Logic

```python
import time
from pathlib import Path

draft_path = Path("AI_Employee_Vault/Social_Media/Facebook_Posts/Draft")
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