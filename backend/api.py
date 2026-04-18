"""
NZ Open Banking Demo — FastAPI backend v2.

Architecture:
  Provider (mock/Akahu) ──POST /sync──► SQLite/PostgreSQL DB
  GET /transactions              ◄── DB  (fallback: provider if DB empty)
  POST /ai/summary               ◄── DB analytics → Claude
  GET  /debug/*                  ◄── DB  (read-only inspection)

Run: uvicorn api:app --reload --port 8000
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── DB imports ─────────────────────────────────────────────────────────────────
# Always imported — packages are in requirements.txt.
# Individual endpoints fall back gracefully if the DB isn't reachable.
from db.database import SessionLocal, check_db_connection, init_db
from db import repository as db_repo

from models.schema import (
    AccountsResponse,
    AISummaryResponse,
    BalancesResponse,
    DebugQueryRequest,
    HealthResponse,
    PaymentRequest,
    PaymentResponse,
    SyncResult,
    TransactionsResponse,
)
from services.akahu_client import get_accounts, get_balances, get_transactions
from services.analytics import get_summary_from_db
from services.claude_client import get_ai_insights
from services.summarizer import build_summary
from services.sync_service import sync_transactions


# ── App lifecycle ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as e:
        log.warning(
            "DB not available at startup — app runs without persistence: %s", e
        )
    yield


app = FastAPI(
    title="NZ Open Banking Demo",
    version="2.0.0",
    lifespan=lifespan,
)

_frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _provider_mode() -> str:
    return os.getenv("PROVIDER_MODE", "mock").lower()


def _db_ready() -> bool:
    """True if the DB is configured and reachable."""
    try:
        return check_db_connection()
    except Exception:
        return False


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        provider_mode=_provider_mode(),
        db_connected=_db_ready(),
    )


# ── Accounts ───────────────────────────────────────────────────────────────────

@app.get("/accounts", response_model=AccountsResponse)
def accounts() -> AccountsResponse:
    try:
        accs = get_accounts()
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return AccountsResponse(accounts=accs, provider_mode=_provider_mode())


# ── Balances ───────────────────────────────────────────────────────────────────

@app.get("/balances", response_model=BalancesResponse)
def balances() -> BalancesResponse:
    try:
        bals = get_balances()
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return BalancesResponse(balances=bals, provider_mode=_provider_mode())


# ── Transactions: DB-first, provider fallback ──────────────────────────────────

@app.get("/transactions", response_model=TransactionsResponse)
def transactions(
    account_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
) -> TransactionsResponse:
    """
    Returns transactions from the DB if data has been synced.
    Falls back to live provider data if the DB is empty or unavailable.
    Response includes data_source ("db" | "provider") and db_count.
    """
    # 1. Try DB
    if _db_ready():
        try:
            db = SessionLocal()
            try:
                db_txns = db_repo.get_transactions(
                    db,
                    account_id=account_id,
                    date_from=date_from,
                    date_to=date_to,
                )
                db_count = db_repo.get_transaction_count(db)
            finally:
                db.close()

            if db_txns:
                return TransactionsResponse(
                    transactions=db_txns,
                    provider_mode=_provider_mode(),
                    data_source="db",
                    db_count=db_count,
                )
        except Exception as e:
            log.warning("DB query failed, falling back to provider: %s", e)

    # 2. Provider fallback (live or mock)
    try:
        txns = get_transactions()
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return TransactionsResponse(
        transactions=txns,
        provider_mode=_provider_mode(),
        data_source="provider",
        db_count=0,
    )


# ── Sync: fetch provider → persist to DB ──────────────────────────────────────

@app.post("/sync", response_model=SyncResult)
def sync() -> SyncResult:
    """
    Fetch transactions from the configured provider, upsert into the DB.
    Idempotent — running multiple times produces the same DB state.
    """
    if not _db_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Database unavailable. "
                "Ensure DATABASE_URL is set and the database is running. "
                "Default is SQLite (sqlite:///./openbanking.db) which requires no setup."
            ),
        )
    try:
        result = sync_transactions()
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return SyncResult(**result)


# ── AI Summary: DB analytics → Claude ─────────────────────────────────────────

@app.post("/ai/summary", response_model=AISummaryResponse)
def ai_summary() -> AISummaryResponse:
    """
    Generates AI spending insights.
    Analytics are computed from the DB if data has been synced; otherwise
    falls back to a live provider fetch.
    Claude receives only a structured deterministic summary — never raw data.
    """
    data_source = "provider"

    if _db_ready():
        try:
            summary = get_summary_from_db()
            if summary.transaction_count > 0:
                data_source = "db"
                log.info(
                    "AI summary using DB analytics (%d transactions)",
                    summary.transaction_count,
                )
            else:
                log.info("DB is empty — falling back to provider for AI summary")
                summary = _provider_summary()
        except Exception as e:
            log.warning("DB analytics failed, falling back to provider: %s", e)
            summary = _provider_summary()
    else:
        summary = _provider_summary()

    try:
        result = get_ai_insights(summary)
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return result.model_copy(update={"data_source": data_source})


def _provider_summary():
    """Compute a DeterministicSummary from a live provider fetch."""
    try:
        txns = get_transactions()
    except (EnvironmentError, RuntimeError) as e:
        raise HTTPException(
            status_code=502, detail=f"Could not fetch transactions: {e}"
        )
    return build_summary(txns)


# ── Payment mock ───────────────────────────────────────────────────────────────

@app.post("/payment/mock", response_model=PaymentResponse)
def payment_mock(body: PaymentRequest) -> PaymentResponse:
    if not body.payee_name.strip():
        raise HTTPException(status_code=422, detail="payee_name must not be blank")
    if not body.reference.strip():
        raise HTTPException(status_code=422, detail="reference must not be blank")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return PaymentResponse(
        payment_id=f"pay_mock_{body.account_id}_{int(datetime.now(timezone.utc).timestamp())}",
        status="initiated",
        created_at=now,
        message=(
            "Mock pay-by-bank flow started. In a real NZ open banking flow, "
            "the user would now be redirected to their bank to authenticate "
            f"and authorise a payment of ${body.amount:.2f} to {body.payee_name}. "
            "No real payment has been made."
        ),
    )


# ── Debug endpoints (read-only, demo/test use only) ────────────────────────────

@app.get("/debug/transactions")
def debug_transactions(
    limit: int = Query(default=20, ge=1, le=100),
    account_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
):
    """Return raw DB rows for inspection. Not for production use."""
    _assert_db_ready()
    db = SessionLocal()
    try:
        rows = db_repo.get_raw_records(
            db,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
    finally:
        db.close()
    return {"count": len(rows), "transactions": rows}


@app.get("/debug/summary")
def debug_summary(month: Optional[str] = Query(default=None)):
    """Category-level aggregation directly from the DB. Not for production use."""
    _assert_db_ready()
    try:
        summary = get_summary_from_db(month=month)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return summary.model_dump()


@app.post("/debug/query")
def debug_query(body: DebugQueryRequest):
    """
    Run a read-only SQL SELECT against the DB. Max 100 rows returned.
    Only SELECT statements accepted. Not for production use.
    """
    _assert_db_ready()
    from sqlalchemy import text
    try:
        with SessionLocal() as db:
            result = db.execute(text(body.sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchmany(100)]
        return {"columns": columns, "rows": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query failed: {e}")


def _assert_db_ready() -> None:
    if not _db_ready():
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Run POST /sync to populate.",
        )
