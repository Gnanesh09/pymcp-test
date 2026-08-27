"use client";

import { useState } from "react";
import { Plus, Star, Loader2 } from "lucide-react";
import { useUmonApi } from "@/src/lib/api";
import type { Product } from "@/src/lib/types";

export default function ProductCard({ product }: { product: Product }) {
  const api = useUmonApi();
  const [adding, setAdding] = useState(false);

  async function add() {
    setAdding(true);
    try {
      await api.addToCart(product.id, 1);
      // In a real app, replace this with a toast notification (e.g., react-hot-toast)
      window.alert(`${product.name} added to cart.`);
    } catch (error) {
      window.alert(
        error instanceof Error ? error.message : "Could not add product.",
      );
    } finally {
      setAdding(false);
    }
  }

  const isOutOfStock = product.stock <= 0;

  return (
    <article className="group flex h-full w-full flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition-all duration-200 hover:border-gray-300 hover:shadow-md relative">
      {/* Out of Stock Overlay / Badge */}
      {isOutOfStock && (
        <div className="absolute left-2 top-2 z-10 rounded bg-red-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-red-600 ring-1 ring-red-500/20 backdrop-blur-sm">
          Out of stock
        </div>
      )}

      {/* Image Area */}
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-gray-50/50 p-4 sm:aspect-square">
        <img
          src={product.image}
          alt={product.name}
          className={`h-full w-full object-contain transition-transform duration-300 group-hover:scale-105 ${isOutOfStock ? "opacity-50 grayscale" : ""}`}
        />
      </div>

      {/* Content Area */}
      <div className="flex flex-1 flex-col p-3 sm:p-4">
        {/* Brand & Category */}
        <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-gray-400">
          <span className="truncate">{product.brand}</span>
          <span className="h-0.5 w-0.5 rounded-full bg-gray-300"></span>
          <span className="truncate">{product.category}</span>
        </div>

        {/* Title */}
        <h3
          className={`mb-2 text-sm font-semibold leading-snug tracking-tight sm:text-base line-clamp-2 ${isOutOfStock ? "text-gray-500" : "text-gray-900"}`}
          title={product.name}
        >
          {product.name}
        </h3>

        {/* Meta (Rating & Unit) */}
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          {/* Zepto/Instamart style green rating badge */}
          <div className="flex items-center gap-1 rounded bg-green-50 px-1.5 py-0.5 font-bold text-green-700">
            <Star size={10} className="fill-green-700" />
            <span>{product.rating}</span>
          </div>
          <div className="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-600">
            {product.unit}
          </div>
        </div>

        {/* Footer (Price & Action) */}
        <div className="mt-auto flex items-center justify-between gap-2 pt-3">
          <div className="flex flex-col">
            {/* Added small rupee symbol alignment for premium feel */}
            <span
              className={`text-base sm:text-lg font-extrabold tracking-tight ${isOutOfStock ? "text-gray-400" : "text-gray-900"}`}
            >
              <span className="text-sm font-semibold text-gray-500 mr-0.5">
                ₹
              </span>
              {product.price}
            </span>
          </div>

          <button
            onClick={add}
            disabled={adding || isOutOfStock}
            className={`
              relative flex h-8 min-w-[72px] items-center justify-center gap-1 rounded-lg border px-3 text-xs font-bold transition-all
              sm:h-9 sm:text-sm sm:px-4
              ${
                isOutOfStock
                  ? "border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed"
                  : "border-fuchsia-200 bg-fuchsia-50 text-fuchsia-700 hover:bg-fuchsia-100 hover:border-fuchsia-300 active:scale-95 shadow-sm"
              }
            `}
          >
            {adding ? (
              <>
                <Loader2 size={14} className="animate-spin" />
              </>
            ) : isOutOfStock ? (
              "Out"
            ) : (
              <>
                <Plus size={14} className="-ml-1" />
                Add
              </>
            )}
          </button>
        </div>
      </div>
    </article>
  );
}
