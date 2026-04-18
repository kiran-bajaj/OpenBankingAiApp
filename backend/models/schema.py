from pydantic import BaseModel, field_validator
from typing import Literal, Optional


# ── Normalized domain models ──────────────────────────────────────────────────

class Account(BaseModel):
    account_id: str
    account_name: str
    account_type: str          # transaction | savings | credit
    currency: str
    provider: str              # "mock" | "akahu"


class Balance(BaseModel):
    account_id: str
    account_name: str
    currency: str
    available: float
    current: float


class Transaction(BaseModel):
    account_id: str
    account_name: str
    currency: str
    date: str                  # ISO date YYYY-MM-DD
    description: str
    merchant: str
    amount: float              # always positive; direction in debit_credit
    debit_credit: Literal["debit", "credit"]
    category: str
    recurring_flag: bool


# ── API response wrappers ─────────────────────────────────────────────────────

class AccountsResponse(BaseModel):
    accounts: list[Account]
    provider_mode: str


class BalancesResponse(BaseModel):
    balances: list[Balance]
    provider_mode: str


class TransactionsResponse(BaseModel):
    transactions: list[Transaction]
    provider_mode: str
    data_source: str = "provider"  # "db" | "provider"
    db_count: int = 0              # total rows in DB at time of response


# ── Sync ──────────────────────────────────────────────────────────────────────

class SyncResult(BaseModel):
    total_from_provider: int   # transactions returned by the provider
    inserted: int              # net-new rows written to DB
    updated: int               # existing rows refreshed
    total_in_db: int           # total rows in DB after sync
    provider_mode: str


# ── AI summary ────────────────────────────────────────────────────────────────

class RecurringPayment(BaseModel):
    merchant: str
    estimated_amount: float
    confidence: Literal["low", "medium", "high"]


class CategorySpend(BaseModel):
    category: str
    total: float
    count: int


class DeterministicSummary(BaseModel):
    month: str
    total_spending: float
    total_income: float
    net_cashflow: float
    spending_by_category: list[CategorySpend]
    top_merchants: list[dict]           # [{merchant, total}]
    largest_debits: list[dict]          # [{description, amount, date}]
    recurring_payments: list[RecurringPayment]
    fixed_outflow_estimate: float
    transaction_count: int


class AISummaryResponse(BaseModel):
    deterministic: DeterministicSummary
    top_spending_category: str
    recurring_payments_text: str
    unusual_pattern: str
    money_saving_suggestion: str
    plain_english_summary: str
    pay_by_bank_note: str
    data_source: str = "provider"      # "db" | "provider"


# ── Payment mock ──────────────────────────────────────────────────────────────

class PaymentRequest(BaseModel):
    account_id: str
    amount: float
    payee_name: str
    reference: str

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be greater than zero")
        return v


class PaymentResponse(BaseModel):
    payment_id: str
    status: str
    created_at: str
    message: str


# ── Debug ─────────────────────────────────────────────────────────────────────

class DebugQueryRequest(BaseModel):
    sql: str

    @field_validator("sql")
    @classmethod
    def must_be_select(cls, v: str) -> str:
        if not v.strip().upper().startswith("SELECT"):
            raise ValueError("Only SELECT statements are permitted")
        return v


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    provider_mode: str
    db_connected: bool = False
