"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  Loader2,
  Send,
  ShoppingCart,
  Sparkles,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { UserButton } from "@clerk/nextjs";
import { useUmonApi } from "@/src/lib/api";

type Product = {
  id: string;
  name: string;
  brand?: string;
  category?: string;
  price?: number;
  price_paise?: number;
  stock?: number;
  image?: string | null;
  recommendation_reason?: string;
  recommendation_source?: string;
};

type Agent = {
  id: string;
  name: string;
  status: string;
  balance_available_paise?: number;
  policy?: { max_transaction_paise?: number; daily_limit_paise?: number };
};

type Msg = {
  id: string;
  role: "user" | "assistant";
  text: string;
  recommendations?: Product[];
  gaps?: string[];
  affordability?: any;
};

const money = (p = 0) =>
  `₹${(Number(p) / 100).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

export default function AgentPage() {
  const api = useUmonApi();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState("");
  const [cart, setCart] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState("");
  const end = useRef<HTMLDivElement>(null);

  const agent = useMemo(
    () => agents.find((a) => a.id === agentId) ?? null,
    [agents, agentId],
  );

  useEffect(() => {
    Promise.all([api.agents(), api.cart()])
      .then(([a, c]) => {
        const list = a.agents ?? [];
        setAgents(list);
        setCart(c.cart);
        setAgentId(list.find((x: Agent) => x.status === "ACTIVE")?.id ?? "");
      })
      .catch(() => {});
  }, [api]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function add(id: string) {
    setAdding(id);
    try {
      const result = await api.addToCart(id, 1);
      setCart(result.cart);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: e instanceof Error ? e.message : "Could not add the product.",
        },
      ]);
    } finally {
      setAdding("");
    }
  }

  async function send(e?: FormEvent) {
    e?.preventDefault();
    const message = input.trim();
    if (!message || loading) return;
    setInput("");
    setMessages((m) => [
      ...m,
      { id: crypto.randomUUID(), role: "user", text: message },
    ]);
    setLoading(true);

    try {
      const result = await api.agentChat({
        message,
        selected_agent_id: agentId || undefined,
      });
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: result.answer ?? "I checked the current Umon catalogue.",
          recommendations: result.recommendations ?? [],
          gaps: result.basket_gaps ?? [],
          affordability: result.affordability ?? null,
        },
      ]);
      if (result.cart) setCart(result.cart);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text:
            e instanceof Error
              ? e.message
              : "The AI assistant failed. No purchase was made.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-20 border-b border-white/10 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <Link href="/" className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-white font-black text-slate-950">
              U
            </div>
            <div>
              <div className="font-semibold">Umon Mart</div>
              <div className="text-xs text-slate-500">AI Shopping Agent</div>
            </div>
          </Link>
          <div className="flex items-center gap-3">
            <Link
              href="/cart"
              className="hidden rounded-xl border border-white/10 px-3 py-2 text-sm text-slate-300 sm:block"
            >
              <ShoppingCart className="mr-2 inline" size={15} /> Cart{" "}
              {cart?.items?.length ? `(${cart.items.length})` : ""}
            </Link>
            <UserButton />
          </div>
        </div>
      </header>

      <div className="mx-auto grid min-h-[calc(100vh-73px)] max-w-7xl lg:grid-cols-[1fr_320px]">
        <section className="flex min-h-[calc(100vh-73px)] flex-col border-r border-white/10">
          <div className="mx-auto w-full max-w-4xl flex-1 px-5 py-8 sm:px-8">
            <div className="mb-8">
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300">
                <Sparkles size={13} /> Agentic commerce
              </div>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                Tell Umon what you need.
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
                Umon checks the live catalogue, understands your shopping goal,
                finds complementary products and keeps payment authority
                separate.
              </p>
            </div>

            {!messages.length ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  "I need snacks for a movie night for 5 under ₹300.",
                  "What do I need to make paneer biryani?",
                  "Help me complete my current cart.",
                  "Find something useful under ₹100.",
                ].map((p) => (
                  <button
                    key={p}
                    onClick={() => setInput(p)}
                    className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-left text-sm leading-6 text-slate-300 hover:bg-white/[0.06]"
                  >
                    <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-600">
                      Try this
                    </div>
                    {p}
                  </button>
                ))}
              </div>
            ) : (
              <div className="space-y-6">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={m.role === "user" ? "flex justify-end" : ""}
                  >
                    <div
                      className={
                        m.role === "user"
                          ? "max-w-2xl rounded-3xl rounded-br-lg bg-white px-5 py-4 text-sm leading-6 text-slate-950"
                          : "max-w-3xl rounded-3xl rounded-bl-lg border border-white/10 bg-white/[0.035] p-5"
                      }
                    >
                      {m.role === "assistant" && (
                        <div className="mb-3 flex items-center gap-2 text-xs text-slate-400">
                          <span className="grid h-7 w-7 place-items-center rounded-lg bg-white text-slate-950">
                            <Bot size={14} />
                          </span>
                          Umon AI
                        </div>
                      )}
                      <p className="text-sm leading-7">{m.text}</p>

                      {!!m.gaps?.length && (
                        <div className="mt-4 rounded-2xl border border-amber-400/10 bg-amber-400/[0.04] p-4 text-xs leading-5 text-amber-100/75">
                          <div className="mb-1 font-semibold text-amber-200">
                            Not confirmed in Umon
                          </div>
                          {m.gaps.map((g) => (
                            <div key={g}>{g}</div>
                          ))}
                        </div>
                      )}

                      {!!m.recommendations?.length && (
                        <div className="mt-5 grid gap-3 sm:grid-cols-2">
                          {m.recommendations.map((p) => (
                            <article
                              key={p.id}
                              className="overflow-hidden rounded-2xl border border-white/10 bg-slate-900"
                            >
                              <div className="aspect-square bg-slate-800">
                                {p.image ? (
                                  <img
                                    src={p.image}
                                    alt={p.name}
                                    className="h-full w-full object-cover"
                                  />
                                ) : (
                                  <div className="grid h-full place-items-center text-slate-700">
                                    <ShoppingCart />
                                  </div>
                                )}
                              </div>
                              <div className="p-3">
                                <div className="text-sm font-semibold">
                                  {p.name}
                                </div>
                                <div className="mt-1 text-xs text-slate-500">
                                  {p.brand ?? p.category}
                                </div>
                                <div className="mt-2 font-bold">
                                  {money(
                                    p.price_paise ??
                                      Math.round((p.price ?? 0) * 100),
                                  )}
                                </div>
                                <div className="mt-2 text-xs leading-5 text-slate-400">
                                  {p.recommendation_reason}
                                </div>
                                <button
                                  onClick={() => add(p.id)}
                                  disabled={adding === p.id}
                                  className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-white py-2.5 text-xs font-bold text-slate-950 disabled:opacity-50"
                                >
                                  {adding === p.id ? (
                                    <Loader2
                                      size={14}
                                      className="animate-spin"
                                    />
                                  ) : (
                                    <ShoppingCart size={14} />
                                  )}
                                  {adding === p.id
                                    ? "Adding..."
                                    : "Add to cart"}
                                </button>
                              </div>
                            </article>
                          ))}
                        </div>
                      )}

                      {m.affordability && (
                        <div className="mt-5 rounded-2xl border border-white/10 bg-black/10 p-4">
                          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                            <ShieldCheck size={14} /> Agent constraints
                          </div>
                          <div className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                            <div>
                              <div className="text-slate-500">Suggested</div>
                              <div className="mt-1 font-semibold">
                                {m.affordability.recommendation_total}
                              </div>
                            </div>
                            <div>
                              <div className="text-slate-500">Available</div>
                              <div className="mt-1 font-semibold">
                                {m.affordability.available}
                              </div>
                            </div>
                            <div>
                              <div className="text-slate-500">Tx limit</div>
                              <div className="mt-1 font-semibold">
                                {m.affordability.transaction_limit}
                              </div>
                            </div>
                            <div>
                              <div className="text-slate-500">Daily left</div>
                              <div className="mt-1 font-semibold">
                                {m.affordability.daily_remaining}
                              </div>
                            </div>
                          </div>
                          <div className="mt-3 text-[11px] text-slate-600">
                            Recommendation only. No money was moved.
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 size={15} className="animate-spin" /> Umon is
                    checking the live catalogue...
                  </div>
                )}
                <div ref={end} />
              </div>
            )}
          </div>

          <div className="sticky bottom-0 border-t border-white/10 bg-slate-950/95 px-5 py-4 backdrop-blur sm:px-8">
            <form
              onSubmit={send}
              className="mx-auto flex max-w-4xl gap-2 rounded-2xl border border-white/10 bg-white/[0.04] p-2"
            >
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                rows={1}
                placeholder="Ask Umon what to buy..."
                className="min-h-11 flex-1 resize-none bg-transparent px-3 py-3 text-sm outline-none placeholder:text-slate-600"
              />
              <button
                disabled={!input.trim() || loading}
                className="grid h-11 w-11 place-items-center rounded-xl bg-white text-slate-950 disabled:opacity-40"
              >
                {loading ? (
                  <Loader2 size={17} className="animate-spin" />
                ) : (
                  <Send size={17} />
                )}
              </button>
            </form>
            <div className="mx-auto mt-2 max-w-4xl text-center text-[10px] text-slate-600">
              Ephemeral chat · recommendations only · checkout remains
              separately authorized
            </div>
          </div>
        </section>

        <aside className="hidden border-l border-white/10 bg-white/[0.015] p-6 lg:block">
          <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600">
            Purchasing authority
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Select an agent so the assistant can consider its current limits.
            The backend remains authoritative at checkout.
          </p>

          <div className="mt-5 rounded-2xl border border-white/10 bg-white/[0.025] p-4">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold">
              <ShieldCheck size={15} /> Agent
            </div>
            <select
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2.5 text-sm outline-none"
            >
              <option value="">No agent selected</option>
              {agents.map((a) => (
                <option
                  key={a.id}
                  value={a.id}
                  disabled={a.status !== "ACTIVE"}
                >
                  {a.name} {a.status !== "ACTIVE" ? `· ${a.status}` : ""}
                </option>
              ))}
            </select>

            {agent && (
              <div className="mt-4 space-y-3 border-t border-white/10 pt-4 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500">Status</span>
                  <span>{agent.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Available</span>
                  <span>{money(agent.balance_available_paise)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Tx limit</span>
                  <span>{money(agent.policy?.max_transaction_paise)}</span>
                </div>
              </div>
            )}
          </div>

          <Link
            href="/cart"
            className="mt-4 block rounded-2xl border border-white/10 bg-white/[0.025] p-4 text-sm"
          >
            <div className="flex items-center gap-2">
              <ShoppingCart size={15} /> Shared cart
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {cart?.items?.length ? `${cart.items.length} items` : "Empty"}
            </div>
          </Link>
        </aside>
      </div>
    </main>
  );
}
