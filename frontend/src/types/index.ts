// ── Domain types — mirror backend normalized schemas ──────────────────────────

export interface Account {
  account_id: string;
  account_name: string;
  account_type: string;
  currency: string;
  provider: string;
}

export interface Balance {
  account_id: string;
  account_name: string;
  currency: string;
  available: number;
  current: number;
}

export interface Transaction {
  account_id: string;
  account_name: string;
  currency: string;
  date: string;
  description: string;
  merchant: string;
  amount: number;
  debit_credit: "debit" | "credit";
  category: string;
  recurring_flag: boolean;
}

// ── API response wrappers ──────────────────────────────────────────────────────

export interface AccountsResponse {
  accounts: Account[];
  provider_mode: string;
}

export interface BalancesResponse {
  balances: Balance[];
  provider_mode: string;
}

export interface TransactionsResponse {
  transactions: Transaction[];
  provider_mode: string;
  data_source: string;   // "db" | "provider"
  db_count: number;
}

// ── Sync ───────────────────────────────────────────────────────────────────────

export interface SyncResult {
  total_from_provider: number;
  inserted: number;
  updated: number;
  total_in_db: number;
  provider_mode: string;
}

// ── AI summary ─────────────────────────────────────────────────────────────────

export interface CategorySpend {
  category: string;
  total: number;
  count: number;
}

export interface RecurringPayment {
  merchant: string;
  estimated_amount: number;
  confidence: "low" | "medium" | "high";
}

export interface DeterministicSummary {
  month: string;
  total_spending: number;
  total_income: number;
  net_cashflow: number;
  spending_by_category: CategorySpend[];
  top_merchants: { merchant: string; total: number }[];
  largest_debits: { description: string; amount: number; date: string }[];
  recurring_payments: RecurringPayment[];
  fixed_outflow_estimate: number;
  transaction_count: number;
}

export interface AISummaryResponse {
  deterministic: DeterministicSummary;
  top_spending_category: string;
  recurring_payments_text: string;
  unusual_pattern: string;
  money_saving_suggestion: string;
  plain_english_summary: string;
  pay_by_bank_note: string;
  data_source: string;   // "db" | "provider"
}

// ── Payment mock ───────────────────────────────────────────────────────────────

export interface PaymentRequest {
  account_id: string;
  amount: number;
  payee_name: string;
  reference: string;
}

export interface PaymentResponse {
  payment_id: string;
  status: string;
  created_at: string;
  message: string;
}
