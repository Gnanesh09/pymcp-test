"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ArrowLeft,
  CheckCircle2,
  PackageCheck,
  ChevronRight,
} from "lucide-react";

import { useUmonApi } from "@/src/lib/api";

type OrderItem = {
  product_id: string;
  name: string;
  quantity: number;
  line_total_paise: number;
};

type Order = {
  id: string;
  created_at: string;
  status: string;
  payment_method: string;
  amount: number;
  items: OrderItem[];
};

export default function OrdersPage() {
  const api = useUmonApi();

  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);

    try {
      const data = await api.orders();

      setOrders((data.orders ?? []) as Order[]);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="min-h-screen bg-[#f7f7f8] text-gray-900">
      {/* =====================================================
          HEADER
      ====================================================== */}

      <header className="sticky top-0 z-30 border-b border-gray-100 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-5">
          <a
            href="/"
            className="
              group flex items-center gap-2
              text-sm font-medium text-gray-600
              transition hover:text-[#6d28d9]
            "
          >
            <span
              className="
                flex h-9 w-9
                items-center justify-center
                rounded-full
                bg-gray-100
                transition
                group-hover:bg-[#f1eafd]
              "
            >
              <ArrowLeft size={17} />
            </span>

            <span className="hidden sm:block">Back to store</span>
          </a>

          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#f1eafd] text-[#6d28d9]">
              <PackageCheck size={18} />
            </div>

            <span className="text-sm font-medium text-gray-900">Orders</span>
          </div>

          <div className="w-[72px]" />
        </div>
      </header>

      {/* =====================================================
          CONTENT
      ====================================================== */}

      <div className="mx-auto max-w-5xl px-5 py-8 sm:py-10">
        {/* Heading */}

        <div className="mb-7">
          <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[#6d28d9]">
            Purchase history
          </div>

          <div className="flex items-end justify-between gap-4">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-gray-950 sm:text-[34px]">
                Your orders
              </h1>

              <p className="mt-2 text-sm text-gray-500">
                View your previous purchases and payment details.
              </p>
            </div>

            {orders.length > 0 && (
              <span className="shrink-0 rounded-full bg-white px-3 py-1.5 text-xs text-gray-500 shadow-sm ring-1 ring-gray-100">
                {orders.length} {orders.length === 1 ? "order" : "orders"}
              </span>
            )}
          </div>
        </div>

        {/* =====================================================
            LOADING
        ====================================================== */}

        {loading ? (
          <div className="flex min-h-[320px] items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-[#6d28d9]/15 border-t-[#6d28d9]" />

              <p className="text-sm text-gray-400">Loading orders...</p>
            </div>
          </div>
        ) : !orders.length ? (
          /* ===================================================
             EMPTY
          ==================================================== */

          <section
            className="
              flex min-h-[360px]
              flex-col items-center justify-center
              rounded-2xl
              border border-gray-100
              bg-white
              px-6
              text-center
              shadow-[0_2px_12px_rgba(0,0,0,0.035)]
            "
          >
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#f1eafd] text-[#6d28d9]">
              <PackageCheck size={27} />
            </div>

            <h2 className="mt-5 text-lg font-medium text-gray-900">
              No orders yet
            </h2>

            <p className="mt-1.5 max-w-sm text-sm leading-6 text-gray-500">
              Once you complete a purchase, your order history will appear here.
            </p>

            <a
              href="/"
              className="
                mt-6
                inline-flex h-10
                items-center gap-1
                rounded-xl
                bg-[#6d28d9]
                px-4
                text-sm font-medium
                text-white
                transition
                hover:bg-[#5b21b6]
              "
            >
              Browse store
              <ChevronRight size={15} />
            </a>
          </section>
        ) : (
          /* ===================================================
             ORDERS
          ==================================================== */

          <div className="space-y-4">
            {orders.map((order) => {
              const orderTotal = Number(order.amount ?? 0);

              return (
                <article
                  key={order.id}
                  className="
                    overflow-hidden
                    rounded-2xl
                    border border-gray-100
                    bg-white
                    shadow-[0_2px_12px_rgba(0,0,0,0.035)]
                    transition
                    hover:shadow-[0_6px_22px_rgba(0,0,0,0.05)]
                  "
                >
                  {/* =========================================
                      ORDER HEADER
                  ========================================== */}

                  <div className="flex flex-col gap-3 border-b border-gray-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#f1eafd] text-[#6d28d9]">
                        <PackageCheck size={17} />
                      </div>

                      <div>
                        <div className="text-sm font-medium text-gray-900">
                          #{order.id.slice(-8)}
                        </div>

                        <div className="mt-0.5 text-xs text-gray-400">
                          {new Date(order.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>

                    <div
                      className={`
                        inline-flex w-fit items-center gap-1.5
                        rounded-full
                        px-2.5 py-1
                        text-[10px]
                        font-medium
                        uppercase
                        tracking-wide
                        ${
                          order.status === "PAID" ||
                          order.status === "COMPLETED" ||
                          order.status === "SUCCESS"
                            ? "bg-emerald-50 text-emerald-600"
                            : "bg-gray-100 text-gray-500"
                        }
                      `}
                    >
                      <CheckCircle2 size={13} />

                      {order.status}
                    </div>
                  </div>

                  {/* =========================================
                      ITEMS
                  ========================================== */}

                  <div className="divide-y divide-gray-50 px-5">
                    {order.items.map((item) => (
                      <div
                        key={item.product_id}
                        className="
                          flex items-center
                          justify-between
                          gap-4
                          py-3.5
                        "
                      >
                        <div className="min-w-0">
                          <p className="text-sm text-gray-700">
                            <span className="text-gray-400">
                              {item.quantity} ×{" "}
                            </span>

                            <span className="font-medium text-gray-800">
                              {item.name}
                            </span>
                          </p>
                        </div>

                        <span className="shrink-0 text-sm font-medium text-gray-800">
                          ₹{(item.line_total_paise / 100).toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* =========================================
                      FOOTER
                  ========================================== */}

                  <div className="flex flex-col gap-3 border-t border-gray-100 bg-gray-50/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-2 text-xs text-gray-400">
                      <span>Paid via</span>

                      <span className="rounded-md bg-white px-2 py-1 font-medium text-gray-600 ring-1 ring-gray-100">
                        {order.payment_method}
                      </span>
                    </div>

                    <div className="flex items-center justify-between gap-6 sm:justify-end">
                      <span className="text-sm text-gray-500">Total</span>

                      <span className="text-lg font-semibold tracking-tight text-gray-950">
                        ₹{orderTotal.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
