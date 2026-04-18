import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type { AISummaryResponse, PaymentResponse } from "../types";
import Spinner from "../components/Spinner";
import ErrorBanner from "../components/ErrorBanner";

function fmt(amount: number) {
  return `$${amount.toLocaleString("en-NZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function InsightCard({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <div className="insight-card">
      <div className="insight-icon">{icon}</div>
      <div>
        <div className="insight-title">{title}</div>
        <div className="insight-body">{body}</div>
      </div>
    </div>
  );
}

export default function AIInsights() {
  const [insights, setInsights] = useState<AISummaryResponse | null>(null);
  const [loadingInsights, setLoadingInsights] = useState(false);
  const [insightError, setInsightError] = useState("");

  const [payment, setPayment] = useState<PaymentResponse | null>(null);
  const [loadingPayment, setLoadingPayment] = useState(false);
  const [paymentError, setPaymentError] = useState("");

  async function generateInsights() {
    setLoadingInsights(true);
    setInsightError("");
    setInsights(null);
    try {
      const res = await api.getAISummary();
      setInsights(res);
    } catch (e) {
      setInsightError(
        e instanceof ApiError ? e.message : "Failed to generate insights.",
      );
    } finally {
      setLoadingInsights(false);
    }
  }

  async function simulatePayment() {
    setLoadingPayment(true);
    setPaymentError("");
    setPayment(null);
    try {
      const res = await api.postPaymentMock({
        account_id: "acc_1",
        amount: 15.0,
        payee_name: "Demo Merchant NZ",
        reference: "INV-1001",
      });
      setPayment(res);
    } catch (e) {
      setPaymentError(
        e instanceof ApiError ? e.message : "Simulated payment failed.",
      );
    } finally {
      setLoadingPayment(false);
    }
  }

  const d = insights?.deterministic;

  return (
    <div className="page">
      <h2 className="page-title">AI Insights &amp; Action</h2>

      {/* Generate insights */}
      <section className="section">
        <div className="section-header">
          <h3 className="section-title">Spending Insights</h3>
          <button
            className="btn btn-primary"
            onClick={generateInsights}
            disabled={loadingInsights}
          >
            {loadingInsights ? "Generating…" : "Generate AI Insights"}
          </button>
        </div>

        {loadingInsights && <Spinner label="Analysing transactions with Claude…" />}
        {insightError && <ErrorBanner message={insightError} onRetry={generateInsights} />}

        {insights && d && (
          <>
            {/* Deterministic summary strip */}
            <div className="stats-strip">
              <div className="stat">
                <div className="stat-label">Month</div>
                <div className="stat-value">{d.month}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Total Spent</div>
                <div className="stat-value debit">{fmt(d.total_spending)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Total Income</div>
                <div className="stat-value credit">{fmt(d.total_income)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Net Cashflow</div>
                <div className={`stat-value ${d.net_cashflow >= 0 ? "credit" : "debit"}`}>
                  {fmt(d.net_cashflow)}
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Fixed Outflows</div>
                <div className="stat-value">{fmt(d.fixed_outflow_estimate)}</div>
              </div>
            </div>

            {/* AI narrative cards */}
            <div className="insight-cards">
              <InsightCard
                icon="📊"
                title="Top Spending Category"
                body={insights.top_spending_category}
              />
              <InsightCard
                icon="🔁"
                title="Recurring Payments"
                body={insights.recurring_payments_text}
              />
              <InsightCard
                icon="🔍"
                title="Unusual Pattern"
                body={insights.unusual_pattern}
              />
              <InsightCard
                icon="💡"
                title="Money-Saving Suggestion"
                body={insights.money_saving_suggestion}
              />
            </div>

            {/* Plain English summary */}
            <div className="summary-block">
              <h4>Monthly Summary</h4>
              <p>{insights.plain_english_summary}</p>
            </div>

            {/* Recurring payments table */}
            {d.recurring_payments.length > 0 && (
              <div className="section">
                <h4 className="section-title">Detected Recurring Payments</h4>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Merchant</th>
                      <th className="right">Est. Amount</th>
                      <th>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.recurring_payments.map((r) => (
                      <tr key={r.merchant}>
                        <td>{r.merchant}</td>
                        <td className="right">{fmt(r.estimated_amount)}</td>
                        <td>
                          <span className={`confidence ${r.confidence}`}>
                            {r.confidence}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pay by bank note */}
            <div className="pay-by-bank-note">
              <span className="pbk-icon">💳</span>
              <div>
                <strong>How pay-by-bank fits here:</strong>
                <p>{insights.pay_by_bank_note}</p>
              </div>
            </div>
          </>
        )}

        {!insights && !loadingInsights && !insightError && (
          <p className="empty-state">
            Click <em>Generate AI Insights</em> to analyse your transaction history.
          </p>
        )}
      </section>

      {/* Pay by bank simulation */}
      <section className="section">
        <div className="section-header">
          <h3 className="section-title">Simulate Pay by Bank</h3>
        </div>

        <div className="pay-demo-box">
          <p className="pay-demo-desc">
            In a real NZ open banking flow, the user would be redirected to
            their bank to authenticate and authorise a payment — no card
            required. This button demonstrates that concept.
          </p>

          <div className="pay-demo-detail">
            <span>Payee:</span> <strong>Demo Merchant NZ</strong>
            <span>Amount:</span> <strong>$15.00 NZD</strong>
            <span>Reference:</span> <strong>INV-1001</strong>
          </div>

          <button
            className="btn btn-secondary"
            onClick={simulatePayment}
            disabled={loadingPayment}
          >
            {loadingPayment ? "Processing…" : "Simulate Pay by Bank"}
          </button>
        </div>

        {loadingPayment && <Spinner label="Simulating payment initiation…" />}
        {paymentError && <ErrorBanner message={paymentError} onRetry={simulatePayment} />}

        {payment && (
          <div className="payment-result">
            <div className="payment-status">
              ✅ Payment Initiated (Simulated)
            </div>
            <table className="data-table">
              <tbody>
                <tr>
                  <td>Payment ID</td>
                  <td className="mono">{payment.payment_id}</td>
                </tr>
                <tr>
                  <td>Status</td>
                  <td>
                    <span className="status-badge">{payment.status}</span>
                  </td>
                </tr>
                <tr>
                  <td>Created</td>
                  <td className="mono">{payment.created_at}</td>
                </tr>
              </tbody>
            </table>
            <p className="payment-message">{payment.message}</p>
          </div>
        )}
      </section>
    </div>
  );
}
