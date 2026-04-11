# Company Handbook

## Rules of Engagement

These rules govern how the Digital FTE system processes and responds to emails. All automated actions must comply with these guidelines.

---

### 1. Communication Standards

| Rule ID | Rule | Reason |
|---------|------|--------|
| COM-001 | Always maintain a professional tone | Represents company image |
| COM-002 | Use clear, concise language | Avoid misinterpretation |
| COM-003 | Include relevant context in responses | Complete communication |
| COM-004 | Proofread before marking draft ready | Quality assurance |

---

### 2. Security & Compliance

| Rule ID | Rule | Reason |
|---------|------|--------|
| SEC-001 | **Never share account passwords** | Security breach prevention |
| SEC-002 | **Flag any email involving payments over $100 for manual approval** | Financial control |
| SEC-003 | Do not include sensitive data in logs | Data protection |
| SEC-004 | Verify sender identity before acting on requests | Phishing prevention |
| SEC-005 | Never execute file downloads from unknown senders | Malware prevention |

---

### 3. Escalation Rules

| Rule ID | Condition | Action |
|---------|-----------|--------|
| ESC-001 | Payment requests > $100 | Flag for manual approval, do not auto-draft |
| ESC-002 | Emails marked URGENT | Prioritize, but still require approval |
| ESC-003 | Emails from unknown domains | Extra scrutiny, verify sender |
| ESC-004 | Requests for sensitive information | Flag for manual review |
| ESC-005 | Suspected phishing attempts | Move to quarantine, alert admin |

---

### 4. Response Templates

| Scenario | Template Location |
|----------|-------------------|
| Acknowledgment | `/Templates/acknowledgment.md` |
| Meeting Request | `/Templates/meeting.md` |
| Information Request | `/Templates/info_request.md` |
| Out of Office | `/Templates/out_of_office.md` |

---

### 5. Operating Hours

| Setting | Value |
|---------|-------|
| Active Hours | 09:00 - 18:00 (configurable) |
| Timezone | Set in `.env` |
| Weekend Processing | Disabled by default |

---

### 6. Approval Workflow

```
Email Received → Classified → Draft Generated → Human Review → Checkbox Ticked → Send
```

**Critical**: No email is sent automatically. The checkbox `- [ ] Send this email` must be manually checked by a human.

---

### 7. Audit & Logging

All actions are logged to `/Logs` in JSON format:
- Timestamp
- Action type
- Email ID
- Result
- Any flags raised

---

*Version: 1.0.0 | Last Updated: 2026-03-31*
