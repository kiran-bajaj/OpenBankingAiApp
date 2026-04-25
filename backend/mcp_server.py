"""
MCP Analytics Server — FastAPI on port 8001.

Architecture role:
  Provider → DB (via POST /sync on main API) → THIS SERVER → Claude

This server exposes the analytics layer as HTTP "tools" above the database.
It is the analytics MCP layer in the system — it reads only from the DB,
never directly from a provider.

Note on MCP protocol:
  The official MCP Python SDK (mcp package) requires Python 3.10+.
  This server targets Python 3.9 and implements the same tool conventions
  over plain HTTP/JSON — functionally equivalent for local use.
  If upgrading to Python 3.10+, the endpoints here map 1-to-1 to FastMCP tools.

Run:
  uvicorn mcp_server:mcp_app --port 8001 --reload

Tools available:
  GET /tools/monthly-summary      → monthly_summary
  GET /tools/spending-by-category → spending_by_category
  GET /tools/top-merchants        → top_merchants
  GET /tools/recurring-payments   → recurring_payments
  GET /tools/cashflow             → cashflow_snapshot
  GET /tools                      → tool registry (list all tools)
"""
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

from db.database import check_db_connection, init_db
from services.analytics import (
    cashflow_snapshot_tool,
    monthly_summary_tool,
    recurring_payments_tool,
    spending_by_category_tool,
    top_merchants_tool,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the DB on startup. Non-fatal if DB is unavailable."""
    try:
        init_db()
        log.info("MCP analytics server: DB ready")
    except Exception as e:
        log.warning("DB not available at startup: %s", e)
    yield


mcp_app = FastAPI(
    title="NZ Open Banking — MCP Analytics Server",
    description=(
        "Analytics layer above the transaction database. "
        "Exposes deterministic spending insights as callable tools. "
        "Run POST /sync on the main API (port 8000) before querying."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

mcp_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local-only server
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


# ── Health ─────────────────────────────────────────────────────────────────────

@mcp_app.get("/health")
def health():
    db_ok = check_db_connection()
    return {
        "status": "ok",
        "server": "mcp-analytics",
        "db_connected": db_ok,
        "hint": "Run POST /sync on port 8000 to populate the database." if not db_ok else None,
    }


# ── Tool registry ──────────────────────────────────────────────────────────────

@mcp_app.get("/tools")
def list_tools():
    """MCP-style tool registry — lists all available analytics tools."""
    return {
        "server": "NZ Open Banking Analytics",
        "tools": [
            {
                "name": "monthly_summary",
                "description": "Full monthly spending summary from persisted transactions",
                "endpoint": "GET /tools/monthly-summary",
                "params": [{"name": "month", "type": "string", "format": "YYYY-MM", "required": False}],
            },
            {
                "name": "spending_by_category",
                "description": "Spending breakdown by category",
                "endpoint": "GET /tools/spending-by-category",
                "params": [{"name": "month", "type": "string", "format": "YYYY-MM", "required": False}],
            },
            {
                "name": "top_merchants",
                "description": "Top merchants by total spend",
                "endpoint": "GET /tools/top-merchants",
                "params": [
                    {"name": "month", "type": "string", "format": "YYYY-MM", "required": False},
                    {"name": "limit", "type": "integer", "default": 5, "required": False},
                ],
            },
            {
                "name": "recurring_payments",
                "description": "Heuristic recurring payment detection",
                "endpoint": "GET /tools/recurring-payments",
                "params": [],
            },
            {
                "name": "cashflow_snapshot",
                "description": "Cautious cashflow summary (income, spending, net, fixed outflows)",
                "endpoint": "GET /tools/cashflow",
                "params": [{"name": "month", "type": "string", "format": "YYYY-MM", "required": False}],
            },
        ],
    }


# ── Tool: monthly summary ──────────────────────────────────────────────────────

@mcp_app.get("/tools/monthly-summary")
def tool_monthly_summary(
    month: str = Query(default="", description="YYYY-MM, e.g. 2026-03"),
):
    """
    MCP Tool: monthly_summary
    Returns total spending, income, net cashflow, and category breakdown.
    Defaults to the most recent month found in the DB.
    """
    _require_db()
    try:
        return monthly_summary_tool(month)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Tool: spending by category ─────────────────────────────────────────────────

@mcp_app.get("/tools/spending-by-category")
def tool_spending_by_category(month: str = Query(default="")):
    """MCP Tool: spending_by_category — spend per category from DB."""
    _require_db()
    try:
        return spending_by_category_tool(month)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Tool: top merchants ────────────────────────────────────────────────────────

@mcp_app.get("/tools/top-merchants")
def tool_top_merchants(
    month: str = Query(default=""),
    limit: int = Query(default=5, ge=1, le=20),
):
    """MCP Tool: top_merchants — highest-spend merchants from DB."""
    _require_db()
    try:
        return top_merchants_tool(month, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Tool: recurring payments ───────────────────────────────────────────────────

@mcp_app.get("/tools/recurring-payments")
def tool_recurring_payments():
    """MCP Tool: recurring_payments — heuristic recurring payment detection."""
    _require_db()
    try:
        return recurring_payments_tool()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Tool: cashflow snapshot ────────────────────────────────────────────────────

@mcp_app.get("/tools/cashflow")
def tool_cashflow(month: str = Query(default="")):
    """
    MCP Tool: cashflow_snapshot
    Income, spending, net cashflow, and fixed outflow estimate.
    Phrased cautiously — not financial advice.
    """
    _require_db()
    try:
        return cashflow_snapshot_tool(month)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Helper ─────────────────────────────────────────────────────────────────────

def _require_db() -> None:
    if not check_db_connection():
        raise HTTPException(
            status_code=503,
            detail=(
                "Database unavailable. "
                "Run POST /sync on the main API (port 8000) to populate the database first."
            ),
        )
