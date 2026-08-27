"use client";

import { useCallback, useEffect, useState } from "react";

import { UserButton } from "@clerk/nextjs";

import {
  Plus,
  WalletCards,
  Activity,
  X,
  Check,
  ChevronRight,
  ShieldCheck,
} from "lucide-react";

import { useUmonApi } from "@/src/lib/api";

type CategoryMode = "ALL" | "SELECTED";

type Agent = {
  id: string;
  name: string;
  description: string | null;
  status: string;
  balance_available: number;

  policy: {
    max_transaction_paise: number;
    daily_limit_paise: number;
    auto_purchase: boolean;

    category_mode?: "ALL" | "SELECTED";

    allowed_categories: string[];
    blocked_categories: string[];
  };
};

type CreateAgentForm = {
  name: string;
  description: string;

  max_transaction: string;
  daily_limit: string;

  auto_purchase: boolean;

  category_mode: CategoryMode;

  allowed_categories: string[];
  blocked_categories: string[];
};

const CATEGORIES = [
  {
    value: "grocery",
    label: "Grocery",
  },
  {
    value: "dairy",
    label: "Dairy",
  },
  {
    value: "snacks",
    label: "Snacks",
  },
  {
    value: "beverages",
    label: "Beverages",
  },
  {
    value: "household",
    label: "Household",
  },
  {
    value: "personal-care",
    label: "Personal Care",
  },
];

const DEFAULT_FORM: CreateAgentForm = {
  name: "",
  description: "",

  max_transaction: "200",
  daily_limit: "400",

  auto_purchase: true,

  category_mode: "ALL",

  allowed_categories: [],
  blocked_categories: [],
};

export default function AgentsPage() {
  const api = useUmonApi();

  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [showCreate, setShowCreate] = useState(false);

  const [form, setForm] = useState<CreateAgentForm>(DEFAULT_FORM);

  const [error, setError] = useState("");

  const loadAgents = useCallback(async () => {
    setLoading(true);

    try {
      const data = await api.agents();

      setAgents((data.agents ?? []) as Agent[]);
    } catch (error) {
      window.alert(
        error instanceof Error ? error.message : "Unable to load agents.",
      );
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  function openCreate() {
    setForm(DEFAULT_FORM);
    setError("");
    setShowCreate(true);
  }

  function closeCreate() {
    if (busy) return;

    setShowCreate(false);
    setForm(DEFAULT_FORM);
    setError("");
  }

  async function submitCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (busy) return;

    setError("");

    const name = form.name.trim();
    const description = form.description.trim();

    const maxTransaction = Number(form.max_transaction);
    const dailyLimit = Number(form.daily_limit);

    if (!name) {
      setError("Agent name is required.");
      return;
    }

    if (!Number.isFinite(maxTransaction) || maxTransaction <= 0) {
      setError("Transaction limit must be greater than zero.");
      return;
    }

    if (!Number.isFinite(dailyLimit) || dailyLimit <= 0) {
      setError("Daily limit must be greater than zero.");
      return;
    }

    if (maxTransaction > dailyLimit) {
      setError("Transaction limit cannot exceed daily limit.");
      return;
    }

    if (
      form.category_mode === "SELECTED" &&
      form.allowed_categories.length === 0
    ) {
      setError("Select at least one category.");
      return;
    }

    setBusy(true);

    try {
      const data = await api.createAgent({
        name,
        description: description || null,

        max_transaction: maxTransaction,
        daily_limit: dailyLimit,

        auto_purchase: form.auto_purchase,

        category_mode: form.category_mode,

        allowed_categories:
          form.category_mode === "ALL" ? [] : form.allowed_categories,

        blocked_categories: form.blocked_categories,
      });

      setAgents((current) => [data.agent, ...current]);

      setShowCreate(false);
      setForm(DEFAULT_FORM);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Unable to create agent.",
      );
    } finally {
      setBusy(false);
    }
  }

  function toggleAllowed(value: string) {
    setForm((current) => ({
      ...current,

      allowed_categories: current.allowed_categories.includes(value)
        ? current.allowed_categories.filter((x) => x !== value)
        : [...current.allowed_categories, value],

      blocked_categories: current.blocked_categories.filter((x) => x !== value),
    }));
  }

  function toggleBlocked(value: string) {
    setForm((current) => ({
      ...current,

      blocked_categories: current.blocked_categories.includes(value)
        ? current.blocked_categories.filter((x) => x !== value)
        : [...current.blocked_categories, value],

      allowed_categories: current.allowed_categories.filter((x) => x !== value),
    }));
  }

  return (
    <main className="min-h-screen bg-[#f7f7f8] text-gray-900">
      {/* =====================================================
          HEADER
      ====================================================== */}

      <header className="sticky top-0 z-30 border-b border-gray-100 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#6d28d9] text-sm font-medium text-white">
              U
            </div>

            <div>
              <div className="text-sm font-medium text-gray-900">Umon Mart</div>

              <div className="text-[11px] text-gray-400">Agent control</div>
            </div>
          </div>

          <UserButton />
        </div>
      </header>

      {/* =====================================================
          CONTENT
      ====================================================== */}

      <div className="mx-auto max-w-6xl px-5 py-8 sm:py-10">
        {/* Page heading */}

        <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[#6d28d9]">
              Purchasing agents
            </div>

            <h1 className="text-3xl font-semibold tracking-tight text-gray-950 sm:text-[34px]">
              Your agents
            </h1>

            <p className="mt-2 max-w-lg text-sm leading-6 text-gray-500">
              Manage purchasing access, spending limits and categories.
            </p>
          </div>

          <button
            type="button"
            onClick={openCreate}
            className="
              inline-flex h-11 items-center justify-center gap-2
              rounded-xl
              bg-[#6d28d9]
              px-4
              text-sm font-medium
              text-white
              shadow-[0_4px_14px_rgba(109,40,217,0.18)]
              transition
              hover:bg-[#5b21b6]
              hover:shadow-[0_6px_18px_rgba(109,40,217,0.24)]
              active:scale-[0.98]
            "
          >
            <Plus size={17} />
            Create agent
          </button>
        </div>

        {/* =====================================================
            LOADING
        ====================================================== */}

        {loading ? (
          <div className="flex min-h-[300px] items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-[#6d28d9]/15 border-t-[#6d28d9]" />

              <p className="text-sm text-gray-400">Loading agents...</p>
            </div>
          </div>
        ) : (
          /* ===================================================
             AGENT GRID
          ==================================================== */

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {agents.map((agent) => (
              <article
                key={agent.id}
                className="
                  rounded-2xl
                  border border-gray-100
                  bg-white
                  p-5
                  shadow-[0_2px_12px_rgba(0,0,0,0.035)]
                  transition
                  hover:-translate-y-0.5
                  hover:shadow-[0_8px_28px_rgba(0,0,0,0.06)]
                "
              >
                {/* Card top */}

                <div className="flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#f1eafd] text-[#6d28d9]">
                    <Activity size={18} />
                  </div>

                  <span
                    className={
                      agent.status === "ACTIVE"
                        ? "rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide text-emerald-600"
                        : "rounded-full bg-gray-100 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide text-gray-500"
                    }
                  >
                    {agent.status}
                  </span>
                </div>

                {/* Name */}

                <h2 className="mt-5 text-[17px] font-medium text-gray-900">
                  {agent.name}
                </h2>

                <p className="mt-1 min-h-[20px] text-sm text-gray-500">
                  {agent.description || "Purchasing agent"}
                </p>

                {/* Balance */}

                <div className="mt-5 rounded-xl bg-gray-50 px-4 py-3.5">
                  <span className="text-xs text-gray-400">
                    Available balance
                  </span>

                  <div className="mt-1 text-2xl font-semibold tracking-tight text-gray-950">
                    ₹{Number(agent.balance_available ?? 0).toFixed(2)}
                  </div>
                </div>

                {/* Policy */}

                <div className="mt-4 grid grid-cols-3 divide-x divide-gray-100">
                  <div className="pr-3">
                    <span className="block text-[10px] text-gray-400">
                      Per purchase
                    </span>

                    <span className="mt-1 block text-sm font-medium text-gray-800">
                      ₹{(agent.policy.max_transaction_paise / 100).toFixed(0)}
                    </span>
                  </div>

                  <div className="px-3">
                    <span className="block text-[10px] text-gray-400">
                      Daily
                    </span>

                    <span className="mt-1 block text-sm font-medium text-gray-800">
                      ₹{(agent.policy.daily_limit_paise / 100).toFixed(0)}
                    </span>
                  </div>

                  <div className="pl-3">
                    <span className="block text-[10px] text-gray-400">
                      Scope
                    </span>

                    <span className="mt-1 block truncate text-sm font-medium text-gray-800">
                      {(agent.policy.category_mode ?? "ALL") === "ALL"
                        ? "Everything"
                        : "Selected"}
                    </span>
                  </div>
                </div>

                {/* Manage */}

                <a
                  href={`/agents/${agent.id}`}
                  className="
                    mt-5 flex h-10 items-center
                    justify-center gap-1
                    rounded-xl
                    border border-gray-200
                    text-sm font-medium
                    text-gray-700
                    transition
                    hover:border-gray-300
                    hover:bg-gray-50
                  "
                >
                  Manage agent
                  <ChevronRight size={15} />
                </a>
              </article>
            ))}

            {/* =================================================
                EMPTY STATE
            ================================================== */}

            {!agents.length && (
              <div
                className="
                  col-span-full
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
                  <WalletCards size={27} />
                </div>

                <h3 className="mt-5 text-lg font-medium text-gray-900">
                  No agents yet
                </h3>

                <p className="mt-1.5 max-w-sm text-sm leading-6 text-gray-500">
                  Create your first agent and set its purchasing permissions and
                  spending limits.
                </p>

                <button
                  type="button"
                  onClick={openCreate}
                  className="
                    mt-6
                    inline-flex h-10
                    items-center gap-2
                    rounded-xl
                    bg-[#6d28d9]
                    px-4
                    text-sm font-medium
                    text-white
                    transition
                    hover:bg-[#5b21b6]
                  "
                >
                  <Plus size={16} />
                  Create agent
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* =====================================================
          CREATE AGENT MODAL
      ====================================================== */}

      {showCreate && (
        <div
          className="
            fixed inset-0 z-50
            flex items-center justify-center
            bg-black/35
            p-4
            backdrop-blur-[2px]
          "
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeCreate();
            }
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-agent-title"
            className="
              flex max-h-[92vh]
              w-full max-w-[560px]
              flex-col
              overflow-hidden
              rounded-3xl
              bg-white
              shadow-[0_24px_80px_rgba(0,0,0,0.18)]
            "
          >
            {/* =================================================
                MODAL HEADER
            ================================================== */}

            <div className="flex shrink-0 items-center justify-between border-b border-gray-100 bg-white px-6 py-5">
              <div>
                <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-[#6d28d9]">
                  New agent
                </div>

                <h2
                  id="create-agent-title"
                  className="mt-1 text-xl font-semibold tracking-tight text-gray-950"
                >
                  Create agent
                </h2>

                <p className="mt-1 text-xs text-gray-400">
                  Set up purchasing permissions.
                </p>
              </div>

              <button
                type="button"
                onClick={closeCreate}
                disabled={busy}
                className="
                  flex h-9 w-9
                  items-center justify-center
                  rounded-full
                  text-gray-400
                  transition
                  hover:bg-gray-100
                  hover:text-gray-700
                  disabled:opacity-40
                "
              >
                <X size={18} />
              </button>
            </div>

            {/* =================================================
                FORM
            ================================================== */}

            <form onSubmit={submitCreate} className="overflow-y-auto">
              <div className="space-y-6 p-6">
                {/* ---------------------------------------------
                    BASIC INFORMATION
                ---------------------------------------------- */}

                <div className="space-y-4">
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-gray-800">
                      Agent name
                    </span>

                    <input
                      value={form.name}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          name: event.target.value,
                        }))
                      }
                      placeholder="Shopping Agent"
                      maxLength={80}
                      autoFocus
                      className="
                        h-11 w-full
                        rounded-xl
                        border border-gray-200
                        bg-white
                        px-3.5
                        text-sm text-gray-900
                        outline-none
                        placeholder:text-gray-300
                        transition
                        focus:border-[#6d28d9]
                        focus:ring-4
                        focus:ring-[#6d28d9]/10
                      "
                    />
                  </label>

                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-gray-800">
                      Description
                    </span>

                    <textarea
                      value={form.description}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          description: event.target.value,
                        }))
                      }
                      placeholder="What should this agent handle?"
                      rows={3}
                      maxLength={500}
                      className="
                        w-full
                        resize-none
                        rounded-xl
                        border border-gray-200
                        bg-white
                        px-3.5 py-3
                        text-sm text-gray-900
                        outline-none
                        placeholder:text-gray-300
                        transition
                        focus:border-[#6d28d9]
                        focus:ring-4
                        focus:ring-[#6d28d9]/10
                      "
                    />
                  </label>
                </div>

                {/* ---------------------------------------------
                    PURCHASE ACCESS
                ---------------------------------------------- */}

                <div>
                  <div className="mb-3">
                    <h3 className="text-sm font-medium text-gray-900">
                      Purchase access
                    </h3>

                    <p className="mt-1 text-xs text-gray-400">
                      Choose where this agent can shop.
                    </p>
                  </div>

                  <div className="space-y-2">
                    {/* Everything */}

                    <button
                      type="button"
                      onClick={() =>
                        setForm((current) => ({
                          ...current,
                          category_mode: "ALL",
                          allowed_categories: [],
                        }))
                      }
                      className={`
                        flex w-full items-center gap-3
                        rounded-2xl
                        border
                        p-4
                        text-left
                        transition
                        ${
                          form.category_mode === "ALL"
                            ? "border-[#6d28d9] bg-[#faf8ff]"
                            : "border-gray-200 hover:bg-gray-50"
                        }
                      `}
                    >
                      <span
                        className={`
                          flex h-5 w-5 shrink-0
                          items-center justify-center
                          rounded-full border
                          ${
                            form.category_mode === "ALL"
                              ? "border-[#6d28d9] bg-[#6d28d9]"
                              : "border-gray-300"
                          }
                        `}
                      >
                        {form.category_mode === "ALL" && (
                          <span className="h-2 w-2 rounded-full bg-white" />
                        )}
                      </span>

                      <span>
                        <span className="block text-sm font-medium text-gray-900">
                          Everything
                        </span>

                        <span className="mt-0.5 block text-xs text-gray-400">
                          Can purchase from all categories.
                        </span>
                      </span>
                    </button>

                    {/* Selected */}

                    <button
                      type="button"
                      onClick={() =>
                        setForm((current) => ({
                          ...current,
                          category_mode: "SELECTED",
                        }))
                      }
                      className={`
                        flex w-full items-center gap-3
                        rounded-2xl
                        border
                        p-4
                        text-left
                        transition
                        ${
                          form.category_mode === "SELECTED"
                            ? "border-[#6d28d9] bg-[#faf8ff]"
                            : "border-gray-200 hover:bg-gray-50"
                        }
                      `}
                    >
                      <span
                        className={`
                          flex h-5 w-5 shrink-0
                          items-center justify-center
                          rounded-full border
                          ${
                            form.category_mode === "SELECTED"
                              ? "border-[#6d28d9] bg-[#6d28d9]"
                              : "border-gray-300"
                          }
                        `}
                      >
                        {form.category_mode === "SELECTED" && (
                          <span className="h-2 w-2 rounded-full bg-white" />
                        )}
                      </span>

                      <span>
                        <span className="block text-sm font-medium text-gray-900">
                          Selected categories
                        </span>

                        <span className="mt-0.5 block text-xs text-gray-400">
                          Choose specific categories.
                        </span>
                      </span>
                    </button>
                  </div>

                  {/* Category chips */}

                  {form.category_mode === "SELECTED" && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {CATEGORIES.map((category) => {
                        const selected = form.allowed_categories.includes(
                          category.value,
                        );

                        return (
                          <button
                            type="button"
                            key={category.value}
                            onClick={() => toggleAllowed(category.value)}
                            className={`
                              inline-flex items-center gap-1.5
                              rounded-full
                              border
                              px-3 py-2
                              text-xs
                              transition
                              ${
                                selected
                                  ? "border-[#6d28d9] bg-[#f1eafd] text-[#5b21b6]"
                                  : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                              }
                            `}
                          >
                            {selected && <Check size={13} />}

                            {category.label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* ---------------------------------------------
                    ADVANCED RESTRICTIONS
                ---------------------------------------------- */}

                <details className="group rounded-2xl border border-gray-200">
                  <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3.5 text-sm font-medium text-gray-800">
                    <span>Advanced restrictions</span>

                    <ChevronRight
                      size={16}
                      className="text-gray-400 transition group-open:rotate-90"
                    />
                  </summary>

                  <div className="border-t border-gray-100 px-4 pb-4 pt-3">
                    <p className="mb-3 text-xs leading-5 text-gray-400">
                      Block specific categories from being purchased.
                    </p>

                    <div className="flex flex-wrap gap-2">
                      {CATEGORIES.map((category) => {
                        const blocked = form.blocked_categories.includes(
                          category.value,
                        );

                        return (
                          <button
                            type="button"
                            key={category.value}
                            onClick={() => toggleBlocked(category.value)}
                            className={`
                              inline-flex items-center gap-1.5
                              rounded-full
                              border
                              px-3 py-2
                              text-xs
                              transition
                              ${
                                blocked
                                  ? "border-red-200 bg-red-50 text-red-600"
                                  : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                              }
                            `}
                          >
                            {blocked && <Check size={13} />}

                            {blocked
                              ? `Blocked ${category.label}`
                              : `Block ${category.label}`}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </details>

                {/* ---------------------------------------------
                    SPENDING LIMITS
                ---------------------------------------------- */}

                <div>
                  <div className="mb-3">
                    <h3 className="text-sm font-medium text-gray-900">
                      Spending limits
                    </h3>

                    <p className="mt-1 text-xs text-gray-400">
                      Set how much can be spent.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <label>
                      <span className="mb-2 block text-xs text-gray-500">
                        Per purchase
                      </span>

                      <div className="relative">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400">
                          ₹
                        </span>

                        <input
                          type="number"
                          min="1"
                          value={form.max_transaction}
                          onChange={(event) =>
                            setForm((current) => ({
                              ...current,
                              max_transaction: event.target.value,
                            }))
                          }
                          className="
                            h-11 w-full
                            rounded-xl
                            border border-gray-200
                            bg-white
                            pl-8 pr-3
                            text-sm text-gray-900
                            outline-none
                            transition
                            focus:border-[#6d28d9]
                            focus:ring-4
                            focus:ring-[#6d28d9]/10
                          "
                        />
                      </div>
                    </label>

                    <label>
                      <span className="mb-2 block text-xs text-gray-500">
                        Daily limit
                      </span>

                      <div className="relative">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400">
                          ₹
                        </span>

                        <input
                          type="number"
                          min="1"
                          value={form.daily_limit}
                          onChange={(event) =>
                            setForm((current) => ({
                              ...current,
                              daily_limit: event.target.value,
                            }))
                          }
                          className="
                            h-11 w-full
                            rounded-xl
                            border border-gray-200
                            bg-white
                            pl-8 pr-3
                            text-sm text-gray-900
                            outline-none
                            transition
                            focus:border-[#6d28d9]
                            focus:ring-4
                            focus:ring-[#6d28d9]/10
                          "
                        />
                      </div>
                    </label>
                  </div>
                </div>

                {/* ---------------------------------------------
                    AUTONOMOUS PURCHASING
                ---------------------------------------------- */}

                <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-gray-200 bg-gray-50 p-4 transition hover:bg-gray-100/70">
                  <input
                    type="checkbox"
                    checked={form.auto_purchase}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        auto_purchase: event.target.checked,
                      }))
                    }
                    className="mt-0.5 h-4 w-4 accent-[#6d28d9]"
                  />

                  <span>
                    <span className="flex items-center gap-1.5 text-sm font-medium text-gray-900">
                      Autonomous purchasing
                      <ShieldCheck size={14} className="text-[#6d28d9]" />
                    </span>

                    <span className="mt-1 block text-xs leading-5 text-gray-500">
                      Purchases can be completed without asking for confirmation
                      each time.
                    </span>
                  </span>
                </label>

                {/* ---------------------------------------------
                    ERROR
                ---------------------------------------------- */}

                {error && (
                  <div className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-600">
                    {error}
                  </div>
                )}
              </div>

              {/* =================================================
                  MODAL FOOTER
              ================================================== */}

              <div className="sticky bottom-0 flex shrink-0 justify-end gap-2 border-t border-gray-100 bg-white px-6 py-4">
                <button
                  type="button"
                  onClick={closeCreate}
                  disabled={busy}
                  className="
                    h-11 rounded-xl
                    px-4
                    text-sm font-medium
                    text-gray-600
                    transition
                    hover:bg-gray-100
                    disabled:opacity-40
                  "
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={busy}
                  className="
                    inline-flex h-11
                    items-center justify-center
                    gap-2
                    rounded-xl
                    bg-[#6d28d9]
                    px-5
                    text-sm font-medium
                    text-white
                    shadow-sm
                    transition
                    hover:bg-[#5b21b6]
                    active:scale-[0.98]
                    disabled:cursor-not-allowed
                    disabled:opacity-50
                  "
                >
                  {busy ? (
                    <>
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                      Creating...
                    </>
                  ) : (
                    <>
                      Create agent
                      <ChevronRight size={15} />
                    </>
                  )}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
