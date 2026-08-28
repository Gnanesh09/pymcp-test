import { NextResponse } from "next/server";

type OAuthCompleteBody = {
  client_id: string;
  redirect_uri: string;
  scope: string;
  state: string;
  code_challenge: string;
  code_challenge_method: string;
  clerk_token: string;
};

const MCP_SERVER_URL = (
  process.env.MCP_SERVER_URL ||
  process.env.NEXT_PUBLIC_MCP_BASE_URL ||
  "http://localhost:8002"
).replace(/\/$/, "");

const CHATGPT_HOSTS = new Set(["chatgpt.com", "chat.openai.com"]);

export async function POST(request: Request) {
  try {
    const form = await request.formData();

    const body: OAuthCompleteBody = {
      client_id: String(form.get("client_id") || ""),
      redirect_uri: String(form.get("redirect_uri") || ""),
      scope: String(form.get("scope") || "umon"),
      state: String(form.get("state") || ""),
      code_challenge: String(form.get("code_challenge") || ""),
      code_challenge_method: String(
        form.get("code_challenge_method") || "S256",
      ),
      clerk_token: String(form.get("clerk_token") || ""),
    };

    if (
      !body.client_id ||
      !body.redirect_uri ||
      !body.clerk_token ||
      !body.code_challenge
    ) {
      return NextResponse.json(
        {
          detail: "Incomplete OAuth completion request.",
        },
        { status: 400 },
      );
    }

    /*
     * Never allow the upstream OAuth server to redirect this request
     * somewhere unexpected.
     */
    const redirect = new URL(body.redirect_uri);

    if (!CHATGPT_HOSTS.has(redirect.hostname.toLowerCase())) {
      return NextResponse.json(
        {
          detail: "OAuth redirect URI must belong to ChatGPT.",
        },
        { status: 400 },
      );
    }

    const upstream = await fetch(`${MCP_SERVER_URL}/oauth/complete`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        client_id: body.client_id,
        redirect_uri: body.redirect_uri,
        scope: body.scope,
        state: body.state || null,
        code_challenge: body.code_challenge || null,
        code_challenge_method: body.code_challenge_method || "S256",
        clerk_token: body.clerk_token,
      }),
      redirect: "manual",
      cache: "no-store",
    });

    /*
     * Successful OAuth completion must be a redirect response.
     */
    if (upstream.status < 300 || upstream.status >= 400) {
      let message = `MCP OAuth completion failed (${upstream.status}).`;

      try {
        const data = (await upstream.json()) as {
          detail?: string;
          message?: string;
        };

        message = data.detail || data.message || message;
      } catch {
        // Keep default message.
      }

      console.error("MCP OAuth completion rejected:", upstream.status, message);

      return NextResponse.json(
        {
          detail: message,
        },
        {
          status: upstream.status,
        },
      );
    }

    const location = upstream.headers.get("location");

    if (!location) {
      console.error("MCP OAuth completion returned no Location header.");

      return NextResponse.json(
        {
          detail: "MCP OAuth server did not return a redirect location.",
        },
        {
          status: 502,
        },
      );
    }

    /*
     * Protect against an incorrect backend redirect.
     */
    const finalUrl = new URL(location);

    if (!CHATGPT_HOSTS.has(finalUrl.hostname.toLowerCase())) {
      console.error("Unexpected OAuth redirect:", location);

      return NextResponse.json(
        {
          detail: "Umon returned an unexpected OAuth redirect.",
        },
        {
          status: 502,
        },
      );
    }

    console.log(
      "Umon OAuth complete → ChatGPT:",
      finalUrl.origin,
      finalUrl.pathname,
    );

    /*
     * Return JSON because the client is performing a native top-level
     * navigation after receiving this response.
     */
    return NextResponse.json({
      redirect_url: location,
    });
  } catch (error) {
    console.error("Umon OAuth completion route failed:", error);

    return NextResponse.json(
      {
        detail:
          error instanceof Error
            ? error.message
            : "Unable to complete Umon OAuth connection.",
      },
      {
        status: 500,
      },
    );
  }
}
