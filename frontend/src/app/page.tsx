"use client";

import { useCallback, useEffect, useState } from "react";
import { SignedIn, SignedOut, UserButton } from "@clerk/nextjs";
import {
  Search,
  ShoppingBag,
  Bot,
  ShieldCheck,
  ArrowRight,
} from "lucide-react";
import ProductCard from "@/src/components/ProductCard";
import AgentPanel from "@/src/components/AgentPanel";
import { searchProducts } from "@/src/lib/api";
import type { Product } from "@/src/lib/types";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentId, setAgentId] = useState<string | null>(null);

  const search = useCallback(async () => {
    setLoading(true);

    try {
      const data = await searchProducts(query);
      setProducts(data.products ?? []);
    } catch (error) {
      window.alert(
        error instanceof Error ? error.message : "Search failed.",
      );
    } finally {
      setLoading(false);
    }
  }, [query]);

  return (
    <>
      <SignedOut>
        <main className="shell auth-shell">
          <div className="auth-card">
            <div className="brand-mark">U</div>
            <h1>Umon Mart</h1>
            <p>
              Shop normally today. Create a bounded purchasing agent
              that can later connect to AI clients through MCP.
            </p>
            <a className="primary-button" href="/sign-in">
              Sign in <ArrowRight size={17} />
            </a>
          </div>
        </main>
      </SignedOut>

      <SignedIn>
        <main className="shell">
          <header className="topbar">
            <div className="brand">
              <div className="brand-mark small">U</div>
              <div>
                <strong>Umon Mart</strong>
                <span>AI-native commerce</span>
              </div>
            </div>

            <div className="topbar-actions">
              <a className="icon-link" href="/agents">
                <Bot size={18} />
                Agents
              </a>
              <UserButton />
            </div>
          </header>

          <section className="hero">
            <div>
              <span className="eyebrow">
                ONE MERCHANT • AI READY
              </span>

              <h1>
                Shop normally.
                <br />
                Let your agent shop smarter.
              </h1>

              <p>
                Browse products, fund a purchasing agent, set hard
                spending rules, and later connect that same identity
                to ChatGPT through MCP.
              </p>

              <div className="hero-badges">
                <span>
                  <ShieldCheck size={15} />
                  Backend-enforced guardrails
                </span>
                <span>
                  <ShoppingBag size={15} />
                  Razorpay test funding
                </span>
              </div>
            </div>

            <div className="hero-card">
              <div className="hero-card-label">HOW IT WORKS</div>
              <div className="flow">
                <div>1. Create agent</div>
                <div>2. Fund it</div>
                <div>3. Set hard limits</div>
                <div>4. Connect to AI</div>
              </div>
            </div>
          </section>

          <section className="search-row">
            <div className="search-box">
              <Search size={18} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && search()}
                placeholder="Search milk, Maggi, juice, snacks…"
              />
            </div>

            <button
              className="primary-button"
              onClick={search}
              disabled={loading}
            >
              {loading ? "Searching…" : "Search"}
            </button>
          </section>

          {products.length > 0 && (
            <section>
              <div className="section-heading">
                <div>
                  <span className="eyebrow">CATALOG</span>
                  <h2>Products</h2>
                </div>
                <span className="muted">
                  {products.length} results
                </span>
              </div>

              <div className="product-grid">
                {products.map((product) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    agentId={agentId}
                  />
                ))}
              </div>
            </section>
          )}

          <AgentPanel
            onAgentReady={setAgentId}
          />
        </main>
      </SignedIn>
    </>
  );
}
