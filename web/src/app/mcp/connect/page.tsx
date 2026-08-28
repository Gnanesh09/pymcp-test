"use client";

import { useCallback, useEffect, useState } from "react";
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

function readOAuthParams(): OAuthParams | null {
  if (typeof window === "undefined") {
    return null;
  }

  const search = new URLSearchParams(window.location.search);

  const client_id = search.get("client_id")?.trim() ?? "";
  const redirect_uri = search.get("redirect_uri")?.trim() ?? "";
  const scope = search.get("scope")?.trim() || "umon";
  const state = search.get("state")?.trim() ?? "";
  const code_challenge = search.get("code_challenge")?.trim() ?? "";
  const code_challenge_method =
    search.get("code_challenge_method")?.trim() || "S256";

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
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const { redirectToSignIn } = useClerk();

  const [oauth, setOauth] = useState<OAuthParams | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = readOAuthParams();

    setOauth(params);

    if (!params) {
      setError(
        "This Umon connection request is incomplete or expired. Please start the connection again from ChatGPT.",
      );
    }

    setInitializing(false);
  }, []);

  const startSignIn = useCallback(async () => {
    try {
      await redirectToSignIn({
        signInForceRedirectUrl: window.location.href,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to open Umon sign-in.",
      );
    }
  }, [redirectToSignIn]);
  const completeConnection = useCallback(async () => {
    if (!oauth || connecting) {
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

      /*
       * Use a native browser form POST instead of fetch().
       *
       * The Next.js /mcp/connect/complete route will perform the
       * server-to-server OAuth completion and return the ChatGPT
       * redirect URL.
       *
       * Native navigation avoids the cross-origin fetch/CORS problem
       * we previously hit with chatgpt.com.
       */
      const form = document.createElement("form");

      form.method = "POST";
      form.action = "/mcp/connect/complete";
      form.style.display = "none";

      const fields: Record<string, string> = {
        client_id: oauth.client_id,
        redirect_uri: oauth.redirect_uri,
        scope: oauth.scope,
        state: oauth.state || "",
        code_challenge: oauth.code_challenge || "",
        code_challenge_method: oauth.code_challenge_method || "S256",
        clerk_token: clerkToken,
      };

      for (const [name, value] of Object.entries(fields)) {
        const input = document.createElement("input");

        input.type = "hidden";
        input.name = name;
        input.value = value;

        form.appendChild(input);
      }

      document.body.appendChild(form);

      form.submit();
    } catch (err) {
      setConnecting(false);

      setError(
        err instanceof Error ? err.message : "Unable to connect Umon Mart.",
      );
    }
  }, [connecting, getToken, oauth]);

  /*
   * If the user is already authenticated with Clerk,
   * complete the OAuth transaction automatically.
   *
   * This is why you saw your email immediately before.
   * An existing Clerk browser session means we don't need
   * to show the login screen again.
   */
  useEffect(() => {
    if (!isLoaded || !oauth || !isSignedIn || connecting || error) {
      return;
    }

    void completeConnection();
  }, [isLoaded, oauth, isSignedIn, connecting, error, completeConnection]);

  if (initializing || !isLoaded) {
    return <LoadingScreen />;
  }

  if (!oauth) {
    return (
      <main className="min-h-screen bg-[#f7f8fa] px-5 py-10 text-slate-950">
        <div className="mx-auto flex min-h-[80vh] w-full max-w-[520px] items-center">
          <div className="w-full rounded-[28px] border border-slate-200 bg-white p-8 shadow-[0_24px_80px_rgba(15,23,42,0.08)] sm:p-10">
            <Brand />

            <p className="mt-7 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              Umon Mart
            </p>

            <h1 className="mt-2 text-2xl font-semibold tracking-tight">
              Invalid connection request
            </h1>

            <p className="mt-3 text-sm leading-6 text-slate-500">
              This ChatGPT connection request is missing required information.
              Please return to ChatGPT and start connecting Umon Mart again.
            </p>

            <div className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm font-medium text-amber-900">
                No access was granted.
              </p>
            </div>
          </div>
        </div>
      </main>
    );
  }

  if (!isSignedIn) {
    return (
      <main className="min-h-screen bg-[#f7f8fa] px-5 py-10 text-slate-950">
        <div className="mx-auto flex min-h-[80vh] w-full max-w-[560px] items-center">
          <div className="w-full overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.09)]">
            <div className="p-8 sm:p-10">
              <div className="flex items-center justify-between">
                <Brand />

                <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-500">
                  Secure connection
                </div>
              </div>

              <div className="mt-8">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Connect your account
                </p>

                <h1 className="mt-2 text-[32px] font-semibold tracking-[-0.035em]">
                  Connect Umon Mart
                </h1>

                <p className="mt-3 text-[15px] leading-7 text-slate-500">
                  Sign in with your existing Umon Mart account to let ChatGPT
                  work with your Umon shopping account.
                </p>
              </div>

              <div className="mt-8 space-y-3">
                <PermissionRow
                  icon={<ShoppingBag className="h-4 w-4" />}
                  title="Your Umon shopping account"
                  description="Your products, shared cart and orders remain tied to your Umon account."
                />

                <PermissionRow
                  icon={<Sparkles className="h-4 w-4" />}
                  title="AI-powered shopping"
                  description="ChatGPT can search products, compare options and work with your purchasing agents."
                />

                <PermissionRow
                  icon={<ShieldCheck className="h-4 w-4" />}
                  title="Policy-protected purchases"
                  description="Umon enforces your agent limits, category rules, balances and merchant controls."
                />
              </div>

              {error && <ErrorBox message={error} />}

              <button
                type="button"
                onClick={startSignIn}
                className="
                  mt-8 flex h-12 w-full items-center justify-center gap-2
                  rounded-2xl bg-slate-950 px-5
                  text-sm font-semibold text-white
                  transition hover:bg-slate-800
                  active:scale-[0.99]
                "
              >
                Sign in to continue
                <ArrowRight className="h-4 w-4" />
              </button>

              <p className="mt-4 text-center text-xs leading-5 text-slate-400">
                After signing in, you will automatically return here to finish
                connecting ChatGPT.
              </p>
            </div>

            <SecurityFooter />
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f7f8fa] px-5 py-10 text-slate-950">
      <div className="mx-auto flex min-h-[80vh] w-full max-w-[560px] items-center">
        <div className="w-full rounded-[28px] border border-slate-200 bg-white p-8 shadow-[0_24px_80px_rgba(15,23,42,0.09)] sm:p-10">
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
            {connecting ? "Connecting Umon Mart…" : "Ready to connect"}
          </h1>

          <p className="mt-3 text-sm leading-6 text-slate-500">
            {connecting
              ? "Securely linking your Umon account with ChatGPT."
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

          {error && <ErrorBox message={error} />}

          {!error && (
            <div className="mt-6 rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />

                <div>
                  <p className="text-sm font-semibold text-emerald-950">
                    Secure account binding
                  </p>

                  <p className="mt-1 text-xs leading-5 text-emerald-800">
                    ChatGPT will access Umon through this authenticated account.
                    Purchases remain subject to Umon's guardrails.
                  </p>
                </div>
              </div>
            </div>
          )}

          {error && (
            <button
              type="button"
              onClick={() => {
                setError(null);
                setConnecting(false);
              }}
              className="mt-5 rounded-xl bg-slate-950 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-slate-800"
            >
              Try again
            </button>
          )}

          {!error && (
            <p className="mt-6 text-center text-xs text-slate-400">
              You will be returned to ChatGPT automatically.
            </p>
          )}
        </div>
      </div>
    </main>
  );
}

function Brand() {
  return (
    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-950 text-white">
      <span className="text-lg font-bold">U</span>
    </div>
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

        <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
      </div>
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-4">
      <p className="text-sm font-semibold text-red-900">Connection failed</p>

      <p className="mt-1 text-sm leading-5 text-red-700">{message}</p>
    </div>
  );
}

function SecurityFooter() {
  return (
    <div className="border-t border-slate-100 bg-slate-50/70 px-8 py-5 sm:px-10">
      <div className="flex items-start gap-3">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />

        <p className="text-xs leading-5 text-slate-500">
          Umon does not give ChatGPT unrestricted access to your account.
          Financial actions remain bounded by your purchasing-agent policies and
          Umon merchant controls.
        </p>
      </div>
    </div>
  );
}

function LoadingScreen() {
  return (
    <main className="min-h-screen bg-[#f7f8fa] flex items-center justify-center px-6">
      <div className="flex items-center gap-3 text-sm text-slate-500">
        <Loader2 className="h-5 w-5 animate-spin" />
        Preparing secure connection…
      </div>
    </main>
  );
}
