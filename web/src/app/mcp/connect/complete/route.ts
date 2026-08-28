import { NextResponse } from "next/server";

type CompleteBody = {
  client_id: string;
  redirect_uri: string;
  scope: string;
  state: string;
  code_challenge: string;
  code_challenge_method: string;
  clerk_token: string;
};

const MCP_BASE_URL =
  process.env.MCP_SERVER_URL ||
  process.env.NEXT_PUBLIC_MCP_BASE_URL ||
  "http://localhost:8002";

function isValidBody(body: Partial<CompleteBody>): body is CompleteBody {
  return Boolean(
    body.client_id &&
    body.redirect_uri &&
    body.scope &&
    body.clerk_token &&
    body.code_challenge,
  );
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Partial<CompleteBody>;

    if (!isValidBody(body)) {
      return NextResponse.json(
        {
          detail: "Incomplete OAuth completion request.",
        },
        {
          status: 400,
        },
      );
    }

    /*
     * Server-to-server request.
     *
     * This avoids the browser CORS problem because the browser never
     * directly follows the MCP server's redirect to ChatGPT.
     */
    const upstream = await fetch(
      `${MCP_BASE_URL.replace(/\/$/, "")}/oauth/complete`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
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
      },
    );

    /*
     * The MCP backend should return a 302/303 to ChatGPT.
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
        // Keep default error.
      }

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
     * We return the redirect URL as JSON to the client.
     *
     * The browser then performs a top-level navigation with
     * window.location.assign().
     */
    return NextResponse.json({
      redirect_url: location,
    });
  } catch (error) {
    console.error("MCP OAuth completion failed:", error);

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
