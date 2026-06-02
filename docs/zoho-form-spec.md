# Zoho Form Spec — Continuous Improvement Intake

**Purpose:** Internal-only form for TC staff to submit new CI items. Replaces direct CRM entry.  
**Created by:** Rafael + Les  
**Module:** Solutions (labelled "Improvements" in TC Zoho)  
**Access:** All TC staff (internal only, not public)

---

## Form Title

**"Submit a Continuous Improvement Item"**

Subtitle: *Identified something we can do better? Log it here. All submissions are reviewed before being added to the register.*

---

## Fields

| # | Field Name | Type | Required | Options / Notes |
|---|-----------|------|----------|----------------|
| 1 | **Improvement Title** | Short text | ✅ Yes | Max 150 chars. "What's the improvement in one line?" |
| 2 | **Description** | Long text | ✅ Yes | "Describe the issue or opportunity. What happened? What needs to change?" |
| 3 | **Source** | Dropdown | ✅ Yes | Self-Identified · GAP Assessment/Audit · CQCC · Consumer Feedback · SIRS · Commission Complaint · Commission Directive · Desktop Contact |
| 4 | **Department** | Dropdown | ✅ Yes | Operations · Clinical · Quality · Compliance · Digital · Finance · HR/L&D · Marketing · Care Management |
| 5 | **Owner** | Short text | ✅ Yes | "Who is accountable for this?" (free text — person's name) |
| 6 | **Date Identified** | Date | ✅ Yes | Default: today |
| 7 | **Source Reference** | Short text | No | "If linked to a complaint, incident, or email — put the reference here (e.g. CT-202604-896)" |
| 8 | **Priority** | Dropdown | No | Low · Medium · High · Critical |
| 9 | **Desired Outcome** | Long text | No | "What does 'done' look like?" |
| 10 | **Your Name** | Short text | ✅ Yes | Auto-fill if possible (Zoho user) |
| 11 | **Your Email** | Email | ✅ Yes | Auto-fill if possible |

---

## What's NOT on the form (added later during review)

These get added by you/Les during the clean-up step:

- Reference ID (auto-generated: TC-CI-YYYY-NNNN)
- Quality Standard mapping (1.1, 2.3, etc.)
- Status (starts as "Identified" after approval)
- Evidence links (Linear, Confluence, documents)
- Resolution / what was done
- Completion date

---

## Form Settings

| Setting | Value |
|---------|-------|
| Visibility | Internal only (TC staff) |
| Confirmation message | "Thanks — your submission has been received and will be reviewed by the Quality team." |
| Notification email | Send to: frand@trilogycare.com.au, rafaelf@trilogycare.com.au |
| Duplicate check | None (duplicates caught during review) |
| Record owner | Default to Fran (can be reassigned) |

---

## Where to put the form link

- Zoho CRM sidebar (quick access)
- Confluence — link on the CI policy page (CO-004)
- Teams — pin in the Quality channel
- Portal (future) — when the CI module is built

---

## Workflow after submission

```
Staff submits form
       ↓
Notification sent to Fran + Raf
       ↓
Review within 5 business days:
  → Approve (add standards, assign owner, import to tool)
  → Link to existing CI item (not a duplicate)  
  → Reject (with reason — logged)
       ↓
Approved items get TC-CI reference ID
       ↓
Live in CI Tool register
```

---

## Notes for Les

- This replaces direct entry into the CRM Solutions module
- Once the form is live, lock the CRM module from new records (read-only for everyone except admin)
- The form should write to the existing Solutions module in Zoho OR to a standalone sheet — either works, we'll export and import either way
- Keep it simple — staff need to fill this out in under 2 minutes
- No conditional logic needed for v1
