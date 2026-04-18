"""
Claude API wrapper.

Receives a DeterministicSummary, sends it to Claude, returns structured text fields.
All arithmetic is pre-computed — Claude is used only for narrative generation.
"""

import json
import os

import anthropic

from models.schema import AISummaryResponse, DeterministicSummary


def _build_prompt(summary: DeterministicSummary) -> str:
    cat_lines = "\n".join(
        f"  - {c.category}: ${c.total:.2f} ({c.count} transactions)"
        for c in summary.spending_by_category
    )
    recurring_lines = "\n".join(
        f"  - {r.merchant}: ~${r.estimated_amount:.2f}/month (confidence: {r.confidence})"
        for r in summary.recurring_payments
    ) or "  None detected"

    top_merch_lines = "\n".join(
        f"  - {m['merchant']}: ${m['total']:.2f}"
        for m in summary.top_merchants
    )
    largest_lines = "\n".join(
        f"  - {d['description']}: ${d['amount']:.2f} on {d['date']}"
        for d in summary.largest_debits
    )

    return f"""You are a financial insights assistant for a New Zealand open banking demo.

Given this monthly transaction summary, produce a JSON object with exactly these keys:
- top_spending_category: (string) name of the highest spending category
- recurring_payments_text: (string) short description of likely recurring payments
- unusual_pattern: (string) one unusual or notable spending pattern
- money_saving_suggestion: (string) one specific, actionable money-saving suggestion
- plain_english_summary: (string) 3-sentence plain-English summary of the month
- pay_by_bank_note: (string) short note on how a pay-by-bank flow could fit this product

Rules:
- Be specific and reference actual merchants or categories from the data
- Keep each value concise (1-3 sentences max, except plain_english_summary which is 3 sentences)
- Do not give regulated financial advice
- Do not make lending decisions
- Use New Zealand context (NZD, NZ merchants, NZ banks)
- Return only valid JSON, no markdown fences, no extra text

Monthly summary for {summary.month}:
- Total spending: ${summary.total_spending:.2f}
- Total income: ${summary.total_income:.2f}
- Net cashflow: ${summary.net_cashflow:.2f}
- Transaction count: {summary.transaction_count}
- Fixed outflow estimate: ${summary.fixed_outflow_estimate:.2f}

Spending by category:
{cat_lines}

Top merchants:
{top_merch_lines}

Largest transactions:
{largest_lines}

Detected recurring payments:
{recurring_lines}
"""


def get_ai_insights(summary: DeterministicSummary) -> AISummaryResponse:
    api_key = os.getenv("CLAUDE_API_KEY", "")
    if not api_key:
        raise EnvironmentError("CLAUDE_API_KEY is not set")

    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    prompt = _build_prompt(summary)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Claude API error: {e}") from e

    raw_text = message.content[0].text if message.content else ""

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        # Claude returned non-JSON — surface a clear error
        raise RuntimeError(
            f"Claude returned unexpected non-JSON response. Raw: {raw_text[:200]}"
        )

    required_keys = [
        "top_spending_category",
        "recurring_payments_text",
        "unusual_pattern",
        "money_saving_suggestion",
        "plain_english_summary",
        "pay_by_bank_note",
    ]
    missing = [k for k in required_keys if k not in parsed]
    if missing:
        raise RuntimeError(f"Claude response missing keys: {missing}")

    return AISummaryResponse(
        deterministic=summary,
        top_spending_category=parsed["top_spending_category"],
        recurring_payments_text=parsed["recurring_payments_text"],
        unusual_pattern=parsed["unusual_pattern"],
        money_saving_suggestion=parsed["money_saving_suggestion"],
        plain_english_summary=parsed["plain_english_summary"],
        pay_by_bank_note=parsed["pay_by_bank_note"],
    )
