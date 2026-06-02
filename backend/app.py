"""
Trilogy Care — Continuous Improvement Tool Backend
FastAPI application with SQLite persistence, reference ID generation,
data refresh engine, and evaluation gate.
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
import sqlite3
import json
import uuid
import os

app = FastAPI(
    title="TC Continuous Improvement API",
    version="1.0.0",
    description="Backend for Trilogy Care CI Register — persistent, auditable, multi-department"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.environ.get("CI_DB_PATH", "ci_register.db")


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ci_items (
        id TEXT PRIMARY KEY,
        ref_id TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        standards TEXT NOT NULL DEFAULT '[]',
        source TEXT NOT NULL,
        source_system TEXT DEFAULT 'manual',
        source_id TEXT,
        source_url TEXT,
        source_ref TEXT,
        status TEXT NOT NULL DEFAULT 'Pending Review',
        owner TEXT NOT NULL,
        department TEXT NOT NULL,
        date_identified DATE NOT NULL,
        target_date DATE,
        resolution TEXT,
        evidence_links TEXT DEFAULT '[]',
        risk_level TEXT DEFAULT 'Medium',
        linked_ci_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by TEXT,
        updated_by TEXT,
        is_deleted INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_name TEXT NOT NULL,
        user_dept TEXT,
        action TEXT NOT NULL,
        item_id TEXT,
        detail TEXT,
        before_state TEXT,
        after_state TEXT
    );

    CREATE TABLE IF NOT EXISTS evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT,
        linked_to TEXT,
        evaluated_by TEXT NOT NULL,
        evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (item_id) REFERENCES ci_items(id)
    );

    CREATE TABLE IF NOT EXISTS data_sources (
        id TEXT PRIMARY KEY,
        system_name TEXT NOT NULL,
        description TEXT,
        last_refreshed TIMESTAMP,
        refresh_status TEXT DEFAULT 'never',
        items_found INTEGER DEFAULT 0,
        items_imported INTEGER DEFAULT 0,
        config TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS refresh_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_system TEXT NOT NULL,
        source_id TEXT NOT NULL,
        source_url TEXT,
        title TEXT NOT NULL,
        description TEXT,
        suggested_standard TEXT,
        suggested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending',
        resolved_by TEXT,
        resolved_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS reference_map (
        internal_id TEXT NOT NULL,
        source_system TEXT NOT NULL,
        source_id TEXT NOT NULL,
        source_url TEXT,
        linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (internal_id, source_system, source_id)
    );

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        department TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'Contributor',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()

    # Seed data sources
    sources = [
        ("linear", "Linear", "Project management — CI delivery tracking"),
        ("confluence", "Confluence", "Process documentation and policies"),
        ("zoho_crm", "Zoho CRM", "CI Register (Solutions/Improvements module)"),
        ("email_m365", "M365 Email", "Commission correspondence — directives and commitments"),
        ("complaints", "Complaints", "Complaint-derived CI items"),
        ("sirs", "SIRS", "Serious Incident Response Scheme items"),
        ("manual", "Manual Entry", "Directly entered by staff"),
    ]
    for sid, name, desc in sources:
        conn.execute(
            "INSERT OR IGNORE INTO data_sources (id, system_name, description) VALUES (?, ?, ?)",
            (sid, name, desc)
        )
    conn.commit()
    conn.close()


# ============================================================
# REFERENCE ID GENERATOR
# ============================================================

def generate_ref_id(conn) -> str:
    year = datetime.now().year
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM ci_items WHERE ref_id LIKE ?",
        (f"TC-CI-{year}-%",)
    ).fetchone()
    seq = (row["cnt"] or 0) + 1
    return f"TC-CI-{year}-{seq:04d}"


# ============================================================
# MODELS
# ============================================================

class Status(str, Enum):
    PENDING = "Pending Review"
    IDENTIFIED = "Identified"
    IN_PROGRESS = "In Progress"
    IMPLEMENTED = "Implemented"
    VERIFIED = "Verified"
    CLOSED = "Closed"


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class Role(str, Enum):
    VIEWER = "Viewer"
    CONTRIBUTOR = "Contributor"
    MANAGER = "Manager"
    ADMIN = "Admin"


class CIItemCreate(BaseModel):
    title: str
    description: str
    standards: List[str]
    source: str
    owner: str
    department: str
    date_identified: date
    target_date: Optional[date] = None
    evidence_links: List[str] = []
    source_ref: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    created_by: Optional[str] = None


class CIItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    standards: Optional[List[str]] = None
    status: Optional[Status] = None
    owner: Optional[str] = None
    department: Optional[str] = None
    target_date: Optional[date] = None
    resolution: Optional[str] = None
    evidence_links: Optional[List[str]] = None
    risk_level: Optional[RiskLevel] = None
    updated_by: Optional[str] = None


class EvaluationDecision(BaseModel):
    decision: str  # "approve" | "reject" | "link"
    reason: Optional[str] = None
    linked_to: Optional[str] = None  # existing CI item ID to link to
    evaluated_by: str


# ============================================================
# ROUTES — ITEMS
# ============================================================

@app.get("/api/items")
def list_items(
    status: Optional[str] = None,
    standard: Optional[str] = None,
    department: Optional[str] = None,
    owner: Optional[str] = None,
    search: Optional[str] = None,
    source: Optional[str] = None,
):
    conn = get_db()
    query = "SELECT * FROM ci_items WHERE is_deleted = 0"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if department:
        query += " AND department = ?"
        params.append(department)
    if owner:
        query += " AND owner LIKE ?"
        params.append(f"%{owner}%")
    if source:
        query += " AND source = ?"
        params.append(source)
    if standard:
        query += " AND standards LIKE ?"
        params.append(f"%{standard}%")
    if search:
        query += " AND (title LIKE ? OR description LIKE ? OR ref_id LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/items/{item_id}")
def get_item(item_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM ci_items WHERE id = ? OR ref_id = ?", (item_id, item_id)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Item not found")
    item = dict(row)
    # Include linked references
    conn = get_db()
    refs = conn.execute("SELECT * FROM reference_map WHERE internal_id = ?", (item["id"],)).fetchall()
    item["references"] = [dict(r) for r in refs]
    conn.close()
    return item


@app.post("/api/items")
def create_item(item: CIItemCreate):
    conn = get_db()
    item_id = str(uuid.uuid4())
    ref_id = generate_ref_id(conn)

    conn.execute("""
        INSERT INTO ci_items (id, ref_id, title, description, standards, source, source_system,
            source_ref, status, owner, department, date_identified, target_date,
            evidence_links, risk_level, created_by, updated_by)
        VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, 'Pending Review', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item_id, ref_id, item.title, item.description,
        json.dumps(item.standards), item.source, item.source_ref,
        item.owner, item.department, item.date_identified.isoformat(),
        item.target_date.isoformat() if item.target_date else None,
        json.dumps(item.evidence_links), item.risk_level.value,
        item.created_by, item.created_by
    ))

    # Log the action
    conn.execute("""
        INSERT INTO activity_log (user_name, action, item_id, detail)
        VALUES (?, 'created', ?, ?)
    """, (item.created_by or "system", item_id, f"New CI item: {item.title}"))

    conn.commit()
    conn.close()
    return {"id": item_id, "ref_id": ref_id, "status": "Pending Review"}


@app.put("/api/items/{item_id}")
def update_item(item_id: str, update: CIItemUpdate):
    conn = get_db()
    existing = conn.execute("SELECT * FROM ci_items WHERE id = ? OR ref_id = ?", (item_id, item_id)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Item not found")

    before = dict(existing)
    fields = []
    params = []

    if update.title is not None:
        fields.append("title = ?"); params.append(update.title)
    if update.description is not None:
        fields.append("description = ?"); params.append(update.description)
    if update.standards is not None:
        fields.append("standards = ?"); params.append(json.dumps(update.standards))
    if update.status is not None:
        fields.append("status = ?"); params.append(update.status.value)
    if update.owner is not None:
        fields.append("owner = ?"); params.append(update.owner)
    if update.department is not None:
        fields.append("department = ?"); params.append(update.department)
    if update.target_date is not None:
        fields.append("target_date = ?"); params.append(update.target_date.isoformat())
    if update.resolution is not None:
        fields.append("resolution = ?"); params.append(update.resolution)
    if update.evidence_links is not None:
        fields.append("evidence_links = ?"); params.append(json.dumps(update.evidence_links))
    if update.risk_level is not None:
        fields.append("risk_level = ?"); params.append(update.risk_level.value)
    if update.updated_by:
        fields.append("updated_by = ?"); params.append(update.updated_by)

    fields.append("updated_at = ?"); params.append(datetime.now().isoformat())
    params.append(existing["id"])

    conn.execute(f"UPDATE ci_items SET {', '.join(fields)} WHERE id = ?", params)
    conn.execute("""
        INSERT INTO activity_log (user_name, action, item_id, detail, before_state)
        VALUES (?, 'updated', ?, ?, ?)
    """, (update.updated_by or "system", existing["id"], f"Updated: {', '.join(f.split(' =')[0] for f in fields[:-1])}", json.dumps(before)))

    conn.commit()
    conn.close()
    return {"status": "updated"}


# ============================================================
# ROUTES — EVALUATION GATE
# ============================================================

@app.get("/api/pending")
def list_pending():
    conn = get_db()
    rows = conn.execute("SELECT * FROM ci_items WHERE status = 'Pending Review' AND is_deleted = 0 ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/pending/{item_id}/evaluate")
def evaluate_item(item_id: str, eval: EvaluationDecision):
    conn = get_db()
    item = conn.execute("SELECT * FROM ci_items WHERE id = ? OR ref_id = ?", (item_id, item_id)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(404, "Item not found")

    if eval.decision == "approve":
        conn.execute("UPDATE ci_items SET status = 'Identified', updated_at = ?, updated_by = ? WHERE id = ?",
                     (datetime.now().isoformat(), eval.evaluated_by, item["id"]))
    elif eval.decision == "reject":
        conn.execute("UPDATE ci_items SET status = 'Closed', is_deleted = 1, updated_at = ?, updated_by = ? WHERE id = ?",
                     (datetime.now().isoformat(), eval.evaluated_by, item["id"]))
    elif eval.decision == "link":
        if not eval.linked_to:
            conn.close()
            raise HTTPException(400, "linked_to required for link decision")
        conn.execute("UPDATE ci_items SET linked_ci_id = ?, status = 'Closed', updated_at = ?, updated_by = ? WHERE id = ?",
                     (eval.linked_to, datetime.now().isoformat(), eval.evaluated_by, item["id"]))
        # Add as evidence to the linked item
        linked = conn.execute("SELECT evidence_links FROM ci_items WHERE id = ? OR ref_id = ?", (eval.linked_to, eval.linked_to)).fetchone()
        if linked:
            links = json.loads(linked["evidence_links"] or "[]")
            links.append(f"Linked from {item['ref_id']}: {item['title']}")
            conn.execute("UPDATE ci_items SET evidence_links = ? WHERE id = ? OR ref_id = ?",
                         (json.dumps(links), eval.linked_to, eval.linked_to))

    # Record evaluation
    conn.execute("""
        INSERT INTO evaluations (item_id, decision, reason, linked_to, evaluated_by)
        VALUES (?, ?, ?, ?, ?)
    """, (item["id"], eval.decision, eval.reason, eval.linked_to, eval.evaluated_by))

    conn.execute("""
        INSERT INTO activity_log (user_name, action, item_id, detail)
        VALUES (?, ?, ?, ?)
    """, (eval.evaluated_by, f"evaluated_{eval.decision}", item["id"],
          f"{eval.decision}: {eval.reason or ''}" + (f" → linked to {eval.linked_to}" if eval.linked_to else "")))

    conn.commit()
    conn.close()
    return {"status": eval.decision, "item_id": item["id"]}


# ============================================================
# ROUTES — STATS & DASHBOARD
# ============================================================

@app.get("/api/stats")
def get_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM ci_items WHERE is_deleted = 0").fetchone()["c"]
    by_status = conn.execute("SELECT status, COUNT(*) as c FROM ci_items WHERE is_deleted = 0 GROUP BY status").fetchall()
    by_dept = conn.execute("SELECT department, COUNT(*) as c FROM ci_items WHERE is_deleted = 0 GROUP BY department").fetchall()
    by_source = conn.execute("SELECT source, COUNT(*) as c FROM ci_items WHERE is_deleted = 0 GROUP BY source").fetchall()
    with_evidence = conn.execute("SELECT COUNT(*) as c FROM ci_items WHERE is_deleted = 0 AND evidence_links != '[]' AND evidence_links IS NOT NULL").fetchone()["c"]
    pending = conn.execute("SELECT COUNT(*) as c FROM ci_items WHERE status = 'Pending Review' AND is_deleted = 0").fetchone()["c"]
    conn.close()

    return {
        "total": total,
        "pending": pending,
        "with_evidence": with_evidence,
        "evidence_pct": round(with_evidence / total * 100) if total else 0,
        "by_status": {r["status"]: r["c"] for r in by_status},
        "by_department": {r["department"]: r["c"] for r in by_dept},
        "by_source": {r["source"]: r["c"] for r in by_source},
    }


# ============================================================
# ROUTES — ACTIVITY LOG
# ============================================================

@app.get("/api/log")
def get_log(limit: int = 50, offset: int = 0):
    conn = get_db()
    rows = conn.execute("SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# ROUTES — DATA SOURCES & REFRESH
# ============================================================

@app.get("/api/sources")
def list_sources():
    conn = get_db()
    rows = conn.execute("SELECT * FROM data_sources ORDER BY system_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/refresh/{source_id}")
def trigger_refresh(source_id: str):
    """Trigger a refresh from a specific data source. Returns suggestions for review."""
    # This will be implemented with MCP tool calls
    # For now, return the interface
    return {
        "status": "refresh_queued",
        "source": source_id,
        "message": f"Refresh from {source_id} queued. Check /api/refresh/suggestions for results."
    }


@app.get("/api/refresh/suggestions")
def list_suggestions():
    conn = get_db()
    rows = conn.execute("SELECT * FROM refresh_suggestions WHERE status = 'pending' ORDER BY suggested_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# ROUTES — IMPORT / EXPORT
# ============================================================

@app.get("/api/export/csv")
def export_csv():
    conn = get_db()
    rows = conn.execute("SELECT * FROM ci_items WHERE is_deleted = 0 ORDER BY ref_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup():
    init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
