"use client";

import { useCallback, useEffect, useState } from "react";
import { SignedIn, SignedOut, UserButton } from "@clerk/nextjs";
import {
  Search,
  ShoppingBag,
  Bot,
  ShieldCheck,
  ArrowRight,
  Activity,
  ReceiptText,
} from "lucide-react";
import ProductCard from "@/src/components/ProductCard";
import AgentPanel from "@/src/components/AgentPanel";
import { searchProducts } from "@/src/lib/api";
import type { Product } from "@/src/lib/types";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);

  const search = useCallback(async () => {
    setLoading(true);
    try {
      setProducts((await searchProducts(query)).products ?? []);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    search().catch(() => undefined);
  }, [search]);

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 font-sans selection:bg-fuchsia-500/20">
      {/* --- LOGGED OUT STATE --- */}
      <SignedOut>
        <main className="flex min-h-screen items-center justify-center p-4 relative overflow-hidden">
          {/* Subtle Background Glow */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-fuchsia-100 blur-[120px] rounded-full pointer-events-none" />

          <div className="relative w-full max-w-md rounded-[2rem] border border-gray-200 bg-white/90 p-8 text-center shadow-xl shadow-gray-200/50 backdrop-blur-xl">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-fuchsia-500 to-purple-600 text-3xl font-bold text-white shadow-lg shadow-fuchsia-500/30">
              U
            </div>
            <h1 className="mb-3 text-3xl font-bold tracking-tight text-gray-900">
              Umon Mart
            </h1>
            <p className="mb-8 text-sm text-gray-500 leading-relaxed">
              Shop normally. Create a bounded purchasing agent that can later
              connect to AI clients through MCP.
            </p>
            <a
              href="/sign-in"
              className="group flex w-full items-center justify-center gap-2 rounded-full bg-gray-900 px-6 py-3.5 text-sm font-semibold text-white transition-all hover:bg-gray-800 active:scale-[0.98] shadow-md"
            >
              Sign in{" "}
              <ArrowRight
                size={18}
                className="transition-transform group-hover:translate-x-1"
              />
            </a>
          </div>
        </main>
      </SignedOut>

      {/* --- LOGGED IN STATE --- */}
      <SignedIn>
        <main className="pb-24">
          {/* Top Navigation */}
          <header className="sticky top-0 z-50 flex items-center justify-between border-b border-gray-200 bg-white/80 px-4 py-3 backdrop-blur-xl sm:px-6 lg:px-8 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-fuchsia-500 to-purple-600 text-xl font-bold text-white shadow-sm shadow-fuchsia-500/30">
                U
              </div>
              <div className="hidden flex-col sm:flex">
                <span className="text-base font-bold leading-tight text-gray-900">
                  Umon Mart
                </span>
                <span className="text-[10px] font-bold uppercase tracking-wider text-fuchsia-600">
                  AI-Native Commerce
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2 sm:gap-6">
              <a
                href="/cart"
                className="flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
              >
                <ShoppingBag size={18} />{" "}
                <span className="hidden md:inline">Cart</span>
              </a>
              <a
                href="/agents"
                className="flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
              >
                <Bot size={18} />{" "}
                <span className="hidden md:inline">Agents</span>
              </a>
              <a
                href="/orders"
                className="flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
              >
                <ReceiptText size={18} />{" "}
                <span className="hidden md:inline">Orders</span>
              </a>
              <a
                href="/activity"
                className="flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 mr-2"
              >
                <Activity size={18} />{" "}
                <span className="hidden md:inline">Activity</span>
              </a>
              <UserButton
                appearance={{
                  elements: {
                    avatarBox: "h-9 w-9 border border-gray-200 shadow-sm",
                  },
                }}
              />
            </div>
          </header>

          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            {/* Hero Section */}
            <section className="relative mt-6 overflow-hidden rounded-[2rem] border border-gray-200 bg-white p-6 sm:p-10 shadow-sm">
              {/* Subtle gradient wash inside hero */}
              <div className="absolute top-0 right-0 h-full w-1/2 bg-gradient-to-l from-fuchsia-50 to-transparent pointer-events-none" />

              <div className="relative flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex-1 space-y-5">
                  <span className="inline-flex items-center rounded-full border border-fuchsia-200 bg-fuchsia-50 px-3 py-1 text-[11px] font-bold uppercase tracking-widest text-fuchsia-700">
                    One Merchant • AI Ready
                  </span>
                  <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl lg:leading-[1.1]">
                    Shop normally.
                    <br />
                    <span className="text-transparent bg-clip-text bg-gradient-to-r from-fuchsia-600 to-purple-600">
                      Let your agent shop smarter.
                    </span>
                  </h1>
                  <p className="max-w-xl text-base text-gray-600">
                    Browse products, create and fund purchasing agents, set hard
                    spending rules, and later connect the same identity to AI
                    clients through MCP.
                  </p>
                  <div className="flex flex-wrap gap-3 pt-2">
                    <span className="flex items-center gap-1.5 rounded-xl border border-gray-200 bg-gray-50 px-3.5 py-2 text-xs font-semibold text-gray-700">
                      <ShieldCheck size={16} className="text-emerald-500" />{" "}
                      Backend-enforced guardrails
                    </span>
                    <span className="flex items-center gap-1.5 rounded-xl border border-gray-200 bg-gray-50 px-3.5 py-2 text-xs font-semibold text-gray-700">
                      <ShoppingBag size={16} className="text-blue-500" />{" "}
                      Razorpay test funding
                    </span>
                  </div>
                </div>

                {/* How it works card */}
                <div className="w-full shrink-0 rounded-2xl border border-gray-200 bg-gray-50/80 p-5 shadow-inner lg:w-80">
                  <div className="mb-4 text-xs font-bold uppercase tracking-wider text-gray-500">
                    How It Works
                  </div>
                  <div className="flex flex-col gap-4">
                    {[
                      "Create agent",
                      "Fund it",
                      "Set hard limits",
                      "Choose agent or Razorpay at checkout",
                    ].map((step, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white border border-gray-200 shadow-sm text-xs font-bold text-fuchsia-600">
                          {i + 1}
                        </div>
                        <span className="text-sm font-medium text-gray-700">
                          {step}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </section>

            {/* Sticky Search Row */}
            <section className="sticky top-[64px] z-40 mt-8 py-4 bg-gray-50/95 backdrop-blur-xl">
              <div className="flex w-full items-center gap-3">
                <div className="relative flex-1 group shadow-sm rounded-full">
                  <Search
                    size={20}
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 transition-colors group-focus-within:text-fuchsia-500"
                  />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && search()}
                    placeholder="Search milk, Maggi, juice, snacks…"
                    className="w-full rounded-full border border-gray-200 bg-white py-3.5 pl-12 pr-4 text-sm text-gray-900 placeholder-gray-400 outline-none transition-all focus:border-fuchsia-500 focus:ring-4 focus:ring-fuchsia-500/10 hover:border-gray-300"
                  />
                </div>
                <button
                  onClick={search}
                  disabled={loading}
                  className="shrink-0 rounded-full bg-gray-900 px-6 py-3.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-gray-800 active:scale-95 disabled:opacity-70 disabled:active:scale-100"
                >
                  {loading ? "Searching…" : "Search"}
                </button>
              </div>
            </section>

            {/* Product Catalog Grid */}
            {products.length > 0 && (
              <section className="mt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="mb-6 flex items-end justify-between">
                  <div>
                    <span className="mb-1 block text-xs font-bold uppercase tracking-wider text-fuchsia-600">
                      Catalog
                    </span>
                    <h2 className="text-2xl font-bold text-gray-900">
                      Products
                    </h2>
                  </div>
                  <span className="rounded-full bg-gray-200/60 px-3 py-1 text-xs font-medium text-gray-700">
                    {products.length} results
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:gap-6">
                  {products.map((p) => (
                    <ProductCard key={p.id} product={p} />
                  ))}
                </div>
              </section>
            )}

            {/* Agent Panel (Assumed to be a full-width section or modal) */}
            <div className="mt-12 border-t border-gray-200 pt-12">
              <AgentPanel />
            </div>
          </div>
        </main>
      </SignedIn>
    </div>
  );
}
