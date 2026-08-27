"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo } from "react";

const baseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api";

// ============================================================
// TYPES
// ============================================================

export type CategoryMode = "ALL" | "SELECTED";

export type AgentCreateInput = {
  name: string;
  description: string | null;

  max_transaction: number;
  daily_limit: number;

  auto_purchase: boolean;

  category_mode: CategoryMode;

  allowed_categories: string[];
  blocked_categories: string[];
};

export type AgentPolicyUpdateInput = {
  max_transaction?: number;
  daily_limit?: number;

  auto_purchase?: boolean;

  category_mode?: CategoryMode;

  allowed_categories?: string[];
  blocked_categories?: string[];
};

export type AgentUpdateInput = {
  name?: string;
  description?: string | null;
};

// ============================================================
// RAW REQUEST
// ============================================================

async function rawRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,

    headers: {
      ...(init?.body
        ? {
            "Content-Type": "application/json",
          }
        : {}),

      ...(init?.headers ?? {}),
    },

    cache: "no-store",
  });

  let data: unknown = null;

  try {
    data = await response.json();
  } catch {
    data = {
      detail: "Invalid server response.",
    };
  }

  if (!response.ok) {
    const errorData = data as {
      detail?: string;
      message?: string;
    };

    throw new Error(
      errorData?.detail ||
        errorData?.message ||
        `Request failed (${response.status})`,
    );
  }

  return data as T;
}

// ============================================================
// AUTHENTICATED API
// ============================================================

export function useUmonApi() {
  const { getToken } = useAuth();

  const authRequest = async <T>(
    path: string,
    init?: RequestInit,
  ): Promise<T> => {
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
  };

  return useMemo(
    () => ({
      // ======================================================
      // USER
      // ======================================================

      me: () =>
        authRequest<{
          success: boolean;
          user: any;
        }>("/me"),

      // ======================================================
      // AGENTS
      // ======================================================

      agents: () => authRequest<any>("/agents"),

      agent: (id: string) =>
        authRequest<any>(`/agents/${encodeURIComponent(id)}`),

      adminDashboard: () => authRequest<any>("/admin/dashboard"),

      adminMerchant: () => authRequest<any>("/admin/merchant"),

      updateAdminMerchant: (body: {
        name?: string;
        status?: "ACTIVE" | "DISABLED";
        ai_discovery?: boolean;
        ai_purchasing?: boolean;
        ai_checkout?: boolean;
        recommendations_enabled?: boolean;
        max_order_value?: number;
        allowed_categories?: string[];
      }) =>
        authRequest<any>("/admin/merchant", {
          method: "PATCH",
          body: JSON.stringify(body),
        }),

      adminProducts: (query = "") =>
        authRequest<any>(
          `/admin/products?q=${encodeURIComponent(
            query,
          )}&include_inactive=true`,
        ),

      adminCreateProduct: (body: {
        name: string;
        brand: string;
        category: string;
        price: number;
        mrp: number;
        stock: number;
        unit: string;
        description: string;
        image?: string | null;
        tags: string[];
      }) =>
        authRequest<any>("/admin/products", {
          method: "POST",
          body: JSON.stringify(body),
        }),

      adminUpdateProduct: (
        productId: string,
        body: {
          name?: string;
          brand?: string;
          category?: string;
          price?: number;
          mrp?: number;
          stock?: number;
          unit?: string;
          description?: string;
          image?: string | null;
          tags?: string[];
          active?: boolean;
        },
      ) =>
        authRequest<any>(`/admin/products/${encodeURIComponent(productId)}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        }),

      adminDeleteProduct: (productId: string) =>
        authRequest<any>(`/admin/products/${encodeURIComponent(productId)}`, {
          method: "DELETE",
        }),

      adminOrders: () => authRequest<any>("/admin/orders?limit=300"),

      adminPayments: () => authRequest<any>("/admin/payments?limit=300"),

      adminUsers: (query = "") =>
        authRequest<any>(`/admin/users?q=${encodeURIComponent(query)}`),

      adminAgents: () => authRequest<any>("/admin/agents?limit=300"),

      adminAudit: () => authRequest<any>("/admin/audit?limit=300"),

      agentStats: (id: string) =>
        authRequest<any>(`/agents/${encodeURIComponent(id)}/stats`),

      createAgent: (body: AgentCreateInput) =>
        authRequest<any>("/agents", {
          method: "POST",
          body: JSON.stringify(body),
        }),

      updateAgent: (id: string, body: AgentUpdateInput) =>
        authRequest<any>(`/agents/${encodeURIComponent(id)}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        }),

      updateAgentPolicy: (
        agentId: string,
        body: {
          max_transaction?: number;
          daily_limit?: number;
          auto_purchase?: boolean;
          category_mode?: "ALL" | "SELECTED";
          allowed_categories?: string[];
          blocked_categories?: string[];
        },
      ) =>
        authRequest<any>(`/agents/${encodeURIComponent(agentId)}/policy`, {
          method: "PATCH",
          body: JSON.stringify(body),
        }),

      updateAgentStatus: (
        id: string,
        status: "ACTIVE" | "DISABLED" | "REVOKED",
      ) =>
        authRequest<any>(`/agents/${encodeURIComponent(id)}/status`, {
          method: "PATCH",
          body: JSON.stringify({
            status,
          }),
        }),

      deleteAgent: (id: string) =>
        authRequest<any>(`/agents/${encodeURIComponent(id)}`, {
          method: "DELETE",
        }),

      // ======================================================
      // AGENT FUNDING
      // ======================================================

      createFundingOrder: (agentId: string, amount: number) =>
        authRequest<any>(
          `/agents/${encodeURIComponent(agentId)}/funding-order`,
          {
            method: "POST",
            body: JSON.stringify({
              amount,
            }),
          },
        ),

      verifyFunding: (
        agentId: string,
        body: {
          payment_id: string;
          razorpay_order_id: string;
          razorpay_payment_id: string;
          razorpay_signature: string;
        },
      ) =>
        authRequest<any>(
          `/agents/${encodeURIComponent(agentId)}/funding/verify`,
          {
            method: "POST",
            body: JSON.stringify(body),
          },
        ),

      // ======================================================
      // SHARED CART
      //
      // IMPORTANT:
      // There is intentionally NO agentId here.
      // ======================================================

      cart: () => authRequest<any>("/cart"),

      addToCart: (productId: string, quantity: number) =>
        authRequest<any>("/cart/items", {
          method: "POST",
          body: JSON.stringify({
            product_id: productId,
            quantity,
          }),
        }),

      updateCartItem: (productId: string, quantity: number) =>
        authRequest<any>(`/cart/items/${encodeURIComponent(productId)}`, {
          method: "PATCH",
          body: JSON.stringify({
            quantity,
          }),
        }),

      removeCartItem: (productId: string) =>
        authRequest<any>(`/cart/items/${encodeURIComponent(productId)}`, {
          method: "DELETE",
        }),

      clearCart: () =>
        authRequest<any>("/cart/clear", {
          method: "POST",
        }),

      // ======================================================
      // CHECKOUT — AGENT BALANCE
      //
      // Agent is chosen ONLY here.
      // ======================================================

      checkoutWithAgentBalance: (agentId: string, confirmed = false) =>
        authRequest<any>("/checkout/agent-balance", {
          method: "POST",
          body: JSON.stringify({
            agent_id: agentId,
            confirmed,
          }),
        }),

      // ======================================================
      // CHECKOUT — DIRECT RAZORPAY
      // ======================================================

      createRazorpayCheckout: () =>
        authRequest<any>("/checkout/razorpay", {
          method: "POST",
        }),

      verifyRazorpayCheckout: (body: {
        payment_id: string;
        razorpay_order_id: string;
        razorpay_payment_id: string;
        razorpay_signature: string;
      }) =>
        authRequest<any>("/checkout/razorpay/verify", {
          method: "POST",
          body: JSON.stringify(body),
        }),

      // ======================================================
      // ORDERS
      // ======================================================

      orders: () => authRequest<any>("/orders"),

      order: (id: string) =>
        authRequest<any>(`/orders/${encodeURIComponent(id)}`),

      // ======================================================
      // AUDIT
      // ======================================================

      audit: (agentId?: string) =>
        authRequest<any>(
          agentId ? `/audit?agent_id=${encodeURIComponent(agentId)}` : "/audit",
        ),
    }),

    [getToken],
  );
}

// ============================================================
// PUBLIC CATALOG
// ============================================================

export async function searchProducts(query = "") {
  return rawRequest<any>(`/products?q=${encodeURIComponent(query)}`);
}

export async function getRecommendations(productId: string) {
  return rawRequest<any>(
    `/products/${encodeURIComponent(productId)}/recommendations`,
  );
}
