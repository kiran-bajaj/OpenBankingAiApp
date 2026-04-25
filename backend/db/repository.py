"""
Database read/write for transactions.

All public functions accept an open SQLAlchemy Session.
The caller is responsible for session lifecycle (open/close/rollback).

Upsert strategy (dialect-aware):
  PostgreSQL: native INSERT ... ON CONFLICT DO UPDATE — single bulk round-trip.
  SQLite:     check-then-insert fallback — correct but N round-trips.

Switching between dialects is transparent to callers.
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

    Priority:
      1. provider_transaction_id (e.g. Akahu _id) — use directly; avoids
         hash collisions and survives description/amount normalisation changes.
      2. hash(account_id | date | amount | description) — for mock data and
         any provider that does not supply a stable transaction ID.

    Repeated syncs with the same data produce the same key → idempotent.
    """
    if t.provider_transaction_id:
        # Sanitise and prefix to avoid namespace collisions between providers
        safe = t.provider_transaction_id.replace("|", "_")[:52]
        return f"pt_{safe}"
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

    Uses PostgreSQL's native ON CONFLICT DO UPDATE for efficiency.
    Falls back to row-by-row check-then-insert for SQLite.

    Returns (inserted_count, updated_count).
    """
    if not txns:
        return 0, 0

    from db.database import engine
    if engine.dialect.name == "postgresql":
        return _upsert_pg(txns, db, provider)
    return _upsert_sqlite(txns, db, provider)


def _upsert_pg(
    txns: list[Transaction],
    db: Session,
    provider: str,
) -> Tuple[int, int]:
    """
    PostgreSQL-native bulk upsert.

    One pre-fetch query to count existing keys, then a single INSERT ...
    ON CONFLICT DO UPDATE for the whole batch — efficient and race-safe.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = datetime.now(timezone.utc)

    # Build dedupe_key → Transaction mapping (deduplicates within the batch)
    dks: dict[str, Transaction] = {make_dedupe_key(t): t for t in txns}

    # One query to find which keys already exist → compute insert/update counts
    existing_keys: set[str] = {
        row.dedupe_key
        for row in db.query(TransactionRecord.dedupe_key)
        .filter(TransactionRecord.dedupe_key.in_(list(dks.keys())))
        .all()
    }

    records = [
        {
            "dedupe_key": dk,
            "provider_transaction_id": t.provider_transaction_id,
            "account_id": t.account_id,
            "account_name": t.account_name,
            "currency": t.currency,
            "date": t.date,
            "description": t.description,
            "merchant": t.merchant,
            "amount": t.amount,
            "debit_credit": t.debit_credit,
            "category": t.category,
            "recurring_flag": t.recurring_flag,
            "provider": provider,
            "raw_json": None,
            "created_at": now,
            "updated_at": now,
        }
        for dk, t in dks.items()
    ]

    stmt = pg_insert(TransactionRecord).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["dedupe_key"],
        set_={
            # Re-sync may legitimately update these fields (e.g. re-categorisation)
            "account_name": stmt.excluded.account_name,
            "merchant": stmt.excluded.merchant,
            "category": stmt.excluded.category,
            "recurring_flag": stmt.excluded.recurring_flag,
            "updated_at": stmt.excluded.updated_at,
            # Intentionally NOT overwriting:
            #   dedupe_key, account_id, currency, date, description,
            #   amount, debit_credit, provider, created_at
        },
    )
    db.execute(stmt)
    db.commit()

    inserted = len(dks) - len(existing_keys)
    updated = len(existing_keys)
    log.info(
        "PG upsert complete: %d inserted, %d updated (batch size %d)",
        inserted, updated, len(dks),
    )
    return inserted, updated


def _upsert_sqlite(
    txns: list[Transaction],
    db: Session,
    provider: str,
) -> Tuple[int, int]:
    """
    SQLite fallback: check-then-insert/update.
    Correct for demo volumes; no PostgreSQL dialect required.
    """
    now = datetime.now(timezone.utc)
    inserted = 0
    updated = 0

    for t in txns:
        dk = make_dedupe_key(t)
        existing = db.get(TransactionRecord, dk)

        if existing is None:
            db.add(TransactionRecord(
                dedupe_key=dk,
                provider_transaction_id=t.provider_transaction_id,
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
            ))
            inserted += 1
        else:
            # Update fields that may change on re-sync
            existing.account_name = t.account_name
            existing.merchant = t.merchant
            existing.category = t.category
            existing.recurring_flag = t.recurring_flag
            existing.updated_at = now
            updated += 1

    db.commit()
    log.info(
        "SQLite upsert complete: %d inserted, %d updated (total %d)",
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
        provider_transaction_id=r.provider_transaction_id,
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
        "provider_transaction_id": r.provider_transaction_id,
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
