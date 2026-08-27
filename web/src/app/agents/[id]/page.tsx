"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleDollarSign,
  CreditCard,
  Package,
  Power,
  Save,
  ShieldCheck,
  ShoppingBag,
  Trash2,
  WalletCards,
} from "lucide-react";

import { useParams } from "next/navigation";

import { useUmonApi } from "@/src/lib/api";
import FundingModal from "@/src/components/FundingModal";

type CategoryMode = "ALL" | "SELECTED";

type Agent = {
  id: string;
  name: string;
  description: string | null;
  status: "ACTIVE" | "DISABLED" | "REVOKED" | string;

  balance_available: number;
  balance_available_paise: number;
  balance_reserved_paise: number;

  policy: {
    max_transaction_paise: number;
    daily_limit_paise: number;
    auto_purchase: boolean;

    category_mode?: CategoryMode;

    allowed_categories: string[];
    blocked_categories: string[];
  };
};

type LedgerEntry = {
  id: string;
  type: string;
  amount_paise: number;
  reason?: string;
  reference?: string;
  created_at?: string;
};

type AgentOrder = {
  id: string;
  status: string;
  payment_status: string;
  payment_method: string;
  amount_paise: number;
  created_at?: string;
};

type AgentStats = {
  agent: Agent;

  balance: {
    available_paise: number;
    available: string;
    reserved_paise: number;
    reserved: string;
  };

  spending: {
    today_paise: number;
    today: string;

    daily_limit_paise: number;
    daily_limit: string;

    daily_remaining_paise: number;
    daily_remaining: string;

    this_month_paise: number;
    this_month: string;

    lifetime_paise: number;
    lifetime: string;
  };

  funding: {
    lifetime_funded_paise: number;
    lifetime_funded: string;
  };

  limits: {
    transaction_paise: number;
    transaction: string;
  };

  ledger: LedgerEntry[];

  orders: AgentOrder[];

  activity?: ActivityEvent[];
};

type ActivityEvent = {
  id: string;
  action: string;
  result: string;
  amount_paise?: number | null;
  reason?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
};

const CATEGORIES = [
  {
    value: "grocery",
    label: "Grocery",
    icon: "🛒",
  },
  {
    value: "dairy",
    label: "Dairy",
    icon: "🥛",
  },
  {
    value: "snacks",
    label: "Snacks",
    icon: "🍿",
  },
  {
    value: "beverages",
    label: "Beverages",
    icon: "🥤",
  },
  {
    value: "household",
    label: "Household",
    icon: "🏠",
  },
  {
    value: "personal-care",
    label: "Personal Care",
    icon: "🧴",
  },
];

function money(paise: number) {
  return `₹${(Number(paise || 0) / 100).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function categoryLabel(value: string) {
  return value
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDate(value?: string) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return date.toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function shortDate(value: Date) {
  return value.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
}

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();

  const id = params?.id;

  const api = useUmonApi();

  const [stats, setStats] = useState<AgentStats | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const [fundAmount, setFundAmount] = useState("500");

  const [maxTxn, setMaxTxn] = useState("200");
  const [dailyLimit, setDailyLimit] = useState("400");

  const [autoPurchase, setAutoPurchase] = useState(true);

  const [categoryMode, setCategoryMode] = useState<CategoryMode>("ALL");

  const [allowedCategories, setAllowedCategories] = useState<string[]>([]);

  const [blockedCategories, setBlockedCategories] = useState<string[]>([]);

  const [showAdvanced, setShowAdvanced] = useState(false);

  const [saving, setSaving] = useState(false);
  const [changingStatus, setChangingStatus] = useState(false);
  const [revoking, setRevoking] = useState(false);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    if (!id) return;

    try {
      setError("");

      const data = await api.agentStats(id);

      const result = data as AgentStats;

      setStats(result);

      setName(result.agent.name ?? "");
      setDescription(result.agent.description ?? "");

      setMaxTxn(
        String(Number(result.agent.policy.max_transaction_paise ?? 0) / 100),
      );

      setDailyLimit(
        String(Number(result.agent.policy.daily_limit_paise ?? 0) / 100),
      );

      setAutoPurchase(Boolean(result.agent.policy.auto_purchase));

      setCategoryMode(result.agent.policy.category_mode ?? "ALL");

      setAllowedCategories(result.agent.policy.allowed_categories ?? []);

      setBlockedCategories(result.agent.policy.blocked_categories ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load agent.");
    }
  }, [api, id]);

  useEffect(() => {
    load();
  }, [load]);

  const availablePaise =
    stats?.balance.available_paise ?? stats?.agent.balance_available_paise ?? 0;

  const reservedPaise =
    stats?.balance.reserved_paise ?? stats?.agent.balance_reserved_paise ?? 0;

  const spentTodayPaise = stats?.spending.today_paise ?? 0;

  const spentThisMonthPaise = stats?.spending.this_month_paise ?? 0;

  const lifetimeSpentPaise = stats?.spending.lifetime_paise ?? 0;

  const lifetimeFundedPaise = stats?.funding.lifetime_funded_paise ?? 0;

  const dailyLimitPaise =
    stats?.spending.daily_limit_paise ??
    stats?.agent.policy.daily_limit_paise ??
    0;

  const remainingTodayPaise = Math.max(0, dailyLimitPaise - spentTodayPaise);

  const spendingPercent =
    dailyLimitPaise > 0
      ? Math.min(100, (spentTodayPaise / dailyLimitPaise) * 100)
      : 0;

  const scopeLabel = useMemo(() => {
    if (categoryMode === "ALL") {
      if (blockedCategories.length) {
        return `Everything except ${blockedCategories
          .map(categoryLabel)
          .join(", ")}`;
      }

      return "Everything";
    }

    if (!allowedCategories.length) {
      return "Nothing selected";
    }

    return allowedCategories.map(categoryLabel).join(" · ");
  }, [categoryMode, allowedCategories, blockedCategories]);

  /*
   * ----------------------------------------------------------
   * 7 DAY SPENDING GRAPH
   * ----------------------------------------------------------
   *
   * Uses existing ledger data.
   * Debit-like entries are treated as spending.
   */

  const weeklySpending = useMemo(() => {
    const today = new Date();

    const days = Array.from({ length: 7 }, (_, index) => {
      const date = new Date(today);

      date.setHours(0, 0, 0, 0);

      date.setDate(today.getDate() - (6 - index));

      return {
        date,
        label: shortDate(date),
        value: 0,
      };
    });

    for (const entry of stats?.ledger ?? []) {
      if (!entry.created_at) continue;

      const date = new Date(entry.created_at);

      if (Number.isNaN(date.getTime())) {
        continue;
      }

      const entryDay = new Date(date);

      entryDay.setHours(0, 0, 0, 0);

      const matchingDay = days.find(
        (day) => day.date.getTime() === entryDay.getTime(),
      );

      if (!matchingDay) continue;

      const type = entry.type.toUpperCase();

      const isCredit =
        type === "CREDIT" || type === "FUND" || type === "FUNDING";

      const isRelease = type === "RELEASE" || type === "REFUND";

      if (!isCredit && !isRelease) {
        matchingDay.value += Math.max(0, Number(entry.amount_paise || 0));
      }
    }

    /*
     * If ledger data has no daily entries but today's
     * spending exists, show today's actual spending.
     */
    if (days.every((day) => day.value === 0) && spentTodayPaise > 0) {
      days[6].value = spentTodayPaise;
    }

    return days;
  }, [stats?.ledger, spentTodayPaise]);

  const maxWeeklySpend = Math.max(...weeklySpending.map((day) => day.value), 1);

  function toggleAllowed(category: string) {
    setAllowedCategories((current) =>
      current.includes(category)
        ? current.filter((value) => value !== category)
        : [...current, category],
    );

    setBlockedCategories((current) =>
      current.filter((value) => value !== category),
    );
  }

  function toggleBlocked(category: string) {
    setBlockedCategories((current) =>
      current.includes(category)
        ? current.filter((value) => value !== category)
        : [...current, category],
    );

    setAllowedCategories((current) =>
      current.filter((value) => value !== category),
    );
  }

  async function save() {
    setError("");
    setSuccess("");

    const numericMaxTxn = Number(maxTxn);
    const numericDaily = Number(dailyLimit);

    if (!name.trim()) {
      setError("Agent name is required.");
      return;
    }

    if (!Number.isFinite(numericMaxTxn) || numericMaxTxn <= 0) {
      setError("Maximum transaction must be greater than zero.");
      return;
    }

    if (!Number.isFinite(numericDaily) || numericDaily <= 0) {
      setError("Daily spending limit must be greater than zero.");
      return;
    }

    if (numericMaxTxn > numericDaily) {
      setError("Transaction limit cannot exceed daily limit.");
      return;
    }

    if (categoryMode === "SELECTED" && allowedCategories.length === 0) {
      setError("Select at least one category.");
      return;
    }

    setSaving(true);

    try {
      await api.updateAgent(id, {
        name: name.trim(),
        description: description.trim() || null,
      });

      await api.updateAgentPolicy(id, {
        max_transaction: numericMaxTxn,
        daily_limit: numericDaily,
        auto_purchase: autoPurchase,
        category_mode: categoryMode,
        allowed_categories: categoryMode === "ALL" ? [] : allowedCategories,
        blocked_categories: blockedCategories,
      });

      await load();

      setSuccess("Agent settings saved successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save agent.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleStatus() {
    if (!stats) return;

    const nextStatus = stats.agent.status === "ACTIVE" ? "DISABLED" : "ACTIVE";

    setChangingStatus(true);
    setError("");
    setSuccess("");

    try {
      await api.updateAgentStatus(id, nextStatus);

      await load();

      setSuccess(
        nextStatus === "ACTIVE" ? "Agent enabled." : "Agent disabled.",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to change agent status.",
      );
    } finally {
      setChangingStatus(false);
    }
  }

  async function revoke() {
    const confirmed = window.confirm(
      "Revoke this agent?\n\nThe agent will no longer be usable for purchasing. Existing orders and spending history will remain visible.",
    );

    if (!confirmed) return;

    setRevoking(true);
    setError("");
    setSuccess("");

    try {
      await api.deleteAgent(id);

      await load();

      setSuccess("Agent revoked.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to revoke agent.");
    } finally {
      setRevoking(false);
    }
  }

  if (!stats) {
    return (
      <main className="min-h-screen bg-[#f7f7f8]">
        <div className="mx-auto flex min-h-screen max-w-6xl items-center justify-center px-5">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-[#6d28d9]/15 border-t-[#6d28d9]" />

            <p className="text-sm text-gray-400">
              {error || "Loading agent..."}
            </p>
          </div>
        </div>
      </main>
    );
  }

  const active = stats.agent.status === "ACTIVE";

  return (
    <main className="min-h-screen bg-[#f7f7f8] text-gray-900">
      <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        {/* =====================================================
            BACK
        ====================================================== */}

        <a
          href="/agents"
          className="mb-6 inline-flex items-center gap-2 text-sm text-gray-500 transition hover:text-gray-900"
        >
          <ArrowLeft size={16} />
          Back to agents
        </a>

        {/* =====================================================
            HEADER
        ====================================================== */}

        <section className="mb-6 flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-[#f1eafd] text-[#6d28d9]">
              <ShieldCheck size={25} />
            </div>

            <div>
              <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.15em] text-[#6d28d9]">
                Purchasing agent
              </div>

              <h1 className="text-2xl font-semibold tracking-tight text-gray-950 sm:text-3xl">
                {stats.agent.name}
              </h1>

              <p className="mt-1 max-w-xl text-sm text-gray-500">
                {stats.agent.description ||
                  "Manage this agent's purchasing access and spending."}
              </p>
            </div>
          </div>

          <div
            className={
              active
                ? "flex w-fit items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-600"
                : "flex w-fit items-center gap-2 rounded-full bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-500"
            }
          >
            <span
              className={
                active
                  ? "h-2 w-2 rounded-full bg-emerald-500"
                  : "h-2 w-2 rounded-full bg-gray-400"
              }
            />

            {stats.agent.status}
          </div>
        </section>

        {/* =====================================================
            ALERTS
        ====================================================== */}

        {error && (
          <div className="mb-4 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertTriangle size={17} className="shrink-0" />

            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            <Check size={17} className="shrink-0" />

            <span>{success}</span>
          </div>
        )}

        {/* =====================================================
            TOP OVERVIEW
        ====================================================== */}

        <section className="grid gap-4 lg:grid-cols-[1.35fr_0.65fr]">
          {/* BALANCE HERO */}

          <article className="relative overflow-hidden rounded-3xl bg-[#6d28d9] p-6 text-white shadow-[0_8px_30px_rgba(109,40,217,0.18)]">
            <div className="relative z-10">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-white/65">Available balance</p>

                  <p className="mt-2 text-4xl font-semibold tracking-tight">
                    {money(availablePaise)}
                  </p>
                </div>

                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10">
                  <WalletCards size={21} />
                </div>
              </div>

              <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div className="rounded-2xl bg-white/10 p-3">
                  <p className="text-[11px] text-white/55">Reserved</p>

                  <p className="mt-1 text-sm font-medium">
                    {money(reservedPaise)}
                  </p>
                </div>

                <div className="rounded-2xl bg-white/10 p-3">
                  <p className="text-[11px] text-white/55">Funded</p>

                  <p className="mt-1 text-sm font-medium">
                    {money(lifetimeFundedPaise)}
                  </p>
                </div>

                <div className="col-span-2 rounded-2xl bg-white/10 p-3 sm:col-span-1">
                  <p className="text-[11px] text-white/55">Lifetime spent</p>

                  <p className="mt-1 text-sm font-medium">
                    {money(lifetimeSpentPaise)}
                  </p>
                </div>
              </div>
            </div>

            <div className="absolute -right-20 -top-20 h-56 w-56 rounded-full bg-white/[0.06]" />
            <div className="absolute -bottom-24 -left-10 h-48 w-48 rounded-full bg-white/[0.05]" />
          </article>

          {/* TODAY */}

          <article className="rounded-3xl border border-gray-100 bg-white p-6 shadow-[0_2px_12px_rgba(0,0,0,0.035)]">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-gray-400">Today's spending</p>

                <p className="mt-1 text-2xl font-semibold tracking-tight text-gray-950">
                  {money(spentTodayPaise)}
                </p>
              </div>

              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#f1eafd] text-[#6d28d9]">
                <Activity size={18} />
              </div>
            </div>

            <div className="mt-6">
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="text-gray-400">Daily limit</span>

                <span className="font-medium text-gray-700">
                  {money(dailyLimitPaise)}
                </span>
              </div>

              <div className="h-2 overflow-hidden rounded-full bg-gray-100">
                <div
                  className="h-full rounded-full bg-[#6d28d9] transition-all duration-500"
                  style={{
                    width: `${spendingPercent}%`,
                  }}
                />
              </div>

              <div className="mt-3 flex items-center justify-between">
                <span className="text-xs text-gray-400">
                  {Math.round(spendingPercent)}% used
                </span>

                <span className="text-xs font-medium text-gray-700">
                  {money(remainingTodayPaise)} left
                </span>
              </div>
            </div>
          </article>
        </section>

        {/* =====================================================
            SPENDING GRAPH + SUMMARY
        ====================================================== */}

        <section className="mt-4 grid gap-4 lg:grid-cols-[1.35fr_0.65fr]">
          {/* GRAPH */}

          <article className="rounded-3xl border border-gray-100 bg-white p-5 shadow-[0_2px_12px_rgba(0,0,0,0.035)] sm:p-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-gray-400">Spending activity</p>

                <h2 className="mt-1 text-lg font-medium text-gray-950">
                  Last 7 days
                </h2>
              </div>

              <div className="flex items-center gap-1.5 rounded-full bg-gray-50 px-2.5 py-1.5 text-[10px] text-gray-400">
                <span className="h-1.5 w-1.5 rounded-full bg-[#6d28d9]" />
                Spending
              </div>
            </div>

            <div className="mt-7">
              <div className="flex h-44 items-end gap-2 sm:gap-4">
                {weeklySpending.map((day, index) => {
                  const height =
                    day.value > 0
                      ? Math.max(8, (day.value / maxWeeklySpend) * 100)
                      : 4;

                  const isToday = index === weeklySpending.length - 1;

                  return (
                    <div
                      key={day.label}
                      className="flex h-full flex-1 flex-col items-center justify-end gap-2"
                    >
                      <div className="relative flex w-full flex-1 items-end justify-center">
                        {day.value > 0 && (
                          <div className="group relative w-full max-w-[34px]">
                            <div
                              className={`
                                  w-full rounded-t-xl
                                  transition-all duration-300
                                  ${isToday ? "bg-[#6d28d9]" : "bg-[#ddd3f5]"}
                                `}
                              style={{
                                height: `${height}%`,
                                minHeight: "8px",
                              }}
                            />

                            <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-gray-900 px-2 py-1 text-[10px] text-white opacity-0 shadow-lg transition group-hover:opacity-100">
                              {money(day.value)}
                            </div>
                          </div>
                        )}

                        {day.value === 0 && (
                          <div className="w-full max-w-[34px] rounded-full bg-gray-100 h-1" />
                        )}
                      </div>

                      <span
                        className={
                          isToday
                            ? "text-[10px] font-medium text-[#6d28d9]"
                            : "text-[10px] text-gray-400"
                        }
                      >
                        {day.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </article>

          {/* SPENDING SUMMARY */}

          <article className="rounded-3xl border border-gray-100 bg-white p-5 shadow-[0_2px_12px_rgba(0,0,0,0.035)] sm:p-6">
            <p className="text-xs text-gray-400">Spending summary</p>

            <div className="mt-5 space-y-5">
              <SummaryMetric
                icon={<Activity size={17} />}
                label="Today"
                value={money(spentTodayPaise)}
                detail={`${Math.round(spendingPercent)}% of daily limit`}
              />

              <SummaryMetric
                icon={<ShoppingBag size={17} />}
                label="This month"
                value={money(spentThisMonthPaise)}
                detail="Current month"
              />

              <SummaryMetric
                icon={<CircleDollarSign size={17} />}
                label="Lifetime"
                value={money(lifetimeSpentPaise)}
                detail="Total spending"
              />
            </div>
          </article>
        </section>

        {/* =====================================================
            FUNDING + SETTINGS
        ====================================================== */}

        <section className="mt-4 grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
          {/* FUNDING */}

          <article className="rounded-3xl border border-gray-100 bg-white p-5 shadow-[0_2px_12px_rgba(0,0,0,0.035)] sm:p-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-gray-400">Add funds</p>

                <h2 className="mt-1 text-lg font-medium text-gray-950">
                  Fund this agent
                </h2>
              </div>

              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gray-50 text-gray-600">
                <CreditCard size={18} />
              </div>
            </div>

            <p className="mt-2 text-sm leading-5 text-gray-500">
              Add balance that can be used for future purchases.
            </p>

            <div className="mt-6 flex gap-2">
              <div className="flex flex-1 items-center rounded-xl border border-gray-200 bg-gray-50 px-3 focus-within:border-[#6d28d9] focus-within:bg-white">
                <span className="text-sm text-gray-400">₹</span>

                <input
                  type="number"
                  min="1"
                  step="1"
                  value={fundAmount}
                  onChange={(event) => setFundAmount(event.target.value)}
                  className="w-full bg-transparent px-2 py-3 text-sm text-gray-900 outline-none"
                />
              </div>

              <FundingModal
                agentId={id}
                amount={Number(fundAmount)}
                onSuccess={load}
              />
            </div>

            <div className="mt-5 border-t border-gray-100 pt-5">
              <BalanceRow label="Available" value={money(availablePaise)} />

              <BalanceRow label="Reserved" value={money(reservedPaise)} />

              <BalanceRow
                label="Lifetime funded"
                value={money(lifetimeFundedPaise)}
              />
            </div>
          </article>

          {/* SETTINGS */}

          <article className="rounded-3xl border border-gray-100 bg-white p-5 shadow-[0_2px_12px_rgba(0,0,0,0.035)] sm:p-6">
            <div className="mb-6">
              <p className="text-xs text-gray-400">Settings</p>

              <h2 className="mt-1 text-lg font-medium text-gray-950">
                Purchasing controls
              </h2>

              <p className="mt-1 text-sm text-gray-500">
                Choose what this agent can purchase and how much it can spend.
              </p>
            </div>

            <div className="space-y-5">
              {/* NAME */}

              <Field label="Agent name">
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={80}
                  className={inputClass}
                />
              </Field>

              {/* DESCRIPTION */}

              <Field label="Description">
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={3}
                  maxLength={500}
                  className={`${inputClass} resize-y`}
                />
              </Field>

              {/* LIMITS */}

              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Per purchase">
                  <MoneyInput value={maxTxn} onChange={setMaxTxn} />
                </Field>

                <Field label="Daily limit">
                  <MoneyInput value={dailyLimit} onChange={setDailyLimit} />
                </Field>
              </div>

              {/* SCOPE */}

              <div className="border-t border-gray-100 pt-5">
                <div>
                  <p className="text-sm font-medium text-gray-900">
                    Purchase access
                  </p>

                  <p className="mt-1 text-xs text-gray-400">
                    Choose where this agent can shop.
                  </p>
                </div>

                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <ScopeButton
                    selected={categoryMode === "ALL"}
                    title="Everything"
                    description="All categories"
                    onClick={() => {
                      setCategoryMode("ALL");
                      setAllowedCategories([]);
                    }}
                  />

                  <ScopeButton
                    selected={categoryMode === "SELECTED"}
                    title="Selected"
                    description="Choose categories"
                    onClick={() => setCategoryMode("SELECTED")}
                  />
                </div>

                {categoryMode === "SELECTED" && (
                  <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {CATEGORIES.map((category) => {
                      const selected = allowedCategories.includes(
                        category.value,
                      );

                      return (
                        <button
                          key={category.value}
                          type="button"
                          onClick={() => toggleAllowed(category.value)}
                          className={`
                              flex min-h-[72px]
                              flex-col
                              items-start
                              justify-between
                              rounded-xl
                              border
                              p-3
                              text-left
                              transition
                              ${
                                selected
                                  ? "border-[#6d28d9] bg-[#faf8ff]"
                                  : "border-gray-200 hover:bg-gray-50"
                              }
                            `}
                        >
                          <span className="text-lg">{category.icon}</span>

                          <span className="flex w-full items-center justify-between gap-1">
                            <span
                              className={
                                selected
                                  ? "text-xs font-medium text-[#5b21b6]"
                                  : "text-xs text-gray-600"
                              }
                            >
                              {category.label}
                            </span>

                            {selected && (
                              <Check size={14} className="text-[#6d28d9]" />
                            )}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* ADVANCED */}

              <div className="border-t border-gray-100 pt-4">
                <button
                  type="button"
                  onClick={() => setShowAdvanced((current) => !current)}
                  className="flex w-full items-center justify-between text-left text-sm text-gray-700"
                >
                  <span>Advanced restrictions</span>

                  <ChevronDown
                    size={16}
                    className={
                      showAdvanced
                        ? "rotate-180 text-gray-400 transition"
                        : "text-gray-400 transition"
                    }
                  />
                </button>

                {showAdvanced && (
                  <div className="mt-4">
                    <p className="mb-3 text-xs leading-5 text-gray-400">
                      Block specific categories from being purchased.
                    </p>

                    <div className="flex flex-wrap gap-2">
                      {CATEGORIES.map((category) => {
                        const blocked = blockedCategories.includes(
                          category.value,
                        );

                        return (
                          <button
                            key={category.value}
                            type="button"
                            onClick={() => toggleBlocked(category.value)}
                            className={
                              blocked
                                ? "rounded-full border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600"
                                : "rounded-full border border-gray-200 bg-white px-3 py-2 text-xs text-gray-600 hover:bg-gray-50"
                            }
                          >
                            {blocked ? "Blocked " : "Block "}
                            {category.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* AUTO PURCHASE */}

              <div className="flex items-center justify-between gap-4 rounded-2xl bg-gray-50 p-4">
                <div>
                  <p className="text-sm font-medium text-gray-900">
                    Autonomous purchasing
                  </p>

                  <p className="mt-1 max-w-md text-xs leading-5 text-gray-500">
                    {autoPurchase
                      ? "Purchases can proceed automatically when all limits are satisfied."
                      : "Purchases require explicit confirmation."}
                  </p>
                </div>

                <button
                  type="button"
                  role="switch"
                  aria-checked={autoPurchase}
                  onClick={() => setAutoPurchase((current) => !current)}
                  className={
                    autoPurchase
                      ? "relative h-6 w-11 shrink-0 rounded-full bg-[#6d28d9] transition"
                      : "relative h-6 w-11 shrink-0 rounded-full bg-gray-300 transition"
                  }
                >
                  <span
                    className={
                      autoPurchase
                        ? "absolute left-[22px] top-[3px] h-5 w-5 rounded-full bg-white shadow-sm transition"
                        : "absolute left-[3px] top-[3px] h-5 w-5 rounded-full bg-white shadow-sm transition"
                    }
                  />
                </button>
              </div>

              {/* SUMMARY */}

              <div className="rounded-2xl border border-gray-100 bg-[#fafafa] p-4">
                <p className="text-[10px] uppercase tracking-wider text-gray-400">
                  Current access
                </p>

                <p className="mt-1 text-sm text-gray-700">{scopeLabel}</p>

                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="rounded-full bg-white px-2.5 py-1 text-[10px] text-gray-500 ring-1 ring-gray-100">
                    ₹{maxTxn} per purchase
                  </span>

                  <span className="rounded-full bg-white px-2.5 py-1 text-[10px] text-gray-500 ring-1 ring-gray-100">
                    ₹{dailyLimit} daily
                  </span>
                </div>
              </div>

              {/* SAVE */}

              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="
                  flex w-full
                  items-center justify-center gap-2
                  rounded-xl
                  bg-[#6d28d9]
                  px-4 py-3
                  text-sm font-medium
                  text-white
                  shadow-[0_5px_16px_rgba(109,40,217,0.18)]
                  transition
                  hover:bg-[#5b21b6]
                  disabled:cursor-not-allowed
                  disabled:opacity-50
                "
              >
                <Save size={16} />

                {saving ? "Saving..." : "Save changes"}
              </button>
            </div>
          </article>
        </section>

        {/* =====================================================
            RECENT ACTIVITY
        ====================================================== */}

        <section className="mt-4 grid gap-4 lg:grid-cols-2">
          {/* LEDGER */}

          <article className="overflow-hidden rounded-3xl border border-gray-100 bg-white shadow-[0_2px_12px_rgba(0,0,0,0.035)]">
            <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
              <div>
                <p className="text-xs text-gray-400">Recent activity</p>

                <h2 className="mt-1 text-lg font-medium text-gray-950">
                  Transactions
                </h2>
              </div>

              <span className="text-xs text-gray-400">
                {stats.ledger.length}
              </span>
            </div>

            <div className="divide-y divide-gray-100">
              {stats.ledger.slice(0, 7).map((entry) => {
                const type = entry.type.toUpperCase();

                const credit =
                  type === "CREDIT" || type === "FUND" || type === "FUNDING";

                const release = type === "RELEASE" || type === "REFUND";

                return (
                  <div
                    key={entry.id}
                    className="flex items-center gap-3 px-5 py-3.5"
                  >
                    <div
                      className={
                        credit
                          ? "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600"
                          : release
                            ? "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gray-100 text-gray-500"
                            : "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#f1eafd] text-[#6d28d9]"
                      }
                    >
                      {credit ? (
                        <ArrowDownRight size={16} />
                      ) : (
                        <ArrowUpRight size={16} />
                      )}
                    </div>

                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-gray-800">
                        {entry.reason || entry.type}
                      </p>

                      <p className="mt-0.5 truncate text-[11px] text-gray-400">
                        {formatDate(entry.created_at)}
                      </p>
                    </div>

                    <span
                      className={
                        credit
                          ? "text-sm font-medium text-emerald-600"
                          : "text-sm font-medium text-gray-800"
                      }
                    >
                      {credit ? "+" : "-"}
                      {money(entry.amount_paise)}
                    </span>
                  </div>
                );
              })}

              {!stats.ledger.length && (
                <div className="px-5 py-10 text-center text-sm text-gray-400">
                  No transactions yet.
                </div>
              )}
            </div>
          </article>

          {/* ORDERS */}

          <article className="overflow-hidden rounded-3xl border border-gray-100 bg-white shadow-[0_2px_12px_rgba(0,0,0,0.035)]">
            <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
              <div>
                <p className="text-xs text-gray-400">Purchase history</p>

                <h2 className="mt-1 text-lg font-medium text-gray-950">
                  Recent orders
                </h2>
              </div>

              <span className="text-xs text-gray-400">
                {stats.orders.length}
              </span>
            </div>

            <div className="divide-y divide-gray-100">
              {stats.orders.slice(0, 7).map((order) => (
                <div
                  key={order.id}
                  className="flex items-center gap-3 px-5 py-3.5"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gray-50 text-gray-500">
                    <Package size={16} />
                  </div>

                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-gray-800">
                      Order {order.id.slice(-8)}
                    </p>

                    <p className="mt-0.5 text-[11px] text-gray-400">
                      {formatDate(order.created_at)}
                    </p>
                  </div>

                  <div className="text-right">
                    <p className="text-sm font-medium text-gray-900">
                      {money(order.amount_paise)}
                    </p>

                    <p className="mt-0.5 text-[10px] text-gray-400">
                      {order.status}
                    </p>
                  </div>
                </div>
              ))}

              {!stats.orders.length && (
                <div className="px-5 py-10 text-center text-sm text-gray-400">
                  No purchases yet.
                </div>
              )}
            </div>
          </article>
        </section>

        {/* =====================================================
            CONTROL AREA
        ====================================================== */}

        <section className="mt-4 mb-10 rounded-3xl border border-red-100 bg-white p-5 sm:p-6">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-50 text-red-500">
                  <Power size={15} />
                </div>

                <p className="text-sm font-medium text-gray-900">
                  Agent controls
                </p>
              </div>

              <p className="mt-2 max-w-lg text-xs leading-5 text-gray-500">
                Disable the agent temporarily or revoke it permanently. Existing
                orders and transaction history remain available.
              </p>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                onClick={toggleStatus}
                disabled={changingStatus || revoking}
                className="
                  inline-flex
                  items-center
                  justify-center
                  gap-2
                  rounded-xl
                  border
                  border-gray-200
                  bg-white
                  px-4 py-2.5
                  text-sm
                  text-gray-700
                  transition
                  hover:bg-gray-50
                  disabled:opacity-50
                "
              >
                <Power size={15} />

                {changingStatus
                  ? "Updating..."
                  : active
                    ? "Disable agent"
                    : "Enable agent"}
              </button>

              <button
                type="button"
                onClick={revoke}
                disabled={
                  revoking || changingStatus || stats.agent.status === "REVOKED"
                }
                className="
                  inline-flex
                  items-center
                  justify-center
                  gap-2
                  rounded-xl
                  border
                  border-red-200
                  bg-white
                  px-4 py-2.5
                  text-sm
                  text-red-600
                  transition
                  hover:bg-red-50
                  disabled:opacity-50
                "
              >
                <Trash2 size={15} />

                {revoking ? "Revoking..." : "Revoke agent"}
              </button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

/* =============================================================
   SHARED UI
============================================================= */

const inputClass =
  "w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-900 outline-none transition placeholder:text-gray-400 focus:border-[#6d28d9] focus:bg-white focus:ring-4 focus:ring-[#6d28d9]/10";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs text-gray-600">{label}</span>

      {children}
    </label>
  );
}

function MoneyInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex items-center rounded-xl border border-gray-200 bg-gray-50 px-3 transition focus-within:border-[#6d28d9] focus-within:bg-white focus-within:ring-4 focus-within:ring-[#6d28d9]/10">
      <span className="text-sm text-gray-400">₹</span>

      <input
        type="number"
        min="1"
        step="1"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full bg-transparent px-2 py-3 text-sm text-gray-900 outline-none"
      />
    </div>
  );
}

function BalanceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5">
      <span className="text-sm text-gray-500">{label}</span>

      <span className="text-sm font-medium text-gray-900">{value}</span>
    </div>
  );
}

function ScopeButton({
  selected,
  title,
  description,
  onClick,
}: {
  selected: boolean;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        flex items-center gap-3
        rounded-xl
        border
        p-3
        text-left
        transition
        ${
          selected
            ? "border-[#6d28d9] bg-[#faf8ff]"
            : "border-gray-200 bg-white hover:bg-gray-50"
        }
      `}
    >
      <span
        className={`
          flex h-5 w-5 shrink-0
          items-center justify-center
          rounded-full border
          ${selected ? "border-[#6d28d9] bg-[#6d28d9]" : "border-gray-300"}
        `}
      >
        {selected && <span className="h-2 w-2 rounded-full bg-white" />}
      </span>

      <span>
        <span className="block text-sm text-gray-800">{title}</span>

        <span className="mt-0.5 block text-[11px] text-gray-400">
          {description}
        </span>
      </span>
    </button>
  );
}

function SummaryMetric({
  icon,
  label,
  value,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#f1eafd] text-[#6d28d9]">
        {icon}
      </div>

      <div className="min-w-0 flex-1">
        <p className="text-xs text-gray-400">{label}</p>

        <p className="mt-0.5 text-base font-medium text-gray-900">{value}</p>
      </div>

      <span className="text-[10px] text-gray-400">{detail}</span>
    </div>
  );
}
