"""
Deterministic summarizer — all arithmetic is done here, not by Claude.

Claude only produces narrative text; it receives this structured summary as input.
"""

from collections import defaultdict
from datetime import date, datetime
from typing import Optional

from models.schema import (
    CategorySpend,
    DeterministicSummary,
    RecurringPayment,
    Transaction,
)


def _parse_date(d: str) -> Optional[date]:
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _infer_recurring(
    merchant: str, txns: list[Transaction]
) -> tuple[bool, str]:
    """
    Heuristic recurring detection for a single merchant across all transactions.
    Returns (is_recurring, confidence).
    Conservative: prefer false negatives over false positives.
    """
    merchant_txns = [
        t for t in txns
        if t.merchant == merchant and t.debit_credit == "debit"
    ]
    if len(merchant_txns) < 2:
        return False, "low"

    amounts = [t.amount for t in merchant_txns]
    amount_variance = max(amounts) - min(amounts)
    similar_amounts = amount_variance < 2.0  # within $2

    dates = sorted([_parse_date(t.date) for t in merchant_txns if _parse_date(t.date)])
    if len(dates) >= 2:
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        avg_gap = sum(gaps) / len(gaps)
        # weekly ~7, fortnightly ~14, monthly ~28-31
        periodic = any(abs(avg_gap - p) <= 5 for p in [7, 14, 28, 30, 31])
    else:
        periodic = False

    if similar_amounts and periodic:
        confidence = "high"
    elif similar_amounts or periodic:
        confidence = "medium"
    else:
        confidence = "low"

    is_recurring = confidence in ("medium", "high")
    return is_recurring, confidence


def build_summary(transactions: list[Transaction]) -> DeterministicSummary:
    if not transactions:
        return DeterministicSummary(
            month="Unknown",
            total_spending=0.0,
            total_income=0.0,
            net_cashflow=0.0,
            spending_by_category=[],
            top_merchants=[],
            largest_debits=[],
            recurring_payments=[],
            fixed_outflow_estimate=0.0,
            transaction_count=0,
        )

    # Determine the dominant month from transaction dates
    parsed_dates = [_parse_date(t.date) for t in transactions if _parse_date(t.date)]
    if parsed_dates:
        most_common_month = max(set((d.year, d.month) for d in parsed_dates),
                                key=lambda ym: sum(1 for d in parsed_dates if (d.year, d.month) == ym))
        month_label = date(most_common_month[0], most_common_month[1], 1).strftime("%B %Y")
        # Filter to that month only for summary
        month_txns = [
            t for t in transactions
            if (d := _parse_date(t.date)) and (d.year, d.month) == most_common_month
        ]
    else:
        month_label = "Unknown"
        month_txns = transactions

    debits = [t for t in month_txns if t.debit_credit == "debit"]
    credits = [t for t in month_txns if t.debit_credit == "credit"]

    total_spending = round(sum(t.amount for t in debits), 2)
    total_income = round(sum(t.amount for t in credits), 2)
    net_cashflow = round(total_income - total_spending, 2)

    # Spending by category
    cat_totals: dict[str, float] = defaultdict(float)
    cat_counts: dict[str, int] = defaultdict(int)
    for t in debits:
        cat_totals[t.category] += t.amount
        cat_counts[t.category] += 1

    spending_by_category = [
        CategorySpend(
            category=cat,
            total=round(cat_totals[cat], 2),
            count=cat_counts[cat],
        )
        for cat in sorted(cat_totals, key=lambda c: cat_totals[c], reverse=True)
    ]

    # Top merchants by spend
    merchant_totals: dict[str, float] = defaultdict(float)
    for t in debits:
        merchant_totals[t.merchant] += t.amount

    top_merchants = [
        {"merchant": m, "total": round(merchant_totals[m], 2)}
        for m in sorted(merchant_totals, key=lambda m: merchant_totals[m], reverse=True)[:5]
    ]

    # Largest single debits
    largest_debits = [
        {"description": t.description, "amount": t.amount, "date": t.date}
        for t in sorted(debits, key=lambda t: t.amount, reverse=True)[:5]
    ]

    # Recurring payment detection
    unique_merchants = list({t.merchant for t in debits})
    recurring_payments: list[RecurringPayment] = []
    for merchant in unique_merchants:
        # Pass only the full transaction list (month_txns is already a subset of it)
        is_rec, confidence = _infer_recurring(merchant, transactions)
        if is_rec:
            avg_amount = round(
                sum(t.amount for t in debits if t.merchant == merchant)
                / len([t for t in debits if t.merchant == merchant]),
                2,
            )
            recurring_payments.append(
                RecurringPayment(
                    merchant=merchant,
                    estimated_amount=avg_amount,
                    confidence=confidence,  # type: ignore[arg-type]
                )
            )

    # Fixed outflow = sum of debits explicitly marked recurring in source data.
    # Heuristic inferences (grocery runs, transport) are excluded — those are
    # variable spend, not fixed obligations.
    fixed_outflow_estimate = round(
        sum(t.amount for t in debits if t.recurring_flag),
        2,
    )

    return DeterministicSummary(
        month=month_label,
        total_spending=total_spending,
        total_income=total_income,
        net_cashflow=net_cashflow,
        spending_by_category=spending_by_category,
        top_merchants=top_merchants,
        largest_debits=largest_debits,
        recurring_payments=recurring_payments,
        fixed_outflow_estimate=fixed_outflow_estimate,
        transaction_count=len(month_txns),
    )
