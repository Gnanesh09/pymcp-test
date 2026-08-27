"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  ShoppingCart,
  Minus,
  Plus,
  Trash2,
  CreditCard,
  ShieldCheck,
  ChevronRight,
  Truck,
  Lock,
} from "lucide-react";

import { useUmonApi } from "@/src/lib/api";

export default function CartPage() {
  const api = useUmonApi();

  const [cart, setCart] = useState<any>(null);
  const [agents, setAgents] = useState<any[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<
    "AGENT_BALANCE" | "RAZORPAY"
  >("AGENT_BALANCE");
  const [agentId, setAgentId] = useState("");
  const [decision, setDecision] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [cartData, agentsData] = await Promise.all([
      api.cart(),
      api.agents(),
    ]);

    setCart(cartData.cart);

    const list = agentsData.agents ?? [];
    setAgents(list);

    setAgentId(
      (cur) =>
        cur ||
        list.find((a: any) => a.status === "ACTIVE")?.id ||
        list[0]?.id ||
        "",
    );
  }, [api]);

  useEffect(() => {
    load().catch((e) =>
      alert(e instanceof Error ? e.message : "Unable to load cart."),
    );
  }, [load]);

  async function change(productId: string, quantity: number) {
    setBusy(true);

    try {
      setCart((await api.updateCartItem(productId, quantity)).cart);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Unable to update cart.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(productId: string) {
    setBusy(true);

    try {
      setCart((await api.removeCartItem(productId)).cart);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Unable to remove item.");
    } finally {
      setBusy(false);
    }
  }

  async function startRazorpay() {
    setBusy(true);
    setDecision(null);

    try {
      if (!window.Razorpay) {
        throw new Error("Razorpay Checkout has not loaded yet.");
      }

      const order = await api.createRazorpayCheckout();

      const checkout = new window.Razorpay({
        key: order.key_id,
        amount: order.amount_paise,
        currency: order.currency,
        name: "Umon Mart",
        description: "Umon Mart order",
        order_id: order.razorpay_order_id,

        handler: async (resp: any) => {
          try {
            const result = await api.verifyRazorpayCheckout({
              payment_id: order.payment_id,
              razorpay_order_id: resp.razorpay_order_id,
              razorpay_payment_id: resp.razorpay_payment_id,
              razorpay_signature: resp.razorpay_signature,
            });

            setDecision({
              success: true,
              status: "PAID",
              order: result,
            });

            await load();
          } catch (e) {
            setDecision({
              success: false,
              status: "FAILED",
              reason:
                e instanceof Error ? e.message : "Payment verification failed.",
            });
          } finally {
            setBusy(false);
          }
        },

        modal: {
          ondismiss: () => setBusy(false),
        },

        theme: {
          color: "#6D28D9",
        },
      });

      checkout.open();
    } catch (e) {
      setBusy(false);

      setDecision({
        success: false,
        status: "FAILED",
        reason: e instanceof Error ? e.message : "Unable to start Razorpay.",
      });
    }
  }

  async function agentCheckout(confirmed = false) {
    if (!agentId) {
      setDecision({
        success: false,
        status: "BLOCK",
        policy: {
          reason: "Select an active purchasing agent.",
        },
      });

      return;
    }

    setBusy(true);
    setDecision(null);

    try {
      setDecision(await api.checkoutWithAgentBalance(agentId, confirmed));
      await load();
    } catch (e) {
      setDecision({
        success: false,
        status: "ERROR",
        policy: {
          reason: e instanceof Error ? e.message : "Checkout failed.",
        },
      });
    } finally {
      setBusy(false);
    }
  }

  if (!cart) {
    return (
      <main className="min-h-screen bg-[#f7f7f8]">
        <div className="mx-auto flex min-h-screen max-w-3xl items-center justify-center px-5">
          <div className="flex flex-col items-center gap-3">
            <div className="h-10 w-10 animate-spin rounded-full border-4 border-[#6d28d9]/20 border-t-[#6d28d9]" />
            <p className="text-sm font-medium text-gray-500">
              Loading your cart...
            </p>
          </div>
        </div>
      </main>
    );
  }

  const total = ((cart.total_paise ?? 0) / 100).toFixed(2);
  const subtotal = ((cart.subtotal_paise ?? 0) / 100).toFixed(2);
  const delivery = ((cart.delivery_fee_paise ?? 0) / 100).toFixed(2);

  return (
    <main className="min-h-screen bg-[#f7f7f8] pb-32">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-gray-100 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6">
          <a
            href="/"
            className="group flex items-center gap-2 text-sm font-semibold text-gray-700 transition hover:text-[#6d28d9]"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 transition group-hover:bg-[#f1eafd]">
              <ArrowLeft size={17} />
            </div>
            <span className="hidden sm:block">Back to store</span>
          </a>

          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#f1eafd] text-[#6d28d9]">
              <ShoppingCart size={18} />
            </div>
            <span className="text-lg font-bold tracking-tight text-gray-900">
              Cart
            </span>
          </div>

          <div className="text-right">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
              Total
            </p>
            <p className="text-base font-bold text-gray-900">₹{total}</p>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
        {/* Page heading */}
        <div className="mb-6">
          <div className="flex items-end justify-between">
            <div>
              <p className="mb-1 text-xs font-bold uppercase tracking-[0.15em] text-[#6d28d9]">
                Checkout
              </p>

              <h1 className="text-3xl font-bold tracking-tight text-gray-950 sm:text-4xl">
                Your cart
              </h1>
            </div>

            {cart.items?.length > 0 && (
              <div className="rounded-full bg-white px-3 py-1.5 text-xs font-bold text-gray-500 shadow-sm ring-1 ring-gray-100">
                {cart.items.length} {cart.items.length === 1 ? "item" : "items"}
              </div>
            )}
          </div>
        </div>

        {!cart.items?.length ? (
          /* Empty cart */
          <section className="rounded-3xl bg-white px-6 py-16 text-center shadow-[0_4px_24px_rgba(0,0,0,0.04)] ring-1 ring-gray-100">
            <div className="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-full bg-[#f1eafd] text-[#6d28d9]">
              <ShoppingCart size={32} strokeWidth={2.2} />
            </div>

            <h2 className="text-xl font-bold text-gray-950">
              Your cart is empty
            </h2>

            <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-gray-500">
              Looks like you haven't added anything yet. Find something
              delicious and add it to your cart.
            </p>

            <a
              href="/"
              className="mt-7 inline-flex h-12 items-center justify-center rounded-xl bg-[#6d28d9] px-7 text-sm font-bold text-white shadow-[0_6px_18px_rgba(109,40,217,0.25)] transition hover:bg-[#5b21b6] active:scale-[0.98]"
            >
              Browse products
              <ChevronRight size={17} className="ml-1" />
            </a>
          </section>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[1fr_350px]">
            {/* LEFT */}
            <div className="space-y-5">
              {/* Cart items */}
              <section className="overflow-hidden rounded-3xl bg-white shadow-[0_4px_24px_rgba(0,0,0,0.04)] ring-1 ring-gray-100">
                <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4 sm:px-6">
                  <div>
                    <h2 className="font-bold text-gray-950">
                      Items in your cart
                    </h2>
                    <p className="mt-0.5 text-xs text-gray-400">
                      Review your items before paying
                    </p>
                  </div>

                  <ShoppingCart size={19} className="text-gray-300" />
                </div>

                <div className="divide-y divide-gray-100">
                  {cart.items.map((item: any) => (
                    <article
                      key={item.product_id}
                      className="flex gap-3 px-4 py-4 sm:gap-4 sm:px-6"
                    >
                      {/* Product image */}
                      <div className="h-[76px] w-[76px] shrink-0 overflow-hidden rounded-2xl bg-gray-50 sm:h-24 sm:w-24">
                        <img
                          src={item.image}
                          alt={item.name}
                          className="h-full w-full object-contain mix-blend-multiply"
                        />
                      </div>

                      {/* Product details */}
                      <div className="min-w-0 flex-1">
                        <div className="flex justify-between gap-3">
                          <div className="min-w-0">
                            <h3 className="truncate text-sm font-bold text-gray-900 sm:text-[15px]">
                              {item.name}
                            </h3>

                            <p className="mt-1 text-xs text-gray-400">
                              {item.category}
                            </p>

                            <p className="mt-1.5 text-xs font-semibold text-gray-500">
                              ₹{(item.unit_price_paise / 100).toFixed(2)} each
                            </p>
                          </div>

                          <p className="shrink-0 text-sm font-bold text-gray-950">
                            ₹{(item.line_total_paise / 100).toFixed(2)}
                          </p>
                        </div>

                        {/* Quantity */}
                        <div className="mt-3 flex items-center justify-between">
                          <div className="flex h-9 items-center overflow-hidden rounded-xl border border-gray-200 bg-white">
                            <button
                              disabled={busy || item.quantity <= 1}
                              onClick={() =>
                                change(item.product_id, item.quantity - 1)
                              }
                              className="flex h-full w-9 items-center justify-center text-gray-500 transition hover:bg-gray-50 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-30"
                            >
                              <Minus size={14} strokeWidth={2.5} />
                            </button>

                            <span className="w-8 text-center text-sm font-bold text-gray-900">
                              {item.quantity}
                            </span>

                            <button
                              disabled={busy}
                              onClick={() =>
                                change(item.product_id, item.quantity + 1)
                              }
                              className="flex h-full w-9 items-center justify-center text-gray-500 transition hover:bg-gray-50 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-30"
                            >
                              <Plus size={14} strokeWidth={2.5} />
                            </button>
                          </div>

                          <button
                            disabled={busy}
                            onClick={() => remove(item.product_id)}
                            className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-bold text-gray-400 transition hover:bg-red-50 hover:text-red-500 disabled:opacity-40"
                          >
                            <Trash2 size={14} />
                            <span className="hidden sm:inline">Remove</span>
                          </button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              </section>

              {/* Payment */}
              <section className="rounded-3xl bg-white p-5 shadow-[0_4px_24px_rgba(0,0,0,0.04)] ring-1 ring-gray-100 sm:p-6">
                <div className="mb-5">
                  <h2 className="font-bold text-gray-950">Payment method</h2>
                  <p className="mt-1 text-xs text-gray-400">
                    Choose how you'd like to pay
                  </p>
                </div>

                <div className="space-y-3">
                  {/* Agent balance */}
                  <label
                    className={`block cursor-pointer rounded-2xl border p-4 transition ${
                      paymentMethod === "AGENT_BALANCE"
                        ? "border-[#6d28d9] bg-[#faf8ff] ring-1 ring-[#6d28d9]/20"
                        : "border-gray-200 bg-white hover:border-gray-300"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="radio"
                        checked={paymentMethod === "AGENT_BALANCE"}
                        onChange={() => setPaymentMethod("AGENT_BALANCE")}
                        className="mt-1 h-4 w-4 accent-[#6d28d9]"
                      />

                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#f1eafd] text-[#6d28d9]">
                        <CreditCard size={19} />
                      </div>

                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-bold text-gray-900">
                          Pay with balance
                        </p>

                        <p className="mt-1 text-xs leading-5 text-gray-500">
                          Use your available purchasing balance.
                        </p>
                      </div>
                    </div>

                    {paymentMethod === "AGENT_BALANCE" && (
                      <div className="mt-4 ml-7">
                        <select
                          value={agentId}
                          onChange={(e) => setAgentId(e.target.value)}
                          className="h-11 w-full rounded-xl border border-gray-200 bg-white px-3 text-sm font-semibold text-gray-800 outline-none transition focus:border-[#6d28d9] focus:ring-2 focus:ring-[#6d28d9]/10"
                        >
                          {agents.map((a: any) => (
                            <option
                              key={a.id}
                              value={a.id}
                              disabled={a.status !== "ACTIVE"}
                            >
                              {a.name} · ₹{a.balance_available.toFixed(2)}{" "}
                              available
                            </option>
                          ))}
                        </select>

                        {agentId && (
                          <div className="mt-3 flex items-center gap-2 rounded-xl bg-gray-50 px-3 py-2.5">
                            <ShieldCheck
                              size={15}
                              className="shrink-0 text-emerald-600"
                            />

                            <span className="text-[11px] font-medium text-gray-500">
                              Available balance and spending limits will be
                              checked before payment.
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </label>

                  {/* Razorpay */}
                  <label
                    className={`block cursor-pointer rounded-2xl border p-4 transition ${
                      paymentMethod === "RAZORPAY"
                        ? "border-[#6d28d9] bg-[#faf8ff] ring-1 ring-[#6d28d9]/20"
                        : "border-gray-200 bg-white hover:border-gray-300"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="radio"
                        checked={paymentMethod === "RAZORPAY"}
                        onChange={() => setPaymentMethod("RAZORPAY")}
                        className="mt-1 h-4 w-4 accent-[#6d28d9]"
                      />

                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gray-100 text-gray-700">
                        <CreditCard size={19} />
                      </div>

                      <div>
                        <p className="text-sm font-bold text-gray-900">
                          Pay with Razorpay
                        </p>

                        <p className="mt-1 text-xs leading-5 text-gray-500">
                          Pay securely using UPI, cards or net banking.
                        </p>
                      </div>
                    </div>
                  </label>
                </div>
              </section>

              {/* Delivery assurance */}
              <div className="flex items-center gap-3 rounded-2xl bg-[#f1eafd] px-4 py-3.5">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-[#6d28d9]">
                  <Truck size={17} />
                </div>

                <div>
                  <p className="text-xs font-bold text-gray-900">
                    Fast & reliable delivery
                  </p>

                  <p className="mt-0.5 text-[11px] text-gray-500">
                    Your order will be processed immediately after successful
                    payment.
                  </p>
                </div>
              </div>
            </div>

            {/* RIGHT / ORDER SUMMARY */}
            <aside className="lg:sticky lg:top-24 lg:h-fit">
              <section className="overflow-hidden rounded-3xl bg-white shadow-[0_6px_30px_rgba(0,0,0,0.06)] ring-1 ring-gray-100">
                <div className="border-b border-gray-100 px-5 py-5">
                  <h2 className="text-base font-bold text-gray-950">
                    Bill details
                  </h2>
                </div>

                <div className="space-y-4 px-5 py-5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500">Item total</span>
                    <span className="font-semibold text-gray-800">
                      ₹{subtotal}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500">Delivery fee</span>
                    <span className="font-semibold text-gray-800">
                      ₹{delivery}
                    </span>
                  </div>

                  <div className="border-t border-dashed border-gray-200 pt-4">
                    <div className="flex items-end justify-between">
                      <span className="font-bold text-gray-950">To pay</span>

                      <span className="text-2xl font-bold tracking-tight text-gray-950">
                        ₹{total}
                      </span>
                    </div>
                  </div>

                  <button
                    disabled={busy}
                    onClick={() =>
                      paymentMethod === "RAZORPAY"
                        ? startRazorpay()
                        : agentCheckout(false)
                    }
                    className="flex h-13 w-full items-center justify-center gap-2 rounded-2xl bg-[#6d28d9] px-5 py-3.5 text-sm font-bold text-white shadow-[0_8px_20px_rgba(109,40,217,0.24)] transition hover:bg-[#5b21b6] hover:shadow-[0_10px_25px_rgba(109,40,217,0.3)] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busy ? (
                      <>
                        <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <CreditCard size={17} />
                        {paymentMethod === "RAZORPAY"
                          ? "Pay with Razorpay"
                          : "Pay now"}
                      </>
                    )}
                  </button>

                  <div className="flex items-center justify-center gap-1.5 pt-1 text-[10px] font-semibold text-gray-400">
                    <Lock size={11} />
                    Secure payment
                  </div>
                </div>
              </section>
            </aside>
          </div>
        )}

        {/* Decision / result */}
        {decision && (
          <section
            className={`mt-6 overflow-hidden rounded-3xl border p-5 shadow-sm sm:p-6 ${
              decision.success
                ? "border-emerald-200 bg-emerald-50"
                : decision.status === "CONFIRM"
                  ? "border-amber-200 bg-amber-50"
                  : "border-red-200 bg-red-50"
            }`}
          >
            <div className="flex gap-4">
              <div
                className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${
                  decision.success
                    ? "bg-emerald-100 text-emerald-600"
                    : decision.status === "CONFIRM"
                      ? "bg-amber-100 text-amber-600"
                      : "bg-red-100 text-red-600"
                }`}
              >
                {decision.success ? (
                  <ShieldCheck size={21} />
                ) : (
                  <CreditCard size={21} />
                )}
              </div>

              <div className="flex-1">
                <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-gray-400">
                  Order status
                </p>

                <h2 className="mt-1 text-lg font-black text-gray-950">
                  {decision.success
                    ? decision.status === "PAID"
                      ? "Payment confirmed"
                      : "Order confirmed"
                    : decision.status === "CONFIRM"
                      ? "Confirmation required"
                      : decision.status === "BLOCK"
                        ? "Purchase blocked"
                        : "Payment failed"}
                </h2>

                <p className="mt-1 text-sm leading-6 text-gray-600">
                  {decision.success
                    ? decision.order_id
                      ? `Order ${decision.order_id} was created successfully.`
                      : "Your order has been completed successfully."
                    : decision.policy?.reason || decision.reason}
                </p>

                <div className="mt-4 flex flex-wrap gap-2">
                  {decision.status === "CONFIRM" && (
                    <button
                      className="inline-flex items-center justify-center rounded-xl bg-[#6d28d9] px-5 py-2.5 text-xs font-bold text-white transition hover:bg-[#5b21b6] disabled:opacity-50"
                      disabled={busy}
                      onClick={() => agentCheckout(true)}
                    >
                      Confirm & pay ₹
                      {(
                        (decision.total_paise ?? cart.total_paise) / 100
                      ).toFixed(2)}
                    </button>
                  )}

                  {decision.success && (
                    <a
                      href="/orders"
                      className="inline-flex items-center justify-center rounded-xl bg-white px-5 py-2.5 text-xs font-bold text-gray-800 shadow-sm ring-1 ring-gray-200 transition hover:bg-gray-50"
                    >
                      View orders
                      <ChevronRight size={14} className="ml-1" />
                    </a>
                  )}
                </div>
              </div>
            </div>
          </section>
        )}
      </div>

      {/* Mobile sticky checkout */}
      {cart.items?.length > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-gray-200 bg-white/95 p-3 backdrop-blur lg:hidden">
          <div className="mx-auto flex max-w-5xl items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                Total
              </p>
              <p className="truncate text-lg font-black text-gray-950">
                ₹{total}
              </p>
            </div>

            <button
              disabled={busy}
              onClick={() =>
                paymentMethod === "RAZORPAY"
                  ? startRazorpay()
                  : agentCheckout(false)
              }
              className="flex h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-[#6d28d9] px-5 text-sm font-bold text-white shadow-[0_6px_18px_rgba(109,40,217,0.25)] transition active:scale-[0.98] disabled:opacity-50"
            >
              {busy ? (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              ) : (
                <>
                  <CreditCard size={16} />
                  Pay now
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
