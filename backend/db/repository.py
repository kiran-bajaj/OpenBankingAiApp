"""
Database read/write for transactions.

All public functions accept an open SQLAlchemy Session.
The caller is responsible for session lifecycle (open/close/rollback).

Upsert strategy:
  Check-then-insert/update — dialect-agnostic, works with SQLite and PostgreSQL.
  For a demo with <1,000 transactions this is perfectly adequate.
  Switching to PostgreSQL's native ON CONFLICT DO UPDATE is a small refactor if needed.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from db.models import TransactionRecord
from models.schema import Transaction

log = logging.getLogger(__name__)


# ── Key generation ─────────────────────────────────────────────────────────────

def make_dedupe_key(t: Transaction) -> str:
    """
    Stable, deterministic unique key for a transaction.
    Uses account_id + date + amount (4dp) + description.
    Repeated syncs with the same data produce the same key → idempotent.
    """
    raw = f"{t.account_id}|{t.date}|{t.amount:.4f}|{t.description}"
    return "dk_" + hashlib.sha256(raw.encode()).hexdigest()[:24]


# ── Write ──────────────────────────────────────────────────────────────────────

def upsert_transactions(
    txns: list[Transaction],
    db: Session,
    provider: str = "mock",
) -> Tuple[int, int]:
    """
    Insert or update transactions. Idempotent — safe to call repeatedly.
    Returns (inserted_count, updated_count).
    """
    if not txns:
        return 0, 0

    now = datetime.now(timezone.utc)
    inserted = 0
    updated = 0

    for t in txns:
        dk = make_dedupe_key(t)
        existing = db.get(TransactionRecord, dk)

        if existing is None:
            record = TransactionRecord(
                dedupe_key=dk,
                provider_transaction_id=None,
                account_id=t.account_id,
                account_name=t.account_name,
                currency=t.currency,
                date=t.date,
                description=t.description,
                merchant=t.merchant,
                amount=t.amount,
                debit_credit=t.debit_credit,
                category=t.category,
                recurring_flag=t.recurring_flag,
                provider=provider,
                raw_json=None,
                created_at=now,
                updated_at=now,
            )
            db.add(record)
            inserted += 1
        else:
            # Update fields that may change on re-sync (e.g. re-categorisation)
            existing.account_name = t.account_name
            existing.merchant = t.merchant
            existing.category = t.category
            existing.recurring_flag = t.recurring_flag
            existing.updated_at = now
            updated += 1

    db.commit()
    log.info(
        "Upsert complete: %d inserted, %d updated (total %d)",
        inserted, updated, len(txns),
    )
    return inserted, updated


# ── Read ───────────────────────────────────────────────────────────────────────

def get_transactions(
    db: Session,
    account_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 500,
) -> list[Transaction]:
    """Query DB and return normalized Transaction objects, newest-first."""
    q = db.query(TransactionRecord)
    if account_id:
        q = q.filter(TransactionRecord.account_id == account_id)
    if date_from:
        q = q.filter(TransactionRecord.date >= date_from)
    if date_to:
        q = q.filter(TransactionRecord.date <= date_to)
    q = q.order_by(TransactionRecord.date.desc()).limit(limit)
    return [_to_transaction(r) for r in q.all()]


def get_transaction_count(db: Session) -> int:
    return db.query(TransactionRecord).count()


def get_raw_records(
    db: Session,
    account_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Return raw DB rows as dicts for debug endpoints. Max 100 rows enforced."""
    q = db.query(TransactionRecord)
    if account_id:
        q = q.filter(TransactionRecord.account_id == account_id)
    if date_from:
        q = q.filter(TransactionRecord.date >= date_from)
    if date_to:
        q = q.filter(TransactionRecord.date <= date_to)
    q = q.order_by(TransactionRecord.date.desc()).limit(min(limit, 100))
    return [_record_to_dict(r) for r in q.all()]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_transaction(r: TransactionRecord) -> Transaction:
    return Transaction(
        account_id=r.account_id,
        account_name=r.account_name or "",
        currency=r.currency or "NZD",
        date=r.date,
        description=r.description or "",
        merchant=r.merchant or "",
        amount=r.amount,
        debit_credit=r.debit_credit,  # type: ignore[arg-type]
        category=r.category or "other",
        recurring_flag=bool(r.recurring_flag),
    )


def _record_to_dict(r: TransactionRecord) -> dict:
    return {
        "dedupe_key": r.dedupe_key,
        "account_id": r.account_id,
        "account_name": r.account_name,
        "currency": r.currency,
        "date": r.date,
        "description": r.description,
        "merchant": r.merchant,
        "amount": r.amount,
        "debit_credit": r.debit_credit,
        "category": r.category,
        "recurring_flag": r.recurring_flag,
        "provider": r.provider,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
