import type {
  AccountsResponse,
  AISummaryResponse,
  BalancesResponse,
  PaymentRequest,
  PaymentResponse,
  SyncResult,
  TransactionsResponse,
} from "../types";

const BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError(
      0,
      "Cannot reach the backend. Is it running on port 8000?",
    );
  }

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore parse failure — use the status code message
    }
    throw new ApiError(resp.status, detail);
  }

  return resp.json() as Promise<T>;
}

export const api = {
  getAccounts: () => request<AccountsResponse>("/accounts"),
  getBalances: () => request<BalancesResponse>("/balances"),
  getTransactions: () => request<TransactionsResponse>("/transactions"),
  syncTransactions: () => request<SyncResult>("/sync", { method: "POST" }),
  getAISummary: () =>
    request<AISummaryResponse>("/ai/summary", { method: "POST" }),
  postPaymentMock: (body: PaymentRequest) =>
    request<PaymentResponse>("/payment/mock", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
