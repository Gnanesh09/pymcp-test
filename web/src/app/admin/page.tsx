"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Activity,
  AlertTriangle,
  Boxes,
  Check,
  ChevronRight,
  CircleDollarSign,
  ExternalLink,
  Package,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings2,
  ShoppingCart,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  Trash2,
  Users,
  WalletCards,
  X,
} from "lucide-react";

import { useUmonApi } from "@/src/lib/api";

type Product = {
  id: string;
  name: string;
  brand: string;
  category: string;
  price_paise: number;
  mrp_paise: number;
  stock: number;
  unit: string;
  description: string;
  image?: string | null;
  tags: string[];
  active: boolean;
};

type Merchant = {
  _id: string;
  name: string;
  status: "ACTIVE" | "DISABLED" | string;
  ai_discovery: boolean;
  ai_purchasing: boolean;
  ai_checkout: boolean;
  recommendations_enabled: boolean;
  max_order_value: number;
  allowed_categories: string[];
};

type DashboardData = {
  merchant: Merchant;

  metrics: {
    users: number;
    agents: number;
    active_agents: number;
    orders: number;
    paid_orders: number;
    pending_payments: number;
    products: number;
    active_products: number;
    gmv_paise: number;
    gmv: string;
    agent_available_paise: number;
    agent_available: string;
    agent_reserved_paise: number;
    agent_reserved: string;
  };

  recent_orders: any[];
  recent_audit: any[];
};

type AdminSection =
  | "overview"
  | "merchant"
  | "catalog"
  | "orders"
  | "payments"
  | "agents"
  | "users"
  | "audit";

const CATEGORIES = [
  "grocery",
  "dairy",
  "snacks",
  "beverages",
  "household",
  "personal-care",
];

const sectionItems: {
  id: AdminSection;
  label: string;
  icon: React.ReactNode;
}[] = [
  {
    id: "overview",
    label: "Overview",
    icon: <Activity size={16} />,
  },
  {
    id: "merchant",
    label: "Merchant",
    icon: <Settings2 size={16} />,
  },
  {
    id: "catalog",
    label: "Catalog",
    icon: <Boxes size={16} />,
  },
  {
    id: "orders",
    label: "Orders",
    icon: <ShoppingCart size={16} />,
  },
  {
    id: "payments",
    label: "Payments",
    icon: <CircleDollarSign size={16} />,
  },
  {
    id: "agents",
    label: "Agents",
    icon: <WalletCards size={16} />,
  },
  {
    id: "users",
    label: "Users",
    icon: <Users size={16} />,
  },
  {
    id: "audit",
    label: "Audit",
    icon: <Activity size={16} />,
  },
];

export default function AdminPage() {
  const api = useUmonApi();

  const [section, setSection] = useState<AdminSection>("overview");

  const [dashboard, setDashboard] = useState<DashboardData | null>(null);

  const [merchant, setMerchant] = useState<Merchant | null>(null);

  const [products, setProducts] = useState<Product[]>([]);

  const [orders, setOrders] = useState<any[]>([]);

  const [payments, setPayments] = useState<any[]>([]);

  const [agents, setAgents] = useState<any[]>([]);

  const [users, setUsers] = useState<any[]>([]);

  const [auditEvents, setAuditEvents] = useState<any[]>([]);

  const [loading, setLoading] = useState(true);

  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState("");

  const [search, setSearch] = useState("");

  const [editingProduct, setEditingProduct] = useState<Product | null>(null);

  const [showProductModal, setShowProductModal] = useState(false);

  const [savingMerchant, setSavingMerchant] = useState(false);

  const [showMobileNav, setShowMobileNav] = useState(false);

  const loadEverything = useCallback(
    async (silent = false) => {
      try {
        if (silent) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }

        setError("");

        const [
          dashboardData,
          merchantData,
          productsData,
          ordersData,
          paymentsData,
          agentsData,
          usersData,
          auditData,
        ] = await Promise.all([
          api.adminDashboard(),
          api.adminMerchant(),
          api.adminProducts(),
          api.adminOrders(),
          api.adminPayments(),
          api.adminAgents(),
          api.adminUsers(),
          api.adminAudit(),
        ]);

        setDashboard(dashboardData);

        setMerchant(merchantData.merchant);

        setProducts(productsData.products ?? []);

        setOrders(ordersData.orders ?? []);

        setPayments(paymentsData.payments ?? []);

        setAgents(agentsData.agents ?? []);

        setUsers(usersData.users ?? []);

        setAuditEvents(auditData.events ?? []);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Unable to load admin data.",
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [api],
  );

  useEffect(() => {
    void loadEverything();
  }, [loadEverything]);

  async function saveMerchant() {
    if (!merchant) return;

    setSavingMerchant(true);
    setError("");

    try {
      const result = await api.updateAdminMerchant({
        name: merchant.name,
        status: merchant.status as "ACTIVE" | "DISABLED",
        ai_discovery: merchant.ai_discovery,
        ai_purchasing: merchant.ai_purchasing,
        ai_checkout: merchant.ai_checkout,
        recommendations_enabled: merchant.recommendations_enabled,
        max_order_value: merchant.max_order_value / 100,
        allowed_categories: merchant.allowed_categories,
      });

      setMerchant(result.merchant);

      await loadEverything(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save merchant.");
    } finally {
      setSavingMerchant(false);
    }
  }

  async function deleteProduct(product: Product) {
    const confirmed = window.confirm(
      `Disable "${product.name}" from the catalog?`,
    );

    if (!confirmed) return;

    try {
      await api.adminDeleteProduct(product.id);

      await loadEverything(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to disable product.",
      );
    }
  }

  const visibleProducts = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) {
      return products;
    }

    return products.filter((product) =>
      [product.name, product.brand, product.category]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [products, search]);

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-50">
        <div className="flex min-h-screen items-center justify-center">
          <div className="text-sm text-slate-500">Loading admin console…</div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950">
      {/* ====================================================
          TOP BAR
          ==================================================== */}

      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center justify-between px-4 lg:px-6">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-slate-950 text-sm font-bold text-white">
              U
            </div>

            <div>
              <p className="text-sm font-semibold">Umon Control</p>

              <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-400">
                Development Admin
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <a
              href="/"
              className="hidden items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:text-slate-950 sm:inline-flex"
            >
              Store
              <ExternalLink size={13} />
            </a>

            <button
              type="button"
              onClick={() => void loadEverything(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:text-slate-950"
            >
              <RefreshCw
                size={14}
                className={refreshing ? "animate-spin" : ""}
              />
              Refresh
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1500px]">
        {/* ==================================================
            SIDEBAR
            ================================================== */}

        <aside className="hidden min-h-[calc(100vh-64px)] w-60 shrink-0 border-r border-slate-200 bg-white p-4 lg:block">
          <nav className="space-y-1">
            {sectionItems.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSection(item.id)}
                className={
                  section === item.id
                    ? "flex w-full items-center gap-3 rounded-xl bg-slate-950 px-3 py-2.5 text-sm font-semibold text-white"
                    : "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-500 hover:bg-slate-50 hover:text-slate-950"
                }
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </nav>

          <div className="mt-8 rounded-xl border border-amber-100 bg-amber-50 p-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-amber-700">
              Development only
            </p>

            <p className="mt-1 text-[11px] leading-5 text-amber-700/80">
              Admin authentication is intentionally disabled for the local
              buildathon console.
            </p>
          </div>
        </aside>

        {/* ==================================================
            MAIN
            ================================================== */}

        <section className="min-w-0 flex-1 p-4 lg:p-6">
          {/* MOBILE NAV */}

          <div className="mb-4 lg:hidden">
            <button
              type="button"
              onClick={() => setShowMobileNav((value) => !value)}
              className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold shadow-sm"
            >
              {sectionItems.find((item) => item.id === section)?.label}

              <ChevronRight
                size={16}
                className={showMobileNav ? "rotate-90" : ""}
              />
            </button>

            {showMobileNav && (
              <div className="mt-2 rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
                {sectionItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setSection(item.id);
                      setShowMobileNav(false);
                    }}
                    className={
                      section === item.id
                        ? "flex w-full items-center gap-3 rounded-lg bg-slate-950 px-3 py-2.5 text-sm font-semibold text-white"
                        : "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-600"
                    }
                  >
                    {item.icon}
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* ERROR */}

          {error && (
            <div className="mb-4 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle size={16} />

              <span className="flex-1">{error}</span>

              <button
                type="button"
                onClick={() => setError("")}
                className="rounded-lg p-1 hover:bg-red-100"
              >
                <X size={14} />
              </button>
            </div>
          )}

          {/* ==================================================
              OVERVIEW
              ================================================== */}

          {section === "overview" && <Overview dashboard={dashboard} />}

          {/* ==================================================
              MERCHANT
              ================================================== */}

          {section === "merchant" && merchant && (
            <MerchantSettings
              merchant={merchant}
              setMerchant={setMerchant}
              saving={savingMerchant}
              onSave={saveMerchant}
            />
          )}

          {/* ==================================================
              CATALOG
              ================================================== */}

          {section === "catalog" && (
            <Catalog
              products={visibleProducts}
              search={search}
              setSearch={setSearch}
              onEdit={(product) => {
                setEditingProduct(product);
                setShowProductModal(true);
              }}
              onDelete={deleteProduct}
              onCreate={() => {
                setEditingProduct(null);
                setShowProductModal(true);
              }}
              onRefresh={() => loadEverything(true)}
            />
          )}

          {section === "orders" && (
            <DataTable
              title="Orders"
              eyebrow="COMMERCE"
              data={orders}
              columns={[
                "id",
                "status",
                "payment_status",
                "payment_method",
                "amount",
                "agent_id",
                "created_at",
              ]}
            />
          )}

          {section === "payments" && (
            <DataTable
              title="Payments"
              eyebrow="MONEY"
              data={payments}
              columns={[
                "id",
                "type",
                "status",
                "amount",
                "agent_id",
                "order_id",
                "provider_payment_id",
                "created_at",
              ]}
            />
          )}

          {section === "agents" && (
            <DataTable
              title="Agents"
              eyebrow="PURCHASING AUTHORITY"
              data={agents}
              columns={[
                "id",
                "name",
                "status",
                "balance_available",
                "balance_reserved",
                "created_at",
              ]}
            />
          )}

          {section === "users" && (
            <DataTable
              title="Users"
              eyebrow="CUSTOMERS"
              data={users}
              columns={["id", "clerk_user_id", "email", "status", "created_at"]}
            />
          )}

          {section === "audit" && (
            <DataTable
              title="Audit trail"
              eyebrow="SYSTEM ACTIVITY"
              data={auditEvents}
              columns={[
                "action",
                "result",
                "amount",
                "agent_id",
                "reason",
                "created_at",
              ]}
            />
          )}
        </section>
      </div>

      {/* ====================================================
          PRODUCT MODAL
          ==================================================== */}

      {showProductModal && (
        <ProductModal
          product={editingProduct}
          onClose={() => setShowProductModal(false)}
          onSaved={async () => {
            setShowProductModal(false);
            setEditingProduct(null);
            await loadEverything(true);
          }}
          api={api}
        />
      )}
    </main>
  );
}

/* ============================================================
   OVERVIEW
   ============================================================ */

function Overview({ dashboard }: { dashboard: DashboardData | null }) {
  if (!dashboard) {
    return null;
  }

  const metrics = dashboard.metrics;

  return (
    <div>
      <PageHeading
        eyebrow="CONTROL CENTER"
        title="Overview"
        description="Operate your Umon merchant, catalog and agentic commerce environment from one place."
      />

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard
          label="GMV"
          value={metrics.gmv}
          icon={<CircleDollarSign size={18} />}
        />

        <StatCard
          label="Orders"
          value={String(metrics.orders)}
          icon={<ShoppingCart size={18} />}
        />

        <StatCard
          label="Users"
          value={String(metrics.users)}
          icon={<Users size={18} />}
        />

        <StatCard
          label="Agents"
          value={String(metrics.agents)}
          icon={<WalletCards size={18} />}
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel title="Platform state" eyebrow="LIVE">
          <div className="grid grid-cols-2 gap-3">
            <MiniStat label="Paid orders" value={metrics.paid_orders} />

            <MiniStat
              label="Pending payments"
              value={metrics.pending_payments}
            />

            <MiniStat
              label="Active products"
              value={`${metrics.active_products}/${metrics.products}`}
            />

            <MiniStat
              label="Active agents"
              value={`${metrics.active_agents}/${metrics.agents}`}
            />
          </div>
        </Panel>

        <Panel title="Agent money" eyebrow="BALANCE">
          <div className="grid grid-cols-2 gap-3">
            <MiniMoney label="Available" value={metrics.agent_available} />

            <MiniMoney label="Reserved" value={metrics.agent_reserved} />
          </div>
        </Panel>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel title="Recent orders" eyebrow="ORDERS">
          <div className="divide-y divide-slate-100">
            {dashboard.recent_orders.slice(0, 6).map((order) => (
              <div key={order.id} className="flex items-center gap-3 py-3">
                <div className="grid h-8 w-8 place-items-center rounded-lg bg-slate-50 text-slate-500">
                  <Package size={15} />
                </div>

                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-slate-800">
                    {order.id}
                  </p>

                  <p className="text-[10px] text-slate-400">
                    {order.payment_method}
                    {" · "}
                    {order.status}
                  </p>
                </div>

                <span className="text-xs font-semibold text-slate-800">
                  {order.amount}
                </span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Recent activity" eyebrow="AUDIT">
          <div className="divide-y divide-slate-100">
            {dashboard.recent_audit.slice(0, 6).map((event) => (
              <div key={event.id} className="py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-xs font-semibold text-slate-800">
                    {event.action}
                  </p>

                  <span
                    className={
                      event.result === "SUCCESS"
                        ? "text-[10px] font-bold text-emerald-600"
                        : event.result === "BLOCK"
                          ? "text-[10px] font-bold text-red-600"
                          : "text-[10px] font-bold text-slate-500"
                    }
                  >
                    {event.result}
                  </span>
                </div>

                <p className="mt-1 truncate text-[10px] text-slate-400">
                  {event.reason || "No reason recorded"}
                </p>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

/* ============================================================
   MERCHANT SETTINGS
   ============================================================ */

function MerchantSettings({
  merchant,
  setMerchant,
  saving,
  onSave,
}: {
  merchant: Merchant;
  setMerchant: React.Dispatch<React.SetStateAction<Merchant | null>>;
  saving: boolean;
  onSave: () => void;
}) {
  return (
    <div>
      <PageHeading
        eyebrow="MERCHANT"
        title={merchant.name}
        description="Control how Umon presents and processes your merchant through agentic commerce."
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_0.8fr]">
        <Panel title="Merchant settings" eyebrow="STORE">
          <div className="space-y-5">
            <Field label="Store name">
              <input
                value={merchant.name}
                onChange={(event) =>
                  setMerchant((current) =>
                    current
                      ? {
                          ...current,
                          name: event.target.value,
                        }
                      : current,
                  )
                }
                className={inputClass}
              />
            </Field>

            <Field label="Status">
              <select
                value={merchant.status}
                onChange={(event) =>
                  setMerchant((current) =>
                    current
                      ? {
                          ...current,
                          status: event.target.value,
                        }
                      : current,
                  )
                }
                className={inputClass}
              >
                <option value="ACTIVE">Active</option>
                <option value="DISABLED">Disabled</option>
              </select>
            </Field>

            <Field label="Maximum AI order value">
              <div className="flex items-center rounded-xl border border-slate-200 bg-slate-50 px-3">
                <span className="text-sm font-semibold text-slate-400">₹</span>

                <input
                  type="number"
                  min="1"
                  value={merchant.max_order_value / 100}
                  onChange={(event) =>
                    setMerchant((current) =>
                      current
                        ? {
                            ...current,
                            max_order_value: Number(event.target.value) * 100,
                          }
                        : current,
                    )
                  }
                  className="w-full bg-transparent px-2 py-3 text-sm outline-none"
                />
              </div>
            </Field>

            <button
              type="button"
              disabled={saving}
              onClick={onSave}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
            >
              <Save size={16} />
              {saving ? "Saving…" : "Save merchant"}
            </button>
          </div>
        </Panel>

        <Panel title="AI commerce controls" eyebrow="AGENTIC">
          <div className="space-y-2">
            <ToggleRow
              label="AI discovery"
              description="Allow AI clients to discover merchant products."
              checked={merchant.ai_discovery}
              onChange={() =>
                setMerchant((current) =>
                  current
                    ? {
                        ...current,
                        ai_discovery: !current.ai_discovery,
                      }
                    : current,
                )
              }
            />

            <ToggleRow
              label="AI purchasing"
              description="Allow AI agents to purchase from this merchant."
              checked={merchant.ai_purchasing}
              onChange={() =>
                setMerchant((current) =>
                  current
                    ? {
                        ...current,
                        ai_purchasing: !current.ai_purchasing,
                      }
                    : current,
                )
              }
            />

            <ToggleRow
              label="AI checkout"
              description="Allow agentic checkout through Umon."
              checked={merchant.ai_checkout}
              onChange={() =>
                setMerchant((current) =>
                  current
                    ? {
                        ...current,
                        ai_checkout: !current.ai_checkout,
                      }
                    : current,
                )
              }
            />

            <ToggleRow
              label="Recommendations"
              description="Enable product recommendations and cross-sell surfaces."
              checked={merchant.recommendations_enabled}
              onChange={() =>
                setMerchant((current) =>
                  current
                    ? {
                        ...current,
                        recommendations_enabled:
                          !current.recommendations_enabled,
                      }
                    : current,
                )
              }
            />
          </div>

          <div className="mt-5 border-t border-slate-100 pt-5">
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-slate-400">
              Allowed merchant categories
            </p>

            <div className="mt-3 grid grid-cols-2 gap-2">
              {CATEGORIES.map((category) => {
                const enabled = merchant.allowed_categories.includes(category);

                return (
                  <button
                    type="button"
                    key={category}
                    onClick={() =>
                      setMerchant((current) =>
                        current
                          ? {
                              ...current,
                              allowed_categories: enabled
                                ? current.allowed_categories.filter(
                                    (value) => value !== category,
                                  )
                                : [...current.allowed_categories, category],
                            }
                          : current,
                      )
                    }
                    className={
                      enabled
                        ? "flex items-center gap-2 rounded-xl border border-slate-900 bg-slate-50 px-3 py-2.5 text-xs font-semibold text-slate-900"
                        : "flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs font-semibold text-slate-500"
                    }
                  >
                    {enabled ? (
                      <Check size={13} />
                    ) : (
                      <span className="h-3 w-3 rounded-sm border border-slate-300" />
                    )}

                    {category}
                  </button>
                );
              })}
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

/* ============================================================
   CATALOG
   ============================================================ */

function Catalog({
  products,
  search,
  setSearch,
  onEdit,
  onDelete,
  onCreate,
  onRefresh,
}: {
  products: Product[];
  search: string;
  setSearch: (value: string) => void;
  onEdit: (product: Product) => void;
  onDelete: (product: Product) => void;
  onCreate: () => void;
  onRefresh: () => void;
}) {
  return (
    <div>
      <PageHeading
        eyebrow="CATALOG"
        title="Products"
        description="Manage everything the agent and Umon storefront can discover."
        action={
          <button
            type="button"
            onClick={onCreate}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
          >
            <Plus size={16} />
            Add product
          </button>
        }
      />

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />

            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search products…"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-sm outline-none focus:border-slate-400 focus:bg-white"
            />
          </div>

          <button
            type="button"
            onClick={onRefresh}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-semibold text-slate-600 hover:text-slate-950"
          >
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>

        <div className="divide-y divide-slate-100">
          {products.map((product) => (
            <div
              key={product.id}
              className="flex flex-col gap-4 p-4 md:flex-row md:items-center"
            >
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <div className="h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-slate-100">
                  {product.image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={product.image}
                      alt={product.name}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="grid h-full w-full place-items-center text-slate-400">
                      <Package size={18} />
                    </div>
                  )}
                </div>

                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-900">
                    {product.name}
                  </p>

                  <p className="mt-0.5 text-xs text-slate-500">
                    {product.brand}
                    {" · "}
                    {product.category}
                  </p>

                  <p className="mt-1 text-[11px] text-slate-400">
                    Stock {product.stock}
                    {" · "}
                    {product.unit}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-5 text-right md:w-80">
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">
                    Price
                  </p>

                  <p className="mt-1 text-sm font-semibold">
                    ₹{(product.price_paise / 100).toFixed(2)}
                  </p>
                </div>

                <div>
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">
                    Stock
                  </p>

                  <p className="mt-1 text-sm font-semibold">{product.stock}</p>
                </div>

                <div>
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">
                    Status
                  </p>

                  <p
                    className={
                      product.active
                        ? "mt-1 text-xs font-bold text-emerald-600"
                        : "mt-1 text-xs font-bold text-slate-400"
                    }
                  >
                    {product.active ? "Active" : "Inactive"}
                  </p>
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => onEdit(product)}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:text-slate-950"
                >
                  <Pencil size={14} />
                  Edit
                </button>

                {product.active && (
                  <button
                    type="button"
                    onClick={() => onDelete(product)}
                    className="inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-50"
                  >
                    <Trash2 size={14} />
                    Disable
                  </button>
                )}
              </div>
            </div>
          ))}

          {!products.length && (
            <div className="px-6 py-16 text-center text-sm text-slate-400">
              No products found.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   PRODUCT MODAL
   ============================================================ */

function ProductModal({
  product,
  onClose,
  onSaved,
  api,
}: {
  product: Product | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
  api: ReturnType<typeof useUmonApi>;
}) {
  const [name, setName] = useState(product?.name ?? "");

  const [brand, setBrand] = useState(product?.brand ?? "");

  const [category, setCategory] = useState(product?.category ?? "grocery");

  const [price, setPrice] = useState(
    product ? String(product.price_paise / 100) : "",
  );

  const [mrp, setMrp] = useState(
    product ? String(product.mrp_paise / 100) : "",
  );

  const [stock, setStock] = useState(product ? String(product.stock) : "0");

  const [unit, setUnit] = useState(product?.unit ?? "");

  const [description, setDescription] = useState(product?.description ?? "");

  const [image, setImage] = useState(product?.image ?? "");

  const [tags, setTags] = useState(product?.tags.join(", ") ?? "");

  const [active, setActive] = useState(product?.active ?? true);

  const [saving, setSaving] = useState(false);

  const [error, setError] = useState("");

  async function save() {
    setError("");

    const priceValue = Number(price);

    const mrpValue = Number(mrp);

    const stockValue = Number(stock);

    if (!name.trim()) {
      setError("Product name is required.");
      return;
    }

    if (!Number.isFinite(priceValue) || priceValue <= 0) {
      setError("Price must be greater than zero.");
      return;
    }

    if (!Number.isFinite(mrpValue) || mrpValue < priceValue) {
      setError("MRP must be at least the selling price.");
      return;
    }

    if (!Number.isInteger(stockValue) || stockValue < 0) {
      setError("Stock must be a non-negative whole number.");
      return;
    }

    setSaving(true);

    try {
      const body = {
        name: name.trim(),
        brand: brand.trim(),
        category: category.trim(),
        price: priceValue,
        mrp: mrpValue,
        stock: stockValue,
        unit: unit.trim(),
        description: description.trim(),
        image: image.trim() || null,
        tags: tags
          .split(",")
          .map((value) => value.trim().toLowerCase())
          .filter(Boolean),
        active,
      };

      if (product) {
        await api.adminUpdateProduct(product.id, body);
      } else {
        await api.adminCreateProduct(body);
      }

      await onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save product.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm">
      <div className="max-h-[92vh] w-full max-w-2xl overflow-auto rounded-2xl border border-slate-200 bg-white shadow-2xl">
        <div className="sticky top-0 flex items-center justify-between border-b border-slate-100 bg-white px-5 py-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
              CATALOG
            </p>

            <h2 className="mt-1 text-lg font-semibold">
              {product ? "Edit product" : "Add product"}
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 text-slate-500 hover:text-slate-950"
          >
            <X size={17} />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Product name">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                className={inputClass}
                placeholder="Aashirvaad Atta 5kg"
              />
            </Field>

            <Field label="Brand">
              <input
                value={brand}
                onChange={(event) => setBrand(event.target.value)}
                className={inputClass}
                placeholder="Aashirvaad"
              />
            </Field>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Category">
              <select
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                className={inputClass}
              >
                {CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Price">
              <input
                type="number"
                min="1"
                step="0.01"
                value={price}
                onChange={(event) => setPrice(event.target.value)}
                className={inputClass}
              />
            </Field>

            <Field label="MRP">
              <input
                type="number"
                min="1"
                step="0.01"
                value={mrp}
                onChange={(event) => setMrp(event.target.value)}
                className={inputClass}
              />
            </Field>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Stock">
              <input
                type="number"
                min="0"
                step="1"
                value={stock}
                onChange={(event) => setStock(event.target.value)}
                className={inputClass}
              />
            </Field>

            <Field label="Unit">
              <input
                value={unit}
                onChange={(event) => setUnit(event.target.value)}
                className={inputClass}
                placeholder="1 kg"
              />
            </Field>
          </div>

          <Field label="Description">
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              className={`${inputClass} resize-y`}
            />
          </Field>

          <Field label="Image URL">
            <input
              value={image}
              onChange={(event) => setImage(event.target.value)}
              className={inputClass}
              placeholder="https://..."
            />
          </Field>

          <Field label="Tags">
            <input
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              className={inputClass}
              placeholder="atta, flour, wheat"
            />
          </Field>

          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div>
              <p className="text-sm font-semibold">Active in store</p>

              <p className="mt-1 text-xs text-slate-500">
                Inactive products won't appear in normal catalog discovery.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setActive((value) => !value)}
              className="text-slate-700"
            >
              {active ? <ToggleRight size={34} /> : <ToggleLeft size={34} />}
            </button>
          </div>

          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
            >
              <Save size={15} />

              {saving ? "Saving…" : product ? "Save product" : "Create product"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   GENERIC DATA TABLE
   ============================================================ */

function DataTable({
  title,
  eyebrow,
  data,
  columns,
}: {
  title: string;
  eyebrow: string;
  data: any[];
  columns: string[];
}) {
  return (
    <div>
      <PageHeading
        eyebrow={eyebrow}
        title={title}
        description={`Live ${title.toLowerCase()} from the current Umon environment.`}
      />

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left">
            <thead className="border-b border-slate-100 bg-slate-50">
              <tr>
                {columns.map((column) => (
                  <th
                    key={column}
                    className="whitespace-nowrap px-4 py-3 text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400"
                  >
                    {column.replaceAll("_", " ")}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-100">
              {data.map((row, index) => (
                <tr key={row.id ?? index} className="hover:bg-slate-50">
                  {columns.map((column) => (
                    <td
                      key={column}
                      className="max-w-[280px] whitespace-nowrap px-4 py-3 text-xs text-slate-600"
                    >
                      {renderValue(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!data.length && (
          <div className="px-6 py-14 text-center text-sm text-slate-400">
            No records found.
          </div>
        )}
      </div>
    </div>
  );
}

/* ============================================================
   UI HELPERS
   ============================================================ */

const inputClass =
  "w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-slate-400 focus:bg-white";

function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-400">
          {eyebrow}
        </p>

        <h1 className="mt-1 text-3xl font-semibold tracking-[-0.035em] text-slate-950">
          {title}
        </h1>

        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
          {description}
        </p>
      </div>

      {action}
    </div>
  );
}

function Panel({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-5">
        <p className="text-[10px] font-bold uppercase tracking-[0.13em] text-slate-400">
          {eyebrow}
        </p>

        <h2 className="mt-1 text-base font-semibold text-slate-950">{title}</h2>
      </div>

      {children}
    </section>
  );
}

function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
}) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="grid h-9 w-9 place-items-center rounded-xl bg-slate-50 text-slate-500">
        {icon}
      </div>

      <p className="mt-4 text-xs font-medium text-slate-500">{label}</p>

      <p className="mt-1 text-xl font-semibold tracking-tight text-slate-950">
        {value}
      </p>
    </article>
  );
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <p className="text-[11px] text-slate-400">{label}</p>

      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function MiniMoney({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <p className="text-[11px] text-slate-400">{label}</p>

      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-bold text-slate-700">
        {label}
      </span>

      {children}
    </label>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-slate-900">{label}</p>

        <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
      </div>

      <button
        type="button"
        onClick={onChange}
        className="shrink-0 text-slate-700"
      >
        {checked ? (
          <ToggleRight size={38} />
        ) : (
          <ToggleLeft size={38} className="text-slate-300" />
        )}
      </button>
    </div>
  );
}

function renderValue(value: unknown): React.ReactNode {
  if (value === null || value === undefined) {
    return "—";
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (value instanceof Date) {
    return value.toLocaleString("en-IN");
  }

  if (typeof value === "object") {
    return (
      <span className="block max-w-[280px] truncate">
        {JSON.stringify(value)}
      </span>
    );
  }

  return String(value);
}
