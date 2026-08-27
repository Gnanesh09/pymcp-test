"use client";

import { useState } from "react";
import { useUmonApi } from "@/src/lib/api";
import { Loader2, Wallet } from "lucide-react";
export default function FundingModal({
  agentId,
  amount,
  onSuccess,
}: {
  agentId: string;
  amount: number;
  onSuccess: () => void;
}) {
  const api = useUmonApi();
  const [busy, setBusy] = useState(false);

  async function startFunding() {
    if (!window.Razorpay) {
      window.alert("Razorpay Checkout has not loaded yet.");
      return;
    }

    setBusy(true);

    try {
      const order = await api.createFundingOrder(agentId, amount);

      const checkout = new window.Razorpay({
        key: order.key_id,
        amount: order.amount_paise,
        currency: order.currency,
        name: "Umon Mart",
        description: "Purchasing Agent Funding",
        order_id: order.razorpay_order_id,
        handler: async (response: any) => {
          try {
            await api.verifyFunding(agentId, {
              payment_id: order.payment_id,
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });

            onSuccess();
            window.alert("Agent funded successfully.");
          } catch (error) {
            window.alert(
              error instanceof Error
                ? error.message
                : "Payment was received but funding verification failed.",
            );
          } finally {
            setBusy(false);
          }
        },
        modal: {
          ondismiss: () => setBusy(false),
        },
        theme: {
          color: "#111827",
        },
      });

      checkout.open();
    } catch (error) {
      setBusy(false);
      window.alert(
        error instanceof Error
          ? error.message
          : "Unable to create Razorpay funding order.",
      );
    }
  }

  return (
    <button
      onClick={startFunding}
      disabled={busy}
      className="group relative flex w-full items-center justify-center gap-2 rounded-xl bg-gray-900 px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:bg-gray-800 hover:shadow-md active:scale-[0.98] disabled:pointer-events-none disabled:opacity-70 sm:w-auto"
    >
      {busy ? (
        <>
          <Loader2 size={16} className="animate-spin text-fuchsia-400" />
          <span>Opening Razorpay&hellip;</span>
        </>
      ) : (
        <>
          <Wallet
            size={16}
            className="text-gray-300 transition-colors group-hover:text-fuchsia-400"
          />
          <span>
            Fund <span className="font-bold tracking-tight">₹{amount}</span>
          </span>
        </>
      )}
    </button>
  );
}
