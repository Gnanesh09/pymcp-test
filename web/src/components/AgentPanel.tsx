"use client";
import { useCallback, useEffect, useState } from "react";
import { Bot, ChevronRight } from "lucide-react";
import { useUmonApi } from "@/src/lib/api";

export default function AgentPanel() {
  const api = useUmonApi();
  const [agents, setAgents] = useState<any[]>([]);
  const load = useCallback(async () => {
    try {
      setAgents((await api.agents()).agents ?? []);
    } catch {}
  }, [api]);
  useEffect(() => {
    load();
  }, [load]);
  if (!agents.length) {
    return (
      <section className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6 rounded-[2rem] border border-fuchsia-100 bg-gradient-to-br from-fuchsia-50/50 to-white p-6 sm:p-8 shadow-sm">
        <div>
          <span className="mb-2 block text-[11px] font-bold uppercase tracking-widest text-fuchsia-600">
            Agentic Commerce
          </span>
          <h2 className="mb-2 text-xl font-bold text-gray-900 sm:text-2xl">
            Create your purchasing agent
          </h2>
          <p className="text-sm text-gray-600 max-w-md sm:text-base leading-relaxed">
            Fund it, set hard limits, then choose it at checkout.
          </p>
        </div>
        <a
          href="/agents"
          className="group inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-gray-900 px-6 py-3.5 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:bg-gray-800 hover:shadow-md active:scale-[0.98]"
        >
          Create agent
          <ChevronRight
            size={18}
            className="transition-transform group-hover:translate-x-1"
          />
        </a>
      </section>
    );
  }

  return (
    <section className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 rounded-2xl border border-gray-200 bg-white p-5 sm:p-6 shadow-sm transition-all hover:border-gray-300 hover:shadow-md">
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-fuchsia-50 border border-fuchsia-100 text-fuchsia-600 shadow-sm shadow-fuchsia-100/50">
          <Bot size={24} />
        </div>
        <div>
          <div className="text-base font-bold text-gray-900">
            {agents.length} purchasing agent{agents.length > 1 ? "s" : ""}{" "}
            available
          </div>
          <div className="mt-1 text-sm text-gray-500">
            The cart is shared. Choose which agent funds the purchase at
            checkout.
          </div>
        </div>
      </div>
      <a
        href="/agents"
        className="mt-2 w-full sm:mt-0 sm:w-auto inline-flex shrink-0 items-center justify-center rounded-xl border border-gray-200 bg-white px-5 py-2.5 text-sm font-semibold text-gray-700 shadow-sm transition-all duration-200 hover:bg-gray-50 hover:text-gray-900 active:scale-[0.98]"
      >
        Manage agents
      </a>
    </section>
  );
}
