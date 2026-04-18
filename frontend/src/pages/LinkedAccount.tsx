import { useState } from "react";
import { api, ApiError } from "../lib/api";
import Spinner from "../components/Spinner";
import ErrorBanner from "../components/ErrorBanner";

interface Props {
  connected: boolean;
  onConnect: () => void;
}

type Status = "idle" | "connecting" | "connected" | "error";

export default function LinkedAccount({ connected, onConnect }: Props) {
  const [status, setStatus] = useState<Status>(connected ? "connected" : "idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [providerMode, setProviderMode] = useState<string | null>(null);

  async function handleConnect() {
    setStatus("connecting");
    setErrorMsg("");

    try {
      // Verify backend is reachable and detect provider mode
      const health = await api.getAccounts();
      setProviderMode(health.provider_mode);
      // Simulate a brief connection handshake for demo effect
      await new Promise((r) => setTimeout(r, 800));
      setStatus("connected");
      setTimeout(onConnect, 600);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : "Unexpected error. Check the backend is running.";
      setErrorMsg(msg);
      setStatus("error");
    }
  }

  const isMock = providerMode === "mock" || providerMode === null;

  return (
    <div className="page">
      <div className="card hero-card">
        <div className="hero-icon">🏦</div>
        <h2 className="hero-title">Open Banking Account Link</h2>
        <p className="hero-desc">
          This demo shows how open banking works in New Zealand using the{" "}
          <strong>Akahu</strong> platform. Connect your account to fetch
          real-time balances and transactions, then get AI-powered spending
          insights.
        </p>

        {isMock && (
          <div className="mode-badge mock">
            🧪 Running in <strong>mock / demo mode</strong> — no real bank
            connection required
          </div>
        )}
        {!isMock && providerMode === "akahu" && (
          <div className="mode-badge akahu">
            🔗 <strong>Akahu mode</strong> — reads from your linked Akahu
            personal app or Demo Bank setup
          </div>
        )}

        <div className="connect-section">
          {status === "idle" && (
            <button className="btn btn-primary btn-lg" onClick={handleConnect}>
              Connect Account
            </button>
          )}

          {status === "connecting" && (
            <Spinner label="Establishing connection…" />
          )}

          {status === "connected" && (
            <div className="success-state">
              <span className="success-icon">✅</span>
              <span>Account connected! Redirecting…</span>
            </div>
          )}

          {status === "error" && (
            <>
              <ErrorBanner message={errorMsg} onRetry={handleConnect} />
            </>
          )}
        </div>

        <div className="how-it-works">
          <h3>How open banking works in NZ</h3>
          <ol>
            <li>
              <strong>Consent:</strong> You authorise the app to read your
              account data via your bank's secure OAuth flow.
            </li>
            <li>
              <strong>Data access:</strong> Akahu fetches balances and
              transactions on your behalf — read-only.
            </li>
            <li>
              <strong>Insights:</strong> Your data is analysed locally by
              Claude AI to surface spending patterns.
            </li>
            <li>
              <strong>Pay by bank:</strong> Future open banking APIs will allow
              payment initiation — demonstrated here as a concept.
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
