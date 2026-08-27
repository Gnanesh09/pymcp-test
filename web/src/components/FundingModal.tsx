"use client";

import { useState } from "react";
import { useUmonApi } from "@/src/lib/api";

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
      const order = await api.createFundingOrder(
        agentId,
        amount,
      );

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
      className="primary-button"
      onClick={startFunding}
      disabled={busy}
    >
      {busy ? "Opening Razorpay…" : `Fund ₹${amount}`}
    </button>
  );
}
