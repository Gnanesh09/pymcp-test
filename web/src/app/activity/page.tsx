"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Check, X, Clock3, Activity } from "lucide-react";
import { useUmonApi } from "@/src/lib/api";

export default function ActivityPage() {
  const api = useUmonApi();
  const [events, setEvents] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [agentId, setAgentId] = useState("");

  const load = useCallback(
    async () => setEvents((await api.audit(agentId || undefined)).events ?? []),
    [api, agentId],
  );

  useEffect(() => {
    api
      .agents()
      .then((x: any) => setAgents(x.agents ?? []))
      .catch(console.error);
  }, [api]);

  useEffect(() => {
    load().catch(console.error);
  }, [load]);

  return (
    // #F5F5F7 is the classic Apple system background color
    <div className="min-h-screen bg-[#F5F5F7] py-10 font-sans text-[#1D1D1F] selection:bg-[#0071E3]/20">
      <main className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
        {/* Back Link */}
        <a
          href="/"
          className="group mb-8 inline-flex items-center gap-2 text-sm font-medium text-[#0071E3] transition-opacity hover:opacity-70"
        >
          <ArrowLeft size={18} strokeWidth={2.5} />
          Back to store
        </a>

        {/* Header Section */}
        <div className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <span className="mb-1 block text-xs font-semibold tracking-widest text-[#86868B] uppercase">
              Audit Trail
            </span>
            <h1 className="text-3xl font-bold tracking-tight text-[#1D1D1F] sm:text-4xl">
              Activity
            </h1>
          </div>

          {/* Clean Picker Dropdown */}
          <div className="relative min-w-[200px]">
            <select
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              className="w-full appearance-none rounded-[14px] border-0 bg-white py-3 pl-4 pr-10 text-[15px] font-medium text-[#1D1D1F] shadow-[0_2px_10px_rgba(0,0,0,0.04)] outline-none ring-1 ring-black/[0.04] transition-all focus:ring-2 focus:ring-[#0071E3] cursor-pointer"
            >
              <option value="">All agents</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#86868B]">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </div>
          </div>
        </div>

        {/* Content Area */}
        {!events.length ? (
          /* Empty State */
          <div className="flex flex-col items-center justify-center rounded-[24px] bg-white p-14 text-center shadow-[0_2px_20px_rgba(0,0,0,0.03)] ring-1 ring-black/[0.02]">
            <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-[#F5F5F7] text-[#86868B]">
              <Activity size={32} strokeWidth={2} />
            </div>
            <h3 className="mb-2 text-xl font-semibold text-[#1D1D1F]">
              No activity yet
            </h3>
            <p className="text-[15px] text-[#86868B] max-w-sm leading-relaxed">
              Agent decisions, blocks, and monetary actions will appear here in
              a chronological audit trail.
            </p>
          </div>
        ) : (
          /* Timeline */
          <div className="relative ml-4 md:ml-5 space-y-6 pb-8">
            {/* Simple, clean timeline track */}
            <div className="absolute bottom-0 left-[15px] top-2 w-[2px] bg-[#E5E5EA]"></div>

            {events.map((event) => {
              const isSuccess = event.result === "SUCCESS";
              const isDanger =
                event.result === "BLOCK" || event.result === "FAILED";

              return (
                <div className="relative pl-12 sm:pl-16 group" key={event.id}>
                  {/* Timeline Node Icon (iOS System Colors) */}
                  <div
                    className={`absolute left-0 top-1.5 flex h-8 w-8 items-center justify-center rounded-full text-white shadow-sm ring-4 ring-[#F5F5F7]
                      ${
                        isSuccess
                          ? "bg-[#34C759]" // System Green
                          : isDanger
                            ? "bg-[#FF3B30]" // System Red
                            : "bg-[#8E8E93]" // System Gray
                      }
                    `}
                  >
                    {isSuccess ? (
                      <Check size={16} strokeWidth={3} />
                    ) : isDanger ? (
                      <X size={16} strokeWidth={3} />
                    ) : (
                      <Clock3 size={16} strokeWidth={2.5} />
                    )}
                  </div>

                  {/* Timeline Card */}
                  <div className="rounded-[20px] bg-white p-5 shadow-[0_2px_12px_rgba(0,0,0,0.03)] ring-1 ring-black/[0.03] transition-shadow hover:shadow-[0_4px_24px_rgba(0,0,0,0.06)]">
                    <div className="flex flex-col gap-1 mb-2 sm:flex-row sm:items-center sm:justify-between sm:mb-2.5">
                      <strong className="text-[17px] font-semibold text-[#1D1D1F] tracking-tight">
                        {event.action}
                      </strong>
                      <span className="text-[13px] font-medium text-[#86868B]">
                        {new Date(event.created_at).toLocaleString(undefined, {
                          month: "short",
                          day: "numeric",
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>

                    <p className="text-[15px] text-[#515154] leading-relaxed mb-4">
                      {event.reason ||
                        "No additional explanation provided for this action."}
                    </p>

                    {/* Amount Badge */}
                    {event.amount_paise ? (
                      <div className="inline-flex items-center gap-1 rounded-lg bg-[#F5F5F7] px-3 py-1.5 text-[14px] font-semibold text-[#1D1D1F]">
                        <span className="text-[#86868B] font-medium">₹</span>
                        {(event.amount_paise / 100).toFixed(2)}
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
