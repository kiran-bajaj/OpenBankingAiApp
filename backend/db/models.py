"""
SQLAlchemy ORM model for persisted normalized transactions.

dedupe_key is the primary key:
  - Derived from hash(account_id | date | amount | description)
  - Stable across repeated syncs → idempotent upserts

raw_json uses SQLAlchemy's JSON type (works with both SQLite and PostgreSQL).
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Index, String

from db.database import Base


class TransactionRecord(Base):
    __tablename__ = "transactions"

    dedupe_key = Column(String(64), primary_key=True)
    provider_transaction_id = Column(String, nullable=True)

    account_id = Column(String, nullable=False)
    account_name = Column(String, nullable=False, default="")
    currency = Column(String(8), nullable=False, default="NZD")
    date = Column(String(10), nullable=False)           # YYYY-MM-DD
    description = Column(String, nullable=False, default="")
    merchant = Column(String, nullable=False, default="")
    amount = Column(Float, nullable=False)
    debit_credit = Column(String(6), nullable=False)    # "debit" | "credit"
    category = Column(String, nullable=False, default="other")
    recurring_flag = Column(Boolean, nullable=False, default=False)
    provider = Column(String, nullable=False, default="mock")
    raw_json = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_txn_account_id", "account_id"),
        Index("ix_txn_date", "date"),
    )
