"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo } from "react";

const baseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api";

async function rawRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  let data: any = null;
  try { data = await response.json(); } catch { data = { detail: "Invalid server response" }; }
  if (!response.ok) throw new Error(data?.detail || data?.message || "Request failed");
  return data as T;
}

export function useUmonApi() {
  const { getToken } = useAuth();

  const authRequest = async <T>(path: string, init?: RequestInit) => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Please sign in again.");
    return rawRequest<T>(path, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, ...(init?.headers ?? {}) },
    });
  };

  return useMemo(() => ({
    me: () => authRequest<any>("/me"),
    agents: () => authRequest<any>("/agents"),
    agent: (id: string) => authRequest<any>(`/agents/${encodeURIComponent(id)}`),
    agentStats: (id: string) => authRequest<any>(`/agents/${encodeURIComponent(id)}/stats`),
    createAgent: (body: any) => authRequest<any>("/agents", { method: "POST", body: JSON.stringify(body) }),
    updateAgent: (id: string, body: any) => authRequest<any>(`/agents/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
    deleteAgent: (id: string) => authRequest<any>(`/agents/${encodeURIComponent(id)}`, { method: "DELETE" }),
    updateStatus: (id: string, status: string) => authRequest<any>(`/agents/${encodeURIComponent(id)}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
    updatePolicy: (id: string, body: any) => authRequest<any>(`/agents/${encodeURIComponent(id)}/policy`, { method: "PATCH", body: JSON.stringify(body) }),
    createFundingOrder: (id: string, amount: number) => authRequest<any>(`/agents/${encodeURIComponent(id)}/funding-order`, { method: "POST", body: JSON.stringify({ amount }) }),
    verifyFunding: (id: string, body: any) => authRequest<any>(`/agents/${encodeURIComponent(id)}/funding/verify`, { method: "POST", body: JSON.stringify(body) }),
    cart: () => authRequest<any>("/cart"),
    addToCart: (productId: string, quantity: number) => authRequest<any>("/cart/items", { method: "POST", body: JSON.stringify({ product_id: productId, quantity }) }),
    updateCartItem: (productId: string, quantity: number) => authRequest<any>(`/cart/items/${encodeURIComponent(productId)}`, { method: "PATCH", body: JSON.stringify({ quantity }) }),
    removeCartItem: (productId: string) => authRequest<any>(`/cart/items/${encodeURIComponent(productId)}`, { method: "DELETE" }),
    clearCart: () => authRequest<any>("/cart/clear", { method: "POST" }),
    checkoutWithAgentBalance: (agentId: string, confirmed = false) => authRequest<any>("/checkout/agent-balance", { method: "POST", body: JSON.stringify({ agent_id: agentId, confirmed }) }),
    createRazorpayCheckout: () => authRequest<any>("/checkout/razorpay", { method: "POST" }),
    verifyRazorpayCheckout: (body: any) => authRequest<any>("/checkout/razorpay/verify", { method: "POST", body: JSON.stringify(body) }),
    orders: () => authRequest<any>("/orders"),
    order: (id: string) => authRequest<any>(`/orders/${encodeURIComponent(id)}`),
    audit: (agentId?: string) => authRequest<any>(agentId ? `/audit?agent_id=${encodeURIComponent(agentId)}` : "/audit"),
  }), [getToken]);
}

export async function searchProducts(query = "") {
  return rawRequest<any>(`/products?q=${encodeURIComponent(query)}`);
}

export async function getRecommendations(productId: string) {
  return rawRequest<any>(`/products/${encodeURIComponent(productId)}/recommendations`);
}
