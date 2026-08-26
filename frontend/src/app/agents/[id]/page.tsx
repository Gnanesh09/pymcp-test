"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ShieldCheck, WalletCards, Save } from "lucide-react";
import { useParams } from "next/navigation";
import { useUmonApi } from "@/src/lib/api";
import FundingModal from "@/src/components/FundingModal";

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const api = useUmonApi();

  const [agent, setAgent] = useState<any>(null);
  const [amount, setAmount] = useState("500");
  const [maxTransaction, setMaxTransaction] = useState("200");
  const [dailyLimit, setDailyLimit] = useState("400");
  const [autoPurchase, setAutoPurchase] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const data = await api.agent(id);
    setAgent(data.agent);
    setMaxTransaction(
      String(data.agent.policy.max_transaction_paise / 100),
    );
    setDailyLimit(
      String(data.agent.policy.daily_limit_paise / 100),
    );
    setAutoPurchase(data.agent.policy.auto_purchase);
  }, [api, id]);

  useEffect(() => {
    load().catch((error) => {
      window.alert(
        error instanceof Error
          ? error.message
          : "Unable to load agent.",
      );
    });
  }, [load]);

  async function savePolicy() {
    setSaving(true);

    try {
      const data = await api.updatePolicy(id, {
        max_transaction: Number(maxTransaction),
        daily_limit: Number(dailyLimit),
        auto_purchase: autoPurchase,
      });
      setAgent(data.agent);
    } catch (error) {
      window.alert(
        error instanceof Error
          ? error.message
          : "Unable to save policy.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (!agent) {
    return (
      <main className="shell">
        <div className="loading">Loading agent…</div>
      </main>
    );
  }

  return (
    <main className="shell narrow">
      <a className="back-link" href="/agents">
        <ArrowLeft size={17} />
        Back to agents
      </a>

      <section className="detail-hero">
        <div>
          <span className="eyebrow">PURCHASING AGENT</span>
          <h1>{agent.name}</h1>
          <p>{agent.description}</p>
        </div>

        <div className="detail-status">
          <ShieldCheck size={16} />
          {agent.status}
        </div>
      </section>

      <section className="detail-grid">
        <article className="panel-card balance-card">
          <div className="panel-label">
            AVAILABLE AGENT BALANCE
          </div>

          <div className="big-number">
            ₹{agent.balance_available.toFixed(2)}
          </div>

          <div className="subtle">
            Reserved ₹
            {(agent.balance_reserved_paise / 100).toFixed(2)}
          </div>

          <div className="fund-row">
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              type="number"
              min="1"
            />

            <FundingModal
              agentId={id}
              amount={Number(amount)}
              onSuccess={load}
            />
          </div>

          <div className="funding-note">
            Test Mode funding uses Razorpay Checkout. The backend only
            credits the agent after server-side payment verification.
          </div>
        </article>

        <article className="panel-card">
          <div className="panel-label">
            AGENT GUARDRAILS
          </div>

          <label className="field">
            <span>Maximum per transaction</span>
            <input
              value={maxTransaction}
              onChange={(e) =>
                setMaxTransaction(e.target.value)
              }
              type="number"
              min="1"
            />
          </label>

          <label className="field">
            <span>Daily spending limit</span>
            <input
              value={dailyLimit}
              onChange={(e) =>
                setDailyLimit(e.target.value)
              }
              type="number"
              min="1"
            />
          </label>

          <label className="switch-row">
            <span>
              <strong>Autonomous purchasing</strong>
              <small>
                Backend policy still decides every transaction.
              </small>
            </span>

            <input
              type="checkbox"
              checked={autoPurchase}
              onChange={(e) =>
                setAutoPurchase(e.target.checked)
              }
            />
          </label>

          <button
            className="secondary-button full"
            onClick={savePolicy}
            disabled={saving}
          >
            <Save size={16} />
            {saving ? "Saving…" : "Save guardrails"}
          </button>
        </article>
      </section>

      <section className="guardrail-preview">
        <span className="eyebrow">EXAMPLE</span>
        <h2>How the agent behaves</h2>
        <div className="decision-grid">
          <div>
            <strong>₹100 juice</strong>
            <span className="allow">ALLOW</span>
          </div>
          <div>
            <strong>₹200 order</strong>
            <span className="allow">ALLOW</span>
          </div>
          <div>
            <strong>₹300 order</strong>
            <span className="block">BLOCK</span>
          </div>
        </div>
        <p>
          The final decision is made by FastAPI, not by the LLM.
          Balance, limits, merchant rules, categories, stock and the
          current product price are checked before an order is committed.
        </p>
      </section>
    </main>
  );
}
