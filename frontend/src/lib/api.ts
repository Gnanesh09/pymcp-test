"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo } from "react";

const baseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

async function rawRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  let data: any = null;
  try {
    data = await response.json();
  } catch {
    data = { detail: "Invalid server response" };
  }

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Request failed");
  }

  return data as T;
}

export function useUmonApi() {
  const { getToken } = useAuth();

  async function authRequest<T>(
    path: string,
    init?: RequestInit,
  ): Promise<T> {
    const token = await getToken();

    if (!token) {
      throw new Error("Your session has expired. Please sign in again.");
    }

    return rawRequest<T>(path, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init?.headers ?? {}),
      },
    });
  }

  return useMemo(() => ({
    me: () => authRequest<any>("/me"),

    agents: () => authRequest<any>("/agents"),

    agent: (id: string) =>
      authRequest<any>(`/agents/${encodeURIComponent(id)}`),

    createAgent: (body: any) =>
      authRequest<any>("/agents", {
        method: "POST",
        body: JSON.stringify(body),
      }),

    updatePolicy: (id: string, body: any) =>
      authRequest<any>(`/agents/${encodeURIComponent(id)}/policy`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),

    balance: (id: string) =>
      authRequest<any>(`/agents/${encodeURIComponent(id)}/balance`),

    createFundingOrder: (id: string, amount: number) =>
      authRequest<any>(`/agents/${encodeURIComponent(id)}/funding-order`, {
        method: "POST",
        body: JSON.stringify({ amount }),
      }),

    verifyFunding: (id: string, body: any) =>
      authRequest<any>(`/agents/${encodeURIComponent(id)}/funding/verify`, {
        method: "POST",
        body: JSON.stringify(body),
      }),

    addToCart: (agentId: string, productId: string, quantity: number) =>
      authRequest<any>(`/cart/items?agent_id=${encodeURIComponent(agentId)}`, {
        method: "POST",
        body: JSON.stringify({ product_id: productId, quantity }),
      }),

    cart: (agentId: string) =>
      authRequest<any>(`/cart?agent_id=${encodeURIComponent(agentId)}`),

    updateCartItem: (agentId: string, productId: string, quantity: number) =>
      authRequest<any>(`/cart/items/${encodeURIComponent(productId)}?agent_id=${encodeURIComponent(agentId)}`, {
        method: "PATCH",
        body: JSON.stringify({ product_id: productId, quantity }),
      }),

    removeCartItem: (agentId: string, productId: string) =>
      authRequest<any>(`/cart/items/${encodeURIComponent(productId)}?agent_id=${encodeURIComponent(agentId)}`, {
        method: "DELETE",
      }),

    clearCart: (agentId: string) =>
      authRequest<any>(`/cart/clear?agent_id=${encodeURIComponent(agentId)}`, {
        method: "POST",
      }),

    checkoutWithAgentBalance: (agentId: string, confirmed = false) =>
      authRequest<any>("/checkout/agent-balance", {
        method: "POST",
        body: JSON.stringify({ agent_id: agentId, confirmed }),
      }),

    orders: () => authRequest<any>("/orders"),
    order: (id: string) => authRequest<any>(`/orders/${encodeURIComponent(id)}`),
    audit: (agentId?: string) => authRequest<any>(agentId ? `/audit?agent_id=${encodeURIComponent(agentId)}` : "/audit"),
  }), [getToken]);

}

export async function searchProducts(query = "") {
  return rawRequest<any>(
    `/products?q=${encodeURIComponent(query)}`,
  );
}

export async function getRecommendations(productId: string) {
  return rawRequest<any>(
    `/products/${encodeURIComponent(productId)}/recommendations`,
  );
}
