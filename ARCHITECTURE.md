# CI Tool — Architecture & Design Document

## Overview

Standalone Continuous Improvement tool for Trilogy Care. Enterprise-grade, multi-department, persistent, audit-ready.

**Lifespan:** Permanent and ongoing — every department adds CI items over time. This is not a one-off audit tool, it's the living CI system.

## Core Principles

1. **Own source of truth** — tool generates its own reference IDs, maintains its own state
2. **Persistent memory** — data survives restarts, accessible across departments
3. **Human evaluation gate** — new items go through gatekeeper before accepted
4. **Data lineage** — every record traces back to its source (CRM, Linear, Confluence, email, manual)
5. **Live refresh** — can pull updates from connected systems on demand or schedule
6. **Multi-department access** — role-based, any area can submit and view

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (GitHub Pages)                │
│  Single-page app — dashboard, register, forms, search   │
│  localStorage for offline draft persistence             │
└────────────────────────────┬────────────────────────────┘
                             │ REST API
┌────────────────────────────▼────────────────────────────┐
│              PYTHON BACKEND (FastAPI)                     │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ API      │  │ Refresh  │  │ Reference ID         │  │
│  │ Routes   │  │ Engine   │  │ Generator            │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Auth &   │  │ Audit    │  │ Data Migration       │  │
│  │ Roles    │  │ Logger   │  │ Engine               │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│                                                          │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│              DATA LAYER (SQLite / PostgreSQL)             │
│                                                          │
│  ci_items          — the register                        │
│  activity_log      — full audit trail                    │
│  refresh_log       — when data was synced from where     │
│  users             — department, role, permissions       │
│  evaluations       — gatekeeper review decisions         │
│  data_sources      — registry of connected systems       │
│  reference_map     — source_id ↔ internal_id linkage    │
└─────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│           EXTERNAL DATA SOURCES (MCP / API)              │
│                                                          │
│  Linear ──────── issues, projects, status                │
│  Confluence ──── process docs, policies                  │
│  M365 Email ──── Commission correspondence               │
│  Zoho CRM ────── CI register (via CSV import)            │
│  Complaints ──── complaint-sourced items                 │
│  Qdrant ──────── semantic matching to standards          │
└─────────────────────────────────────────────────────────┘
```

---

## Reference ID System

Format: `TC-CI-YYYY-NNNN`

- `TC-CI` — prefix (Trilogy Care Continuous Improvement)
- `YYYY` — year identified
- `NNNN` — sequential number within that year

Example: `TC-CI-2025-0001`, `TC-CI-2026-0042`

Generated server-side only. Never duplicated. Once assigned, permanent.

---

## Data Source Tracking (Lineage)

Every CI item records WHERE it came from:

```python
class DataSource:
    source_system: str      # "linear" | "confluence" | "zoho_crm" | "email" | "manual" | "complaint" | "sirs"
    source_id: str          # External ID (e.g. "OPE-112", "SOL-00142", "CT-202604-896")
    source_url: str         # Direct link back to source
    imported_at: datetime   # When it was pulled in
    last_synced: datetime   # Last time we checked for updates
    sync_status: str        # "current" | "stale" | "conflict" | "deleted_upstream"
```

---

## Refresh / Data Migration Engine

### How it works:

1. **On-demand refresh** — user clicks "Refresh" → backend hits MCP tools for each connected source
2. **Scheduled refresh** — cron job runs daily, pulls updates from Linear/Confluence/etc.
3. **Diff detection** — compares incoming data against stored records:
   - New items not in our register → flagged as "Suggested Import" (goes through evaluation gate)
   - Existing items with changed status → auto-updated (status, assignee, dates)
   - Deleted upstream → flagged as "Source Removed" for human review

### Data Migration Map:

```
Source System        → What We Pull           → Maps To CI Field
─────────────────────────────────────────────────────────────────
Linear               → issue title            → title
                     → issue description      → desc
                     → issue status           → status (mapped)
                     → issue assignee         → owner
                     → project name           → category
                     → labels                 → standards (if tagged)
                     → issue URL              → evidence_links

Confluence           → page title             → evidence_links (as supporting doc)
                     → page URL               → evidence_links
                     → last modified          → (freshness check)

Zoho CRM (CSV)       → Solution_Title         → title
                     → Question               → desc
                     → Answer                 → resolution
                     → Status                 → status (mapped)
                     → Owner                  → owner
                     → Tag                    → standards (parsed)
                     → Created_Time           → date_identified

Commission Email     → directive text         → desc
                     → reference number       → source_ref
                     → deadline               → target_date
                     → complaint ref          → linked_complaint

Complaints (MCP)     → complaint category     → source context
                     → complaint ID           → source_ref
                     → provider/issue         → desc context
```

---

## Evaluation Gate (Human Review)

### Flow:
```
New Item Arrives (manual entry OR system import)
        │
        ▼
  ┌─────────────┐
  │  PENDING    │ ← Sits here until a gatekeeper reviews
  └──────┬──────┘
         │
    Gatekeeper reviews
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌────────┐
│APPROVED│ │REJECTED│
│→ Linked│ │→ Reason│
│  to CI │ │  logged│
└────────┘ └────────┘
```

### Key: Link to existing CI, not always new entry

When a gatekeeper reviews a pending item, they can:
- **Approve as new** — becomes its own CI entry
- **Link to existing** — attach as evidence/sub-action to an existing CI item (not a duplicate)
- **Reject** — with reason (logged in audit trail)
- **Merge** — combine with another pending item

---

## User Roles & Permissions

| Role | Can View | Can Submit | Can Approve | Can Admin |
|------|----------|-----------|-------------|-----------|
| Viewer | ✅ | ❌ | ❌ | ❌ |
| Contributor | ✅ | ✅ | ❌ | ❌ |
| Manager | ✅ | ✅ | ✅ (own dept) | ❌ |
| Admin | ✅ | ✅ | ✅ (all) | ✅ |

Department-scoped: Managers can only approve items from their department.

---

## Persistent Memory Model

Data lives in the Python backend database. Frontend syncs via API.

- **Primary store:** SQLite (single file, easy backup) or PostgreSQL (if scaling needed)
- **Offline fallback:** Frontend localStorage caches last-loaded state for read-only access
- **Backup:** Daily automated export to CSV stored in workspace
- **Recovery:** Import from any previous export

Every mutation (create, update, approve, reject, import, refresh) is logged to `activity_log` with:
- Timestamp
- User
- Action type
- Before/after state
- Source (manual / system / import)

---

## Tooltip / Help System

Every section and field gets contextual help:

- **Inline tooltips** — hover any field label for a one-line explanation
- **Help panel** — slide-out panel with section-by-section guide
- **Process map** — embedded flowchart showing "how CI works at TC"
- **First-run tour** — guided walkthrough for new users

---

## API Endpoints (Python FastAPI)

```
GET    /api/items              — list all CI items (with filters)
GET    /api/items/{id}         — get single item
POST   /api/items              — create new item (goes to pending)
PUT    /api/items/{id}         — update item
DELETE /api/items/{id}         — soft-delete (audit logged)

GET    /api/pending            — items awaiting review
POST   /api/pending/{id}/approve  — approve with optional link-to
POST   /api/pending/{id}/reject   — reject with reason
POST   /api/pending/{id}/link     — link to existing CI item

POST   /api/refresh            — trigger data refresh from all sources
GET    /api/refresh/status     — last refresh time + results
GET    /api/refresh/suggestions — items found but not yet imported

GET    /api/log                — activity log (paginated)
GET    /api/stats              — dashboard KPIs
GET    /api/standards          — items grouped by standard

POST   /api/import/csv         — bulk import from CSV
GET    /api/export/csv         — full register export

GET    /api/users              — list users
POST   /api/auth/login         — authenticate (department-based or SSO)
```

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python FastAPI | Stakeholder requirement, fast, async, auto-docs |
| Database | SQLite (→ PostgreSQL later) | Zero config, single file, portable |
| Frontend | Vanilla HTML/CSS/JS | Same as AECT, no build step, GitHub Pages |
| Hosting (backend) | TC container / EC2 | Alongside existing TC services |
| Hosting (frontend) | GitHub Pages | Free, fast, version-controlled |
| Auth | Simple token + department | Can upgrade to SSO later |

---

## Lifespan & Growth

This tool is permanent. It will grow with:

- Every department adding CI items continuously
- New data sources connecting over time (Portal CI module, new MCP tools)
- Increasing automation (auto-detect improvements from system changes)
- Eventually feeding back INTO Zoho CRM / Portal when those modules are ready

The design accommodates this by:
- Flexible schema (JSON fields for extension)
- Source tracking (any new system gets a `data_source` entry)
- Role expansion (new departments just get added)
- API-first (anything can integrate with it)
