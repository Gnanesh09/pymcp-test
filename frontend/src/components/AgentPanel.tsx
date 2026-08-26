"use client";

import { useCallback, useEffect, useState } from "react";
import { Bot, ChevronRight } from "lucide-react";
import { useUmonApi } from "@/src/lib/api";

export default function AgentPanel({
  onAgentReady,
}: {
  onAgentReady: (id: string | null) => void;
}) {
  const api = useUmonApi();
  const [agent, setAgent] = useState<any>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.agents();
      const first = data.agents?.[0] ?? null;
      setAgent(first);
      onAgentReady(first?.id ?? null);
    } catch {
      setAgent(null);
      onAgentReady(null);
    }
  }, [api, onAgentReady]);

  useEffect(() => {
    load();
  }, [load]);

  if (!agent) {
    return (
      <section className="agent-banner">
        <div>
          <span className="eyebrow">AGENTIC COMMERCE</span>
          <h2>Create your purchasing agent</h2>
          <p>
            Fund it, set hard limits, and connect this same identity to
            ChatGPT later.
          </p>
        </div>

        <a className="primary-button" href="/agents">
          Create agent <ChevronRight size={17} />
        </a>
      </section>
    );
  }

  return (
    <section className="agent-banner">
      <div className="agent-banner-icon">
        <Bot size={21} />
      </div>

      <div className="agent-banner-copy">
        <div className="agent-banner-title">{agent.name}</div>
        <div className="agent-banner-sub">
          ₹{agent.balance_available.toFixed(2)} available · ₹
          {agent.policy.max_transaction_paise / 100} per purchase ·{" "}
          {agent.policy.auto_purchase ? "auto" : "confirmation"}
        </div>
      </div>

      <a className="secondary-button" href={`/agents/${agent.id}`}>
        Manage
      </a>
    </section>
  );
}
