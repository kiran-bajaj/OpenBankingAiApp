"""
Sync service — orchestrates the full provider → DB import flow.

Flow:
  1. Fetch transactions from provider (mock or Akahu)
  2. Normalize (already done by akahu_client)
  3. Upsert to DB (idempotent — repeated syncs are safe)
  4. Return a summary dict with counts

This is the single entry point for data import. The rest of the app
reads from the DB; this is the only place that writes from a provider.
"""
import logging
import os

from db.database import SessionLocal
from db.repository import get_transaction_count, upsert_transactions
from services.akahu_client import get_transactions as provider_get_transactions

log = logging.getLogger(__name__)


def sync_transactions() -> dict:
    """
    Fetch from the configured provider, upsert to DB, return sync summary.
    Idempotent: running twice produces the same DB state.
    Raises RuntimeError on provider or DB failure.
    """
    provider_mode = os.getenv("PROVIDER_MODE", "mock").lower()
    log.info("Sync starting from provider '%s'", provider_mode)

    try:
        txns = provider_get_transactions()
    except EnvironmentError as e:
        raise RuntimeError(f"Provider credentials missing: {e}") from e
    except RuntimeError as e:
        raise RuntimeError(f"Provider fetch failed: {e}") from e

    if not txns:
        log.warning("Provider returned 0 transactions — nothing to sync")

    db = SessionLocal()
    try:
        count_before = get_transaction_count(db)
        inserted, updated = upsert_transactions(txns, db, provider=provider_mode)
        count_after = get_transaction_count(db)
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"DB upsert failed: {e}") from e
    finally:
        db.close()

    result = {
        "total_from_provider": len(txns),
        "inserted": inserted,
        "updated": updated,
        "total_in_db": count_after,
        "provider_mode": provider_mode,
    }
    log.info("Sync complete: %s", result)
    return result
