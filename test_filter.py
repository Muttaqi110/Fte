def clean_content(draft_content):
    # EMERGENCY FILTER: If this is skill meta text, throw it away and generate fallback
    if "I need permission" in draft_content or "system will automatically" in draft_content or "Once created" in draft_content:
        return "FALLBACK POST"
    else:
        # Clean normal post content
        lines = draft_content.splitlines()
        cleaned = []
        skip = False

        for line in lines:
            l = line.strip().lower()

            # Skip wrapper lines
            if "here's the" in l or "completed post" in l or "x post" in l or "twitter post" in l or "i'll generate" in l or "generate the post" in l or "directly now" in l or "final facebook post" in l or "ready for publishing" in l:
                skip = True
                continue
            if skip and line.strip() == "":
                continue
            skip = False

            # Remove blockquote markers
            line = line.lstrip("> ").lstrip()

            # Remove markdown code block markers
            if line.strip().startswith("```"):
                continue

            cleaned.append(line)

        draft_content = "\n".join(cleaned).strip()
    return draft_content


test_input = """Here is the final Facebook post ready for publishing:

```
🤖 AI isn't just about robots or science fiction. It's about real people, real progress, and real lives getting better every single day.

Right now AI is:
✅ Helping doctors detect cancer earlier than human eyes ever could
✅ Translating in real time so a farmer in Kenya can sell crops to a buyer in Germany
✅ Optimizing power grids so we waste less energy and fight climate change
✅ Helping students with learning disabilities get personalised education that actually works
✅ Accurately predicting natural disasters so communities can evacuate safely

This isn't about replacing us. It's about giving every single one of us superpowers. It's about taking the boring, repetitive, dangerous work off our plates so we can focus on what humans do best: create, care, connect, and dream.

We're at the very beginning. The best is still ahead.

💬 What's one way AI has already made your life better? Drop it in the comments below!
```
"""

result = clean_content(test_input)
print("=== FILTERED RESULT ===")
print(repr(result))
print("\n=== ACTUAL OUTPUT ===")
print(result)
