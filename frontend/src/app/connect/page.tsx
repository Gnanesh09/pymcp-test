"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Check,
  ShieldCheck,
  ShoppingBag,
  Loader2,
  AlertCircle,
} from "lucide-react";
import {
  RedirectToSignIn,
  SignedIn,
  SignedOut,
  useAuth,
  UserButton,
} from "@clerk/nextjs";

export default function MCPConnectPage() {
  const searchParams = useSearchParams();
  const { getToken, isLoaded } = useAuth();

  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");

  const oauth = useMemo(() => {
    return {
      clientId: searchParams.get("client_id") || "",
      redirectUri: searchParams.get("redirect_uri") || "",
      scope: searchParams.get("scope") || "mcp",
      state: searchParams.get("state") || "",
      codeChallenge: searchParams.get("code_challenge") || "",
      codeChallengeMethod: searchParams.get("code_challenge_method") || "S256",
    };
  }, [searchParams]);

  const mcpBase =
    process.env.NEXT_PUBLIC_MCP_BASE_URL ||
    (
      process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api"
    ).replace(/\/api\/?$/, "");

  async function approve() {
    setError("");

    if (!oauth.clientId || !oauth.redirectUri) {
      setError("Invalid connection request.");
      return;
    }

    if (!oauth.codeChallenge) {
      setError("This connection is missing PKCE protection.");
      return;
    }

    if (!isLoaded) return;

    setConnecting(true);

    try {
      const token = await getToken();

      if (!token) {
        throw new Error(
          "Your Umon session could not be verified. Please sign in again.",
        );
      }

      const response = await fetch(`${mcpBase}/oauth/consent`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          clerk_token: token,
          client_id: oauth.clientId,
          redirect_uri: oauth.redirectUri,
          scope: oauth.scope,
          state: oauth.state || null,
          code_challenge: oauth.codeChallenge,
          code_challenge_method: oauth.codeChallengeMethod,
        }),
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            data?.message ||
            "Unable to approve the Umon connection.",
        );
      }

      if (!data?.redirect_to) {
        throw new Error("Umon did not return an OAuth callback URL.");
      }

      window.location.assign(data.redirect_to);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect Umon.");
      setConnecting(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-5 py-10 text-slate-950">
      <div className="mx-auto flex min-h-[80vh] max-w-xl items-center justify-center">
        <SignedOut>
          <RedirectToSignIn />
        </SignedOut>

        <SignedIn>
          <section className="w-full overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.10)]">
            <div className="border-b border-slate-100 px-7 py-6 sm:px-8">
              <div className="flex items-center justify-between">
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-slate-950 text-white">
                  U
                </div>
                <UserButton />
              </div>

              <p className="mt-7 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
                Umon Mart connection
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">
                Connect Umon to ChatGPT
              </h1>
              <p className="mt-3 text-sm leading-6 text-slate-500">
                Allow ChatGPT to use your Umon Mart account to discover
                products, manage your shared cart and request purchases through
                your existing purchasing agents.
              </p>
            </div>

            <div className="space-y-4 px-7 py-6 sm:px-8">
              <Permission
                icon={<ShoppingBag size={17} />}
                title="Discover products"
                text="Search live Umon catalog data, prices and availability."
              />

              <Permission
                icon={<Check size={17} />}
                title="Manage your cart"
                text="Add, update and remove items from your single shared cart."
              />

              <Permission
                icon={<ShieldCheck size={17} />}
                title="Use your purchasing agents"
                text="View the agents you own and their configured guardrails."
              />

              <Permission
                icon={<ShieldCheck size={17} />}
                title="Request purchases"
                text="Purchases are still subject to Umon's backend policy, balance and confirmation checks."
              />

              {error && (
                <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  <AlertCircle className="mt-0.5 shrink-0" size={17} />
                  <span>{error}</span>
                </div>
              )}

              <button
                type="button"
                onClick={approve}
                disabled={connecting || !isLoaded}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-950 px-5 py-3.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {connecting && <Loader2 size={16} className="animate-spin" />}
                {connecting ? "Connecting…" : "Approve connection"}
              </button>

              <p className="text-center text-[11px] leading-5 text-slate-400">
                You are connecting the same Umon account you use on the Umon
                storefront. Umon never gives ChatGPT your card details.
              </p>
            </div>
          </section>
        </SignedIn>
      </div>
    </main>
  );
}

function Permission({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div className="flex gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-slate-600 shadow-sm">
        {icon}
      </div>
      <div>
        <p className="text-sm font-semibold text-slate-900">{title}</p>
        <p className="mt-1 text-xs leading-5 text-slate-500">{text}</p>
      </div>
    </div>
  );
}
