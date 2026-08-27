"use client";
import { useCallback, useEffect, useState } from "react";
import { Bot, ChevronRight } from "lucide-react";
import { useUmonApi } from "@/src/lib/api";

export default function AgentPanel() {
  const api = useUmonApi();
  const [agents, setAgents] = useState<any[]>([]);
  const load = useCallback(async()=>{try{setAgents((await api.agents()).agents??[])}catch{}},[api]);
  useEffect(()=>{load()},[load]);
  if(!agents.length) return <section className="agent-banner"><div><span className="eyebrow">AGENTIC COMMERCE</span><h2>Create your purchasing agent</h2><p>Fund it, set hard limits, then choose it at checkout.</p></div><a className="primary-button" href="/agents">Create agent <ChevronRight size={17}/></a></section>;
  return <section className="agent-banner"><div className="agent-banner-icon"><Bot size={21}/></div><div className="agent-banner-copy"><div className="agent-banner-title">{agents.length} purchasing agent{agents.length>1?"s":""} available</div><div className="agent-banner-sub">The cart is shared. Choose which agent funds the purchase at checkout.</div></div><a className="secondary-button" href="/agents">Manage agents</a></section>;
}
