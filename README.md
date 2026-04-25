# NZ Open Banking Demo

A full-stack demo app for NZ open banking concepts — account linking, transaction persistence, AI spending insights, and simulated pay-by-bank.

**Stack:** React 18 + Vite 5 + TypeScript · FastAPI + Python 3.9+ · PostgreSQL · SQLAlchemy 2 · Claude AI (claude-sonnet-4-6)

---

## Architecture

```
Frontend (React/Vite :5173)
  └─► Backend API (FastAPI :8000)
        ├─► Provider layer  (mock JSON or live Akahu API)
        ├─► PostgreSQL DB   (persisted normalized transactions)
        ├─► MCP Analytics   (FastAPI :8001 — analytics above the DB)
        └─► Claude AI       (narrative insights, never raw arithmetic)
```

**Data flow:**
1. `POST /sync` — fetches from provider, normalizes, upserts to DB (idempotent)
2. `GET /transactions` — reads from DB; falls back to live provider if DB is empty
3. `POST /ai/summary` — analytics from DB → Claude → structured insights

---

## Prerequisites

- Python 3.9+
- Node 18+ (install via [nvm](https://github.com/nvm-sh/nvm) if needed)
- PostgreSQL (Docker preferred) **or** skip Docker and use SQLite fallback

---

## 1 — Start PostgreSQL

### Option A: Docker (preferred)

```bash
docker run -d \
  --name openbanking-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=openbanking \
  -p 5432:5432 \
  postgres:15
```

### Option B: Native PostgreSQL

```bash
# macOS (Homebrew)
brew install postgresql@15
brew services start postgresql@15
createdb openbanking

# Or connect to an existing Postgres and run:
# CREATE DATABASE openbanking;
```

### Option C: SQLite fallback (zero setup)

Edit `backend/.env` and change `DATABASE_URL` to:
```
DATABASE_URL=sqlite:///./openbanking.db
```

No Docker or native install required. All features work; PostgreSQL-native ON CONFLICT is replaced by a row-by-row upsert.

---

## 2 — Backend setup

```bash
cd backend

# Create and activate virtualenv
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set CLAUDE_API_KEY and confirm DATABASE_URL
```

**`backend/.env` minimum:**
```
PROVIDER_MODE=mock
CLAUDE_API_KEY=sk-ant-...your-key...
CLAUDE_MODEL=claude-sonnet-4-6
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/openbanking
FRONTEND_ORIGIN=http://localhost:5173
```

Tables are created automatically on first startup (`create_all` — no migrations needed for demo).

---

## 3 — Run the backend

```bash
# From backend/ with .venv activated:
uvicorn api:app --reload --port 8000
```

Health check: http://localhost:8000/health

Expected response when DB is up:
```json
{"status": "ok", "provider_mode": "mock", "db_connected": true}
```

---

## 4 — Run the MCP analytics server

In a **separate terminal**:

```bash
cd backend
source .venv/bin/activate
uvicorn mcp_server:mcp_app --port 8001 --reload
```

Health check: http://localhost:8001/health  
Tool registry: http://localhost:8001/tools

The MCP server reads **only** from the DB — never from the provider directly.

---

## 5 — Run the frontend

Node 18+ is required. If you use nvm:

```bash
nvm use 20   # or: nvm install 20
```

```bash
cd frontend
npm install
npm run dev          # or: bash start.sh (uses explicit nvm path)
```

App: http://localhost:5173

---

## 6 — Demo flow

1. **Link Account** tab → click _Connect Account_ (verifies backend is reachable)
2. **Transactions & Balances** tab → click _⟳ Sync & Save_
   - Fetches from mock/Akahu provider
   - Upserts to PostgreSQL (idempotent — sync twice, row count stays the same)
   - Badge switches from ⚡ provider to 🗄️ database
3. **AI Insights & Action** tab → click _Generate AI Insights_
   - Analytics computed from DB (deterministic)
   - Claude generates narrative from structured analytics only
   - Badge shows 🗄️ Insights from persisted database
4. Click _Simulate Pay by Bank_ to see the conceptual pay-by-bank flow

---

## 7 — Verify deduplication

```bash
# Sync once
curl -s -X POST http://localhost:8000/sync | python3 -m json.tool

# Sync again — row count must not increase
curl -s -X POST http://localhost:8000/sync | python3 -m json.tool
# Expected: inserted: 0, updated: 32 (all rows already exist)

# Confirm total in DB
curl -s http://localhost:8000/debug/transactions?limit=5 | python3 -m json.tool
```

---

## 8 — SQL verification queries

Connect to Postgres:
```bash
docker exec -it openbanking-postgres psql -U postgres -d openbanking
# or: psql postgresql://postgres:postgres@localhost:5432/openbanking
```

```sql
-- Total transactions (must not double after repeated syncs)
SELECT COUNT(*) FROM transactions;

-- Spending by category
SELECT category, SUM(amount) AS total, COUNT(*) AS txn_count
FROM transactions
WHERE debit_credit = 'debit'
GROUP BY category
ORDER BY total DESC;

-- Most recent 10 transactions
SELECT date, merchant, amount, debit_credit, category
FROM transactions
ORDER BY date DESC
LIMIT 10;

-- Confirm no duplicate dedupe_keys
SELECT dedupe_key, COUNT(*) FROM transactions GROUP BY dedupe_key HAVING COUNT(*) > 1;
-- Expected: 0 rows
```

---

## 9 — Debug endpoints (demo use only)

| Endpoint | Description |
|---|---|
| `GET /health` | Backend + DB status |
| `GET /debug/transactions?limit=20` | Last N rows from DB |
| `GET /debug/summary?month=2026-03` | Category aggregation from DB |
| `POST /debug/query` `{"sql": "SELECT ..."}` | Read-only SQL (SELECT only) |
| `GET /tools` (port 8001) | MCP tool registry |
| `GET /tools/monthly-summary` (port 8001) | Monthly summary from DB |
| `GET /tools/cashflow` (port 8001) | Cashflow snapshot from DB |

---

## 10 — Switching to Akahu (live data)

1. Create an Akahu personal app at https://my.akahu.nz
2. Set in `backend/.env`:
   ```
   PROVIDER_MODE=akahu
   AKAHU_APP_TOKEN=app_token_...
   AKAHU_USER_TOKEN=user_token_...
   ```
3. Restart the backend
4. Click _⟳ Sync & Save_ — live transactions are fetched, normalized, and persisted

Akahu transaction IDs (`_id`) are used as the stable dedupe key — repeated syncs are safe.

---

## Troubleshooting

**`db_connected: false` in /health**
- PostgreSQL container not running: `docker start openbanking-postgres`
- Wrong DATABASE_URL: check `backend/.env`
- Switch to SQLite: `DATABASE_URL=sqlite:///./openbanking.db`

**`POST /sync` returns 503**
- DB not reachable — see above

**`POST /ai/summary` returns 401/503**
- `CLAUDE_API_KEY` missing or invalid in `backend/.env`
- Model name wrong: must be `claude-sonnet-4-6` (check `CLAUDE_MODEL`)

**Frontend `Cannot reach the backend`**
- Backend not running on port 8000
- Kill stale process: `lsof -ti :8000 | xargs kill -9`

**Node version error**
- Vite requires Node 18+: `nvm install 20 && nvm use 20`
