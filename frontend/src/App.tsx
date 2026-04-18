import { useState } from "react";
import LinkedAccount from "./pages/LinkedAccount";
import TransactionsBalances from "./pages/TransactionsBalances";
import AIInsights from "./pages/AIInsights";

type Tab = "link" | "data" | "insights";

const TABS: { id: Tab; label: string }[] = [
  { id: "link", label: "1. Link Account" },
  { id: "data", label: "2. Transactions & Balances" },
  { id: "insights", label: "3. AI Insights & Action" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("link");
  const [connected, setConnected] = useState(false);

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <span className="header-logo">🏦</span>
          <div>
            <h1 className="header-title">NZ Open Banking Demo</h1>
            <p className="header-subtitle">Spending insights powered by open banking + AI</p>
          </div>
        </div>
      </header>

      <nav className="tab-nav">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`tab-btn${activeTab === tab.id ? " active" : ""}${
              tab.id !== "link" && !connected ? " tab-disabled" : ""
            }`}
            onClick={() => {
              if (tab.id !== "link" && !connected) return;
              setActiveTab(tab.id);
            }}
            title={tab.id !== "link" && !connected ? "Connect an account first" : undefined}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main className="app-main">
        {activeTab === "link" && (
          <LinkedAccount
            connected={connected}
            onConnect={() => {
              setConnected(true);
              setActiveTab("data");
            }}
          />
        )}
        {activeTab === "data" && <TransactionsBalances />}
        {activeTab === "insights" && <AIInsights />}
      </main>

      <footer className="app-footer">
        <p>
          Demo only — no real banking data or payments. Built with{" "}
          <strong>Akahu</strong> + <strong>Claude AI</strong>.
        </p>
      </footer>
    </div>
  );
}
