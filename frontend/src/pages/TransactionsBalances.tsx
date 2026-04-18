import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Balance, CategorySpend, SyncResult, Transaction } from "../types";
import BarChart from "../components/BarChart";
import ErrorBanner from "../components/ErrorBanner";
import Spinner from "../components/Spinner";

type LoadState = "idle" | "loading" | "done" | "error";
type SyncState = "idle" | "syncing" | "done" | "error";

function fmt(amount: number) {
  return `$${amount.toLocaleString("en-NZ", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function categoryTotals(txns: Transaction[]): CategorySpend[] {
  const map: Record<string, number> = {};
  for (const t of txns) {
    if (t.debit_credit === "debit") {
      map[t.category] = (map[t.category] ?? 0) + t.amount;
    }
  }
  return Object.entries(map)
    .map(([category, total]) => ({
      category,
      total: Math.round(total * 100) / 100,
      count: 0,
    }))
    .sort((a, b) => b.total - a.total);
}

export default function TransactionsBalances() {
  const [balances, setBalances] = useState<Balance[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [dataSource, setDataSource] = useState<string>("provider");
  const [dbCount, setDbCount] = useState<number>(0);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [loadError, setLoadError] = useState("");

  const [syncState, setSyncState] = useState<SyncState>("idle");
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncError, setSyncError] = useState("");

  async function load() {
    setLoadState("loading");
    setLoadError("");
    try {
      const [bRes, tRes] = await Promise.all([
        api.getBalances(),
        api.getTransactions(),
      ]);
      setBalances(bRes.balances ?? []);
      setTransactions(tRes.transactions ?? []);
      setDataSource(tRes.data_source ?? "provider");
      setDbCount(tRes.db_count ?? 0);
      setLoadState("done");
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load data.");
      setLoadState("error");
    }
  }

  async function handleSync() {
    setSyncState("syncing");
    setSyncResult(null);
    setSyncError("");
    try {
      const result = await api.syncTransactions();
      setSyncResult(result);
      setSyncState("done");
      // Reload transactions from DB after sync
      await load();
    } catch (e) {
      setSyncError(
        e instanceof ApiError ? e.message : "Sync failed. Is the backend running?",
      );
      setSyncState("error");
    }
  }

  useEffect(() => {
    load();
  }, []);

  const catData = categoryTotals(transactions);

  return (
    <div className="page">
      <div className="page-header-row">
        <h2 className="page-title">Transactions &amp; Balances</h2>
        <button
          className={`btn btn-primary${syncState === "syncing" ? " btn-loading" : ""}`}
          onClick={handleSync}
          disabled={syncState === "syncing"}
        >
          {syncState === "syncing" ? "Syncing…" : "⟳ Sync & Save"}
        </button>
      </div>

      {/* Sync result / error */}
      {syncState === "done" && syncResult && (
        <div className="sync-result">
          <span className="sync-icon">✅</span>
          <span>
            Synced <strong>{syncResult.total_from_provider}</strong> transactions
            from {syncResult.provider_mode} provider —{" "}
            <strong>{syncResult.inserted}</strong> new,{" "}
            <strong>{syncResult.updated}</strong> refreshed.{" "}
            <strong>{syncResult.total_in_db}</strong> total in database.
          </span>
        </div>
      )}
      {syncState === "error" && (
        <ErrorBanner message={syncError} onRetry={handleSync} />
      )}

      {/* Data source badge */}
      {loadState === "done" && (
        <div className={`data-source-badge ${dataSource}`}>
          {dataSource === "db" ? (
            <>🗄️ Showing <strong>{dbCount} persisted transactions</strong> from database</>
          ) : (
            <>⚡ Showing live data from provider — click <strong>Sync &amp; Save</strong> to persist</>
          )}
        </div>
      )}

      {loadState === "loading" && <Spinner label="Fetching account data…" />}
      {loadState === "error" && (
        <ErrorBanner message={loadError} onRetry={load} />
      )}

      {loadState === "done" && (
        <>
          {/* Balances */}
          <section className="section">
            <h3 className="section-title">Account Balances</h3>
            {balances.length === 0 ? (
              <p className="empty-state">No balances available.</p>
            ) : (
              <div className="balance-grid">
                {balances.map((b) => (
                  <div key={b.account_id} className="balance-card">
                    <div className="balance-name">{b.account_name}</div>
                    <div className="balance-amount">{fmt(b.current)}</div>
                    <div className="balance-currency">{b.currency}</div>
                    {b.available !== b.current && (
                      <div className="balance-available">
                        Available: {fmt(b.available)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Spending chart */}
          <section className="section">
            <h3 className="section-title">Monthly Spending by Category</h3>
            {catData.length === 0 ? (
              <p className="empty-state">No spending data to chart.</p>
            ) : (
              <>
                <BarChart
                  data={catData.map((c) => ({
                    label: c.category,
                    value: c.total,
                  }))}
                />
                <table className="data-table category-table">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th className="right">Total Spent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {catData.map((c) => (
                      <tr key={c.category}>
                        <td className="capitalize">{c.category}</td>
                        <td className="right">{fmt(c.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </section>

          {/* Transaction table */}
          <section className="section">
            <h3 className="section-title">
              Transactions{" "}
              <span className="count-badge">{transactions.length}</span>
            </h3>
            {transactions.length === 0 ? (
              <p className="empty-state">
                No transactions found. Click <strong>Sync &amp; Save</strong> to
                import from the provider.
              </p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Merchant</th>
                      <th>Category</th>
                      <th>Account</th>
                      <th className="right">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...transactions]
                      .sort((a, b) => b.date.localeCompare(a.date))
                      .map((t, i) => (
                        <tr key={`${t.date}-${i}`} className={t.debit_credit}>
                          <td className="mono">{t.date}</td>
                          <td>
                            {t.merchant}
                            {t.recurring_flag && (
                              <span
                                className="recurring-tag"
                                title="Recurring payment"
                              >
                                ↻
                              </span>
                            )}
                          </td>
                          <td className="capitalize">{t.category}</td>
                          <td>{t.account_name}</td>
                          <td className={`right amount ${t.debit_credit}`}>
                            {t.debit_credit === "credit" ? "+" : "−"}
                            {fmt(t.amount)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
