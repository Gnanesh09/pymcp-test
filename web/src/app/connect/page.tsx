"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth, useClerk, useUser } from "@clerk/nextjs";
import {
  ArrowRight,
  Check,
  Loader2,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  WalletCards,
} from "lucide-react";

type OAuthParams = {
  client_id: string;
  redirect_uri: string;
  scope: string;
  state: string;
  code_challenge: string;
  code_challenge_method: string;
};

type CompleteResponse = {
  success?: boolean;
  detail?: string;
  message?: string;
};

const MCP_BASE_URL = (
  process.env.NEXT_PUBLIC_MCP_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/api\/?$/, "") ||
  "http://localhost:8002"
).replace(/\/$/, "");

function getOAuthParams(): OAuthParams | null {
  if (typeof window === "undefined") {
    return null;
  }

  const params = new URLSearchParams(window.location.search);

  const client_id = params.get("client_id") || "";
  const redirect_uri = params.get("redirect_uri") || "";
  const scope = params.get("scope") || "umon";
  const state = params.get("state") || "";
  const code_challenge = params.get("code_challenge") || "";
  const code_challenge_method = params.get("code_challenge_method") || "S256";

  if (!client_id || !redirect_uri) {
    return null;
  }

  return {
    client_id,
    redirect_uri,
    scope,
    state,
    code_challenge,
    code_challenge_method,
  };
}

export default function MCPConnectPage() {
  const { isLoaded: authLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const { redirectToSignIn } = useClerk();

  const [oauth, setOauth] = useState<OAuthParams | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const returnUrl = useMemo(() => {
    if (typeof window === "undefined") {
      return "";
    }

    return window.location.href;
  }, []);

  useEffect(() => {
    const params = getOAuthParams();

    if (!params) {
      setError(
        "This connection request is incomplete or has expired. Please start the connection again from ChatGPT.",
      );
    }

    setOauth(params);
    setLoading(false);
  }, []);

  const startSignIn = useCallback(async () => {
    if (!returnUrl) {
      return;
    }

    try {
      await redirectToSignIn({
        signInForceRedirectUrl: returnUrl,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to open Umon sign-in.",
      );
    }
  }, [redirectToSignIn, returnUrl]);

  const completeConnection = useCallback(async () => {
    if (!oauth) {
      return;
    }

    setConnecting(true);
    setError(null);

    try {
      const clerkToken = await getToken();

      if (!clerkToken) {
        throw new Error(
          "Your Umon session could not be verified. Please sign in again.",
        );
      }

      const response = await fetch(`${MCP_BASE_URL}/oauth/complete`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          client_id: oauth.client_id,
          redirect_uri: oauth.redirect_uri,
          scope: oauth.scope,
          state: oauth.state || null,
          code_challenge: oauth.code_challenge || null,
          code_challenge_method: oauth.code_challenge_method || "S256",
          clerk_token: clerkToken,
        }),
        cache: "no-store",
      });

      /*
       * IMPORTANT:
       *
       * /oauth/complete intentionally returns a 302 redirect
       * to ChatGPT with:
       *
       *   ?code=...
       *   &state=...
       *
       * fetch() follows that redirect internally.
       *
       * Therefore, after successful completion we explicitly
       * navigate to the final response URL.
       */

      if (!response.ok) {
        let message = `Connection failed (${response.status}).`;

        try {
          const data = (await response.json()) as CompleteResponse;

          message = data.detail || data.message || message;
        } catch {
          // Keep the default error message.
        }

        throw new Error(message);
      }

      /*
       * Because browsers don't expose the final redirect URL
       * in a way we should depend on here, use the redirect
       * response URL supplied by fetch.
       */
      if (response.url && response.url !== `${MCP_BASE_URL}/oauth/complete`) {
        window.location.assign(response.url);
        return;
      }

      throw new Error(
        "Umon approved the connection, but the redirect to ChatGPT could not be completed.",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to connect Umon Mart.",
      );
      setConnecting(false);
    }
  }, [getToken, oauth]);

  /*
   * Automatically complete the OAuth transaction once the
   * user has authenticated.
   *
   * This is important when ChatGPT sends the user to Umon
   * and they were already signed in.
   */
  useEffect(() => {
    if (!authLoaded || !oauth || !isSignedIn || connecting || error) {
      return;
    }

    void completeConnection();
  }, [authLoaded, oauth, isSignedIn, connecting, error, completeConnection]);

  if (loading || !authLoaded) {
    return (
      <main className="min-h-screen bg-[#f7f8fa] text-[#101828] flex items-center justify-center px-6">
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          Preparing secure connection…
        </div>
      </main>
    );
  }

  if (!oauth) {
    return (
      <main className="min-h-screen bg-[#f7f8fa] text-[#101828] flex items-center justify-center px-6">
        <section className="w-full max-w-[520px]">
          <div className="rounded-[28px] border border-slate-200 bg-white p-8 shadow-[0_24px_70px_rgba(15,23,42,0.08)]">
            <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-950 text-white">
              <ShoppingBag className="h-6 w-6" />
            </div>

            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              Umon Mart
            </p>

            <h1 className="text-2xl font-semibold tracking-tight">
              Invalid connection request
            </h1>

            <p className="mt-3 text-sm leading-6 text-slate-500">
              This Umon connection request is missing required OAuth
              information. Return to ChatGPT and start the connection again.
            </p>

            <div className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              The connection was not approved and no access token was issued.
            </div>
          </div>
        </section>
      </main>
    );
  }

  /*
   * User isn't signed in.
   *
   * Keep the complete OAuth query string in returnBackUrl so
   * Clerk returns the user to THIS exact connection request.
   */
  if (!isSignedIn) {
    return (
      <main className="min-h-screen bg-[#f7f8fa] text-[#101828] flex items-center justify-center px-6 py-10">
        <section className="w-full max-w-[520px]">
          <div className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.09)]">
            <div className="p-8 sm:p-10">
              <div className="mb-8 flex items-center justify-between">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-sm">
                  <span className="text-lg font-bold">U</span>
                </div>

                <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-500">
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                  Secure connection
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Connect your account
                </p>

                <h1 className="mt-2 text-[30px] font-semibold tracking-[-0.03em] text-slate-950">
                  Connect Umon Mart
                </h1>

                <p className="mt-3 text-[15px] leading-6 text-slate-500">
                  Sign in with your existing Umon Mart account to let ChatGPT
                  access your Umon shopping experience securely.
                </p>
              </div>

              <div className="mt-7 space-y-3">
                <PermissionRow
                  icon={<ShoppingBag className="h-4 w-4" />}
                  title="Your Umon shopping account"
                  description="Your products, cart and orders remain tied to your Umon account."
                />

                <PermissionRow
                  icon={<Sparkles className="h-4 w-4" />}
                  title="AI shopping"
                  description="ChatGPT can search products and use your connected purchasing agents."
                />

                <PermissionRow
                  icon={<ShieldCheck className="h-4 w-4" />}
                  title="Policy-protected purchases"
                  description="Agent limits and merchant rules are enforced by Umon."
                />
              </div>

              <button
                type="button"
                onClick={startSignIn}
                className="mt-8 flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-950 px-5 py-3.5 text-sm font-semibold text-white transition hover:bg-slate-800 active:scale-[0.99]"
              >
                Sign in to continue
                <ArrowRight className="h-4 w-4" />
              </button>

              <p className="mt-4 text-center text-xs leading-5 text-slate-400">
                You will return here automatically after signing in.
              </p>
            </div>

            <div className="border-t border-slate-100 bg-slate-50/70 px-8 py-5">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />

                <p className="text-xs leading-5 text-slate-500">
                  Umon never gives ChatGPT unrestricted access to your account.
                  Financial actions remain subject to your purchasing-agent
                  policies and Umon merchant controls.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>
    );
  }

  /*
   * Signed in + OAuth request is valid.
   *
   * The effect above will automatically complete the OAuth
   * transaction. This screen is therefore intentionally
   * simple and reassuring.
   */
  return (
    <main className="min-h-screen bg-[#f7f8fa] text-[#101828] flex items-center justify-center px-6 py-10">
      <section className="w-full max-w-[520px]">
        <div className="rounded-[28px] border border-slate-200 bg-white p-8 shadow-[0_24px_80px_rgba(15,23,42,0.09)] sm:p-10">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50">
            {connecting ? (
              <Loader2 className="h-6 w-6 animate-spin text-emerald-600" />
            ) : (
              <Check className="h-6 w-6 text-emerald-600" />
            )}
          </div>

          <p className="mt-7 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Umon Mart
          </p>

          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            {connecting ? "Connecting your account…" : "Ready to connect"}
          </h1>

          <p className="mt-3 text-sm leading-6 text-slate-500">
            {connecting
              ? `Securely linking ${
                  user?.primaryEmailAddress?.emailAddress || "your Umon account"
                } with ChatGPT.`
              : "Your Umon account is authenticated."}
          </p>

          <div className="mt-7 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white shadow-sm">
                <WalletCards className="h-5 w-5 text-slate-700" />
              </div>

              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-900">
                  ChatGPT → Umon Mart
                </p>

                <p className="mt-0.5 truncate text-xs text-slate-500">
                  {user?.primaryEmailAddress?.emailAddress ||
                    "Authenticated Umon user"}
                </p>
              </div>

              <Check className="ml-auto h-5 w-5 shrink-0 text-emerald-600" />
            </div>
          </div>

          {error && (
            <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-4">
              <p className="text-sm font-semibold text-red-900">
                Connection failed
              </p>

              <p className="mt-1 text-sm leading-5 text-red-700">{error}</p>

              <button
                type="button"
                onClick={() => {
                  setError(null);
                  setConnecting(false);
                }}
                className="mt-4 rounded-xl bg-red-900 px-4 py-2 text-xs font-semibold text-white hover:bg-red-800"
              >
                Try again
              </button>
            </div>
          )}

          {!error && (
            <p className="mt-6 text-center text-xs text-slate-400">
              You will be returned to ChatGPT automatically.
            </p>
          )}
        </div>
      </section>
    </main>
  );
}

function PermissionRow({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-3 rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-50 text-slate-600">
        {icon}
      </div>

      <div>
        <p className="text-sm font-semibold text-slate-900">{title}</p>

        <p className="mt-0.5 text-xs leading-5 text-slate-500">{description}</p>
      </div>
    </div>
  );
}
