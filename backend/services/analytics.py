"""
Analytics layer — sits above the DB, below Claude.

Architecture:
  Provider → DB (via sync) → analytics (this module) → Claude summary

This module:
1. Queries the DB for transactions
2. Delegates to the existing deterministic summarizer
3. Returns Pydantic models or JSON-serializable dicts

Used by:
  - api.py      (directly, for POST /ai/summary and debug endpoints)
  - mcp_server.py (wrapped as HTTP analytics tools)

Claude receives the structured output of these functions, never raw transactions.
"""
import logging
from typing import Optional

from db.database import SessionLocal
from db import repository as db_repo
from models.schema import DeterministicSummary
from services.summarizer import build_summary

log = logging.getLogger(__name__)


# ── Core: returns DeterministicSummary ────────────────────────────────────────

def get_summary_from_db(
    month: Optional[str] = None,
    account_id: Optional[str] = None,
) -> DeterministicSummary:
    """
    Fetch transactions from DB and compute a DeterministicSummary.
    month: 'YYYY-MM' (e.g. '2026-03'). If None, uses all available data
    and summarizer picks the dominant month.
    Returns an empty summary if the DB has no transactions.
    """
    date_from, date_to = _month_range(month)
    db = SessionLocal()
    try:
        txns = db_repo.get_transactions(
            db,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
    finally:
        db.close()

    return build_summary(txns)


# ── Dict-returning variants used by the MCP server and debug endpoints ─────────

def monthly_summary_tool(month: str = "") -> dict:
    """MCP Tool — full monthly summary from DB as a JSON-serializable dict."""
    return get_summary_from_db(month or None).model_dump()


def spending_by_category_tool(month: str = "") -> list:
    """MCP Tool — spending by category from DB."""
    summary = get_summary_from_db(month or None)
    return [c.model_dump() for c in summary.spending_by_category]


def top_merchants_tool(month: str = "", limit: int = 5) -> list:
    """MCP Tool — top merchants by spend from DB."""
    summary = get_summary_from_db(month or None)
    return summary.top_merchants[:limit]


def recurring_payments_tool() -> list:
    """MCP Tool — heuristically-detected recurring payments from DB."""
    summary = get_summary_from_db()
    return [r.model_dump() for r in summary.recurring_payments]


def cashflow_snapshot_tool(month: str = "") -> dict:
    """
    MCP Tool — cautious cashflow snapshot from DB.
    Phrased carefully: informational only, not financial advice.
    """
    s = get_summary_from_db(month or None)
    return {
        "month": s.month,
        "total_income": s.total_income,
        "total_spending": s.total_spending,
        "net_cashflow": s.net_cashflow,
        "fixed_outflow_estimate": s.fixed_outflow_estimate,
        "note": (
            "These figures are computed from available transaction data and are "
            "informational only. They do not constitute financial advice."
        ),
    }


# ── Internal ───────────────────────────────────────────────────────────────────

def _month_range(month: Optional[str]) -> tuple:
    """Convert 'YYYY-MM' to (date_from, date_to) or (None, None)."""
    if not month:
        return None, None
    try:
        year, m = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        log.warning("Invalid month format '%s', ignoring filter", month)
        return None, None
    date_from = f"{year}-{m:02d}-01"
    date_to = f"{year + 1}-01-01" if m == 12 else f"{year}-{m + 1:02d}-01"
    return date_from, date_to
