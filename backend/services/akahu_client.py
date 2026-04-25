"""
Akahu client and mock data provider.

In mock mode: loads JSON from sample_data/.
In akahu mode: calls the Akahu API using env-var credentials.

All data is normalized to internal schema before returning —
the rest of the app never touches raw Akahu payloads.
"""

import json
import os
from pathlib import Path
from typing import Any

import httpx

from models.schema import Account, Balance, Transaction

SAMPLE_DATA = Path(__file__).parent.parent / "sample_data"

# ── Config ─────────────────────────────────────────────────────────────────────

def _provider_mode() -> str:
    return os.getenv("PROVIDER_MODE", "mock").lower()


def _akahu_headers() -> dict[str, str]:
    app_token = os.getenv("AKAHU_APP_TOKEN", "")
    user_token = os.getenv("AKAHU_USER_TOKEN", "")
    if not app_token or not user_token:
        raise EnvironmentError(
            "AKAHU_APP_TOKEN and AKAHU_USER_TOKEN must be set when PROVIDER_MODE=akahu"
        )
    return {
        "Authorization": f"Bearer {user_token}",
        "X-Akahu-ID": app_token,
        "Accept": "application/json",
    }


def _akahu_base() -> str:
    return os.getenv("AKAHU_BASE_URL", "https://api.akahu.io/v1")


# ── HTTP helper ────────────────────────────────────────────────────────────────

def _akahu_get(path: str) -> Any:
    url = f"{_akahu_base()}{path}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=_akahu_headers())
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"Akahu returned {e.response.status_code} for {path}"
        ) from e
    except httpx.RequestError as e:
        raise RuntimeError(f"Network error reaching Akahu: {e}") from e


# ── Normalizers ────────────────────────────────────────────────────────────────

def normalize_account(raw: dict) -> Account:
    """
    Map a raw Akahu account object to the internal Account schema.
    TODO: Confirm exact field names against live Akahu /accounts payload.
    """
    return Account(
        account_id=raw.get("_id", "unknown"),
        account_name=raw.get("name", "Unnamed Account"),
        account_type=raw.get("type", "transaction").lower(),
        currency=raw.get("currency", "NZD"),
        provider="akahu",
    )


def normalize_balance(raw: dict) -> Balance:
    """
    Map a raw Akahu account object (which carries balance) to Balance schema.
    TODO: Confirm 'balance' sub-object field names against Akahu docs.
    """
    balance_obj = raw.get("balance") or {}
    current = balance_obj.get("current", 0.0)
    available = balance_obj.get("available", current)
    return Balance(
        account_id=raw.get("_id", "unknown"),
        account_name=raw.get("name", "Unnamed Account"),
        currency=raw.get("currency", "NZD"),
        available=float(available),
        current=float(current),
    )


def normalize_transaction(raw: dict) -> Transaction:
    """
    Map a raw Akahu transaction object to the internal Transaction schema.

    provider_transaction_id is set from Akahu's stable '_id' field — this
    becomes the dedupe key in the DB and prevents duplicate rows on re-sync.

    TODO: Confirm 'merchant.name' path and debit_credit heuristic against Akahu docs.
    """
    amount_raw = raw.get("amount", 0.0)
    amount = abs(float(amount_raw))

    # Akahu amounts: negative = debit, positive = credit
    if isinstance(amount_raw, (int, float)):
        debit_credit = "credit" if float(amount_raw) > 0 else "debit"
    else:
        debit_credit = "debit"

    merchant_obj = raw.get("merchant") or {}
    merchant = merchant_obj.get("name") or raw.get("description", "Unknown")

    # Akahu may provide a category; fall back to "other"
    category_obj = raw.get("category") or {}
    category = category_obj.get("name", "other").lower()

    date_raw = raw.get("date", "")
    # Akahu dates are ISO 8601; take the date portion only
    date = date_raw[:10] if date_raw else ""

    return Transaction(
        provider_transaction_id=raw.get("_id") or None,
        account_id=raw.get("_account", "unknown"),
        account_name="",  # populated by caller after account lookup
        currency=raw.get("currency", "NZD"),
        date=date,
        description=raw.get("description", ""),
        merchant=merchant,
        amount=amount,
        debit_credit=debit_credit,  # type: ignore[arg-type]
        category=category,
        recurring_flag=False,  # conservative: do not infer recurring from raw
    )


# ── Mock providers ─────────────────────────────────────────────────────────────

def _load_json(filename: str) -> list[dict]:
    path = SAMPLE_DATA / filename
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Sample data file not found: {path}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Malformed sample data in {filename}: {e}") from e


def _mock_accounts() -> list[Account]:
    raw = _load_json("accounts.json")
    return [Account(**item) for item in raw]


def _mock_balances() -> list[Balance]:
    raw = _load_json("balances.json")
    return [Balance(**item) for item in raw]


def _mock_transactions() -> list[Transaction]:
    raw = _load_json("transactions.json")
    return [Transaction(**item) for item in raw]


# ── Akahu providers ────────────────────────────────────────────────────────────

def _akahu_accounts() -> list[Account]:
    data = _akahu_get("/accounts")
    items = data.get("items") or []
    return [normalize_account(r) for r in items if isinstance(r, dict)]


def _akahu_balances() -> list[Balance]:
    data = _akahu_get("/accounts")
    items = data.get("items") or []
    return [normalize_balance(r) for r in items if isinstance(r, dict)]


def _akahu_transactions() -> list[Transaction]:
    # Build a name lookup so we can populate account_name
    accs = _akahu_get("/accounts").get("items") or []
    name_map: dict[str, str] = {
        a.get("_id", ""): a.get("name", "") for a in accs if isinstance(a, dict)
    }

    data = _akahu_get("/transactions")
    items = data.get("items") or []
    txns = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        txn = normalize_transaction(raw)
        txn = txn.model_copy(update={"account_name": name_map.get(txn.account_id, "")})
        txns.append(txn)
    return txns


# ── Public API ─────────────────────────────────────────────────────────────────

def get_accounts() -> list[Account]:
    if _provider_mode() == "akahu":
        return _akahu_accounts()
    return _mock_accounts()


def get_balances() -> list[Balance]:
    if _provider_mode() == "akahu":
        return _akahu_balances()
    return _mock_balances()


def get_transactions() -> list[Transaction]:
    if _provider_mode() == "akahu":
        return _akahu_transactions()
    return _mock_transactions()
