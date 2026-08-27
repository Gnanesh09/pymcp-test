"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ShoppingCart, Minus, Plus, Trash2, CreditCard, ShieldCheck } from "lucide-react";
import { useUmonApi } from "@/src/lib/api";

export default function CartPage() {
  const api = useUmonApi();
  const [cart,setCart]=useState<any>(null);
  const [agents,setAgents]=useState<any[]>([]);
  const [paymentMethod,setPaymentMethod]=useState<"AGENT_BALANCE"|"RAZORPAY">("AGENT_BALANCE");
  const [agentId,setAgentId]=useState("");
  const [decision,setDecision]=useState<any>(null);
  const [busy,setBusy]=useState(false);

  const load=useCallback(async()=>{
    const [cartData, agentsData] = await Promise.all([api.cart(),api.agents()]);
    setCart(cartData.cart); const list=agentsData.agents??[]; setAgents(list);
    setAgentId(cur=>cur||list.find((a:any)=>a.status==="ACTIVE")?.id||list[0]?.id||"");
  },[api]);
  useEffect(()=>{load().catch(e=>alert(e instanceof Error?e.message:"Unable to load cart."))},[load]);

  async function change(productId:string,quantity:number){setBusy(true);try{setCart((await api.updateCartItem(productId,quantity)).cart)}catch(e){alert(e instanceof Error?e.message:"Unable to update cart.")}finally{setBusy(false)}}
  async function remove(productId:string){setBusy(true);try{setCart((await api.removeCartItem(productId)).cart)}catch(e){alert(e instanceof Error?e.message:"Unable to remove item.")}finally{setBusy(false)}}

  async function startRazorpay(){
    setBusy(true); setDecision(null);
    try{
      if(!window.Razorpay) throw new Error("Razorpay Checkout has not loaded yet.");
      const order=await api.createRazorpayCheckout();
      const checkout=new window.Razorpay({
        key:order.key_id, amount:order.amount_paise, currency:order.currency, name:"Umon Mart", description:"Umon Mart order", order_id:order.razorpay_order_id,
        handler:async(resp:any)=>{try{const result=await api.verifyRazorpayCheckout({payment_id:order.payment_id,razorpay_order_id:resp.razorpay_order_id,razorpay_payment_id:resp.razorpay_payment_id,razorpay_signature:resp.razorpay_signature});setDecision({success:true,status:"PAID",order:result});await load()}catch(e){setDecision({success:false,status:"FAILED",reason:e instanceof Error?e.message:"Payment verification failed."})}finally{setBusy(false)}},
        modal:{ondismiss:()=>setBusy(false)},theme:{color:"#111827"}
      }); checkout.open();
    }catch(e){setBusy(false);setDecision({success:false,status:"FAILED",reason:e instanceof Error?e.message:"Unable to start Razorpay."})}
  }

  async function agentCheckout(confirmed=false){
    if(!agentId){setDecision({success:false,status:"BLOCK",policy:{reason:"Select an active purchasing agent."}});return}
    setBusy(true);setDecision(null);
    try{setDecision(await api.checkoutWithAgentBalance(agentId,confirmed));await load()}catch(e){setDecision({success:false,status:"ERROR",policy:{reason:e instanceof Error?e.message:"Checkout failed."}})}finally{setBusy(false)}
  }

  if(!cart) return <main className="shell narrow"><div className="loading">Loading cart…</div></main>;

  return <main className="shell narrow">
    <a className="back-link" href="/"><ArrowLeft size={17}/>Back to store</a>
    <div className="section-heading standalone"><div><span className="eyebrow">CHECKOUT</span><h1>Your cart</h1></div><div className="cart-total">₹{((cart.total_paise??0)/100).toFixed(2)}</div></div>
    {!cart.items?.length ? <section className="empty-card"><div className="empty-icon"><ShoppingCart size={24}/></div><h3>Your cart is empty</h3><p>Add a product from the store to start a purchase.</p><a className="secondary-button" href="/">Browse products</a></section> : <>
      <section className="cart-list">{cart.items.map((item:any)=><article className="cart-item" key={item.product_id}><img src={item.image} alt={item.name}/><div className="cart-item-main"><strong>{item.name}</strong><span>{item.category} · ₹{(item.unit_price_paise/100).toFixed(2)} each</span><div className="qty-controls"><button disabled={busy||item.quantity<=1} onClick={()=>change(item.product_id,item.quantity-1)}><Minus size={15}/></button><b>{item.quantity}</b><button disabled={busy} onClick={()=>change(item.product_id,item.quantity+1)}><Plus size={15}/></button><button className="danger-button" disabled={busy} onClick={()=>remove(item.product_id)}><Trash2 size={15}/></button></div></div><strong>₹{(item.line_total_paise/100).toFixed(2)}</strong></article>)}</section>
      <section className="payment-choice panel-card"><div className="panel-label">CHOOSE HOW TO PAY</div>
        <label className={`payment-option ${paymentMethod==="AGENT_BALANCE"?"selected":""}`}><input type="radio" checked={paymentMethod==="AGENT_BALANCE"} onChange={()=>setPaymentMethod("AGENT_BALANCE")}/><div><strong>Pay using purchasing agent</strong><small>The selected agent's balance and guardrails are checked by the backend.</small></div></label>
        {paymentMethod==="AGENT_BALANCE" && <div className="agent-payment-select"><select value={agentId} onChange={e=>setAgentId(e.target.value)}>{agents.map((a:any)=><option key={a.id} value={a.id} disabled={a.status!=="ACTIVE"}>{a.name} · ₹{a.balance_available.toFixed(2)} available · max ₹{a.policy.max_transaction_paise/100}</option>)}</select>{agentId&&<div className="agent-mini"><ShieldCheck size={16}/><span>Agent rules will be evaluated before any balance is reserved.</span></div>}</div>}
        <label className={`payment-option ${paymentMethod==="RAZORPAY"?"selected":""}`}><input type="radio" checked={paymentMethod==="RAZORPAY"} onChange={()=>setPaymentMethod("RAZORPAY")}/><div><strong>Pay directly with Razorpay</strong><small>No agent balance is used. Standard Razorpay Test Checkout is opened.</small></div></label>
      </section>
      <section className="checkout-card"><div className="summary-row"><span>Subtotal</span><strong>₹{((cart.subtotal_paise??0)/100).toFixed(2)}</strong></div><div className="summary-row"><span>Delivery</span><strong>₹{((cart.delivery_fee_paise??0)/100).toFixed(2)}</strong></div><div className="summary-row total"><span>Total</span><strong>₹{((cart.total_paise??0)/100).toFixed(2)}</strong></div><button className="primary-button checkout-button" disabled={busy} onClick={()=>paymentMethod==="RAZORPAY"?startRazorpay():agentCheckout(false)}><CreditCard size={17}/>{paymentMethod==="RAZORPAY"?"Pay with Razorpay":"Pay with selected agent"}</button></section>
      {decision&&<section className={`decision-card ${decision.success?"success":decision.status==="CONFIRM"?"confirm":"blocked"}`}><span className="eyebrow">PURCHASE DECISION</span><h2>{decision.success?(decision.status==="PAID"?"Payment confirmed":"Order confirmed"):decision.status==="CONFIRM"?"Confirmation required":decision.status==="BLOCK"?"Purchase blocked":"Payment failed"}</h2><p>{decision.success?(decision.order_id?`Order ${decision.order_id} was created.`:`Order completed.`):decision.policy?.reason||decision.reason}</p>{decision.status==="CONFIRM"&&<button className="primary-button" disabled={busy} onClick={()=>agentCheckout(true)}>Confirm and pay ₹{((decision.total_paise??cart.total_paise)/100).toFixed(2)}</button>}{decision.success&&<a className="secondary-button" href="/orders">View orders</a>}</section>}
    </>}
  </main>
}
