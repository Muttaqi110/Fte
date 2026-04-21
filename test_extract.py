import re

def test_extract(md_content):
    match = re.search(
        r"## Post Content\s*\n+(.*?)(?=\n---|\n## |\Z)",
        md_content,
        re.DOTALL
    )
    if match:
        content = match.group(1).strip()
        if content.startswith("**") and content.endswith("**"):
            content = content[2:-2].strip()
        return content
    return None

# Test with the actual draft content that was created
test_content = """# X (Twitter) Post Draft

## Status: DRAFT - AWAITING APPROVAL

---

## Post Content

**AI doesn't replace humans—it amplifies us.**

The best results come from human creativity + AI capability working together.

Your edge isn't fighting AI. It's collaborating with it.

How are you using AI as your partner? 🤝

#AI #FutureOfWork #HumanAI

---
**Platform:** X (Twitter)
**Generated:** 2026-04-21T11:17:34.892634*

---

## Approval Instructions
"""

result = test_extract(test_content)
print("EXTRACTED CONTENT:")
print("-------------------")
print(repr(result))
print("-------------------")
