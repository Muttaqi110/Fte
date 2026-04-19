---
name: x-post
description: Create an X (Twitter) post request. Use this skill when user asks to "create x post", "post to x", "make twitter post", or "x post about [topic]". Creates a post request which is automatically processed by the SocialPostWatcher.
---

# X (Twitter) Post Skill

## Usage

```
create x post about launching new ai product
```

or

```
x post about we are hiring a new developer
```

or

```
twitter post about big announcement coming soon
```

## Post Format

```markdown
---
platform: x
type: business_update
created: 2026-04-12
---

# X Post Request

Post about: launching new ai product

## Details

- **Topic:** New AI product launch
- **Tone:** Punchy, professional
- **Max:** 280 characters
- **Include:** Hashtags, call to action
```

## Executing the Skill- IMPORTANT: Follow These Steps IN ORDER

**CRITICAL: Always start with Step 1. Never skip steps.**

When invoked:
1. Create post request file in `AI_Employee_Vault/Social_Media/x_post_request/`
2. Poll Draft folder every 15 seconds (max 12 attempts = 3 minutes)
3. Once draft appears, show it to user for approval
4. Instruct user to move to Approved/ to publish

## Draft Detection

Check for new draft files by:
- Looking for files in `Social_Media/X_Posts/Draft/`
- Polling every 15 seconds
- Stop polling after 12 attempts (3 minutes max)

## Polling Logic

```python
import time
from pathlib import Path

draft_path = Path("AI_Employee_Vault/Social_Media/X_Posts/Draft")
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