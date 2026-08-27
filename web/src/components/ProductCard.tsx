"use client";

import { useState } from "react";
import { Plus, Star } from "lucide-react";
import { useUmonApi } from "@/src/lib/api";
import type { Product } from "@/src/lib/types";

export default function ProductCard({ product }: { product: Product }) {
  const api = useUmonApi();
  const [adding, setAdding] = useState(false);

  async function add() {
    setAdding(true);
    try {
      await api.addToCart(product.id, 1);
      window.alert(`${product.name} added to cart.`);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Could not add product.");
    } finally {
      setAdding(false);
    }
  }

  return (
    <article className="product-card">
      <div className="product-image-wrap"><img src={product.image} alt={product.name} /></div>
      <div className="product-body">
        <div className="product-category">{product.category}</div>
        <h3>{product.name}</h3>
        <div className="product-brand">{product.brand}</div>
        <div className="product-meta">
          <span><Star size={13} fill="currentColor" /> {product.rating}</span>
          <span>{product.unit}</span>
          <span>{product.stock > 0 ? "In stock" : "Out"}</span>
        </div>
        <div className="product-footer">
          <strong>₹{product.price}</strong>
          <button onClick={add} disabled={adding || product.stock <= 0}><Plus size={16} />{adding ? "Adding" : "Add"}</button>
        </div>
      </div>
    </article>
  );
}
