"use client";

import { useCallback, useEffect, useState } from "react";
import { UserButton } from "@clerk/nextjs";
import { Plus, WalletCards, Activity } from "lucide-react";
import { useUmonApi } from "@/src/lib/api";

export default function AgentsPage() {
  const api = useUmonApi();
  const [agents, setAgents] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.agents();
      setAgents(data.agents ?? []);
    } catch (error) {
      window.alert(
        error instanceof Error ? error.message : "Unable to load agents.",
      );
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  async function createAgent() {
    setBusy(true);

    try {
      const data = await api.createAgent({
        name: "Grocery Agent",
        description: "My Umon grocery purchasing agent",
        max_transaction: 200,
        daily_limit: 400,
        auto_purchase: true,
        allowed_categories: [
          "grocery",
          "dairy",
          "snacks",
          "beverages",
        ],
        blocked_categories: [],
      });

      setAgents((current) => [data.agent, ...current]);
    } catch (error) {
      window.alert(
        error instanceof Error ? error.message : "Unable to create agent.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark small">U</div>
          <div>
            <strong>Umon Mart</strong>
            <span>Agent control</span>
          </div>
        </div>
        <UserButton />
      </header>

      <div className="section-heading standalone">
        <div>
          <span className="eyebrow">PURCHASING AGENTS</span>
          <h1>Your agents</h1>
        </div>

        <button
          className="primary-button"
          onClick={createAgent}
          disabled={busy}
        >
          <Plus size={17} />
          {busy ? "Creating…" : "Create agent"}
        </button>
      </div>

      <div className="agent-grid">
        {agents.map((agent) => (
          <article className="agent-card" key={agent.id}>
            <div className="card-topline">
              <div className="agent-avatar">
                <Activity size={19} />
              </div>
              <span
                className={
                  agent.status === "ACTIVE"
                    ? "status active"
                    : "status"
                }
              >
                {agent.status}
              </span>
            </div>

            <h2>{agent.name}</h2>
            <p>{agent.description}</p>

            <div className="balance">
              <span>Available balance</span>
              <strong>
                ₹{agent.balance_available.toFixed(2)}
              </strong>
            </div>

            <div className="policy-mini">
              <div>
                <span>Per transaction</span>
                <strong>
                  ₹{agent.policy.max_transaction_paise / 100}
                </strong>
              </div>
              <div>
                <span>Daily</span>
                <strong>
                  ₹{agent.policy.daily_limit_paise / 100}
                </strong>
              </div>
              <div>
                <span>Auto purchase</span>
                <strong>
                  {agent.policy.auto_purchase ? "ON" : "OFF"}
                </strong>
              </div>
            </div>

            <a
              className="secondary-button"
              href={`/agents/${agent.id}`}
            >
              Manage agent
            </a>
          </article>
        ))}

        {!agents.length && (
          <div className="empty-card">
            <div className="empty-icon">
              <WalletCards size={24} />
            </div>
            <h3>No agent yet</h3>
            <p>
              Create one, fund it, and define its spending rules.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
